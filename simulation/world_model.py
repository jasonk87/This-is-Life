from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar
from collections.abc import MutableMapping
import uuid

from simulation.ids import new_id

from data.decorations import DECORATION_ITEM_DEFINITIONS
from data.items import ITEM_DEFINITIONS
from entities.items import Inventory, ItemReference


class Building:
    def __init__(self, x, y, width, height, building_type="house", category="residential", global_chunk_x_start=0, global_chunk_y_start=0, variant_id=None):
        self.id = new_id()
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.building_type = building_type
        self.category = category
        self.variant_id = variant_id
        self.interior_decorated = False
        self.occupants = []
        self.residents = []
        self.building_inventory = Inventory()
        self.interaction_points = {}
        self.work_zone_tiles: dict[str, list[tuple[int, int]]] = {}
        self.global_origin_x = global_chunk_x_start + x
        self.global_origin_y = global_chunk_y_start + y
        self.global_center_x = self.global_origin_x + width // 2
        self.global_center_y = self.global_origin_y + height // 2
        self.player_owned: bool = False
        self.owner_id: int | None = None
        self.requester_id: int | None = None
        self.max_workers: int = 2
        self.region_id: str | None = None
        self.settlement_id: str | None = None
        self.territory_claim_id: str | None = None
        self.anchors: list[dict[str, Any]] = []

    def __setattr__(self, name, value):
        if name == "building_inventory" and not isinstance(value, Inventory):
            value = Inventory(value or {})
        super().__setattr__(name, value)

    @property
    def max_workers(self):
        return getattr(self, "_max_workers", 2)

    @max_workers.setter
    def max_workers(self, value):
        self._max_workers = value

    def contains_global_coords(self, world_x: int, world_y: int) -> bool:
        return (
            self.global_origin_x <= world_x < self.global_origin_x + self.width
            and self.global_origin_y <= world_y < self.global_origin_y + self.height
        )

    def get_anchor_coordinates(self, anchor_types: list[str] | str, fallback_coords: tuple[int, int] | None = None, world=None, requesting_entity=None, ideal_role: str | None = None) -> tuple[int, int] | None:
        """Return the best matching anchor using simple role, occupancy, and proximity preferences."""
        if isinstance(anchor_types, str):
            anchor_types = [anchor_types]

        best_score = None
        best_coords = None

        for anchor in self.anchors:
            if anchor.get("type") not in anchor_types:
                continue

            x = anchor.get("x")
            y = anchor.get("y")
            if x is None or y is None:
                continue

            tags = anchor.get("tags", {})
            score = 0

            if ideal_role and tags.get("role") == ideal_role:
                score += 100

            if tags.get("fallback") == "true":
                score -= 10

            if world:
                occupant_id = getattr(world, "entity_positions", {}).get((x, y))
                if occupant_id is not None and (not requesting_entity or occupant_id != requesting_entity.id):
                    score -= 25

                if requesting_entity:
                    dist = abs(requesting_entity.x - x) + abs(requesting_entity.y - y)
                    score -= dist

            if best_score is None or score > best_score:
                best_score = score
                best_coords = (x, y)

        if best_coords is not None:
            return best_coords

        return fallback_coords

    def refine_anchor_coordinates(self, world, start_x: int, start_y: int, radius: int = 1, requesting_entity=None) -> tuple[int, int] | None:
        """Finds a walkable, unoccupied tile near the given coordinates."""
        # Check exactly on the tile first if it's perfectly fine
        tile = world.get_tile_at(start_x, start_y)
        if tile and getattr(tile, "passable", False):
            occupant_id = getattr(world, "entity_positions", {}).get((start_x, start_y))
            if occupant_id is None or (requesting_entity and occupant_id == requesting_entity.id):
                return start_x, start_y

        candidates = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = start_x + dx, start_y + dy
                if not self.contains_global_coords(nx, ny):
                    continue
                tile = world.get_tile_at(nx, ny)
                if tile and getattr(tile, "passable", False):
                    occupant_id = getattr(world, "entity_positions", {}).get((nx, ny))
                    is_occupied = occupant_id is not None and (not requesting_entity or occupant_id != requesting_entity.id)
                    # Prioritize unoccupied tiles, then distance
                    score = (10 if not is_occupied else 0) - (abs(dx) + abs(dy))
                    candidates.append((score, nx, ny))

        if candidates:
            candidates.sort(key=lambda c: c[0], reverse=True)
            return candidates[0][1], candidates[0][2]

        return start_x, start_y


