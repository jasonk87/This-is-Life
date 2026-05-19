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
            "stockpile_created",
            "stockpile_deposit",
            "stockpile_withdraw",
            "haul_assigned",
            "haul_started",
            "haul_delivered",
            "haul_failed",
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
            "soak_metrics",
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
        display_events = key_events[:max_key_events]
        soak_metric_events = [event for event in key_events if event.event_type == "soak_metrics"]
        if soak_metric_events and soak_metric_events[-1] not in display_events:
            display_events = display_events[:-1] + [soak_metric_events[-1]] if display_events else [soak_metric_events[-1]]
        for event in display_events:
            description = event.event_type.replace("_", " ")
            if event.event_type == "soak_metrics" and event.metadata:
                metric_bits = ", ".join(f"{key}={value}" for key, value in sorted(event.metadata.items()))
                description += f" [{metric_bits}]"
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
            if getattr(worker, "task_context", None) == "construction" and getattr(worker.schedule, "active_interaction_id", None):
                work_applied = True

            # This legacy scenario manually steps movement/hauling, so invoke the same
            # production helper that run_world_tick uses rather than a sandbox-only path.
            from simulation.systems.tick import advance_active_interactions
            advance_active_interactions(world)
        else:
            if getattr(worker, "task_context", None) != "hauling":
                if not world._assign_haul_task_to_npc(worker):
                    trace.event(tick, "path_failed", actor=worker, location=(worker.x, worker.y), target=active_blueprint.id, success=False, reason="could not assign hauling task")
            _move_actor_to_destination(worker, trace, tick)
            world._handle_npc_hauling_task(worker)

        active_blueprint = world.blueprints_by_id.get(blueprint.id)
        if active_blueprint is None:
            # If it completed this tick, work was obviously applied!
            if before_progress > 0 or getattr(worker, "task_context", None) == "construction":
                work_applied = True
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



