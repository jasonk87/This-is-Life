"""Business ownership, delegated labor, and lightweight production chain helpers."""

from __future__ import annotations

from dataclasses import dataclass

from data.items import ITEM_DEFINITIONS
from simulation.careers import normalize_profession
from simulation.world_model import Business, Building, TownEconomicNeed, Village


@dataclass(frozen=True)
class ProductionRecipe:
    inputs: dict[str, int]
    outputs: dict[str, int]
    duration_ticks: int
    worker_roles: tuple[str, ...]
    activity_label: str
    shortage_label: str = "Short on inputs."
    destination_building_types: tuple[str, ...] = ()


BUSINESS_TYPE_BY_BUILDING = {
    "lumber_mill": "lumber_operation",
    "tavern": "tavern",
    "blacksmith_shop": "blacksmith",
    "farm": "farm",
    "stable": "stable",
    "general_store": "general_labor_company",
}

BUSINESS_PROFESSION_BY_TYPE = {
    "lumber_operation": "Lumber Mill Foreman",
    "tavern": "Tavern Keeper",
    "blacksmith": "Blacksmith",
    "farm": "Farmer",
    "stable": "Stable Keeper",
    "general_labor_company": "Merchant",
}

BUSINESS_ROLE_BY_TYPE = {
    "lumber_operation": "producer",
    "tavern": "service",
    "blacksmith": "producer",
    "farm": "producer",
    "stable": "service",
    "general_labor_company": "logistics",
}

BUSINESS_RECIPES = {
    "lumber_operation": ProductionRecipe(
        inputs={"raw_log": 1},
        outputs={"wooden_plank": 2},
        duration_ticks=8,
        worker_roles=("Woodcutter", "Lumber Mill Foreman"),
        activity_label="Sawing lumber",
        shortage_label="Short on raw logs.",
        destination_building_types=("general_store",),
    ),
    "tavern": ProductionRecipe(
        inputs={"wheat": 1, "raw_log": 1},
        outputs={"bread": 1},
        duration_ticks=10,
        worker_roles=("Tavern Keeper",),
        activity_label="Cooking tavern food",
        shortage_label="Short on food or firewood.",
        destination_building_types=("general_store",),
    ),
    "blacksmith": ProductionRecipe(
        inputs={"iron_ore": 2, "coal": 1},
        outputs={"iron_ingot": 1},
        duration_ticks=12,
        worker_roles=("Blacksmith",),
        activity_label="Forging metal",
        shortage_label="Short on ore or fuel.",
        destination_building_types=("general_store",),
    ),
    "farm": ProductionRecipe(
        inputs={},
        outputs={"wheat": 2},
        duration_ticks=10,
        worker_roles=("Farmer",),
        activity_label="Tending crops",
        shortage_label="No farm labor available.",
        destination_building_types=("tavern", "general_store"),
    ),
    "stable": ProductionRecipe(
        inputs={"wheat": 1},
        outputs={},
        duration_ticks=10,
        worker_roles=("Stable Keeper", "Laborer"),
        activity_label="Feeding animals",
        shortage_label="Short on feed.",
    ),
}

OWNER_MANAGEMENT_TASKS = {
    "hiring", "supervising", "inspecting", "negotiating", "balancing_ledger"
}

LOW_LEVEL_WORK_ROLES = {"Laborer", "Woodcutter", "Farmer", "Miner"}
HIGH_STATUS_OWNER_ROLES = {"Merchant", "Tavern Keeper", "Blacksmith", "Lumber Mill Foreman", "Town Official"}


def ensure_world_business_registry(world) -> dict[str, Business]:
    if not hasattr(world, "businesses_by_id"):
        world.businesses_by_id = {}
    return world.businesses_by_id


def get_business(world, business_id: str | None) -> Business | None:
    if not business_id:
        return None
    return ensure_world_business_registry(world).get(business_id)