@dataclass
class ConstructionComponent:
    id: str
    type: str
    x: int
    y: int
    required_materials: dict[str, int]
    deposited_inventory: Inventory = field(default_factory=Inventory)
    required_work: int = 100
    build_progress: int = 0
    status: str = "pending"  # pending, building, complete
    claimed_by_actor_id: int | str | None = None
    claim_expiration_tick: int | None = None

    def __post_init__(self):
        if not isinstance(self.deposited_inventory, Inventory):
            self.deposited_inventory = Inventory(self.deposited_inventory or {})

    def remaining_materials(self) -> dict[str, int]:
        return {
            item_key: max(0, int(required_qty) - self.deposited_inventory.get(item_key, 0))
            for item_key, required_qty in self.required_materials.items()
            if max(0, int(required_qty) - self.deposited_inventory.get(item_key, 0)) > 0
        }

    def needs_material(self, item_key: str) -> bool:
        return self.remaining_materials().get(item_key, 0) > 0

    def has_all_materials(self) -> bool:
        return sum(self.remaining_materials().values()) == 0

    def remaining_work(self) -> int:
        return max(0, self.required_work - self.build_progress)

    def has_remaining_work(self) -> bool:
        return self.remaining_work() > 0 and self.status != "complete"

    def claim_is_active(self, current_tick: int | None = None) -> bool:
        if self.claimed_by_actor_id is None:
            return False
        if self.status == "complete" or not self.has_remaining_work():
            return False
        if self.claim_expiration_tick is None or current_tick is None:
            return True
        return current_tick <= self.claim_expiration_tick

    def is_claimed_by(self, actor_id: int | str | None, current_tick: int | None = None) -> bool:
        return actor_id is not None and self.claimed_by_actor_id == actor_id and self.claim_is_active(current_tick)

    def claim_for_actor(self, actor_id: int | str, current_tick: int | None = None, *, duration: int = 120) -> bool:
        if actor_id is None or self.status == "complete" or not self.has_remaining_work():
            return False
        if self.claim_is_active(current_tick) and self.claimed_by_actor_id != actor_id:
            return False
        self.claimed_by_actor_id = actor_id
        self.claim_expiration_tick = (current_tick + duration) if current_tick is not None else None
        return True

    def release_claim(self, actor_id: int | str | None = None) -> bool:
        if self.claimed_by_actor_id is None:
            return False
        if actor_id is not None and self.claimed_by_actor_id != actor_id:
            return False
        self.claimed_by_actor_id = None
        self.claim_expiration_tick = None
        return True

    def expire_claim_if_needed(self, current_tick: int | None = None) -> bool:
        if self.claimed_by_actor_id is None or self.claim_expiration_tick is None or current_tick is None:
            return False
        if current_tick <= self.claim_expiration_tick:
            return False
        return self.release_claim()

    def deposit_item_reference(self, item_reference) -> bool:
        if item_reference is None or not self.needs_material(item_reference.key):
            return False
        self.deposited_inventory.add_item_reference(item_reference)
        return True

    def apply_work(self, amount: int) -> bool:
        if not self.has_all_materials() or self.status == "complete":
            return False
        self.status = "building"
        self.build_progress = min(self.required_work, self.build_progress + max(0, int(amount)))
        if self.build_progress >= self.required_work:
            self.status = "complete"
            self.release_claim()
        return self.status == "complete"


