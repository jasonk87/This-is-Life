"""Composable anatomy and body-part health state."""
from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass, field

from entities.pickle_compat import dataclass_setstate


DEFAULT_HUMANOID_PARTS = {
    "head": 5,
    "torso": 10,
    "left_arm": 5,
    "right_arm": 5,
    "left_leg": 5,
    "right_leg": 5,
}
DEFAULT_DAMAGE_SPILLOVER_ORDER = ["torso", "head", "left_arm", "right_arm", "left_leg", "right_leg"]


@dataclass
class BodyPart:
    name: str
    hp: int
    max_hp: int
    status_effects: list[str] = field(default_factory=list)
    parent: str | None = None
    coverage: str | None = None
    hit_weight: float = 1.0
    function: str | None = None
    tissues: tuple[str, ...] = ("skin", "muscle", "bone")

    def ensure_status(self, effect: str) -> None:
        if effect not in self.status_effects:
            self.status_effects.append(effect)

    def __setstate__(self, state):
        dataclass_setstate(self, state)


class BodyPartValueProxy(MutableMapping):
    """Mutable mapping view over anatomy body-part hp/max_hp values."""

    def __init__(self, anatomy: "Anatomy", attribute: str):
        self.anatomy = anatomy
        self.attribute = attribute

    def __getitem__(self, key: str) -> int:
        if self.anatomy.body_plan and self.attribute == "hp":
            from entities.body_model import part_function
            return round(self.anatomy.get_part(key).max_hp * part_function(self.anatomy,key))
        return getattr(self.anatomy.get_part(key), self.attribute)

    def __setitem__(self, key: str, value: int) -> None:
        if self.anatomy.body_plan and self.attribute == "hp":
            raise TypeError("Body HP is derived; use wound treatment/healing, not a limb-HP assignment")
        setattr(self.anatomy.get_part(key), self.attribute, int(value))

    def __delitem__(self, key: str) -> None:
        raise TypeError("Body parts cannot be deleted")

    def __iter__(self):
        return iter(self.anatomy.parts)

    def __len__(self) -> int:
        return len(self.anatomy.parts)

    def copy(self) -> dict[str, int]:
        return {name: self[name] for name in self.anatomy.parts}


@dataclass
class Anatomy:
    parts: dict[str, BodyPart] = field(default_factory=dict)
    body_plan: str | None = None
    wounds: list = field(default_factory=list)
    scars: list = field(default_factory=list)
    blood: float = 1.0
    systemic_loss: float = 0.0
    display_max_hp: int = 35
    last_body_tick: int | None = None
    next_wound_id: int = 1
    death_cause: str | None = None
    death_processed: bool = False
    death_event_processed: bool = False
    weapon_hand: str = "right_hand"
    attack_ready_tick: int = 0
    last_attack_target: tuple | None = None
    last_attack_kind: str = "fight"
    movement_credit: float = 0.0
    movement_tick: int | None = None
    last_attacker_id: int | str | None = None
    last_attacked_tick: int = -1000000
    treatment_ready_tick: int = 0

    def __post_init__(self):
        self._hp_proxy = BodyPartValueProxy(self, "hp")
        self._max_hp_proxy = BodyPartValueProxy(self, "max_hp")

    def __setstate__(self, state):
        dataclass_setstate(self, state)
        # _hp_proxy/_max_hp_proxy are set in __post_init__, not declared as
        # dataclass fields, so dataclass_setstate's field-backfill can't see
        # them - rebuild fresh ones unconditionally rather than trusting
        # whatever pickle restored (cheap, stateless wrappers; safer than
        # assuming an old pickle's proxy objects are still bound correctly).
        self._hp_proxy = BodyPartValueProxy(self, "hp")
        self._max_hp_proxy = BodyPartValueProxy(self, "max_hp")

    @classmethod
    def humanoid(cls, part_layout: dict[str, int] | None = None) -> "Anatomy":
        layout = dict(part_layout or DEFAULT_HUMANOID_PARTS)
        return cls(parts={name: BodyPart(name=name, hp=value, max_hp=value) for name, value in layout.items()})

    @property
    def hp_proxy(self) -> BodyPartValueProxy:
        return self._hp_proxy

    @property
    def max_hp_proxy(self) -> BodyPartValueProxy:
        return self._max_hp_proxy

    def get_part(self, name: str) -> BodyPart:
        return self.parts[name]

    def get_total_hp(self) -> int:
        if self.body_plan:
            from entities.body_model import health_fraction
            fraction = health_fraction(self)
            return max(1, round(self.display_max_hp * fraction)) if fraction > 0 else 0
        return sum(part.hp for part in self.parts.values())

    def get_total_max_hp(self) -> int:
        if self.body_plan:
            return self.display_max_hp
        return sum(part.max_hp for part in self.parts.values())

    def set_total_hp(self, value: int) -> None:
        if self.body_plan:
            # Legacy disease/environment/healing callers can affect systemic
            # reserve, but cannot heal fractures, close wounds or refill blood.
            delta = (self.get_total_hp()-int(value))/max(1,self.display_max_hp)
            self.systemic_loss = min(1,max(0,self.systemic_loss+delta))
            if value <= 0:
                self.systemic_loss = 1.0
            return
        current_hp = self.get_total_hp()
        if value <= 0:
            for part in self.parts.values():
                part.hp = 0
            return
        if value == self.get_total_max_hp():
            for part in self.parts.values():
                part.hp = part.max_hp
            return

        ratio = value / current_hp if current_hp > 0 else 0
        for part in self.parts.values():
            part.hp = int(part.hp * ratio)
        diff = value - self.get_total_hp()
        if diff != 0 and "torso" in self.parts:
            self.parts["torso"].hp += diff

    def scale_total_max_hp(self, value: int) -> None:
        if self.body_plan:
            self.display_max_hp = max(1,int(value))
            return
        current_max = self.get_total_max_hp()
        if current_max == 0:
            return
        ratio = value / current_max
        for part in self.parts.values():
            part.max_hp = max(1, int(part.max_hp * ratio))
        diff = value - self.get_total_max_hp()
        if diff != 0 and "torso" in self.parts:
            self.parts["torso"].max_hp += diff

    def apply_damage(self, hit_part_name: str, damage: int, spillover_order: list[str] | None = None) -> int:
        if self.body_plan:
            from entities.body_model import inflict
            inflict(self,hit_part_name,"crush",damage,self.last_body_tick or 0)
            return 0
        remaining_damage = damage
        hit_part = self.get_part(hit_part_name)
        if hit_part.hp >= remaining_damage:
            hit_part.hp -= remaining_damage
            if hit_part.hp <= 0:
                hit_part.ensure_status("broken")
            return 0

        remaining_damage -= hit_part.hp
        hit_part.hp = 0
        hit_part.ensure_status("broken")

        for part_name in spillover_order or DEFAULT_DAMAGE_SPILLOVER_ORDER:
            if remaining_damage <= 0:
                break
            part = self.get_part(part_name)
            if part.hp <= 0:
                continue
            if part.hp >= remaining_damage:
                part.hp -= remaining_damage
                if part.hp <= 0:
                    part.ensure_status("broken")
                remaining_damage = 0
            else:
                remaining_damage -= part.hp
                part.hp = 0
                part.ensure_status("broken")
        return remaining_damage
