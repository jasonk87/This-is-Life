"""Inventory and equipment compatibility helpers for NPC entities."""
from __future__ import annotations

from dataclasses import dataclass
import random

from config import DAY_LENGTH_TICKS
from data.items import ITEM_DEFINITIONS
from entities.pickle_compat import dataclass_setstate

_MISSING = object()

# `spoilage_chance` in data/items.py is the chance an item spoils over a *day* -
# 2% for bread, 5% for an apple, 20% for raw meat all read as daily figures, and
# World._update_inventory_spoilage (the only other reader) applies them on a
# once-a-day gate. ItemReference.update_tick runs every world tick, though, and
# rolled the daily number directly: at 14400 ticks to the day that gave a loaf
# an expected life of about fifty ticks - five in-game minutes - so no
# settlement could keep food in a building for as long as it took to eat it.
_PER_TICK_SPOILAGE_CACHE: dict[float, float] = {}


def per_tick_spoilage_chance(daily_chance: float) -> float:
    """The per-tick probability equivalent to `daily_chance` over one whole day."""
    if daily_chance <= 0:
        return 0.0
    if daily_chance >= 1:
        return 1.0
    cached = _PER_TICK_SPOILAGE_CACHE.get(daily_chance)
    if cached is None:
        cached = 1.0 - (1.0 - daily_chance) ** (1.0 / DAY_LENGTH_TICKS)
        _PER_TICK_SPOILAGE_CACHE[daily_chance] = cached
    return cached

QUALITY_VALUE_MODIFIERS = {
    "Poor": 0.8,
    "Normal": 1.0,
    "Fine": 1.2,
    "Masterwork": 1.5,
}
QUALITY_UTILITY_MODIFIERS = {
    "Poor": 0.85,
    "Normal": 1.0,
    "Fine": 1.15,
    "Masterwork": 1.35,
}

# Repair mechanic constants (finite-use repair: each repair permanently
# shaves a bit off the item's true max_durability ceiling, rather than
# being a free undo of degrade() forever - see ItemReference.repair()).
REPAIR_WEAR_PER_REPAIR_FRACTION = 0.10
REPAIR_DURABILITY_FLOOR_FRACTION = 0.20

# Repair economics for the player-facing Blacksmith interaction (see
# World.player_attempt_repair_gear in engine.py). A fully-broken item
# (100% missing durability) costs at most half its own value in money to
# fully restore, plus a small amount of a generic repair material -
# deliberately always iron_ingot regardless of the item's actual
# material (a common game simplification: "the smith always wants iron
# and coin," not a fully materials-accurate system).
REPAIR_MONEY_COST_FRACTION_OF_VALUE = 0.5
REPAIR_MATERIAL_KEY = "iron_ingot"
REPAIR_MATERIAL_MAX_QTY = 3


def normalize_item_quality(quality: str | None) -> str:
    normalized = str(quality or "Normal").strip().title()
    return normalized if normalized in QUALITY_VALUE_MODIFIERS else "Normal"


def roll_crafted_item_quality(career_level: int = 0, work_performance: int = 50) -> str:
    """Roll a quality tier for a crafted item from skill and performance."""
    bounded_performance = max(0, min(100, int(work_performance)))
    craftsmanship_score = random.random() + (max(0, int(career_level)) * 0.08) + ((bounded_performance - 50) / 250)
    if craftsmanship_score >= 1.15:
        return "Masterwork"
    if craftsmanship_score >= 0.8:
        return "Fine"
    if craftsmanship_score < 0.2:
        return "Poor"
    return "Normal"


def average_damage_from_dice(damage_dice: str | None) -> float:
    """Return the average roll for a standard XdY damage string."""
    if not damage_dice:
        return 0.0
    normalized = str(damage_dice).strip().lower()
    if "d" not in normalized:
        return 0.0
    try:
        num_dice_str, die_size_str = normalized.split("d", 1)
        num_dice = max(0, int(num_dice_str))
        die_size = max(0, int(die_size_str))
    except (TypeError, ValueError):
        return 0.0
    if num_dice <= 0 or die_size <= 0:
        return 0.0
    return num_dice * ((die_size + 1) / 2.0)