@dataclass
class ConstructionBlueprint:

    x: int
    y: int
    target_build: str
    required_materials: dict[str, int]
    source: str = "decoration"
    tile_def_key: str | None = None
    width: int = 1
    height: int = 1
    category: str = "player_construction"
    settlement_id: str | None = None
    region_id: str | None = None
    owner_id: int | None = None
    requester_id: int | None = None
    build_progress: int = 0
    required_work: int = 100
    status: str = "planning"
    construction_stage: str = "planning"
    stalled_reason: str | None = None
    assigned_workers: list[int] = field(default_factory=list)
    active_tasks: list[str] = field(default_factory=list)
    territory_claim_id: str | None = None
    id: str = field(default_factory=lambda: new_id())
    deposited_inventory: Inventory = field(default_factory=Inventory)
    variant_id: str | None = None
    components: list[ConstructionComponent] = field(default_factory=list)


    STAGES: ClassVar[tuple[str, ...]] = ("planning", "foundation", "framing", "finishing", "complete")

    def __post_init__(self):
        if not isinstance(self.deposited_inventory, Inventory):
            self.deposited_inventory = Inventory(self.deposited_inventory or {})
        primary_material_key = next(iter(self.required_materials), None)
        primary_material_def = ITEM_DEFINITIONS.get(primary_material_key, {})
        fallback = DECORATION_ITEM_DEFINITIONS["rubble"]
        self.char = primary_material_def.get("char", fallback["char"])
        self.color = primary_material_def.get("color", fallback["color"])
        self.name = f"{self.target_build.replace('_', ' ').title()} Construction Site"

        if not self.components:
            # Distribute materials over the components evenly
            total_components = self.width * self.height
            mat_per_comp = {}
            mat_rem = {}
            for k, v in self.required_materials.items():
                mat_per_comp[k] = v // total_components
                mat_rem[k] = v % total_components

            for cy in range(self.height):
                for cx in range(self.width):
                    comp_mats = mat_per_comp.copy()
                    for k in list(mat_rem.keys()):
                        if mat_rem[k] > 0:
                            comp_mats[k] = comp_mats.get(k, 0) + 1
                            mat_rem[k] -= 1

                    # Remove empty requirements
                    comp_mats = {k: v for k, v in comp_mats.items() if v > 0}

                    comp = ConstructionComponent(
                        id=new_id(),
                        type="foundation",
                        x=self.x + cx,
                        y=self.y + cy,
                        required_materials=comp_mats,
                        required_work=max(10, self.required_work // total_components)
                    )
                    self.components.append(comp)

        self.refresh_status()

    @property
    def delivered_materials(self) -> Inventory:
        items = {}
        for comp in self.components:
            for item_key, qty in comp.deposited_inventory.items():
                items[item_key] = items.get(item_key, 0) + qty
        return Inventory(items)

    def remaining_materials(self) -> dict[str, int]:
        remaining = {}
        for comp in self.components:
            for k, v in comp.remaining_materials().items():
                remaining[k] = remaining.get(k, 0) + v
        return remaining

    def needs_material(self, item_key: str) -> bool:
        return self.deposited_inventory.get(item_key, 0) < int(self.required_materials.get(item_key, 0))

    def has_all_materials(self) -> bool:
        return not self.remaining_materials()

    def refresh_status(self) -> None:
        if self.build_progress >= self.required_work:
            self.status = "complete"
            self.construction_stage = "complete"
            self.stalled_reason = None
            return
        missing = self.remaining_materials()
        if missing:
            first_item = next(iter(missing))
            self.status = "stalled" if self.build_progress > 0 else "awaiting_materials"
            self.construction_stage = "planning" if self.build_progress <= 0 else self.construction_stage
            self.stalled_reason = f"Awaiting {first_item}"
            return
        self.status = "building"
        self.stalled_reason = None
        self._update_stage_from_progress()

    def _update_stage_from_progress(self) -> None:
        if self.build_progress >= self.required_work:
            self.construction_stage = "complete"
        elif self.build_progress >= int(self.required_work * 0.66):
            self.construction_stage = "finishing"
        elif self.build_progress >= int(self.required_work * 0.33):
            self.construction_stage = "framing"
        else:
            self.construction_stage = "foundation"

    def deposit_item_reference(self, item_reference, component_id: str | None = None) -> bool:
        if item_reference is None:
            return False
        if component_id:
            for comp in self.components:
                if comp.id == component_id:
                    if comp.deposit_item_reference(item_reference):
                        self.deposited_inventory.add_item_reference(item_reference)
                        self.refresh_status()
                        return True
            return False
        # Fallback to the first component that needs it
        for comp in self.components:
            if comp.deposit_item_reference(item_reference):
                self.deposited_inventory.add_item_reference(item_reference)
                self.refresh_status()
                return True
        return False

    def apply_work(self, amount: int, component_id: str | None = None) -> bool:
        if component_id:
            for comp in self.components:
                if comp.id == component_id:
                    if comp.apply_work(amount):
                        self.refresh_status()
                    return True
        # Original fallback apply to overall if component_id not given
        if not self.has_all_materials() or self.status == "complete":
            self.refresh_status()
            return False
        self.build_progress = min(self.required_work, self.build_progress + max(0, int(amount)))
        self.refresh_status()
        return self.status == "complete"

    def is_complete(self) -> bool:
        return self.status == "complete"


@dataclass
class LandClaim:
    claim_type: str
    claimed_tiles: set[tuple[int, int]] = field(default_factory=set)
    reserved_tiles: set[tuple[int, int]] = field(default_factory=set)
    owner_type: str = "settlement"
    owner_id: str | int | None = None
    settlement_id: str | None = None
    expansion_pressure: int = 0
    active: bool = True
    priority: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: new_id())

    def all_tiles(self) -> set[tuple[int, int]]:
        return set(self.claimed_tiles) | set(self.reserved_tiles)

    def contains(self, x: int, y: int, *, include_reserved: bool = True) -> bool:
        coord = (x, y)
        return coord in self.claimed_tiles or (include_reserved and coord in self.reserved_tiles)

    def label(self) -> str:
        labels = {
            "settlement_core": "Settlement boundary",
            "rural_expansion": "Rural settlement territory",
            "reserved_expansion": "Reserved expansion",
            "farm": "Farm territory",
            "ranch": "Pasture claim",
            "hunting": "Hunting territory",
            "logging": "Logging territory",
            "business": "Business claim",
            "construction_reservation": "Reserved construction site",
        }
        return labels.get(self.claim_type, self.claim_type.replace("_", " ").title())