def create_business_for_building(world, building: Building, owner=None, business_type: str | None = None) -> Business:
    registry = ensure_world_business_registry(world)
    existing = get_business(world, getattr(building, "business_id", None))
    if existing is not None:
        if owner is not None:
            existing.owner_id = getattr(owner, "id", owner)
            building.owner_id = existing.owner_id
        return existing

    business_type = business_type or BUSINESS_TYPE_BY_BUILDING.get(building.building_type, building.building_type)
    owner_id = getattr(owner, "id", owner) if owner is not None else getattr(building, "owner_id", None)
    business = Business(
        owner_id=owner_id,
        profession_type=BUSINESS_PROFESSION_BY_TYPE.get(business_type, building.building_type.replace("_", " ").title()),
        business_type=business_type,
        production_role=BUSINESS_ROLE_BY_TYPE.get(business_type, "service"),
        workplace_building_id=building.id,
        wages={},
        inventory_storage_id=building.id,
    )
    building.business_id = business.id
    building.owner_id = owner_id
    registry[business.id] = business
    return business


def sync_business_from_world(world, business: Business) -> Business:
    building = world.buildings_by_id.get(business.workplace_building_id)
    if building is None:
        business.operating_status = "closed"
        return business
    business.owner_id = business.owner_id if business.owner_id is not None else getattr(building, "owner_id", None)
    business.worker_ids = [
        npc.id for npc in getattr(world, "village_npcs", [])
        if getattr(getattr(npc, "schedule", None), "work_building_id", None) == building.id
        and not getattr(getattr(npc, "physical", None), "is_dead", False)
        and npc.id != business.owner_id
    ]
    business.open_job_ids = [task.id for task in world.town_board.get_open_employment_tasks(building.id)] if hasattr(world, "town_board") else []
    business.inventory_snapshot = {k: int(v) for k, v in getattr(building, "building_inventory", {}).items() if k != "money"}
    if not business.worker_ids:
        business.operating_status = "understaffed"
    elif business.current_shortages:
        business.operating_status = "stalled"
    else:
        business.operating_status = "operating"
    return business


def actor_business_role(world, npc, business: Business | None = None) -> str:
    if business is None:
        building = world.buildings_by_id.get(getattr(getattr(npc, "schedule", None), "work_building_id", None))
        business = get_business(world, getattr(building, "business_id", None)) if building is not None else None
    if business is not None and business.owner_id == getattr(npc, "id", None):
        return "owner"
    profession = normalize_profession(getattr(getattr(npc, "economic", None), "profession", ""))
    if profession in {"Lumber Mill Foreman", "Merchant"}:
        return "manager"
    if profession in {"Blacksmith", "Carpenter", "Miller", "Baker", "Healer", "Scribe"}:
        return "skilled_worker"
    if profession in LOW_LEVEL_WORK_ROLES:
        return "laborer"
    if profession in {"Tavern Keeper"}:
        return "skilled_worker"
    return "helper"


def should_owner_delegate_low_labor(world, owner, business: Business) -> bool:
    if business.owner_id != getattr(owner, "id", None):
        return False
    profession = normalize_profession(getattr(getattr(owner, "economic", None), "profession", ""))
    if profession not in HIGH_STATUS_OWNER_ROLES:
        return False
    if business.worker_ids:
        return True
    desperate = business.demand_pressure >= 80 or bool(business.current_shortages)
    personality = str(getattr(getattr(owner, "social", None), "personality", "")).lower()
    return not desperate and "humble" not in personality and "hardworking" not in personality