@dataclass
class ItemReference:
    """Lightweight item object with instance-specific simulation state."""

    key: str
    quality: str = "Normal"
    crafter_name: str | None = None
    current_durability: int | None = None
    age_in_ticks: int = 0
    written_text: str = ""
    title: str | None = None
    # Cumulative permanent reduction to max_durability from past repairs -
    # see repair(). 0 means "never repaired" / undamaged-ceiling.
    repair_wear: int = 0

    def __post_init__(self) -> None:
        self.quality = normalize_item_quality(self.quality)
        max_durability = self.max_durability
        if self.current_durability is None and max_durability is not None:
            self.current_durability = max_durability

    def __setstate__(self, state):
        # ItemReference was flagged as an explicit, documented scoping
        # exclusion in the earlier save/load migration pass (fix 1) -
        # unpickling bypasses __init__ entirely, so old saves predating a
        # newly-added field (like repair_wear, added alongside the repair
        # mechanic) would otherwise crash the first time something reads
        # it. Closing that gap now since this change is exactly the kind
        # of new-field addition that would have hit it.
        dataclass_setstate(self, state)

    @property
    def definition(self) -> dict:
        return ITEM_DEFINITIONS.get(self.key, {})

    @property
    def name(self) -> str:
        base_name = self.title or self.definition.get("name", self.key.replace("_", " ").title())
        if self.quality == "Normal":
            return base_name
        return f"{self.quality} {base_name}"

    @property
    def description(self) -> str:
        base_description = self.definition.get("description", "")
        if self.written_text:
            base_description = f"{base_description} Its pages are covered in handwriting."
        if self.crafter_name:
            return f"{base_description} Crafted by {self.crafter_name}."
        return base_description

    @property
    def char(self) -> int | None:
        return self.definition.get("char")

    @property
    def color(self):
        return self.definition.get("color")

    @property
    def true_base_max_durability(self) -> int | None:
        """max_durability with quality applied but BEFORE repair_wear -
        i.e. what this item's ceiling would be if it had never been
        repaired. Used as the reference point for both the per-repair wear
        amount and the repair floor, so repeated repairs erode toward a
        fixed floor rather than the floor itself drifting as repair_wear
        accumulates."""
        base_max_durability = self.definition.get("properties", {}).get("max_durability")
        if base_max_durability is None:
            return None
        return max(1, int(round(base_max_durability * self.quality_multiplier)))

    @property
    def max_durability(self) -> int | None:
        true_base = self.true_base_max_durability
        if true_base is None:
            return None
        floor = max(1, int(round(true_base * REPAIR_DURABILITY_FLOOR_FRACTION)))
        return max(floor, true_base - self.repair_wear)

    @property
    def value(self) -> int:
        base_value = self.definition.get("value", 0)
        return max(0, int(round(base_value * self.quality_multiplier)))

    @property
    def tool_type(self) -> str | None:
        return self.definition.get("properties", {}).get("tool_type")

    @property
    def conceals_identity(self) -> bool:
        return bool(self.definition.get("properties", {}).get("conceals_identity", False))

    @property
    def quality_multiplier(self) -> float:
        return QUALITY_VALUE_MODIFIERS[self.quality]

    @property
    def utility_multiplier(self) -> float:
        return QUALITY_UTILITY_MODIFIERS[self.quality]

    @property
    def equip_slot(self) -> str | None:
        return self.definition.get("equip_slot")

    @property
    def durability_ratio(self) -> float:
        max_durability = self.max_durability
        if max_durability is None or max_durability <= 0 or self.current_durability is None:
            return 1.0
        return max(0.0, min(1.0, self.current_durability / max_durability))

    def evaluate_utility(self) -> float:
        """Estimate how useful this item is when choosing gear for an equipment slot."""
        item_properties = self.definition.get("properties", {})
        base_score = 0.0
        if self.equip_slot == "main_hand":
            base_score = average_damage_from_dice(item_properties.get("damage_dice"))
            base_score += max(0, item_properties.get("damage_bonus", 0))
            base_score += max(0, item_properties.get("attack_range", 1) - 1) * 0.25
        elif self.equip_slot in {"body", "head", "hands", "feet", "legs"}:
            base_score = max(0, item_properties.get("defense_bonus", 0)) * 3.0
            base_score += max(0.0, item_properties.get("insulation", 0.0)) * 0.5

        if base_score <= 0:
            return 0.0

        score = base_score * self.utility_multiplier
        durability_ratio = self.durability_ratio
        if durability_ratio < 0.75:
            score *= 0.9
        if durability_ratio < 0.5:
            score *= 0.7
        if durability_ratio < 0.25:
            score *= 0.35
        return round(score, 3)

    def degrade(self, amount: int = 1) -> bool:
        """Reduce durability and report whether the item broke."""
        if self.current_durability is None:
            return False
        self.current_durability = max(0, self.current_durability - max(0, int(amount)))
        return self.current_durability <= 0

    def repair(self) -> dict:
        """Restores current_durability to max_durability and permanently
        wears the item's ceiling down a bit (finite-use repair, per
        Jason's design decision: repair should cost the item something
        real, not just undo degrade() forever for a fee).

        Each call adds REPAIR_WEAR_PER_REPAIR_FRACTION * true_base_max_durability
        to repair_wear - a flat amount per repair regardless of how damaged
        the item was, since it's the act of reworking the material that
        fatigues it, not how much durability happened to be restored.
        max_durability's own floor (REPAIR_DURABILITY_FLOOR_FRACTION of
        true_base_max_durability) means repeated repairs approach a fixed
        floor rather than ever reaching zero/unrepairable.

        Returns a result dict mirroring degrade_equipped_item's shape:
        {"repaired": bool, "new_max_durability": int|None,
        "at_repair_limit": bool} - at_repair_limit is True once this item's
        ceiling is already at (or would already be at) the floor, so
        callers can tell the player "this is as good as repair can make it
        anymore" instead of implying infinite future repairs are useful.
        """
        true_base = self.true_base_max_durability
        if true_base is None or self.current_durability is None:
            return {"repaired": False, "new_max_durability": None, "at_repair_limit": False}

        floor = max(1, int(round(true_base * REPAIR_DURABILITY_FLOOR_FRACTION)))
        wear_increment = max(1, int(round(true_base * REPAIR_WEAR_PER_REPAIR_FRACTION)))
        self.repair_wear = min(true_base - floor, self.repair_wear + wear_increment)

        new_ceiling = self.max_durability
        self.current_durability = new_ceiling
        return {
            "repaired": True,
            "new_max_durability": new_ceiling,
            "at_repair_limit": new_ceiling is not None and new_ceiling <= floor,
        }

    def update_tick(self) -> str:
        """Advance this item by one tick and apply any spoilage transformation."""
        self.age_in_ticks += 1

        properties = self.definition.get("properties", {})
        spoilage_chance = per_tick_spoilage_chance(properties.get("spoilage_chance", 0.0))
        rots_into = properties.get("rots_into")
        if spoilage_chance > 0 and rots_into and random.random() < spoilage_chance:
            self.key = rots_into
            self.quality = "Normal"
            self.crafter_name = None
            self.age_in_ticks = 0
            max_durability = self.max_durability
            self.current_durability = max_durability if max_durability is not None else None
        return self.key