@dataclass
class Stockpile:
    stockpile_id: str
    x: int
    y: int
    accepted_item_types: set[str] = field(default_factory=set)
    max_item_count: int = 100
    owner_id: int | str | None = None
    faction_id: str | None = None
    village_id: str | None = None
    stored_inventory: Inventory = field(default_factory=Inventory)
    reservations: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.stored_inventory, Inventory):
            self.stored_inventory = Inventory(self.stored_inventory or {})
        self.accepted_item_types = set(self.accepted_item_types or set())

    @property
    def position(self) -> tuple[int, int]:
        return self.x, self.y

    def total_item_count(self) -> int:
        return sum(max(0, int(qty)) for qty in self.stored_inventory.values())

    def accepts(self, item_key: str | None) -> bool:
        return bool(item_key) and (not self.accepted_item_types or item_key in self.accepted_item_types)

    def has_capacity_for(self, quantity: int = 1) -> bool:
        return self.total_item_count() + max(0, int(quantity)) <= self.max_item_count

    def quantity(self, item_key: str) -> int:
        return self.stored_inventory.get(item_key, 0)

    def reserved_quantity(self, item_key: str, *, excluding_reservation_id: str | None = None) -> int:
        total = 0
        for reservation_id, reservation in self.reservations.items():
            if reservation_id == excluding_reservation_id or reservation.get("status") != "active":
                continue
            if reservation.get("item_key") == item_key:
                total += max(0, int(reservation.get("quantity", 0)))
        return total

    def available_quantity(self, item_key: str, *, excluding_reservation_id: str | None = None) -> int:
        return max(0, self.quantity(item_key) - self.reserved_quantity(item_key, excluding_reservation_id=excluding_reservation_id))

    def deposit_item_reference(self, item_reference: ItemReference) -> bool:
        if item_reference is None or not self.accepts(item_reference.key) or not self.has_capacity_for(1):
            return False
        self.stored_inventory.add_item_reference(item_reference)
        return True

    def deposit_item(self, item_key: str, quantity: int = 1) -> int:
        if not self.accepts(item_key):
            return 0
        accepted = min(max(0, int(quantity)), max(0, self.max_item_count - self.total_item_count()))
        if accepted <= 0:
            return 0
        self.stored_inventory.add_item(item_key, accepted)
        return accepted

    def create_reservation(self, item_key: str, quantity: int, actor_id: int | str | None = None, task_id: str | None = None, current_tick: int | None = None) -> str | None:
        quantity = max(1, int(quantity))
        if self.available_quantity(item_key) < quantity:
            return None
        reservation_id = new_id()
        self.reservations[reservation_id] = {
            "reservation_id": reservation_id,
            "item_key": item_key,
            "quantity": quantity,
            "actor_id": actor_id,
            "task_id": task_id,
            "created_tick": current_tick,
            "status": "active",
        }
        return reservation_id

    def release_reservation(self, reservation_id: str | None) -> bool:
        if not reservation_id or reservation_id not in self.reservations:
            return False
        self.reservations.pop(reservation_id, None)
        return True

    def withdraw_reserved_item_reference(self, reservation_id: str | None, actor_id: int | str | None = None) -> ItemReference | None:
        reservation = self.reservations.get(reservation_id or "")
        if reservation is None or reservation.get("status") != "active":
            return None
        if actor_id is not None and reservation.get("actor_id") not in {None, actor_id}:
            return None
        item_key = reservation.get("item_key")
        if not item_key or self.quantity(item_key) <= 0:
            return None
        item_reference = self.stored_inventory.pop_item_reference(item_key)
        if item_reference is None:
            return None
        reservation["quantity"] = max(0, int(reservation.get("quantity", 0)) - 1)
        if reservation["quantity"] <= 0:
            self.release_reservation(reservation_id)
        return item_reference

    def withdraw_item_reference(self, item_key: str) -> ItemReference | None:
        if self.available_quantity(item_key) <= 0:
            return None
        return self.stored_inventory.pop_item_reference(item_key)


@dataclass
class HaulTask:
    blueprint_id: str
    item_key: str
    destination_x: int
    destination_y: int
    quantity: int = 1
    id: str = field(default_factory=lambda: new_id())
    assigned_entity_id: int | None = None
    status: str = "open"
    component_id: str | None = None
    source_stockpile_id: str | None = None
    stockpile_reservation_id: str | None = None


