"""Headless developer simulation scenarios and behavior trace helpers.

These helpers intentionally sit beside, rather than inside, the game engine.  The
sandbox drives existing world systems in controlled deterministic setups and
records state transitions as structured trace events for developer/agent review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import random
from pathlib import Path
from typing import Any, Callable

from tools.simulation_snapshot import SnapshotConfig, finalize_snapshot_artifacts, maybe_write_periodic_snapshot


@dataclass
class TraceEvent:
    tick: int
    event_type: str
    actor_id: int | None = None
    actor_name: str | None = None
    location: tuple[int, int] | None = None
    target: str | int | None = None
    success: bool | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tick": self.tick,
            "event_type": self.event_type,
        }
        if self.actor_id is not None:
            payload["actor_id"] = self.actor_id
        if self.actor_name is not None:
            payload["actor_name"] = self.actor_name
        if self.location is not None:
            payload["location"] = list(self.location)
        if self.target is not None:
            payload["target"] = self.target
        if self.success is not None:
            payload["success"] = self.success
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


@dataclass
class AssertionResult:
    name: str
    passed: bool
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name, "passed": self.passed}
        if self.reason:
            payload["reason"] = self.reason
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


class SimulationTrace:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []
        self.assertions: list[AssertionResult] = []

    def event(
        self,
        tick: int,
        event_type: str,
        *,
        actor: Any | None = None,
        actor_id: int | None = None,
        actor_name: str | None = None,
        location: tuple[int, int] | None = None,
        target: str | int | None = None,
        success: bool | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if actor is not None:
            actor_id = getattr(actor, "id", actor_id)
            actor_name = getattr(actor, "name", actor_name)
        self.events.append(
            TraceEvent(
                tick=tick,
                event_type=event_type,
                actor_id=actor_id,
                actor_name=actor_name,
                location=location,
                target=target,
                success=success,
                reason=reason,
                metadata=metadata or {},
            )
        )

    def assert_check(self, tick: int, name: str, passed: bool, reason: str = "", **metadata: Any) -> bool:
        self.assertions.append(AssertionResult(name=name, passed=passed, reason=reason, metadata=metadata))
        self.event(
            tick,
            "assertion_passed" if passed else "assertion_failed",
            success=passed,
            reason=reason or None,
            metadata={"name": name, **metadata},
        )
        return passed


@dataclass
class ScenarioResult:
    scenario: str
    seed: int
    ticks: int
    trace: SimulationTrace
    artifacts: dict[str, Any] = field(default_factory=dict)

    @property
    def result(self) -> str:
        return "PASS" if all(assertion.passed for assertion in self.trace.assertions) else "FAIL"

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "scenario": self.scenario,
            "seed": self.seed,
            "ticks": self.ticks,
            "result": self.result,
            "assertions": [assertion.to_dict() for assertion in self.trace.assertions],
            "events": [event.to_dict() for event in self.trace.events],
        }
        if self.artifacts:
            payload["artifacts"] = self.artifacts
        return payload

    def write_json(self, path: str | Path) -> None:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    def summary_text(self, *, max_key_events: int = 16) -> str:
        key_event_types = {
            "scenario_started",
            "construction_site_created",
            "construction_material_deposited",
            "construction_work_applied",
            "construction_completed",
            "claim_created",
            "claim_conflict",
            "delivery_created",
            "delivery_claimed",
            "delivery_pickup",
            "delivery_deposit",
            "delivery_completed",
            "path_assigned",
            "path_failed",
            "wildlife_manifested",
            "hunt_started",
            "prey_killed",
            "meat_deposited",
            "butcher_processed",
            "expansion_attempt",
            "valid_land_selected",
            "blueprint_placed",
            "scenario_completed",
        }
        lines = [
            f"SCENARIO: {self.scenario}",
            f"SEED: {self.seed}",
            f"TICKS: {self.ticks}",
            f"RESULT: {self.result}",
            "",
            "KEY EVENTS:",
        ]
        key_events = [event for event in self.trace.events if event.event_type in key_event_types]
        for event in key_events[:max_key_events]:
            description = event.event_type.replace("_", " ")
            if event.reason:
                description += f" ({event.reason})"
            lines.append(f"- tick {event.tick}: {description}")
        if len(key_events) > max_key_events:
            lines.append(f"- ... {len(key_events) - max_key_events} more key events")
        if not key_events:
            lines.append("- none")
        failures = [assertion for assertion in self.trace.assertions if not assertion.passed]
        lines.extend(["", "FAILURES:"])
        if failures:
            for assertion in failures:
                reason = f": {assertion.reason}" if assertion.reason else ""
                lines.append(f"- {assertion.name}{reason}")
        else:
            lines.append("- none")
        return "\n".join(lines)

    def write_log(self, path: str | Path) -> None:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.summary_text() + "\n", encoding="utf-8")


ScenarioCallable = Callable[[int, int, SnapshotConfig | None], ScenarioResult]


def _disable_llm_paths() -> None:
    import config
    import engine

    config.ENABLE_OLLAMA_CONNECTION = False
    config.ENABLE_LLM_CONNECTION = False
    engine.ENABLE_OLLAMA_CONNECTION = False
    engine.ENABLE_LLM_CONNECTION = False


def _make_plain_tile():
    from data.tiles import TILE_DEFINITIONS
    from tile_types import Tile

    plains = TILE_DEFINITIONS["plains"]
    return Tile(plains["char"], plains["color"], plains["passable"], plains["name"], properties={})


def _create_headless_world(seed: int):
    _disable_llm_paths()
    random.seed(seed)

    import engine
    from engine import Chunk, ChunkManager, World

    world = World(seed=seed)
    world.npcs = []
    world.village_npcs = []
    world.player.x = 1
    world.player.y = 1
    world.chunk_width = 1
    world.chunk_height = 1
    world.chunk_manager = ChunkManager(engine.CHUNK_SIZE, 1, 1)
    world.calculate_path = lambda sx, sy, ex, ey: [(sx, sy), (ex, ey)] if (sx, sy) != (ex, ey) else []
    world._is_chunk_active = lambda coords: True
    world._is_building_active = lambda building: True

    chunk = Chunk("plains")
    chunk.tiles = [[_make_plain_tile() for _ in range(engine.CHUNK_SIZE)] for _ in range(engine.CHUNK_SIZE)]
    chunk.is_generated = True
    chunk.is_terrain_generated = True
    chunk.allow_wildlife_population = True
    world.chunks = [[chunk]]
    return world, chunk


def _create_village(world, chunk, *, region=None, center: tuple[int, int] = (8, 8)):
    from simulation.world_model import Village

    village = Village(region_id=getattr(region, "id", None), chunk_coords=(0, 0))
    village.interaction_points = {"town_square_center": [center], "noticeboard": [center]}
    chunk.village = village
    world.atlas.add_village(village, chunk_coords=(0, 0), region=region)
    return village


def _add_building(world, village, x: int, y: int, width: int, height: int, building_type: str, category: str):
    from engine import Building

    building = Building(x, y, width, height, building_type=building_type, category=category)
    building.settlement_id = village.id
    building.region_id = getattr(village, "region_id", None)
    village.add_building(building)
    world.buildings_by_id[building.id] = building
    return building


def _move_actor_to_destination(npc, trace: SimulationTrace, tick: int) -> None:
    destination = getattr(getattr(npc, "schedule", None), "current_destination_coords", None)
    if destination is None:
        return
    if (npc.x, npc.y) == tuple(destination):
        return
    if getattr(npc.schedule, "current_path", None) is not None:
        npc.schedule.current_path = []
    npc.x, npc.y = int(destination[0]), int(destination[1])
    trace.event(tick, "path_assigned", actor=npc, location=(npc.x, npc.y), target=str(destination))


def _inventory_count(inventory, key: str) -> int:
    return int(inventory.get(key, 0)) if inventory is not None else 0


def run_construction_basic(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from data.construction import CONSTRUCTION_RECIPES
    from engine import ItemReference, NPC
    from entities.items import Inventory

    scenario = "construction_basic"
    trace = SimulationTrace()
    artifacts: dict[str, Any] = {}
    world, chunk = _create_headless_world(seed)
    village = _create_village(world, chunk)
    trace.event(0, "scenario_started", metadata={"scenario": scenario})

    owner = NPC(3, 3, name="Owner")
    owner.economic.money = 250
    worker = NPC(2, 2, name="Builder")
    worker.economic.profession = "Laborer"
    world.village_npcs.extend([owner, worker])

    blueprint = world.place_construction_blueprint("workshop", 12, 12, owner_id=owner.id, requester_id=owner.id, settlement_id=village.id)
    if blueprint is not None:
        trace.event(
            0,
            "construction_site_created",
            actor=owner,
            location=(blueprint.x, blueprint.y),
            target=blueprint.id,
            success=True,
            metadata={"target_build": blueprint.target_build, "required_materials": dict(blueprint.required_materials)},
        )
        if blueprint.territory_claim_id:
            trace.event(0, "claim_created", location=(blueprint.x, blueprint.y), target=blueprint.territory_claim_id, metadata={"claim_type": "construction_reservation"})
    else:
        trace.event(0, "construction_site_created", actor=owner, location=(12, 12), success=False, reason="place_construction_blueprint returned None")

    source = Inventory()
    if blueprint is not None:
        for item_key, quantity in blueprint.required_materials.items():
            for _ in range(quantity):
                source.add_item_reference(ItemReference(item_key))
    world.items_on_map[(2, 2)] = source

    completed_building = None
    last_delivered = 0
    last_progress = 0
    material_deposited = False
    work_applied = False
    completed = False

    for tick in range(1, ticks + 1):
        world.game_time = tick
        maybe_write_periodic_snapshot(world, trace, snapshot_config, scenario, tick, artifacts)
        if blueprint is None:
            continue
        active_blueprint = world.blueprints_by_id.get(blueprint.id)
        if active_blueprint is None:
            completed_building = next((b for b in world.buildings_by_id.values() if getattr(b, "requester_id", None) == owner.id and b.building_type == "workshop"), None)
            if completed_building is not None and not completed:
                completed = True
                trace.event(tick, "construction_completed", actor=worker, location=(completed_building.global_origin_x, completed_building.global_origin_y), target=completed_building.id, metadata={"building_type": completed_building.building_type})
            break

        before_delivered = sum(_inventory_count(active_blueprint.delivered_materials, item) for item in active_blueprint.required_materials)
        before_progress = active_blueprint.build_progress

        if active_blueprint.has_all_materials():
            if getattr(worker, "task_context", None) != "construction":
                assigned = world._assign_construction_task_to_npc(worker)
                if not assigned:
                    trace.event(tick, "path_failed", actor=worker, location=(worker.x, worker.y), target=active_blueprint.id, success=False, reason="could not assign construction task")
            _move_actor_to_destination(worker, trace, tick)
            world._handle_npc_construction_task(worker)
        else:
            if getattr(worker, "task_context", None) != "hauling":
                if not world._assign_haul_task_to_npc(worker):
                    trace.event(tick, "path_failed", actor=worker, location=(worker.x, worker.y), target=active_blueprint.id, success=False, reason="could not assign hauling task")
            _move_actor_to_destination(worker, trace, tick)
            world._handle_npc_hauling_task(worker)

        active_blueprint = world.blueprints_by_id.get(blueprint.id)
        if active_blueprint is None:
            continue
        delivered = sum(_inventory_count(active_blueprint.delivered_materials, item) for item in active_blueprint.required_materials)
        if delivered > before_delivered and delivered != last_delivered:
            material_deposited = True
            last_delivered = delivered
            trace.event(tick, "construction_material_deposited", actor=worker, location=(active_blueprint.x, active_blueprint.y), target=active_blueprint.id, metadata={"delivered_total": delivered})
        if active_blueprint.build_progress > before_progress and active_blueprint.build_progress != last_progress:
            work_applied = True
            last_progress = active_blueprint.build_progress
            trace.event(tick, "construction_work_applied", actor=worker, location=(active_blueprint.x, active_blueprint.y), target=active_blueprint.id, metadata={"build_progress": active_blueprint.build_progress, "stage": active_blueprint.construction_stage, "animation_cue": "build"})

    if completed_building is None and blueprint is not None:
        completed_building = next((b for b in world.buildings_by_id.values() if getattr(b, "requester_id", None) == owner.id and b.building_type == "workshop"), None)

    recipe = CONSTRUCTION_RECIPES["workshop"]
    trace.assert_check(ticks, "blueprint_created", blueprint is not None, "workshop blueprint should be created")
    trace.assert_check(ticks, "materials_delivered", bool(material_deposited), "at least one material should be physically deposited")
    trace.assert_check(ticks, "work_progress", bool(work_applied), "builder should apply work after materials arrive")
    trace.assert_check(ticks, "building_completed", completed_building is not None, "workshop should complete within the tick budget")
    trace.assert_check(
        ticks,
        "final_building_dimensions",
        completed_building is not None and completed_building.width == recipe["width"] and completed_building.height == recipe["height"],
        "completed workshop should preserve recipe dimensions",
        width=getattr(completed_building, "width", None),
        height=getattr(completed_building, "height", None),
    )
    completed_claim = world.land_claims_by_id.get(getattr(completed_building, "territory_claim_id", None)) if completed_building is not None else None
    trace.assert_check(
        ticks,
        "owner_settlement_claim_variant_preserved",
        completed_building is not None
        and completed_building.owner_id == owner.id
        and completed_building.requester_id == owner.id
        and completed_building.settlement_id == village.id
        and getattr(completed_building, "territory_claim_id", None) is not None
        and completed_claim is not None
        and completed_claim.owner_id == completed_building.id
        and getattr(completed_building, "variant_id", None) == getattr(blueprint, "variant_id", None),
        "completed building should keep owner/requester/settlement/claim/variant fields",
        owner_id=getattr(completed_building, "owner_id", None),
        settlement_id=getattr(completed_building, "settlement_id", None),
        territory_claim_id=getattr(completed_building, "territory_claim_id", None),
        claim_owner_id=getattr(completed_claim, "owner_id", None),
        blueprint_variant_id=getattr(blueprint, "variant_id", None),
        building_variant_id=getattr(completed_building, "variant_id", None),
    )
    overlap_safe = False
    chunk_safe = False
    if completed_building is not None:
        footprint = world._claim_rect_tiles(completed_building.global_origin_x, completed_building.global_origin_y, completed_building.width, completed_building.height)
        other_buildings = [b for b in village.buildings if b.id != completed_building.id]
        overlap_safe = not any(
            completed_building.global_origin_x < b.global_origin_x + b.width
            and completed_building.global_origin_x + completed_building.width > b.global_origin_x
            and completed_building.global_origin_y < b.global_origin_y + b.height
            and completed_building.global_origin_y + completed_building.height > b.global_origin_y
            for b in other_buildings
        )
        chunk_x = completed_building.global_origin_x // __import__("engine").CHUNK_SIZE
        chunk_y = completed_building.global_origin_y // __import__("engine").CHUNK_SIZE
        chunk_safe = all(tx // __import__("engine").CHUNK_SIZE == chunk_x and ty // __import__("engine").CHUNK_SIZE == chunk_y for tx, ty in footprint)
    trace.assert_check(ticks, "overlap_safety", overlap_safe, "completed building should not overlap another village building")
    trace.assert_check(ticks, "chunk_boundary_safety", chunk_safe, "completed building footprint should stay in one chunk")
    trace.event(ticks, "scenario_completed", success=all(assertion.passed for assertion in trace.assertions))
    finalize_snapshot_artifacts(world, trace, snapshot_config, scenario, ticks, artifacts)
    return ScenarioResult(scenario, seed, ticks, trace, artifacts)


def run_delivery_basic(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from engine import ItemReference, NPC

    scenario = "delivery_basic"
    trace = SimulationTrace()
    artifacts: dict[str, Any] = {}
    world, chunk = _create_headless_world(seed)
    village = _create_village(world, chunk)
    trace.event(0, "scenario_started", metadata={"scenario": scenario})

    source = _add_building(world, village, 10, 10, 5, 5, "general_store", "commercial_workplace")
    dest = _add_building(world, village, 0, 0, 5, 5, "blacksmith_shop", "commercial_workplace")
    dest.building_inventory["money"] = 100
    source.building_inventory.add_item_reference(ItemReference("iron_ore"))

    laborer = NPC(5, 5, name="Delivery Laborer")
    laborer.economic.profession = "Laborer"
    world.village_npcs.append(laborer)

    task = world.town_board.post_delivery_task(source.id, dest.id, "iron_ore", 1, world.game_time)
    trace.event(0, "delivery_created", location=(source.global_center_x, source.global_center_y), target=task.id, metadata={"item_key": "iron_ore"})
    initial_source = source.building_inventory.get("iron_ore", 0)
    initial_dest = dest.building_inventory.get("iron_ore", 0)
    source_unchanged_before_pickup = True
    dest_unchanged_before_dropoff = True
    claimed = picked_up = carrying = deposited = completed = False

    for tick in range(1, ticks + 1):
        world.game_time = tick
        maybe_write_periodic_snapshot(world, trace, snapshot_config, scenario, tick, artifacts)
        if getattr(laborer, "task_context", None) is None and world.town_board.get_delivery_task(task.id):
            if world._assign_delivery_task_to_npc(laborer):
                claimed = True
                trace.event(tick, "delivery_claimed", actor=laborer, target=task.id)
        current_task = world.town_board.get_delivery_task(task.id)
        if current_task is None:
            completed = True
            trace.event(tick, "delivery_completed", actor=laborer, target=task.id)
            break
        if not picked_up:
            source_unchanged_before_pickup = source_unchanged_before_pickup and source.building_inventory.get("iron_ore", 0) == initial_source
            dest_unchanged_before_dropoff = dest_unchanged_before_dropoff and dest.building_inventory.get("iron_ore", 0) == initial_dest
        _move_actor_to_destination(laborer, trace, tick)
        before_source = source.building_inventory.get("iron_ore", 0)
        before_dest = dest.building_inventory.get("iron_ore", 0)
        before_carried = laborer.economic.npc_inventory.get("iron_ore", 0)
        world._handle_npc_delivery_task(laborer)
        after_source = source.building_inventory.get("iron_ore", 0)
        after_dest = dest.building_inventory.get("iron_ore", 0)
        after_carried = laborer.economic.npc_inventory.get("iron_ore", 0)
        if after_source < before_source and after_carried > before_carried:
            picked_up = True
            carrying = True
            trace.event(tick, "delivery_pickup", actor=laborer, location=(laborer.x, laborer.y), target=task.id, metadata={"source_inventory": after_source, "carrying": after_carried, "animation_cue": "haul_carry"})
        if after_dest > before_dest:
            deposited = True
            trace.event(tick, "delivery_deposit", actor=laborer, location=(laborer.x, laborer.y), target=task.id, metadata={"destination_inventory": after_dest})

    trace.assert_check(ticks, "task_opened", task is not None, "delivery task should be posted")
    trace.assert_check(ticks, "task_claimed", claimed, "laborer should claim delivery task")
    trace.assert_check(ticks, "source_pickup", picked_up, "laborer should pick up source goods")
    trace.assert_check(ticks, "carrying_state", carrying, "laborer should carry goods after pickup")
    trace.assert_check(ticks, "destination_deposit", deposited, "laborer should deposit goods at destination")
    trace.assert_check(ticks, "completion", completed or world.town_board.get_delivery_task(task.id) is None, "delivery task should complete")
    trace.assert_check(
        ticks,
        "inventory_changes_at_correct_moments",
        source_unchanged_before_pickup and dest_unchanged_before_dropoff and source.building_inventory.get("iron_ore", 0) == 0 and dest.building_inventory.get("iron_ore", 0) == 1,
        "source should change only on pickup and destination only on deposit",
        source_inventory=source.building_inventory.get("iron_ore", 0),
        destination_inventory=dest.building_inventory.get("iron_ore", 0),
    )
    trace.event(ticks, "scenario_completed", success=all(assertion.passed for assertion in trace.assertions))
    finalize_snapshot_artifacts(world, trace, snapshot_config, scenario, ticks, artifacts)
    return ScenarioResult(scenario, seed, ticks, trace, artifacts)


def run_hunting_food_chain(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from engine import NPC

    scenario = "hunting_food_chain"
    trace = SimulationTrace()
    artifacts: dict[str, Any] = {}
    world, chunk = _create_headless_world(seed)
    region = world.atlas.create_region("Sandbox Hunting Grounds", "plains")
    world.atlas.assign_chunk_to_region(0, 0, region)
    chunk.region_id = region.id
    village = _create_village(world, chunk, region=region)
    trace.event(0, "scenario_started", metadata={"scenario": scenario})

    butcher = _add_building(world, village, 4, 4, 6, 6, "butcher_shop", "food_workplace")
    hunter = NPC(10, 10, name="Sandbox Hunter")
    hunter.economic.profession = "Hunter"
    hunter.schedule.work_building_id = butcher.id
    world.village_npcs.append(hunter)

    populations = world.ecology.get_region_populations(world, region.id)
    for species_key, population in populations.items():
        if species_key != "deer":
            population.population_count = 0
            population.refresh_pressure()
    population = populations["deer"]
    population.population_count = 20
    population.carrying_capacity = 30
    population.visible_entity_ids.clear()
    population.refresh_pressure()
    deer = world._manifest_wildlife_entity("deer", 11, 10, region.id, f"{region.id}:deer")
    trace.event(0, "wildlife_manifested", location=(getattr(deer, "x", 0), getattr(deer, "y", 0)), target=getattr(deer, "id", None), metadata={"species": "deer", "population": population.population_count})

    selected = world._find_reachable_hunting_prey(hunter, search_radius=20)
    assigned = False
    prey_killed = False
    ecology_reduced_once = False
    meat_carried = False
    meat_deposited = False
    butcher_processed = False
    before_population = population.population_count

    for tick in range(1, ticks + 1):
        world.game_time = tick
        maybe_write_periodic_snapshot(world, trace, snapshot_config, scenario, tick, artifacts)
        if not assigned:
            assigned = world._assign_hunting_task_to_npc(hunter)
            if assigned:
                trace.event(tick, "hunt_started", actor=hunter, location=(hunter.x, hunter.y), target=getattr(deer, "id", None), metadata={"selected_prey_id": getattr(selected, "id", None)})
        if not assigned:
            continue
        if hunter.task_context_data and hunter.task_context_data.get("state") == "returning":
            _move_actor_to_destination(hunter, trace, tick)
        before_meat = hunter.economic.npc_inventory.get("raw_venison", 0)
        before_processed = butcher.building_inventory.get("processed_meat", 0)
        world._handle_npc_hunting_task(hunter)
        after_meat = hunter.economic.npc_inventory.get("raw_venison", 0)
        after_processed = butcher.building_inventory.get("processed_meat", 0)
        if deer is not None and deer.physical.is_dead and not prey_killed:
            prey_killed = True
            trace.event(tick, "prey_killed", actor=hunter, location=(deer.x, deer.y), target=deer.id, metadata={"population_before": before_population, "population_after": population.population_count, "animation_cue": "attack_lunge"})
        if population.population_count == before_population - 1:
            ecology_reduced_once = True
        if after_meat > before_meat:
            meat_carried = True
            trace.event(tick, "delivery_pickup", actor=hunter, location=(hunter.x, hunter.y), target=getattr(deer, "id", None), metadata={"item_key": "raw_venison", "animation_cue": "haul_carry"})
        if after_processed > before_processed:
            meat_deposited = True
            butcher_processed = True
            trace.event(tick, "meat_deposited", actor=hunter, location=(butcher.global_center_x, butcher.global_center_y), target=butcher.id)
            trace.event(tick, "butcher_processed", location=(butcher.global_center_x, butcher.global_center_y), target=butcher.id, metadata={"processed_meat": after_processed, "animation_cue": "butcher_work"})
            break

    trace.assert_check(ticks, "wildlife_manifested", deer is not None, "visible deer should manifest from regional population")
    trace.assert_check(ticks, "hunter_selected_reachable_prey", selected is deer, "hunter should select reachable deer")
    trace.assert_check(ticks, "prey_killed", prey_killed, "hunter should kill selected prey")
    trace.assert_check(ticks, "ecology_population_reduced_once", ecology_reduced_once and population.population_count == before_population - 1, "regional population should decrease exactly once", before=before_population, after=population.population_count)
    trace.assert_check(ticks, "meat_carried", meat_carried, "hunter should carry raw venison")
    trace.assert_check(ticks, "meat_deposited", meat_deposited, "hunter should deposit meat at butcher/storage")
    trace.assert_check(ticks, "butcher_processed", butcher_processed, "butcher workplace should process raw meat when supported")
    trace.event(ticks, "scenario_completed", success=all(assertion.passed for assertion in trace.assertions))
    finalize_snapshot_artifacts(world, trace, snapshot_config, scenario, ticks, artifacts)
    return ScenarioResult(scenario, seed, ticks, trace, artifacts)


def run_settlement_growth(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from types import SimpleNamespace

    scenario = "settlement_growth"
    trace = SimulationTrace()
    artifacts: dict[str, Any] = {}
    world, chunk = _create_headless_world(seed)
    village = _create_village(world, chunk, center=(15, 15))
    trace.event(0, "scenario_started", metadata={"scenario": scenario})

    house = _add_building(world, village, 10, 10, 7, 7, "house", "residential")
    house.residents = [SimpleNamespace(id="resident_a"), SimpleNamespace(id="resident_b")]
    before_claim_ids = set(world.land_claims_by_id.keys())
    before_blueprints = set(world.blueprints_by_id.keys())

    attempted = False
    for tick in range(1, ticks + 1):
        world.game_time = tick
        maybe_write_periodic_snapshot(world, trace, snapshot_config, scenario, tick, artifacts)
        if not attempted:
            trace.event(tick, "expansion_attempt", location=(15, 15), metadata={"pressure": world._calculate_settlement_expansion_pressure(village)})
            world._plan_village_expansion(village)
            attempted = True
        new_blueprints = [bp for bp_id, bp in world.blueprints_by_id.items() if bp_id not in before_blueprints]
        if new_blueprints:
            blueprint = new_blueprints[0]
            trace.event(tick, "valid_land_selected", location=(blueprint.x, blueprint.y), target=blueprint.id)
            trace.event(tick, "blueprint_placed", location=(blueprint.x, blueprint.y), target=blueprint.id, metadata={"target_build": blueprint.target_build})
            if blueprint.territory_claim_id and blueprint.territory_claim_id not in before_claim_ids:
                trace.event(tick, "claim_created", location=(blueprint.x, blueprint.y), target=blueprint.territory_claim_id, metadata={"claim_type": "construction_reservation"})
            break

    new_blueprints = [bp for bp_id, bp in world.blueprints_by_id.items() if bp_id not in before_blueprints]
    blueprint = new_blueprints[0] if new_blueprints else None
    claim = world.land_claims_by_id.get(getattr(blueprint, "territory_claim_id", None)) if blueprint is not None else None
    no_overlap = False
    if blueprint is not None:
        no_overlap = not any(
            blueprint.x < b.global_origin_x + b.width
            and blueprint.x + blueprint.width > b.global_origin_x
            and blueprint.y < b.global_origin_y + b.height
            and blueprint.y + blueprint.height > b.global_origin_y
            for b in village.buildings
        )
    no_orphan_claim = claim is not None and claim.owner_id == getattr(blueprint, "id", None) and claim.settlement_id == village.id

    trace.assert_check(ticks, "expansion_attempt", attempted, "settlement growth should attempt expansion")
    trace.assert_check(ticks, "valid_land_selected", blueprint is not None, "planner should find valid land under housing pressure")
    trace.assert_check(ticks, "land_claim_created", claim is not None, "blueprint should reserve a land claim")
    trace.assert_check(ticks, "blueprint_placed", blueprint is not None, "growth should place a construction blueprint")
    trace.assert_check(ticks, "no_overlap", no_overlap, "new blueprint should not overlap existing buildings")
    trace.assert_check(ticks, "no_orphan_claim", no_orphan_claim, "construction claim should point back to the blueprint and settlement")
    trace.event(ticks, "scenario_completed", success=all(assertion.passed for assertion in trace.assertions))
    finalize_snapshot_artifacts(world, trace, snapshot_config, scenario, ticks, artifacts)
    return ScenarioResult(scenario, seed, ticks, trace, artifacts)


def run_interaction_parity_basic(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from engine import NPC
    from simulation.systems.interaction import ActionIntent, InteractionResolver
    from tile_types import Tile

    scenario = "interaction_parity_basic"
    trace = SimulationTrace()
    artifacts: dict[str, Any] = {}
    world, chunk = _create_headless_world(seed)
    trace.event(0, "scenario_started", metadata={"scenario": scenario})

    world.interaction_resolver = InteractionResolver()

    player = NPC(10, 10, name="Sandbox Player")
    world.player = player
    world.npcs.append(player)

    npc = NPC(10, 10, name="Sandbox NPC")
    world.npcs.append(npc)

    # Test 1: open_door parity
    from data.decorations import DECORATION_ITEM_DEFINITIONS
    door_def = DECORATION_ITEM_DEFINITIONS.get("wooden_door_closed", {})
    if not door_def:
        door_def = {"char": "+", "color": (100,100,100), "passable": False, "name": "door", "properties": {"is_door": True, "opens_to": "wooden_door_open"}}

    chunk.tiles[10][11] = Tile(
        char=door_def["char"], color=door_def["color"], passable=door_def.get("passable", False),
        name=door_def.get("name", "door"), properties=door_def.get("properties", {"is_door": True, "opens_to": "wooden_door_open"})
    )

    # Player opens door
    p_intent = ActionIntent(actor_id=player.id, action_type="open_door", target_pos=(11, 10), source="player")
    p_res = world.interaction_resolver.resolve(p_intent, world)
    trace.assert_check(1, "player_open_door", p_res.success, "Player should be able to open door")

    # Reset door
    chunk.tiles[10][11] = Tile(
        char=door_def["char"], color=door_def["color"], passable=door_def.get("passable", False),
        name=door_def.get("name", "door"), properties=door_def.get("properties", {"is_door": True, "opens_to": "wooden_door_open"})
    )

    # NPC opens door
    n_intent = ActionIntent(actor_id=npc.id, action_type="open_door", target_pos=(11, 10), source="npc")
    n_res = world.interaction_resolver.resolve(n_intent, world)
    trace.assert_check(2, "npc_open_door", n_res.success, "NPC should be able to open door")

    # Check traces/cues are identical
    trace.assert_check(2, "open_door_parity_cues", p_res.cues_to_fire == n_res.cues_to_fire, "Player and NPC should emit identical cues")

    p_trace_types = [t[0] for t in p_res.traces_to_log]
    n_trace_types = [t[0] for t in n_res.traces_to_log]
    trace.assert_check(2, "open_door_parity_traces", p_trace_types == n_trace_types, "Player and NPC should emit identical traces")

    # Test 2: chop_tree lifecycle and cancellation
    tree_def = DECORATION_ITEM_DEFINITIONS.get("tree", {})
    if not tree_def:
        tree_def = {"char": "T", "color": (0,255,0), "passable": False, "name": "tree", "properties": {"is_tree": True}}

    chunk.tiles[11][10] = Tile(
        char=tree_def["char"], color=tree_def["color"], passable=tree_def.get("passable", False),
        name=tree_def.get("name", "tree"), properties=tree_def.get("properties", {"is_tree": True})
    )

    chop_intent = ActionIntent(actor_id=player.id, action_type="chop_tree", target_pos=(10, 11), source="player")
    chop_res = world.interaction_resolver.resolve(chop_intent, world)
    trace.assert_check(3, "start_chop_tree", chop_res.success, "Should start chopping tree")

    if chop_res.success and chop_res.started_interaction_id:
        iid = chop_res.started_interaction_id
        adv_res = world.interaction_resolver.advance_active_interaction(iid, world)
        trace.assert_check(4, "advance_chop_tree", adv_res and adv_res.success, "Should advance tree chopping")

        # Remove tree
        chunk.tiles[11][10] = Tile(char=".", color=(0,0,0), passable=True, name="ground", properties={})

        cancel_res = world.interaction_resolver.advance_active_interaction(iid, world)
        trace.assert_check(5, "cancel_chop_tree", not cancel_res.success and cancel_res.reason == "cannot_continue", "Should cleanly cancel when tree is gone")

    trace.event(ticks, "scenario_completed", success=all(assertion.passed for assertion in trace.assertions))
    return ScenarioResult(scenario, seed, ticks, trace, artifacts)


SCENARIOS: dict[str, ScenarioCallable] = {
    "construction_basic": run_construction_basic,
    "delivery_basic": run_delivery_basic,
    "hunting_food_chain": run_hunting_food_chain,
    "settlement_growth": run_settlement_growth,
    "interaction_parity_basic": run_interaction_parity_basic,
}


def run_scenario(name: str, *, seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    try:
        scenario = SCENARIOS[name]
    except KeyError as exc:
        available = ", ".join(sorted(SCENARIOS))
        raise ValueError(f"Unknown scenario '{name}'. Available scenarios: {available}") from exc
    return scenario(seed, ticks, snapshot_config)