class Inventory(dict):
    """Dict-compatible inventory wrapper with small helper methods."""

    def __init__(self, initial=None):
        super().__init__()
        self._item_stacks: dict[str, list[ItemReference]] = {}
        if initial:
            self.update(initial)

    def update(self, other=None, /, **kwargs):
        if other:
            items = other.items() if hasattr(other, "items") else other
            for key, value in items:
                self[key] = value
        for key, value in kwargs.items():
            self[key] = value

    def __setitem__(self, key, value):
        self._ensure_item_stacks()
        quantity = int(value)
        if quantity <= 0:
            self.__delitem__(key)
            return
        self._resize_stack(key, quantity)
        super().__setitem__(key, quantity)

    def add_item(self, item_key: str, quantity: int = 1, *, quality: str = "Normal", crafter_name: str | None = None) -> int:
        self._ensure_item_stacks()
        stack = self._item_stacks.setdefault(item_key, [])
        stack.extend(
            self._create_item_reference(item_key, quality=quality, crafter_name=crafter_name)
            for _ in range(max(0, int(quantity)))
        )
        self._sync_quantity(item_key)
        return self.get(item_key, 0)

    def has_item(self, item_key: str, quantity: int = 1) -> bool:
        return self.get(item_key, 0) >= quantity

    def remove_item(self, item_key: str, quantity: int = 1) -> bool:
        if not self.has_item(item_key, quantity):
            return False
        self[item_key] = self.get(item_key, 0) - quantity
        return True

    def get_item_reference(self, item_key: str) -> ItemReference | None:
        stack = self._item_stacks.get(item_key, [])
        return stack[0] if stack else None

    def add_item_reference(self, item: ItemReference) -> int:
        """Insert an existing item object without losing its metadata."""
        self._ensure_item_stacks()
        self._item_stacks.setdefault(item.key, []).append(item)
        self._sync_quantity(item.key)
        return self.get(item.key, 0)

    def has_item_reference(self, item: ItemReference) -> bool:
        self._ensure_item_stacks()
        return item in self._item_stacks.get(item.key, [])

    def pop_item_reference(self, item_key: str) -> ItemReference | None:
        """Remove and return one concrete item object by key."""
        self._ensure_item_stacks()
        stack = self._item_stacks.get(item_key, [])
        if not stack:
            return None
        item = stack.pop(0)
        self._sync_quantity(item_key)
        return item

    def transfer_item_objects(self, destination, item_key: str, quantity: int = 1) -> int:
        """Move concrete item objects to another inventory-like destination."""
        transferred = 0
        for _ in range(max(0, int(quantity))):
            item = self.pop_item_reference(item_key)
            if item is None:
                break
            if hasattr(destination, "add_item_reference"):
                destination.add_item_reference(item)
            else:
                destination[item.key] = destination.get(item.key, 0) + 1
            transferred += 1
        return transferred

    def transfer_item_reference(self, destination, item: ItemReference) -> bool:
        """Move a specific item object to another inventory-like destination."""
        self._ensure_item_stacks()
        if item not in self._item_stacks.get(item.key, []):
            return False
        self._remove_item_reference(item.key, item)
        if hasattr(destination, "add_item_reference"):
            destination.add_item_reference(item)
        else:
            destination[item.key] = destination.get(item.key, 0) + 1
        return True

    def extract_item_reference(self, item: ItemReference) -> ItemReference | None:
        """Remove and return a specific item object without replacing it."""
        self._ensure_item_stacks()
        if item not in self._item_stacks.get(item.key, []):
            return None
        self._remove_item_reference(item.key, item)
        return item

    def iter_item_references(self, item_key: str | None = None):
        """Yield concrete item objects, optionally filtered by key."""
        self._ensure_item_stacks()
        if item_key is not None:
            for item in list(self._item_stacks.get(item_key, [])):
                yield item
            return
        for stack in self._item_stacks.values():
            for item in list(stack):
                yield item

    def process_tick(self) -> None:
        """Advance all item instances and apply any key transformations safely.

        Whether a thing can rot is a property of the item *kind*, so it is
        resolved once per stack rather than once per instance. It used to be
        looked up - and a die rolled - for every object every tick, and 96% of
        what a village stores cannot spoil at all: a general store's coins alone
        are thousands of individual instances, each rolling against a spoilage
        chance of zero. That single pass was costing about a fifth of every
        world tick.
        """
        transformations: list[tuple[str, ItemReference]] = []

        for item_key, stack in list(self._item_stacks.items()):
            if not stack:
                continue
            properties = stack[0].definition.get("properties", {})
            can_spoil = bool(properties.get("spoilage_chance", 0.0)) and bool(properties.get("rots_into"))
            if not can_spoil:
                # Nothing to roll for; age still advances.
                for item in stack:
                    item.age_in_ticks += 1
                continue

            for item in list(stack):
                previous_key = item_key
                updated_key = item.update_tick()
                if updated_key != previous_key:
                    transformations.append((previous_key, item))

        for previous_key, item in transformations:
            previous_stack = self._item_stacks.get(previous_key, [])
            if item in previous_stack:
                previous_stack.remove(item)
                self._sync_quantity(previous_key)

            self._item_stacks.setdefault(item.key, []).append(item)
            self._sync_quantity(item.key)

    def degrade_item(self, item_key: str, amount: int = 1) -> dict:
        """Degrade one item instance by key and handle breakage/replacement."""
        item = self.get_item_reference(item_key)
        return self.degrade_item_reference(item, amount) if item is not None else {
            "degraded": False,
            "broke": False,
            "item_key": item_key,
            "replacement_key": None,
        }

    def degrade_item_reference(self, item: ItemReference | None, amount: int = 1) -> dict:
        """Degrade a concrete item object and handle breakage/replacement."""
        if item is None or item.current_durability is None:
            return {"degraded": False, "broke": False, "item_key": getattr(item, "key", None), "replacement_key": None}

        broke = item.degrade(amount)
        result = {
            "degraded": True,
            "broke": broke,
            "item_key": item.key,
            "replacement_key": None,
            "current_durability": item.current_durability,
        }
        if not broke:
            return result

        broken_item_name = item.name
        broken_tool_type = item.tool_type
        self._remove_item_reference(item.key, item)
        result["item_name"] = broken_item_name

        if broken_tool_type and "broken_tool_handle" in ITEM_DEFINITIONS:
            self.add_item("broken_tool_handle", 1)
            result["replacement_key"] = "broken_tool_handle"

        return result

    def __delitem__(self, key):
        self._ensure_item_stacks()
        self._item_stacks.pop(key, None)
        if key in self:
            super().__delitem__(key)

    def pop(self, key, default=_MISSING):
        if key in self:
            value = self[key]
            self.__delitem__(key)
            return value
        if default is _MISSING:
            raise KeyError(key)
        return default

    def clear(self):
        self._ensure_item_stacks()
        self._item_stacks.clear()
        super().clear()

    def __getstate__(self):
        return {"_item_stacks": self._item_stacks}

    def __setstate__(self, state):
        self._item_stacks = state.get("_item_stacks", {})
        for item_key, quantity in list(self.items()):
            if item_key not in self._item_stacks:
                self._item_stacks[item_key] = []
            self._resize_stack(item_key, quantity)

    def _ensure_item_stacks(self):
        if not hasattr(self, "_item_stacks"):
            self._item_stacks = {}

    def _create_item_reference(self, item_key: str, *, quality: str = "Normal", crafter_name: str | None = None) -> ItemReference:
        return ItemReference(item_key, quality=quality, crafter_name=crafter_name)

    def _resize_stack(self, item_key: str, quantity: int) -> None:
        stack = self._item_stacks.setdefault(item_key, [])
        current_quantity = len(stack)
        if current_quantity < quantity:
            stack.extend(self._create_item_reference(item_key) for _ in range(quantity - current_quantity))
        elif current_quantity > quantity:
            del stack[quantity:]

    def _sync_quantity(self, item_key: str) -> None:
        stack = self._item_stacks.get(item_key, [])
        quantity = len(stack)
        if quantity <= 0:
            self._item_stacks.pop(item_key, None)
            if item_key in self:
                super().__delitem__(item_key)
            return
        super().__setitem__(item_key, quantity)

    def _remove_item_reference(self, item_key: str, item: ItemReference) -> None:
        stack = self._item_stacks.get(item_key, [])
        if item in stack:
            stack.remove(item)
            self._sync_quantity(item_key)