@dataclass
class DeliveryTask:
    source_building_id: str
    destination_building_id: str
    item_key: str
    quantity: int
    id: str = field(default_factory=lambda: new_id())
    assigned_entity_id: int | None = None
    status: str = "open" # open, claimed, going_to_source, carrying, going_to_destination, complete, failed
    created_tick: int = 0
    updated_tick: int = 0


@dataclass
class EmploymentTask:
    target_building_id: str
    profession_role: str
    daily_wage: int
    poster_entity_id: int | None = None
    id: str = field(default_factory=lambda: new_id())
    assigned_entity_id: int | None = None
    status: str = "open"


@dataclass
class TownEconomicNeed:
    id: str = field(default_factory=lambda: new_id())
    type: str = "shortage" # shortage, surplus, service
    target_key: str = "" # e.g. "wood", "blacksmith"
    severity: int = 1 # 1-100
    settlement_id: str | None = None
    creation_tick: int = 0
    description: str = ""



@dataclass
class WorkshopRuntimeState:
    workshop_id: str
    workshop_type: str = "sawbench"
    occupied_by_actor_id: int | None = None
    active_interaction_id: str | None = None
    input_buffer: Inventory = field(default_factory=Inventory)
    reserved_input_entity_ids: list[str] = field(default_factory=list)
    output_buffer: Inventory = field(default_factory=Inventory)
    operational: bool = True
    last_used_tick: int = 0
    lock_expiration_tick: int = 0
    x: int = 0
    y: int = 0


@dataclass
class ReserveTarget:
    reserve_target_id: str
    target_type: str = "stockpile_item"
    target_entity_id: str | None = None
    desired_quantity: int = 1
    minimum_quantity: int = 0
    current_quantity: int = 0
    linked_item_type: str = "raw_log"
    priority: int = 1
    last_evaluated_tick: int = 0
    cooldown_until_tick: int = 0
    active_task_ids: list[str] = field(default_factory=list)

@dataclass
class ProductionTask:
    task_type: str
    status: str = "pending"
    target_entity_id: str | int | None = None
    assigned_actor_ids: list[int] = field(default_factory=list)
    reserved_entity_ids: list[str] = field(default_factory=list)
    created_tick: int = 0
    expiration_tick: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    priority: int = 1
    urgency: int = 0
    last_progress_tick: int = 0
    retry_count: int = 0
    cooldown_until_tick: int = 0
    blocked_reason: str | None = None
    resource_pressure_score: int = 0
    dependency_task_ids: list[str] = field(default_factory=list)
    prerequisite_item_types: list[str] = field(default_factory=list)
    blocked_by_task_ids: list[str] = field(default_factory=list)
    blocking_task_ids: list[str] = field(default_factory=list)
    inherited_priority: int = 0
    dependency_depth: int = 0
    dependency_reason: str | None = None
    last_dependency_eval_tick: int = 0
    id: str = field(default_factory=lambda: new_id())


@dataclass
class DecisionExplanation:
    explanation_id: str
    tick: int
    explanation_type: str
    source_entity_id: str | int | None = None
    target_entity_id: str | int | None = None
    task_id: str | None = None
    actor_id: int | None = None
    decision: str = ""
    primary_reason: str = ""
    contributing_factors: dict[str, Any] = field(default_factory=dict)
    score_snapshot: dict[str, Any] = field(default_factory=dict)
    linked_trace_ids: list[str] = field(default_factory=list)
    created_from: str = "runtime"


@dataclass
class WorldDebugSnapshot:
    tick: int
    reserve_targets: list[dict[str, Any]] = field(default_factory=list)
    production_tasks: list[dict[str, Any]] = field(default_factory=list)
    active_interactions: list[dict[str, Any]] = field(default_factory=list)
    actor_work_profiles: list[dict[str, Any]] = field(default_factory=list)
    stockpiles: list[dict[str, Any]] = field(default_factory=list)
    workshops: list[dict[str, Any]] = field(default_factory=list)
    recent_decision_explanations: list[dict[str, Any]] = field(default_factory=list)
    recent_validation_warnings: list[dict[str, Any]] = field(default_factory=list)
    recent_traces: list[dict[str, Any]] = field(default_factory=list)
    runtime_health_summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class CampfireRuntimeState:
    campfire_id: str
    x: int
    y: int
    operational: bool = True
    lit: bool = True
    fuel_item_type: str = "raw_log"
    fuel_quantity: int = 0
    max_fuel_quantity: int = 10
    minimum_fuel_quantity: int = 2
    burn_rate_per_tick: int = 1
    last_burn_tick: int = 0
    linked_reserve_target_id: str | None = None
    reserved_fuel_entity_ids: list[str] = field(default_factory=list)
    last_refuel_tick: int = 0
    warmth_radius: int = 4
    warmth_value: float = 1.0
    provides_warmth: bool = True