def evaluate_worker_for_job(world, npc, business: Business, role: str, daily_wage: int) -> int:
    building = world.buildings_by_id.get(business.workplace_building_id)
    if building is None:
        return -999
    current_profession = normalize_profession(getattr(getattr(npc, "economic", None), "profession", ""))
    distance = abs(getattr(npc, "x", 0) - building.global_center_x) + abs(getattr(npc, "y", 0) - building.global_center_y)
    score = int(daily_wage) * 3 - distance
    if current_profession == "Unemployed":
        score += 25 + int(getattr(getattr(npc, "economic", None), "days_unemployed", 0)) * 2
    if current_profession == normalize_profession(role):
        score += 35
    elif current_profession != "Unemployed":
        score -= 20
    if getattr(getattr(npc, "economic", None), "money", 0) < 5:
        score += 15
    ambition = str(getattr(getattr(npc, "social", None), "personality", "")).lower()
    if "ambitious" in ambition or "hardworking" in ambition:
        score += 10
    return score


def post_business_openings(world, business: Business, *, force_wage: int | None = None) -> list:
    building = world.buildings_by_id.get(business.workplace_building_id)
    if building is None or not hasattr(world, "town_board"):
        return []
    sync_business_from_world(world, business)
    vacancies = max(0, int(getattr(building, "max_workers", 1)) - len(business.worker_ids))
    open_tasks = list(world.town_board.get_open_employment_tasks(building.id))
    if len(open_tasks) >= vacancies:
        return []
    role = business.profession_type
    wage = force_wage if force_wage is not None else getattr(world, "_get_employment_daily_wage", lambda r, **_: 10)(role)
    if business.demand_pressure >= 70 or business.operating_status in {"understaffed", "stalled"}:
        wage = int(wage * 1.25) + 1
    posted = []
    while len(open_tasks) + len(posted) < vacancies:
        try:
            task = world.town_board.post_employment(building.id, role, wage, poster_entity_id=business.owner_id)
        except TypeError:
            task = world.town_board.post_employment(building.id, role, wage)
        business.open_job_ids.append(task.id)
        business.wages[role] = wage
        posted.append(task)
    return posted


def find_source_inventory_for_inputs(world, village: Village | None, target_building: Building, inputs: dict[str, int]) -> Building | None:
    if not village or not inputs:
        return None
    for building in village.buildings:
        if building.id == target_building.id:
            continue
        inventory = getattr(building, "building_inventory", {})
        if any(inventory.get(item_key, 0) >= qty for item_key, qty in inputs.items()):
            return building
    return None


def pull_missing_inputs(world, village: Village | None, target_building: Building, inputs: dict[str, int]) -> int:
    moved = 0
    if not village:
        return moved
    for item_key, qty in inputs.items():
        missing = max(0, int(qty) - target_building.building_inventory.get(item_key, 0))
        while missing > 0:
            source = next((b for b in village.buildings if b.id != target_building.id and b.building_inventory.get(item_key, 0) > 0), None)
            if source is None:
                break
            source.building_inventory.transfer_item_objects(target_building.building_inventory, item_key, 1)
            moved += 1
            missing -= 1
    return moved


def _inventory_has_inputs(inventory, inputs: dict[str, int]) -> bool:
    return all(inventory.get(item_key, 0) >= int(qty) for item_key, qty in inputs.items())


def _consume_inputs(inventory, inputs: dict[str, int]) -> bool:
    if not _inventory_has_inputs(inventory, inputs):
        return False
    for item_key, qty in inputs.items():
        inventory.remove_item(item_key, int(qty))
    return True


def _add_outputs(inventory, outputs: dict[str, int], crafter_name: str | None = None) -> None:
    for item_key, qty in outputs.items():
        if qty > 0:
            inventory.add_item(item_key, int(qty), crafter_name=crafter_name)


def _update_village_supply_and_demand(village: Village | None, outputs: dict[str, int], shortages: set[str]) -> None:
    if village is None:
        return
    for item_key, qty in outputs.items():
        village.supply[item_key] = village.supply.get(item_key, 0) + int(qty)
        if item_key in village.demand:
            village.demand[item_key] = max(1, village.demand.get(item_key, 1) - int(qty))
    for item_key in shortages:
        village.demand[item_key] = village.demand.get(item_key, 1) + 1