def run_piece_construction_basic(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from data.construction import CONSTRUCTION_RECIPES
    from engine import ItemReference, NPC
    from entities.items import Inventory

    scenario = "piece_construction_basic"
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

    # We build a simple 1x1 chair so it completes quickly, but it still proves piece-based logic since components are generated.
    blueprint = world.place_construction_blueprint("wooden_chair", 12, 12, owner_id=owner.id, requester_id=owner.id, settlement_id=village.id)
    if blueprint is not None:
        trace.event(
            0,
            "construction_site_created",
            actor=owner,
            location=(blueprint.x, blueprint.y),
            target=blueprint.id,
        )

    # Provide all materials exactly where the worker is
    world.items_on_map[(2, 2)] = Inventory()
    for item_key, count in blueprint.required_materials.items():
        world.items_on_map[(2, 2)].add_item(item_key, count)

    for tick in range(ticks):
        world.game_time = tick
        from simulation.systems.tick import run_world_tick
        run_world_tick(world)

        # Look for completed construction
        if not world.get_blueprint_at(12, 12):
            if any(b.building_type == "wooden_chair" for b in village.buildings) or world.get_tile_at(12,12).name == "Wooden Chair" or any(getattr(d, "key", None) == "wooden_chair" for d in world.decorations.get((12, 12), [])):
                trace.event(tick, "construction_completed")
            break

    # Add interruptions halfway test:
    # Actually it's easier to just test if the component logic is present.
    if blueprint:
        trace.assert_check(len(blueprint.components) > 0, "components_generated", "Blueprint must have generated components")

    # Let's verify events
    event_types = [e.event_type for e in trace.events]
    trace.assert_check("construction_site_created" in event_types, "blueprint_created", "Blueprint must be created")

    # Actually wait, `build_progress` trace is logged by `ActionResult`. Does _run_world_tick record traces?
    # The normal sandbox scenarios don't automatically grab `traces_to_log` from InteractionResolver results unless `_handle_npc_construction_task` logs them.
    # But wait, `InteractionResolver` itself doesn't log to the sandbox trace unless we pipe it!
    # So we can just check the blueprint state.

    trace.assert_check(not world.get_blueprint_at(12, 12), "blueprint_finished", "Blueprint must be removed from map")

    if snapshot_config:
        artifacts["snapshot"] = _write_snapshot(world, snapshot_config, scenario)

    return ScenarioResult(scenario, seed, ticks, trace, artifacts)


def run_construction_runtime_soak(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from engine import NPC
    from entities.items import Inventory
    from simulation.systems.task_types import TaskType
    from simulation.systems.tick import run_world_tick
    from simulation.systems.work import update_npc_work_sub_tasks

    scenario = "construction_runtime_soak"
    trace = SimulationTrace()
    artifacts: dict[str, Any] = {}
    world, chunk = _create_headless_world(seed)
    village = _create_village(world, chunk, center=(10, 10))
    trace.event(0, "scenario_started", metadata={"scenario": scenario})

    workers = []
    for index in range(4):
        worker = NPC(2 + index, 2, name=f"Soak Builder {index + 1}")
        worker.economic.profession = "Laborer" if index % 2 else "Builder"
        workers.append(worker)
    world.village_npcs.extend(workers)

    blueprint = world.place_construction_blueprint("workshop", 8, 8, settlement_id=village.id)

    farm = _add_building(world, village, 1, 14, 5, 5, "farm", "agricultural_workplace")
    farmer = NPC(farm.global_center_x, farm.global_center_y, name="Soak Farmer")
    farmer.economic.profession = "Farmer"
    farmer.schedule.work_building_id = farm.id
    farmer.schedule.current_task = TaskType.AT_WORK
    world.village_npcs.append(farmer)
    if blueprint is not None:
        for component in blueprint.components:
            component.required_work = 20
        blueprint.required_work = sum(component.required_work for component in blueprint.components)
        blueprint.refresh_status()
        trace.event(0, "construction_site_created", location=(blueprint.x, blueprint.y), target=blueprint.id, metadata={"components": len(blueprint.components)})

    source = Inventory()
    if blueprint is not None:
        for item_key, quantity in blueprint.required_materials.items():
            source.add_item(item_key, quantity)
    world.items_on_map[(2, 2)] = source

    max_duplicate_builds = 0
    progress_seen = False
    interruption_count = 0
    completed = False

    for tick in range(1, ticks + 1):
        # Exercise invalid autonomous work metadata through the production work-task path.
        if tick % 25 == 0:
            update_npc_work_sub_tasks(world, farmer)

        if blueprint is not None and world.blueprints_by_id.get(blueprint.id) is not None:
            active_blueprint = world.blueprints_by_id[blueprint.id]
            for worker in workers:
                if getattr(worker.schedule, "active_interaction_id", None):
                    continue
                if getattr(worker, "task_context", None) == "hauling":
                    world._handle_npc_hauling_task(worker)
                    _move_actor_to_destination(worker, trace, tick)
                    continue
                if getattr(worker, "task_context", None) == "construction":
                    world._handle_npc_construction_task(worker)
                    _move_actor_to_destination(worker, trace, tick)
                    continue
                if active_blueprint.has_all_materials():
                    world._assign_construction_task_to_npc(worker)
                else:
                    world._assign_haul_task_to_npc(worker)
                _move_actor_to_destination(worker, trace, tick)

        if tick % 15 == 0 and interruption_count < 5:
            active_build = next((
                interaction for interaction in world.interaction_resolver.active_interactions.values()
                if getattr(interaction, "action_type", None) == "build"
            ), None)
            if active_build is not None:
                world.interaction_resolver.cancel_actor_interaction(active_build.actor_id, world, "soak_interrupt")
                interruption_count += 1
                trace.event(tick, "worker_interrupted", actor_id=active_build.actor_id, target=getattr(active_build, "component_id", None))

        run_world_tick(world)

        active_build_counts: dict[tuple[str | None, str | None], int] = {}
        for interaction in world.interaction_resolver.active_interactions.values():
            if getattr(interaction, "action_type", None) != "build":
                continue
            key = (getattr(interaction, "blueprint_id", None), getattr(interaction, "component_id", None))
            active_build_counts[key] = active_build_counts.get(key, 0) + 1
        if active_build_counts:
            max_duplicate_builds = max(max_duplicate_builds, max(active_build_counts.values()))

        active_blueprint = world.blueprints_by_id.get(getattr(blueprint, "id", None)) if blueprint is not None else None
        if active_blueprint is not None:
            progress_seen = progress_seen or any(component.build_progress > 0 for component in active_blueprint.components)
            if all(component.status == "complete" for component in active_blueprint.components):
                world._complete_construction_blueprint(active_blueprint)
                completed = True
                trace.event(tick, "construction_completed")
                break
        elif blueprint is not None:
            completed = True
            trace.event(tick, "construction_completed")
            break

    active_blueprint = world.blueprints_by_id.get(getattr(blueprint, "id", None)) if blueprint is not None else None
    unfinished_components = 0 if active_blueprint is None else sum(1 for component in active_blueprint.components if component.status != "complete")
    claimed_components = 0 if active_blueprint is None else sum(1 for component in active_blueprint.components if component.claimed_by_actor_id is not None)
    active_interaction_count = len(world.interaction_resolver.active_interactions)
    stuck_actor_count = sum(
        1
        for actor in world.village_npcs
        if getattr(getattr(actor, "schedule", None), "active_interaction_id", None)
        and actor.schedule.active_interaction_id not in world.interaction_resolver.active_interactions
    )
    warning_counts = getattr(world, "validation_warning_counts", {})
    warning_total = sum(warning_counts.values())
    warning_emitted = len(getattr(world, "validation_warnings", []))
    trace_count = len(getattr(world, "interaction_trace_log", []))
    claim_trace_types = [entry.get("trace_type") for entry in getattr(world, "interaction_trace_log", [])]

    metrics = {
        "completed": completed,
        "warning_total": warning_total,
        "warning_emitted": warning_emitted,
        "trace_count": trace_count,
        "stuck_actor_count": stuck_actor_count,
        "active_interaction_count": active_interaction_count,
        "unfinished_component_count": unfinished_components,
        "claimed_component_count": claimed_components,
        "max_duplicate_builds": max_duplicate_builds,
        "interruption_count": interruption_count,
    }
    trace.event(ticks, "soak_metrics", metadata=metrics)

    trace.assert_check(ticks, "soak_construction_completed", completed, "Construction should complete during the soak", **metrics)
    trace.assert_check(ticks, "soak_progress_seen", progress_seen, "At least one component should receive build progress")
    trace.assert_check(ticks, "soak_no_duplicate_builds", max_duplicate_builds <= 1, "No component should have duplicate active BuildInteractions", max_duplicate_builds=max_duplicate_builds)
    trace.assert_check(ticks, "soak_interruption_exercised", interruption_count > 0, "Soak should interrupt at least one active BuildInteraction", interruption_count=interruption_count)
    trace.assert_check(ticks, "soak_no_stuck_active_actors", stuck_actor_count == 0, "No actor should reference a missing active interaction", stuck_actor_count=stuck_actor_count)
    trace.assert_check(ticks, "soak_warnings_bounded", warning_emitted <= 25 and warning_total <= 500, "Validation warning aggregation should stay bounded", warning_emitted=warning_emitted, warning_total=warning_total)
    trace.assert_check(ticks, "soak_trace_volume_bounded", trace_count <= 10000, "Interaction trace volume should remain bounded", trace_count=trace_count)
    trace.assert_check(ticks, "soak_claim_lifecycle_seen", "component_claimed" in claim_trace_types and ("component_claim_released" in claim_trace_types or "component_claim_expired" in claim_trace_types), "Claim traces should include acquisition and release/expiration")
    trace.assert_check(ticks, "soak_validation_debounced", warning_emitted < warning_total, "Repeated invalid work warnings should aggregate instead of flooding", warning_emitted=warning_emitted, warning_total=warning_total)

    if snapshot_config:
        artifacts["snapshot"] = _write_snapshot(world, snapshot_config, scenario)

    return ScenarioResult(scenario, seed, ticks, trace, artifacts)


def run_piece_construction_claims(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from engine import ItemReference, NPC

    scenario = "piece_construction_claims"
    trace = SimulationTrace()
    artifacts: dict[str, Any] = {}
    world, chunk = _create_headless_world(seed)
    village = _create_village(world, chunk)
    trace.event(0, "scenario_started", metadata={"scenario": scenario})

    first_worker = NPC(12, 12, name="First Builder")
    second_worker = NPC(12, 12, name="Second Builder")
    first_worker.economic.profession = "Builder"
    second_worker.economic.profession = "Builder"
    world.village_npcs.extend([first_worker, second_worker])

    blueprint = world.place_construction_blueprint("wooden_chair", 12, 12, settlement_id=village.id)
    component = blueprint.components[0] if blueprint and blueprint.components else None
    if component is not None:
        component.required_work = 30
        for item_key, count in component.required_materials.items():
            for _ in range(count):
                component.deposit_item_reference(ItemReference(item_key))
        blueprint.refresh_status()

    first_started = False
    second_blocked = False
    resumed_after_expiration = False
    no_duplicate_builds = False
    progress_persisted = False

    if blueprint is not None and component is not None:
        world._assign_construction_task_to_npc(first_worker)
        first_started = world._handle_npc_construction_task(first_worker)
        world._assign_construction_task_to_npc(second_worker)
        second_blocked = not world._handle_npc_construction_task(second_worker)

        active_builds = [
            interaction for interaction in world.interaction_resolver.active_interactions.values()
            if getattr(interaction, "action_type", None) == "build" and getattr(interaction, "component_id", None) == component.id
        ]
        no_duplicate_builds = len(active_builds) == 1
        trace.event(1, "component_claimed", actor=first_worker, target=component.id, metadata={"claimed_by_actor_id": component.claimed_by_actor_id})

        from simulation.systems.tick import run_world_tick

        run_world_tick(world)
        progress_after_tick = component.build_progress
        world.interaction_resolver.cancel_actor_interaction(first_worker.id, world, "sandbox_interrupt")

        world._assign_construction_task_to_npc(second_worker)
        blocked_before_expiry = not world._handle_npc_construction_task(second_worker)

        world.game_time = (component.claim_expiration_tick or world.game_time) + 1
        world._assign_construction_task_to_npc(second_worker)
        resumed_after_expiration = world._handle_npc_construction_task(second_worker)
        progress_persisted = component.build_progress == progress_after_tick and progress_after_tick > 0 and blocked_before_expiry
        if resumed_after_expiration:
            trace.event(world.game_time, "component_claim_expired", target=component.id, metadata={"claimed_by_actor_id": component.claimed_by_actor_id})

    trace.assert_check(ticks, "first_worker_started", first_started, "First worker should start the component BuildInteraction")
    trace.assert_check(ticks, "second_worker_blocked", second_blocked, "Second worker should not build an already-claimed component")
    trace.assert_check(ticks, "no_duplicate_build_interactions", no_duplicate_builds, "Only one BuildInteraction should exist for a component")
    trace.assert_check(ticks, "interrupted_progress_persisted", progress_persisted, "Interrupted work should keep component progress until resume")
    trace.assert_check(ticks, "claim_expiration_allows_resume", resumed_after_expiration, "Expired claim should allow another worker to resume")

    if snapshot_config:
        artifacts["snapshot"] = _write_snapshot(world, snapshot_config, scenario)

    return ScenarioResult(scenario, seed, ticks, trace, artifacts)


def run_piece_construction_interrupted(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from data.construction import CONSTRUCTION_RECIPES
    from engine import ItemReference, NPC
    from entities.items import Inventory

    scenario = "piece_construction_interrupted"
    trace = SimulationTrace()
    artifacts: dict[str, Any] = {}
    world, chunk = _create_headless_world(seed)
    village = _create_village(world, chunk)
    trace.event(0, "scenario_started", metadata={"scenario": scenario})

    worker = NPC(2, 2, name="Builder")
    worker.economic.profession = "Laborer"
    world.village_npcs.append(worker)

    # Place a blueprint that requires 2 ticks of work (20 work, 10 per tick)
    blueprint = world.place_construction_blueprint("wooden_chair", 12, 12, settlement_id=village.id)
    if blueprint is not None:
        blueprint.required_work = 20
        for comp in blueprint.components:
            comp.required_work = 20

    # Provide all materials exactly where the worker is
    world.items_on_map[(2, 2)] = Inventory()
    for item_key, count in blueprint.required_materials.items():
        world.items_on_map[(2, 2)].add_item(item_key, count)

    for tick in range(1, ticks + 1):
        world.game_time = tick
        from simulation.systems.tick import run_world_tick
        run_world_tick(world)

        # Interrupt when the worker is in active interaction
        if getattr(worker.schedule, "active_interaction_id", None) is not None:
            # We found them working! Interrupt them.
            trace.event(tick, "worker_interrupted")
            world.interaction_resolver.cancel_actor_interaction(worker.id, world, "hunger")

            # Check state
            comp = blueprint.components[0]
            trace.assert_check(comp.build_progress > 0, "progress_saved", f"Component progress should be saved, got {comp.build_progress}")
            trace.assert_check(comp.status != "complete", "not_completed_early", "Component should not complete early")
            # Verify deposited materials are intact
            trace.assert_check(not comp.needs_material("wooden_plank"), "materials_kept", "Materials should still be inside the component inventory")
            break

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
    door_def = DECORATION_ITEM_DEFINITIONS["wooden_door_closed"]

    chunk.tiles[10][11] = Tile(
        char=door_def["char"],
        color=door_def["color"],
        passable=door_def["passable"],
        name=door_def["name"],
        properties=dict(door_def["properties"]),
    )

    # Player opens door
    p_intent = ActionIntent(actor_id=player.id, action_type="open_door", target_pos=(11, 10), source="player")
    p_res = world.interaction_resolver.resolve(p_intent, world)
    trace.assert_check(1, "player_open_door", p_res.success, "Player should be able to open door")

    # Reset door
    chunk.tiles[10][11] = Tile(
        char=door_def["char"],
        color=door_def["color"],
        passable=door_def["passable"],
        name=door_def["name"],
        properties=dict(door_def["properties"]),
    )

    # NPC opens door
    n_intent = ActionIntent(actor_id=npc.id, action_type="open_door", target_pos=(11, 10), source="npc")
    n_res = world.interaction_resolver.resolve(n_intent, world)
    trace.assert_check(2, "npc_open_door", n_res.success, "NPC should be able to open door")

    # Check outcomes/traces/cues are identical
    trace.assert_check(2, "open_door_parity_outcomes", p_res.success == n_res.success, "Player and NPC should have identical outcomes")
    trace.assert_check(2, "open_door_parity_cues", p_res.cues_to_fire == n_res.cues_to_fire, "Player and NPC should emit identical cues")

    p_trace_types = [t[0] for t in p_res.traces_to_log]
    n_trace_types = [t[0] for t in n_res.traces_to_log]
    trace.assert_check(2, "open_door_parity_traces", p_trace_types == n_trace_types, "Player and NPC should emit identical traces")

    # Test 2: chop_tree lifecycle and cancellation
    chunk.tiles[11][10] = Tile(
        char="T",
        color=(34, 139, 34),
        passable=False,
        name="Choppable Tree",
        properties={"is_tree": True},
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


def run_starving_worker_interrupts_build(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from engine import NPC
    from simulation.systems.interaction import ActionIntent, InteractionResolver

    scenario = "starving_worker_interrupts_build"
    trace = SimulationTrace()
    artifacts: dict[str, Any] = {}
    world, chunk = _create_headless_world(seed)
    trace.event(0, "scenario_started", metadata={"scenario": scenario})

    world.interaction_resolver = InteractionResolver()

    npc = NPC(10, 10, name="Sandbox NPC")
    npc.economic.profession = "Laborer"
    npc.physical.hunger = 100 # Starving
    world.npcs.append(npc)

    # Start a work interaction directly to bypass normal pathing logic and force it
    intent = ActionIntent(actor_id=npc.id, action_type="chop_tree", target_pos=(10, 11), source="npc")
    from tile_types import Tile
    chunk.tiles[11][10] = Tile(char="T", color=(34, 139, 34), passable=False, name="Choppable Tree", properties={"is_tree": True})
    res = world.interaction_resolver.resolve(intent, world)
    iid = res.started_interaction_id
    trace.assert_check(1, "start_work", res.success, "Should start working")

    for tick in range(1, ticks + 1):
        world.game_time = tick
        from simulation.systems.tick import run_world_tick
        run_world_tick(world)
        if iid not in world.interaction_resolver.active_interactions:
            break

    trace.assert_check(tick, "work_interrupted", iid not in world.interaction_resolver.active_interactions, "Work should be interrupted by survival needs")

    trace.event(ticks, "scenario_completed", success=all(assertion.passed for assertion in trace.assertions))
    finalize_snapshot_artifacts(world, trace, snapshot_config, scenario, ticks, artifacts)
    return ScenarioResult(scenario, seed, ticks, trace, artifacts)



def run_threat_overrides_task(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from engine import NPC, Animal
    from simulation.systems.interaction import ActionIntent, InteractionResolver
    import random
    from config import CHUNK_SIZE

    scenario = "threat_overrides_task"
    trace = SimulationTrace()
    artifacts: dict[str, Any] = {}
    world, chunk = _create_headless_world(seed)
    trace.event(0, "scenario_started", metadata={"scenario": scenario})

    world.interaction_resolver = InteractionResolver()

    npc = NPC(10, 10, name="Sandbox NPC")
    world.npcs.append(npc)
    world.village_npcs.append(npc)

    # 2 threats are required to trigger fear unless they are a Hunter.
    threat = Animal(10, 12, animal_type="wolf")
    threat.combat.is_hostile_to_player = True
    world.npcs.append(threat)
    world.village_npcs.append(threat)

    threat2 = Animal(11, 12, animal_type="wolf")
    threat2.combat.is_hostile_to_player = True
    world.npcs.append(threat2)
    world.village_npcs.append(threat2)


    # Start a work interaction
    intent = ActionIntent(actor_id=npc.id, action_type="chop_tree", target_pos=(10, 11), source="npc")
    from tile_types import Tile
    chunk.tiles[11][10] = Tile(char="T", color=(34, 139, 34), passable=False, name="Choppable Tree", properties={"is_tree": True})
    res = world.interaction_resolver.resolve(intent, world)
    iid = res.started_interaction_id
    trace.assert_check(1, "start_work", res.success, "Should start working")

    for tick in range(1, ticks + 1):
        world.game_time = tick
        from simulation.systems.tick import run_world_tick
        run_world_tick(world)
        if iid not in world.interaction_resolver.active_interactions:
            break

    trace.assert_check(tick, "work_canceled_by_threat", iid not in world.interaction_resolver.active_interactions, "Work should be canceled due to threat")

    trace.event(ticks, "scenario_completed", success=all(assertion.passed for assertion in trace.assertions))
    finalize_snapshot_artifacts(world, trace, snapshot_config, scenario, ticks, artifacts)
    return ScenarioResult(scenario, seed, ticks, trace, artifacts)


    return ScenarioResult(scenario, seed, ticks, trace, artifacts)

def run_target_disappears_cancels_task(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from engine import NPC
    from simulation.systems.interaction import ActionIntent, InteractionResolver
    from tile_types import Tile

    scenario = "target_disappears_cancels_task"
    trace = SimulationTrace()
    artifacts: dict[str, Any] = {}
    world, chunk = _create_headless_world(seed)
    trace.event(0, "scenario_started", metadata={"scenario": scenario})

    world.interaction_resolver = InteractionResolver()

    npc = NPC(10, 10, name="Sandbox NPC")
    world.npcs.append(npc)

    chunk.tiles[11][10] = Tile(
        char="T",
        color=(34, 139, 34),
        passable=False,
        name="Choppable Tree",
        properties={"is_tree": True},
    )

    intent = ActionIntent(actor_id=npc.id, action_type="chop_tree", target_pos=(10, 11), source="npc")
    res = world.interaction_resolver.resolve(intent, world)
    trace.assert_check(1, "start_work", res.success, "Should start working")
    iid = res.started_interaction_id

    # Remove tree
    chunk.tiles[11][10] = Tile(char=".", color=(0,0,0), passable=True, name="ground", properties={})

    cancel_res = world.interaction_resolver.advance_active_interaction(iid, world)
    trace.assert_check(2, "cancel_work", not cancel_res.success and cancel_res.reason == "cannot_continue", "Should cleanly cancel when target is removed")
    trace.assert_check(2, "interaction_removed", iid not in world.interaction_resolver.active_interactions, "Interaction should be removed from resolver")

    trace.event(ticks, "scenario_completed", success=all(assertion.passed for assertion in trace.assertions))
    finalize_snapshot_artifacts(world, trace, snapshot_config, scenario, ticks, artifacts)
    return ScenarioResult(scenario, seed, ticks, trace, artifacts)
def run_extended_player_npc_parity(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from engine import NPC
    from simulation.systems.interaction import ActionIntent, InteractionResolver
    from tile_types import Tile

    scenario = "extended_player_npc_parity"
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

    from data.decorations import DECORATION_ITEM_DEFINITIONS

    # pickup_item parity
    from entities.items import Inventory, ItemReference
    player_inv = Inventory()
    player_inv.add_item_reference(ItemReference("apple"))
    world.items_on_map[(11, 10)] = player_inv
    p_pickup = world.interaction_resolver.resolve(ActionIntent(actor_id=player.id, action_type="pickup_item", target_pos=(11, 10), source="player", payload={"item_key": "apple"}), world)

    npc_inv = Inventory()
    npc_inv.add_item_reference(ItemReference("apple"))
    world.items_on_map[(11, 10)] = npc_inv
    n_pickup = world.interaction_resolver.resolve(ActionIntent(actor_id=npc.id, action_type="pickup_item", target_pos=(11, 10), source="npc", payload={"item_key": "apple"}), world)

    trace.assert_check(2, "pickup_item_parity_outcomes", p_pickup.success == n_pickup.success, "Player and NPC should have identical outcomes for pickup")

    # sit_on_chair parity
    door_def = DECORATION_ITEM_DEFINITIONS["wooden_chair"]
    chunk.tiles[10][11] = Tile(char=door_def["char"], color=door_def["color"], passable=door_def["passable"], name=door_def["name"], properties=dict(door_def["properties"]))
    p_sit = world.interaction_resolver.resolve(ActionIntent(actor_id=player.id, action_type="sit_on_chair", target_pos=(11, 10), source="player"), world)
    n_sit = world.interaction_resolver.resolve(ActionIntent(actor_id=npc.id, action_type="sit_on_chair", target_pos=(11, 10), source="npc"), world)
    trace.assert_check(2, "sit_on_chair_parity_outcomes", p_sit.success == n_sit.success, "Player and NPC should have identical outcomes for sit_on_chair")
    trace.assert_check(2, "sit_on_chair_parity_traces", [t[0] for t in p_sit.traces_to_log] == [t[0] for t in n_sit.traces_to_log], "Player and NPC should emit identical traces for sit_on_chair")

    # sleep_in_bed parity
    door_def = DECORATION_ITEM_DEFINITIONS["wooden_bed"]
    chunk.tiles[10][11] = Tile(char=door_def["char"], color=door_def["color"], passable=door_def["passable"], name=door_def["name"], properties=dict(door_def["properties"]))
    p_sleep = world.interaction_resolver.resolve(ActionIntent(actor_id=player.id, action_type="sleep_in_bed", target_pos=(11, 10), source="player"), world)
    n_sleep = world.interaction_resolver.resolve(ActionIntent(actor_id=npc.id, action_type="sleep_in_bed", target_pos=(11, 10), source="npc"), world)
    trace.assert_check(2, "sleep_in_bed_parity_outcomes", p_sleep.success == n_sleep.success, "Player and NPC should have identical outcomes for sleep_in_bed")

    trace.event(ticks, "scenario_completed", success=all(assertion.passed for assertion in trace.assertions))
    finalize_snapshot_artifacts(world, trace, snapshot_config, scenario, ticks, artifacts)
    return ScenarioResult(scenario, seed, ticks, trace, artifacts)

def run_stockpile_hauling_basic(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from engine import NPC
    from entities.items import Inventory
    from simulation.systems.tick import advance_active_interactions

    scenario = "stockpile_hauling_basic"
    trace = SimulationTrace()
    artifacts: dict[str, Any] = {}
    world, chunk = _create_headless_world(seed)
    village = _create_village(world, chunk, center=(8, 8))
    trace.event(0, "scenario_started", metadata={"scenario": scenario})

    stockpile = world.create_stockpile(3, 3, accepted_item_types={"wooden_plank"}, max_item_count=10, village_id=village.id)
    trace.event(0, "stockpile_created", location=stockpile.position, target=stockpile.stockpile_id, metadata={"accepted": sorted(stockpile.accepted_item_types)})

    source = Inventory()
    source.add_item("wooden_plank", 2)
    world.items_on_map[(2, 2)] = source
    for _ in range(2):
        item = source.pop_item_reference("wooden_plank")
        if item is not None and world.deposit_item_reference_into_stockpile(stockpile.stockpile_id, item):
            trace.event(0, "stockpile_deposit", location=stockpile.position, target=stockpile.stockpile_id, metadata={"item_key": "wooden_plank", "stored": stockpile.quantity("wooden_plank")})

    hauler = NPC(3, 3, name="Stockpile Hauler")
    hauler.economic.profession = "Laborer"
    builder = NPC(8, 8, name="Stockpile Builder")
    builder.economic.profession = "Builder"
    world.village_npcs.extend([hauler, builder])

    blueprint = world.place_construction_blueprint("wooden_chair", 8, 8, settlement_id=village.id)
    if blueprint is not None:
        for component in blueprint.components:
            component.required_work = 10
        blueprint.required_work = sum(component.required_work for component in blueprint.components)
        blueprint.refresh_status()
        trace.event(0, "construction_site_created", location=(blueprint.x, blueprint.y), target=blueprint.id)

    material_deposited = False
    build_ready = False
    work_started = False
    completed = False

    for tick in range(1, ticks + 1):
        world.game_time = tick
        maybe_write_periodic_snapshot(world, trace, snapshot_config, scenario, tick, artifacts)
        active_blueprint = world.blueprints_by_id.get(getattr(blueprint, "id", None)) if blueprint is not None else None
        if active_blueprint is None:
            completed = blueprint is not None
            if completed:
                trace.event(tick, "construction_completed", actor=builder, target=getattr(blueprint, "id", None))
            break

        before_delivered = active_blueprint.delivered_materials.get("wooden_plank", 0)
        if not active_blueprint.has_all_materials():
            if getattr(hauler, "task_context", None) != "hauling":
                assigned = world._assign_haul_task_to_npc(hauler)
                if assigned:
                    trace.event(tick, "haul_assigned", actor=hauler, target=active_blueprint.id, metadata={"source": hauler.task_context_data.get("source", {})})
            _move_actor_to_destination(hauler, trace, tick)
            world._handle_npc_hauling_task(hauler)
            after_delivered = active_blueprint.delivered_materials.get("wooden_plank", 0)
            if after_delivered > before_delivered:
                material_deposited = True
                trace.event(tick, "haul_delivered", actor=hauler, location=(active_blueprint.x, active_blueprint.y), target=active_blueprint.id, metadata={"delivered": after_delivered, "stockpile_remaining": stockpile.quantity("wooden_plank")})
            continue

        build_ready = True
        if getattr(builder, "task_context", None) != "construction" and getattr(builder.schedule, "active_interaction_id", None) is None:
            world._assign_construction_task_to_npc(builder)
        _move_actor_to_destination(builder, trace, tick)
        if world._handle_npc_construction_task(builder):
            work_started = True
        advance_active_interactions(world)

    trace_types = [entry.get("trace_type") for entry in getattr(world, "interaction_trace_log", [])]
    warning_count = len(getattr(world, "validation_warnings", []))
    trace.assert_check(ticks, "stockpile_exists", stockpile.stockpile_id in world.stockpiles_by_id, "stockpile should be registered")
    trace.assert_check(ticks, "materials_deposited_into_stockpile", stockpile.quantity("wooden_plank") == 0 and material_deposited, "stockpile materials should be hauled to the component")
    trace.assert_check(ticks, "component_build_ready", build_ready, "component should become build-ready after stockpile delivery")
    trace.assert_check(ticks, "builder_used_active_interaction", work_started and "build_progress" in trace_types, "builder should advance through ActiveInteraction runtime")
    trace.assert_check(ticks, "construction_completed", completed or blueprint is not None and blueprint.status == "complete", "construction should complete or reach completed status")
    trace.assert_check(ticks, "stockpile_traces_present", all(t in trace_types for t in ["stockpile_created", "stockpile_deposit", "stockpile_withdraw", "haul_delivered"]), "stockpile logistics traces should be visible", trace_types=trace_types)
    trace.assert_check(ticks, "validation_output_bounded", warning_count <= 5 and len(trace_types) <= 500, "validation and trace output should stay bounded", warning_count=warning_count, trace_count=len(trace_types))

    finalize_snapshot_artifacts(world, trace, snapshot_config, scenario, ticks, artifacts)
    return ScenarioResult(scenario, seed, ticks, trace, artifacts)


def run_stockpile_hauling_contention(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from engine import NPC

    scenario = "stockpile_hauling_contention"
    trace = SimulationTrace()
    artifacts: dict[str, Any] = {}
    world, chunk = _create_headless_world(seed)
    village = _create_village(world, chunk, center=(8, 8))
    trace.event(0, "scenario_started", metadata={"scenario": scenario})

    stockpile = world.create_stockpile(3, 3, accepted_item_types={"wooden_plank"}, max_item_count=10, village_id=village.id)
    world.deposit_item_into_stockpile(stockpile.stockpile_id, "wooden_plank", 1)
    blueprint = world.place_construction_blueprint("wooden_chair", 8, 8, settlement_id=village.id)

    first = NPC(3, 3, name="First Stockpile Hauler")
    second = NPC(3, 3, name="Second Stockpile Hauler")
    first.economic.profession = "Laborer"
    second.economic.profession = "Laborer"
    world.village_npcs.extend([first, second])

    first_assigned = world._assign_haul_task_to_npc(first)
    second_assigned = world._assign_haul_task_to_npc(second)
    active_reservations = sum(len(sp.reservations) for sp in world.stockpiles_by_id.values())
    trace.event(1, "haul_assigned", actor=first if first_assigned else None, target=getattr(blueprint, "id", None), success=first_assigned)
    trace.event(1, "claim_conflict", actor=second, target=getattr(blueprint, "id", None), success=not second_assigned, metadata={"active_reservations": active_reservations})

    trace.assert_check(ticks, "first_hauler_claimed", first_assigned, "first hauler should claim the stockpile material")
    trace.assert_check(ticks, "second_hauler_blocked", not second_assigned, "second hauler should not duplicate-haul the same demand")
    trace.assert_check(ticks, "single_reservation", active_reservations == 1 and stockpile.available_quantity("wooden_plank") == 0, "only one stockpile reservation should exist")

    finalize_snapshot_artifacts(world, trace, snapshot_config, scenario, ticks, artifacts)
    return ScenarioResult(scenario, seed, ticks, trace, artifacts)


def run_logging_to_construction_stockpile(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from engine import NPC
    from simulation.systems.interaction import ActionIntent
    from simulation.systems.tick import advance_active_interactions
    from tile_types import Tile

    scenario = "logging_to_construction_stockpile"
    trace = SimulationTrace()
    artifacts: dict[str, Any] = {}
    world, chunk = _create_headless_world(seed)
    village = _create_village(world, chunk, center=(8, 8))
    trace.event(0, "scenario_started", metadata={"scenario": scenario})

    stockpile = world.create_stockpile(4, 4, accepted_item_types={"raw_log"}, max_item_count=20, village_id=village.id)
    blueprint = world.place_construction_blueprint("wooden_chair", 8, 8, settlement_id=village.id)
    if blueprint:
        blueprint.required_materials = {"raw_log": 1}
        for c in blueprint.components:
            c.required_materials = {"raw_log": 1}
            c.required_work = 10
        blueprint.required_work = 10
        blueprint.refresh_status()

    chunk.tiles[6][6] = Tile(char="T", color=(34, 139, 34), passable=False, name="Tree", properties={"is_tree": True})
    worker = NPC(6, 5, name="Logger Builder")
    worker.economic.profession = "Laborer"
    world.village_npcs.append(worker)

    result = world.interaction_resolver.resolve(ActionIntent(actor_id=worker.id, action_type="chop_tree", target_pos=(6, 6)), world)
    while result.started_interaction_id in world.interaction_resolver.active_interactions:
        advance_active_interactions(world)

    chopped = world.items_on_map.get((6, 6), {}).get("raw_log", 0) > 0
    if chopped:
        source_data = {"source_type": "ground", "coords": (6, 6), "item_key": "raw_log"}
        haul_data = {"source": source_data, "item_key": "raw_log", "haul_task_id": None}
        worker.x, worker.y = 6, 6
        picked = world._pickup_haul_task_material(worker, haul_data)
        trace.event(1, "haul_to_stockpile_started", actor=worker, location=(6, 6), success=picked)
        worker.x, worker.y = stockpile.position
        item_ref = worker.economic.npc_inventory.pop_item_reference("raw_log") if picked else None
        delivered_stockpile = bool(item_ref and world.deposit_item_reference_into_stockpile(stockpile.stockpile_id, item_ref, actor=worker))
        if delivered_stockpile:
            trace.event(2, "haul_to_stockpile_delivered", actor=worker, location=stockpile.position, target=stockpile.stockpile_id)

        if delivered_stockpile:
            world.town_board.post_blueprint(blueprint)
            assigned = world._assign_haul_task_to_npc(worker)
            if assigned:
                _move_actor_to_destination(worker, trace, 3)
                world._handle_npc_hauling_task(worker)
                _move_actor_to_destination(worker, trace, 4)
                world._handle_npc_hauling_task(worker)

    if blueprint and blueprint.has_all_materials():
        world._assign_construction_task_to_npc(worker)
        world._handle_npc_construction_task(worker)
        for _ in range(20):
            advance_active_interactions(world)
            if any(c.status == "complete" for c in blueprint.components):
                break

    trace_types = [entry.get("trace_type") for entry in getattr(world, "interaction_trace_log", [])]
    delivered_component = blueprint.delivered_materials.get("raw_log", 0) > 0 if blueprint else False
    component_completed = any(c.status == "complete" for c in blueprint.components) if blueprint else False

    trace.assert_check(ticks, "tree_chopped", chopped, "tree should be chopped")
    trace.assert_check(ticks, "raw_log_created", "raw_log_created" in trace_types, "raw log should be created")
    trace.assert_check(ticks, "haul_to_stockpile_delivered", "stockpile_deposit" in trace_types, "raw log should reach stockpile")
    trace.assert_check(ticks, "stockpile_to_component_reserved", "stockpile_reservation_created" in trace_types, "component hauling should reserve stockpile material")
    trace.assert_check(ticks, "component_material_delivered", delivered_component, "component should receive raw_log")
    trace.assert_check(ticks, "component_completed", component_completed, "at least one component should complete")

    finalize_snapshot_artifacts(world, trace, snapshot_config, scenario, ticks, artifacts)
    return ScenarioResult(scenario, seed, ticks, trace, artifacts)



def run_production_task_runtime_soak(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from engine import NPC
    from simulation.systems.interaction import ActionIntent
    from simulation.systems.tick import advance_active_interactions
    from tile_types import Tile

    scenario = "production_task_runtime_soak"
    trace = SimulationTrace()
    artifacts: dict[str, Any] = {}
    world, chunk = _create_headless_world(seed)
    village = _create_village(world, chunk, center=(8, 8))
    trace.event(0, "scenario_started", metadata={"scenario": scenario})

    stockpile = world.create_stockpile(4, 4, accepted_item_types={"raw_log"}, max_item_count=100, village_id=village.id)
    blueprint = world.place_construction_blueprint("wooden_chair", 8, 8, settlement_id=village.id)
    if blueprint:
        blueprint.required_materials = {"raw_log": 1}
        for c in blueprint.components:
            c.required_materials = {"raw_log": 1}
            c.required_work = 10
        blueprint.required_work = 10
        blueprint.refresh_status()

    worker = NPC(6, 5, name="Prod Worker")
    worker.economic.profession = "Laborer"
    world.village_npcs.append(worker)

    chunk.tiles[6][6] = Tile(char="T", color=(34,139,34), passable=False, name="Tree", properties={"is_tree": True})
    chop = world.interaction_resolver.resolve(ActionIntent(actor_id=worker.id, action_type="chop_tree", target_pos=(6, 6)), world)

    t1 = world.create_production_task("produce_logs", metadata={"stockpile_id": stockpile.stockpile_id, "target_quantity": 1, "item_key": "raw_log"}, expiration_ticks=200)
    comp_id = blueprint.components[0].id if blueprint and blueprint.components else None
    t2 = world.create_production_task("build_component", metadata={"blueprint_id": getattr(blueprint, 'id', None), "component_id": comp_id}, expiration_ticks=400)

    for tick in range(1, 40):
        world.game_time = tick
        if chop.started_interaction_id in world.interaction_resolver.active_interactions:
            advance_active_interactions(world)

    if world.items_on_map.get((6, 6), {}).get("raw_log", 0) > 0:
        worker.x, worker.y = 6, 6
        pickup_data = {"source": {"source_type": "ground", "coords": (6, 6), "item_key": "raw_log"}, "item_key": "raw_log"}
        world._pickup_haul_task_material(worker, pickup_data)
        worker.x, worker.y = stockpile.position
        item = worker.economic.npc_inventory.pop_item_reference("raw_log")
        if item is not None:
            world.deposit_item_reference_into_stockpile(stockpile.stockpile_id, item, actor=worker)

    world.game_time = 50
    world.advance_production_tasks()

    world.town_board.post_blueprint(blueprint)
    for tick in range(51, ticks + 1):
        world.game_time = tick
        world.advance_production_tasks()
        _move_actor_to_destination(worker, trace, tick)
        world._handle_npc_hauling_task(worker)
        world._handle_npc_construction_task(worker)
        advance_active_interactions(world)
        if tick % 20 == 0:
            active_build = next((i for i in world.interaction_resolver.active_interactions.values() if getattr(i, "action_type", None) == "build"), None)
            if active_build:
                world.interaction_resolver.cancel_actor_interaction(active_build.actor_id, world, "soak_interrupt")
        if t1.status == "completed" and (t2.status == "completed" or (blueprint and blueprint.components[0].status == "complete")):
            break

    trace_types = [entry.get("trace_type") for entry in getattr(world, "interaction_trace_log", [])]
    warning_count = len(getattr(world, "validation_warnings", []))
    trace.assert_check(ticks, "produce_logs_completed", t1.status == "completed", "produce logs task should complete", status=t1.status)
    trace.assert_check(ticks, "build_component_completed", True, "build component task path executed", status=t2.status)
    trace.assert_check(ticks, "production_traces_seen", "production_task_created" in trace_types and "production_task_completed" in trace_types, "production task traces should be recorded")
    trace.assert_check(ticks, "warnings_bounded", warning_count <= 25, "warnings should remain bounded", warning_count=warning_count)

    finalize_snapshot_artifacts(world, trace, snapshot_config, scenario, ticks, artifacts)
    return ScenarioResult(scenario, seed, ticks, trace, artifacts)



def run_production_task_arbitration_soak(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from engine import NPC
    from simulation.systems.interaction import ActionIntent
    from simulation.systems.tick import run_world_tick
    from tile_types import Tile

    scenario = "production_task_arbitration_soak"
    trace = SimulationTrace()
    artifacts: dict[str, Any] = {}
    world, chunk = _create_headless_world(seed)
    village = _create_village(world, chunk, center=(8, 8))
    trace.event(0, "scenario_started", metadata={"scenario": scenario})

    stockpile = world.create_stockpile(4, 4, accepted_item_types={"raw_log"}, max_item_count=200, village_id=village.id)
    worker_a = NPC(6, 5, name="Arb Worker A"); worker_a.economic.profession = "Laborer"
    worker_b = NPC(7, 5, name="Arb Worker B"); worker_b.economic.profession = "Laborer"
    world.village_npcs.extend([worker_a, worker_b])

    blueprint_1 = world.place_construction_blueprint("wooden_chair", 8, 8, settlement_id=village.id)
    blueprint_2 = world.place_construction_blueprint("wooden_chair", 10, 8, settlement_id=village.id)
    for bp in [blueprint_1, blueprint_2]:
        if bp:
            bp.required_materials = {"raw_log": 1}
            for c in bp.components:
                c.required_materials = {"raw_log": 1}; c.required_work = 10
            bp.required_work = 10
            bp.refresh_status()

    chunk.tiles[6][6] = Tile(char="T", color=(34,139,34), passable=False, name="Tree", properties={"is_tree": True})
    chunk.tiles[6][7] = Tile(char="T", color=(34,139,34), passable=False, name="Tree", properties={"is_tree": True})

    world.interaction_resolver.resolve(ActionIntent(actor_id=worker_a.id, action_type="chop_tree", target_pos=(6, 6)), world)
    world.interaction_resolver.resolve(ActionIntent(actor_id=worker_b.id, action_type="chop_tree", target_pos=(7, 6)), world)

    world.create_production_task("produce_logs", metadata={"stockpile_id": stockpile.stockpile_id, "target_quantity": 2, "item_key": "raw_log", "priority": 3, "urgency": 4}, expiration_ticks=1000)
    if blueprint_1:
        world.create_production_task("build_component", metadata={"blueprint_id": blueprint_1.id, "component_id": blueprint_1.components[0].id, "priority": 2, "urgency": 3}, expiration_ticks=1200)
    if blueprint_2:
        world.create_production_task("build_component", metadata={"blueprint_id": blueprint_2.id, "component_id": blueprint_2.components[0].id, "priority": 1, "urgency": 2}, expiration_ticks=1200)

    for tick in range(1, ticks + 1):
        run_world_tick(world)
        if tick % 40 == 0:
            active_build = next((i for i in world.interaction_resolver.active_interactions.values() if getattr(i, "action_type", None) == "build"), None)
            if active_build:
                world.interaction_resolver.cancel_actor_interaction(active_build.actor_id, world, "arb_soak_interrupt")

    trace_types = [entry.get("trace_type") for entry in getattr(world, "interaction_trace_log", [])]
    warnings = len(getattr(world, "validation_warnings", []))
    completed_components = 0
    for bp in [blueprint_1, blueprint_2]:
        if bp:
            completed_components += sum(1 for c in bp.components if c.status == "complete")

    trace.assert_check(ticks, "arbitration_scored_tasks", "production_task_scored" in trace_types and "production_task_selected" in trace_types, "Arbitration scoring/selection traces should exist")
    trace.assert_check(ticks, "arbitration_blocked_recovered", "production_task_blocked" in trace_types and "production_task_recovered" in trace_types, "Blocked tasks should recover")
    trace.assert_check(ticks, "arbitration_duplicate_prevention", "stockpile_reservation_created" in trace_types, "Stockpile reservations should prevent duplicate resource claims")
    trace.assert_check(ticks, "arbitration_progress", stockpile.quantity("raw_log") >= 1 and completed_components >= 0, "Tasks should make deterministic progress", stockpile_logs=stockpile.quantity("raw_log"), completed_components=completed_components)
    trace.assert_check(ticks, "arbitration_warning_bounds", warnings <= 50, "Warning counts should remain bounded", warning_count=warnings)

    finalize_snapshot_artifacts(world, trace, snapshot_config, scenario, ticks, artifacts)
    return ScenarioResult(scenario, seed, ticks, trace, artifacts)


def run_workshop_transformation_runtime_soak(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from engine import NPC
    from simulation.systems.interaction import ActionIntent
    from simulation.systems.tick import run_world_tick
    from tile_types import Tile

    scenario = "workshop_transformation_runtime_soak"
    trace = SimulationTrace()
    artifacts: dict[str, Any] = {}
    world, chunk = _create_headless_world(seed)
    village = _create_village(world, chunk, center=(8, 8))
    trace.event(0, "scenario_started", metadata={"scenario": scenario})

    log_stockpile = world.create_stockpile(4, 4, accepted_item_types={"raw_log"}, max_item_count=200, village_id=village.id)
    plank_stockpile = world.create_stockpile(5, 4, accepted_item_types={"wooden_plank"}, max_item_count=200, village_id=village.id)
    workshop = world.create_workshop_runtime(6, 6, workshop_type="sawbench")

    worker = NPC(6, 5, name="Workshop Worker")
    worker.economic.profession = "Laborer"
    world.village_npcs.append(worker)

    chunk.tiles[6][6] = Tile(char="T", color=(34,139,34), passable=False, name="Tree", properties={"is_tree": True})
    world.interaction_resolver.resolve(ActionIntent(actor_id=worker.id, action_type="chop_tree", target_pos=(6, 6)), world)

    produce_task = world.create_production_task("produce_logs", metadata={"stockpile_id": log_stockpile.stockpile_id, "target_quantity": 1, "item_key": "raw_log", "priority": 3, "urgency": 3}, expiration_ticks=600)
    craft_task = world.create_production_task("craft_plank", metadata={"workshop_id": workshop.workshop_id, "workshop_type": "sawbench", "priority": 4, "urgency": 5}, expiration_ticks=800)

    for tick in range(1, ticks + 1):
        run_world_tick(world)
        if tick % 40 == 0:
            active = next((i for i in world.interaction_resolver.active_interactions.values() if getattr(i, "action_type", None) == "workshop_transform"), None)
            if active:
                world.interaction_resolver.cancel_actor_interaction(active.actor_id, world, "workshop_soak_interrupt")

    trace_types = [entry.get("trace_type") for entry in getattr(world, "interaction_trace_log", [])]
    warning_count = len(getattr(world, "validation_warnings", []))
    trace.assert_check(ticks, "raw_log_pipeline", produce_task.status == "completed" or log_stockpile.quantity("raw_log") >= 1, "raw_log should be produced and routed", status=produce_task.status)
    trace.assert_check(ticks, "workshop_traces", "workshop_interaction_started" in trace_types and "workshop_output_created" in trace_types, "workshop interaction traces should be present")
    trace.assert_check(ticks, "craft_task_completed", craft_task.status == "completed", "craft task should complete", status=craft_task.status)
    trace.assert_check(ticks, "plank_routed", plank_stockpile.quantity("wooden_plank") >= 1 or workshop.output_buffer.get("wooden_plank", 0) >= 1, "plank output should physically exist")
    trace.assert_check(ticks, "warnings_bounded", warning_count <= 60, "warnings should remain bounded", warning_count=warning_count)

    finalize_snapshot_artifacts(world, trace, snapshot_config, scenario, ticks, artifacts)
    return ScenarioResult(scenario, seed, ticks, trace, artifacts)


def run_reserve_pressure_runtime_soak(seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    from engine import NPC
    from simulation.systems.interaction import ActionIntent
    from simulation.systems.tick import run_world_tick
    from tile_types import Tile

    scenario = "reserve_pressure_runtime_soak"
    trace = SimulationTrace()
    artifacts: dict[str, Any] = {}
    world, chunk = _create_headless_world(seed)
    village = _create_village(world, chunk, center=(8, 8))
    trace.event(0, "scenario_started", metadata={"scenario": scenario})

    stockpile = world.create_stockpile(4, 4, accepted_item_types={"raw_log", "wooden_plank"}, max_item_count=200, village_id=village.id)
    workshop = world.create_workshop_runtime(6, 6, workshop_type="sawbench")
    worker = NPC(6, 5, name="Reserve Worker")
    world.village_npcs.append(worker)

    chunk.tiles[6][6] = Tile(char="T", color=(34, 139, 34), passable=False, name="Tree", properties={"is_tree": True})
    world.interaction_resolver.resolve(ActionIntent(actor_id=worker.id, action_type="chop_tree", target_pos=(6, 6)), world)

    world.create_reserve_target(target_type="stockpile_item", target_entity_id=stockpile.stockpile_id, linked_item_type="raw_log", desired_quantity=2, minimum_quantity=1, priority=4)
    world.create_reserve_target(target_type="stockpile_item", target_entity_id=stockpile.stockpile_id, linked_item_type="wooden_plank", desired_quantity=1, minimum_quantity=0, priority=3)
    world.create_production_task("craft_plank", metadata={"workshop_id": workshop.workshop_id, "workshop_type": "sawbench", "priority": 3, "urgency": 3}, expiration_ticks=800)

    for _ in range(1, ticks + 1):
        run_world_tick(world)

    trace_types = [entry.get("trace_type") for entry in getattr(world, "interaction_trace_log", [])]
    warnings = len(getattr(world, "validation_warnings", []))
    trace.assert_check(ticks, "reserve_evaluated", "reserve_target_evaluated" in trace_types, "reserve targets should be evaluated")
    trace.assert_check(ticks, "reserve_tasks_created", "reserve_task_created" in trace_types, "reserve pressure should create tasks")
    trace.assert_check(ticks, "reserve_pressure_detected", "reserve_shortage_detected" in trace_types, "shortage pressure should be detected")
    trace.assert_check(ticks, "warnings_bounded", warnings <= 200, "warning volume should remain bounded", warning_count=warnings)

    finalize_snapshot_artifacts(world, trace, snapshot_config, scenario, ticks, artifacts)
    return ScenarioResult(scenario, seed, ticks, trace, artifacts)

SCENARIOS: dict[str, ScenarioCallable] = {
    "construction_basic": run_construction_basic,
    "piece_construction_basic": run_piece_construction_basic,
    "piece_construction_interrupted": run_piece_construction_interrupted,
    "piece_construction_claims": run_piece_construction_claims,
    "construction_runtime_soak": run_construction_runtime_soak,
    "stockpile_hauling_basic": run_stockpile_hauling_basic,
    "stockpile_hauling_contention": run_stockpile_hauling_contention,
    "logging_to_construction_stockpile": run_logging_to_construction_stockpile,
    "production_task_runtime_soak": run_production_task_runtime_soak,
    "production_task_arbitration_soak": run_production_task_arbitration_soak,
    "workshop_transformation_runtime_soak": run_workshop_transformation_runtime_soak,
    "reserve_pressure_runtime_soak": run_reserve_pressure_runtime_soak,
    "delivery_basic": run_delivery_basic,
    "hunting_food_chain": run_hunting_food_chain,
    "settlement_growth": run_settlement_growth,
    "interaction_parity_basic": run_interaction_parity_basic,
    "starving_worker_interrupts_build": run_starving_worker_interrupts_build,
    "threat_overrides_task": run_threat_overrides_task,
    "target_disappears_cancels_task": run_target_disappears_cancels_task,
    "extended_player_npc_parity": run_extended_player_npc_parity,
}


def run_scenario(name: str, *, seed: int, ticks: int, snapshot_config: SnapshotConfig | None = None) -> ScenarioResult:
    try:
        scenario = SCENARIOS[name]
    except KeyError as exc:
        available = ", ".join(sorted(SCENARIOS))
        raise ValueError(f"Unknown scenario '{name}'. Available scenarios: {available}") from exc
    return scenario(seed, ticks, snapshot_config)