@dataclass
class PoliticalOffice:
    name: str
    daily_salary: int
    holder_id: int | None = None
    last_elected_day: int = -1


@dataclass
class PoliticalWarrant:
    warrant_kind: str
    target_id: int
    issuer_id: int | None
    cost: int
    issued_day: int
    id: str = field(default_factory=lambda: new_id())
    status: str = "active"


@dataclass
class PoliticsTracker:
    town_hall_building_id: str | None = None
    tax_rate: float = 0.10
    last_governance_day: int = -1
    offices: dict[str, PoliticalOffice] = field(
        default_factory=lambda: {
            "Mayor": PoliticalOffice(name="Mayor", daily_salary=40),
            "Captain of the Guard": PoliticalOffice(name="Captain of the Guard", daily_salary=30),
        }
    )
    active_warrants: list[PoliticalWarrant] = field(default_factory=list)

    def get_office(self, office_name: str) -> PoliticalOffice | None:
        return self.offices.get(office_name)


class TownBoard:
    def __init__(self):
        self.haul_tasks: list[HaulTask] = []
        self.employment_tasks: list[EmploymentTask] = []
        self.economic_needs: list[TownEconomicNeed] = []
        self.delivery_tasks: list[DeliveryTask] = []

    def post_blueprint(self, blueprint: ConstructionBlueprint) -> None:
        for comp in blueprint.components:
            for item_key, remaining_qty in comp.remaining_materials().items():
                for _ in range(max(0, int(remaining_qty))):
                    self.haul_tasks.append(
                        HaulTask(
                            blueprint_id=blueprint.id,
                            item_key=item_key,
                            destination_x=comp.x,
                            destination_y=comp.y,
                            component_id=comp.id
                        )
                    )

    def get_open_tasks(self, blueprint_id: str | None = None) -> list[HaulTask]:
        tasks = [task for task in self.haul_tasks if task.status == "open"]
        if blueprint_id is not None:
            tasks = [task for task in tasks if task.blueprint_id == blueprint_id]
        return tasks

    def claim_task(self, task: HaulTask, entity_id: int) -> bool:
        if task.status != "open":
            return False
        task.status = "claimed"
        task.assigned_entity_id = entity_id
        return True

    def release_task(self, task_id: str) -> None:
        for task in self.haul_tasks:
            if task.id == task_id and task.status == "claimed":
                task.status = "open"
                task.assigned_entity_id = None
                return

    def complete_task(self, task_id: str) -> None:
        for task in self.haul_tasks:
            if task.id == task_id:
                task.status = "complete"
                task.assigned_entity_id = None
                return

    def remove_blueprint_tasks(self, blueprint_id: str) -> None:
        self.haul_tasks = [task for task in self.haul_tasks if task.blueprint_id != blueprint_id]

    def get_task(self, task_id: str | None) -> HaulTask | None:
        if not task_id:
            return None
        return next((task for task in self.haul_tasks if task.id == task_id), None)

    def post_delivery_task(self, source_building_id: str, destination_building_id: str, item_key: str, quantity: int, created_tick: int) -> DeliveryTask:
        existing = self.find_active_delivery_task(source_building_id, destination_building_id, item_key)
        if existing is not None:
            return existing

        task = DeliveryTask(
            source_building_id=source_building_id,
            destination_building_id=destination_building_id,
            item_key=item_key,
            quantity=quantity,
            created_tick=created_tick,
            updated_tick=created_tick,
        )
        self.delivery_tasks.append(task)
        return task

    def get_open_delivery_tasks(self, destination_building_id: str | None = None) -> list[DeliveryTask]:
        tasks = [task for task in self.delivery_tasks if task.status == "open"]
        if destination_building_id is not None:
            tasks = [task for task in tasks if task.destination_building_id == destination_building_id]
        return tasks

    def get_active_delivery_tasks(self, destination_building_id: str | None = None) -> list[DeliveryTask]:
        """Return unfinished delivery tasks for dedupe and lifecycle recovery."""
        active_statuses = {"open", "claimed", "going_to_source", "carrying", "going_to_destination"}
        tasks = [task for task in self.delivery_tasks if task.status in active_statuses]
        if destination_building_id is not None:
            tasks = [task for task in tasks if task.destination_building_id == destination_building_id]
        return tasks

    def find_active_delivery_task(self, source_building_id: str, destination_building_id: str, item_key: str) -> DeliveryTask | None:
        for task in self.get_active_delivery_tasks(destination_building_id):
            if task.source_building_id == source_building_id and task.item_key == item_key:
                return task
        return None

    def claim_delivery_task(self, task: DeliveryTask, entity_id: int, *, current_tick: int | None = None) -> bool:
        if task.status != "open":
            return False
        task.status = "claimed"
        task.assigned_entity_id = entity_id
        if current_tick is not None:
            task.updated_tick = current_tick
        return True

    def update_delivery_task_status(self, task_id: str, status: str, *, current_tick: int | None = None) -> None:
        task = self.get_delivery_task(task_id)
        if task is None:
            return
        task.status = status
        if current_tick is not None:
            task.updated_tick = current_tick

    def release_delivery_task(self, task_id: str) -> None:
        for task in self.delivery_tasks:
            if task.id == task_id and task.status in {"claimed", "going_to_source"}:
                task.status = "open"
                task.assigned_entity_id = None
                return

    def complete_delivery_task(self, task_id: str) -> None:
        self.delivery_tasks = [task for task in self.delivery_tasks if task.id != task_id]

    def fail_delivery_task(self, task_id: str) -> None:
        self.delivery_tasks = [task for task in self.delivery_tasks if task.id != task_id]

    def get_delivery_task(self, task_id: str | None) -> DeliveryTask | None:
        if not task_id:
            return None
        return next((task for task in self.delivery_tasks if task.id == task_id), None)

    def post_employment(self, target_building_id: str, profession_role: str, daily_wage: int, *, poster_entity_id: int | None = None) -> EmploymentTask:
        task = EmploymentTask(
            target_building_id=target_building_id,
            profession_role=profession_role,
            daily_wage=max(1, int(daily_wage)),
            poster_entity_id=poster_entity_id,
        )
        self.employment_tasks.append(task)
        return task

    def get_open_employment_tasks(self, target_building_id: str | None = None) -> list[EmploymentTask]:
        tasks = [task for task in self.employment_tasks if task.status == "open"]
        if target_building_id is not None:
            tasks = [task for task in tasks if task.target_building_id == target_building_id]
        return tasks

    def get_employment_task(self, task_id: str | None) -> EmploymentTask | None:
        if not task_id:
            return None
        return next((task for task in self.employment_tasks if task.id == task_id), None)

    def claim_employment_task(self, task: EmploymentTask, entity_id: int) -> bool:
        if task.status != "open":
            return False
        task.status = "claimed"
        task.assigned_entity_id = entity_id
        return True

    def complete_employment_task(self, task_id: str) -> None:
        for task in self.employment_tasks:
            if task.id == task_id:
                task.status = "complete"
                task.assigned_entity_id = None
                return

    def release_employment_task(self, task_id: str) -> None:
        for task in self.employment_tasks:
            if task.id == task_id and task.status == "claimed":
                task.status = "open"
                task.assigned_entity_id = None
                return

    def remove_employment_task(self, task_id: str) -> None:
        self.employment_tasks = [task for task in self.employment_tasks if task.id != task_id]