class EquipmentSlot:
    """String-compatible equipment slot wrapper."""

    __slots__ = ("item_key", "item_reference")

    def __init__(self, item_key: str | None = None, item_reference: ItemReference | None = None):
        self.item_key = item_key or None
        self.item_reference = item_reference if item_reference and item_reference.key == self.item_key else None

    @property
    def item(self) -> ItemReference | None:
        if self.item_reference and self.item_reference.key == self.item_key:
            return self.item_reference
        if not self.item_key:
            return None
        return ItemReference(self.item_key)

    def clear(self) -> None:
        self.item_key = None
        self.item_reference = None

    def set(self, item_key: str | None, item_reference: ItemReference | None = None) -> None:
        self.item_key = item_key or None
        self.item_reference = item_reference if item_reference and item_reference.key == self.item_key else None

    def bind(self, item_reference: ItemReference | None) -> None:
        self.item_key = item_reference.key if item_reference else None
        self.item_reference = item_reference

    def __bool__(self) -> bool:
        return bool(self.item_key)

    def __eq__(self, other) -> bool:
        if isinstance(other, EquipmentSlot):
            return self.item_key == other.item_key
        if isinstance(other, str):
            return self.item_key == other
        if other is None:
            return self.item_key is None
        return False

    def __hash__(self) -> int:
        return hash(self.item_key)

    def __str__(self) -> str:
        return self.item_key or ""

    def __repr__(self) -> str:
        return repr(self.item_key)