def operate_business_tick(world, business: Business, *, worker=None) -> bool:
    building = world.buildings_by_id.get(business.workplace_building_id)
    if building is None:
        business.operating_status = "closed"
        return False
    recipe = BUSINESS_RECIPES.get(business.business_type)
    if recipe is None:
        return False
    sync_business_from_world(world, business)
    if worker is None:
        workers = [npc for npc in getattr(world, "village_npcs", []) if npc.id in business.worker_ids]
    else:
        workers = [worker]
    if recipe.worker_roles:
        qualified_workers = [
            npc for npc in workers
            if normalize_profession(getattr(getattr(npc, "economic", None), "profession", "")) in recipe.worker_roles
            or actor_business_role(world, npc, business) == "owner"
        ]
        workers = qualified_workers
    if not workers:
        business.operating_status = "understaffed"
        business.visible_status = "Hiring laborers."
        post_business_openings(world, business)
        return False
    if worker is not None and actor_business_role(world, worker, business) == "owner" and should_owner_delegate_low_labor(world, worker, business):
        business.visible_status = "Inspecting workers."
        return False

    village = getattr(world, "_get_village_for_npc", lambda *_args, **_kwargs: None)(workers[0], by_coords=True)
    moved = pull_missing_inputs(world, village, building, recipe.inputs)
    if moved:
        business.visible_status = "Delivering supplies."

    if not _inventory_has_inputs(building.building_inventory, recipe.inputs):
        business.current_shortages = {item_key for item_key, qty in recipe.inputs.items() if building.building_inventory.get(item_key, 0) < qty}
        business.operating_status = "stalled"
        business.visible_status = recipe.shortage_label
        business.demand_pressure = min(100, business.demand_pressure + 10)
        _update_village_supply_and_demand(village, {}, business.current_shortages)
        post_business_openings(world, business)
        return False

    business.current_shortages.clear()
    labor_units = max(1, len(workers))
    business.progress_ticks += labor_units
    business.operating_status = "operating"
    if not moved:
        business.visible_status = recipe.activity_label
    for npc in workers:
        if getattr(getattr(npc, "schedule", None), "current_task", None) is not None:
            npc.schedule.current_task = recipe.activity_label.lower().replace(" ", "_")

    if business.progress_ticks < recipe.duration_ticks:
        return True

    if not _consume_inputs(building.building_inventory, recipe.inputs):
        return False
    business.progress_ticks = 0
    _add_outputs(building.building_inventory, recipe.outputs, crafter_name=getattr(workers[0], "name", None))
    _update_village_supply_and_demand(village, recipe.outputs, set())
    business.completed_batches += 1
    business.demand_pressure = max(0, business.demand_pressure - 5)
    business.visible_status = f"Produced {', '.join(ITEM_DEFINITIONS.get(k, {}).get('name', k) for k in recipe.outputs) or 'service'}."
    return True


def sync_businesses_for_village(world, village: Village) -> list[Business]:
    businesses = []
    for building in village.buildings:
        if getattr(building, "building_type", None) in BUSINESS_TYPE_BY_BUILDING:
            business = create_business_for_building(world, building, getattr(building, "owner_id", None))
            sync_business_from_world(world, business)
            businesses.append(business)
    return businesses


def update_business_economic_needs(world, village: Village) -> None:
    if not hasattr(world, "town_board"):
        return
    for business in sync_businesses_for_village(world, village):
        for item_key in business.current_shortages:
            existing = next((n for n in world.town_board.economic_needs if n.settlement_id == village.id and n.type == "shortage" and n.target_key == item_key), None)
            if existing is None:
                world.town_board.economic_needs.append(TownEconomicNeed(
                    type="shortage",
                    target_key=item_key,
                    severity=max(30, business.demand_pressure),
                    settlement_id=village.id,
                    creation_tick=getattr(world, "game_time", 0),
                    description=f"{business.business_type.replace('_', ' ').title()} needs {ITEM_DEFINITIONS.get(item_key, {}).get('name', item_key)}.",
                ))