class LocalOfficeView(MutableMapping):
    """Compatibility ID view; office holders have one authoritative record."""
    def __init__(self, village):
        self.village = village

    def __getitem__(self, name):
        return self.village.politics.offices[name].holder_id

    def __setitem__(self, name, value):
        self.village.politics.offices[name].holder_id = value

    def __delitem__(self, name):
        self[name] = None

    def __iter__(self):
        return iter(self.village.politics.offices)

    def __len__(self):
        return len(self.village.politics.offices)


class Village:
    def __init__(self, primary_biome: str | None = None, chunk_coords: tuple[int, int] | None = None, region_id: str | None = None):
        self.id = new_id()
        self.buildings = []
        self.lore = "No lore generated yet."
        self.interaction_points = {}
        self.supply = {}
        self.demand = {}
        self.local_events = []
        self.known_events = {}
        self.construction_projects = []
        self.village_relationships = {}
        self.at_war_with = set()
        self.population_cache = 0
        self.primary_biome = primary_biome
        self.chunk_coords = chunk_coords
        self.region_id = region_id
        self.history_record_ids: list[str] = []
        self.noticeboard_rumors: dict[str, Any] = {}
        self.territory_claim_ids: list[str] = []
        self.politics = PoliticsTracker()
        self.name = ""
        self.tax_rate: float = 0.10
        self.local_offices: dict[str, int | None] = {
            "Mayor": None,
            "Captain of the Guard": None,
        }

    @property
    def local_offices(self):
        return LocalOfficeView(self)

    @local_offices.setter
    def local_offices(self, holders):
        for name, holder_id in holders.items():
            if name in self.politics.offices:
                self.politics.offices[name].holder_id = holder_id

    @property
    def tax_rate(self):
        return self.politics.tax_rate

    @tax_rate.setter
    def tax_rate(self, value):
        self.politics.tax_rate = value

    def __setstate__(self, state):
        self.__dict__.update(state)
        if "politics" not in state:
            self.politics = PoliticsTracker()
            self.tax_rate = state.get("tax_rate", .10)
            self.local_offices = state.get("local_offices", {})
        self.__dict__.pop("tax_rate", None)
        self.__dict__.pop("local_offices", None)
        self.name = state.get("name", "")

    def add_building(self, building: Building):
        building.settlement_id = self.id
        building.region_id = self.region_id
        self.buildings.append(building)


class Ruin:
    def __init__(self, primary_biome: str | None = None, chunk_coords: tuple[int, int] | None = None, region_id: str | None = None):
        self.id = new_id()
        self.lore = "The origins of this place are lost to time."
        self.primary_biome = primary_biome
        self.chunk_coords = chunk_coords
        self.region_id = region_id
        self.history_record_ids: list[str] = []


@dataclass
class Region:
    name: str
    primary_biome: str
    id: str = field(default_factory=lambda: new_id())
    chunk_coords: set[tuple[int, int]] = field(default_factory=set)
    village_ids: set[str] = field(default_factory=set)
    ruin_ids: set[str] = field(default_factory=set)
    climate_profile: dict[str, Any] = field(default_factory=dict)
    resource_tags: set[str] = field(default_factory=set)
    lore_notes: list[str] = field(default_factory=list)

    def add_chunk(self, chunk_coords: tuple[int, int]):
        self.chunk_coords.add(chunk_coords)

    def add_village(self, village: Village):
        village.region_id = self.id
        self.village_ids.add(village.id)

    def add_ruin(self, ruin: Ruin):
        ruin.region_id = self.id
        self.ruin_ids.add(ruin.id)


class Chunk:
    def __init__(self, biome, poi_type=None, region_id: str | None = None):
        self.biome = biome
        self.poi_type = poi_type
        self.tiles = None
        self.is_generated = False
        self.is_terrain_generated = False
        self.wildlife_generated = False
        self.allow_wildlife_population = False
        self.village = None
        self.ruin = None
        self.region_id = region_id


class WorldAtlas:
    """Owns world geography, settlements, and building indexes."""

    def __init__(self):
        self.villages: list[Village] = []
        self.buildings_by_id: dict[str, Building] = {}
        self.regions_by_id: dict[str, Region] = {}
        self.region_by_chunk: dict[tuple[int, int], str] = {}
        self.ruins_by_id: dict[str, Ruin] = {}

    def create_region(self, name: str, primary_biome: str) -> Region:
        region = Region(name=name, primary_biome=primary_biome)
        self.regions_by_id[region.id] = region
        return region

    def get_region(self, region_id: str | None) -> Region | None:
        if not region_id:
            return None
        return self.regions_by_id.get(region_id)

    def get_village(self, village_id: str | None) -> Village | None:
        if not village_id:
            return None
        return next((village for village in self.villages if village.id == village_id), None)

    def get_region_for_chunk(self, chunk_x: int, chunk_y: int) -> Region | None:
        region_id = self.region_by_chunk.get((chunk_x, chunk_y))
        return self.get_region(region_id)

    def get_region_for_world_coords(self, world_x: int, world_y: int, chunk_size: int) -> Region | None:
        return self.get_region_for_chunk(world_x // chunk_size, world_y // chunk_size)

    def get_or_create_region_for_chunk(self, chunk_x: int, chunk_y: int, biome: str) -> Region:
        existing = self.get_region_for_chunk(chunk_x, chunk_y)
        if existing is not None:
            return existing
        region = self.create_region(name=f"{biome.title()} Region {chunk_x},{chunk_y}", primary_biome=biome)
        self.assign_chunk_to_region(chunk_x, chunk_y, region)
        return region

    def assign_chunk_to_region(self, chunk_x: int, chunk_y: int, region: Region):
        coords = (chunk_x, chunk_y)
        self.region_by_chunk[coords] = region.id
        region.add_chunk(coords)

    def add_village(self, village: Village, chunk_coords: tuple[int, int] | None = None, region: Region | None = None):
        if region is not None:
            region.add_village(village)
        if chunk_coords is not None:
            village.chunk_coords = chunk_coords
        self.villages.append(village)
        for building in village.buildings:
            self.register_building(building)
        return village

    def add_ruin(self, ruin: Ruin, chunk_coords: tuple[int, int] | None = None, region: Region | None = None):
        if region is not None:
            region.add_ruin(ruin)
        if chunk_coords is not None:
            ruin.chunk_coords = chunk_coords
        self.ruins_by_id[ruin.id] = ruin
        return ruin

    def register_building(self, building: Building):
        self.buildings_by_id[building.id] = building
        return building

    def get_building(self, building_id: str | None) -> Building | None:
        if not building_id:
            return None
        return self.buildings_by_id.get(building_id)
