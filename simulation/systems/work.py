"""Work-task progression system for structured NPC profession sub-tasks."""

from __future__ import annotations
import random
from simulation.activity import advance_activity, start_activity
from simulation.systems.task_types import TaskType

from data.professions import get_profession_data, get_sub_task_data
from simulation.careers import get_age_work_performance_ceiling


def _warn(world, warning_type: str, key, message: str, *, actor=None, metadata: dict | None = None) -> None:
    reporter = getattr(world, "_warn_simulation_validation", None)
    if callable(reporter):
        reporter(warning_type, key, message, actor=actor, metadata=metadata)


def _abandon_invalid_task(world, npc, *, reason: str, sub_task_data: dict | None = None, metadata: dict | None = None) -> None:
    abandoner = getattr(world, "_abandon_invalid_work_sub_task", None)
    if callable(abandoner):
        abandoner(npc, reason=reason, sub_task_data=sub_task_data, metadata=metadata)
        return
    npc.clear_work_sub_task_state()
    npc.schedule.current_path = []
    npc.schedule.current_destination_coords = None


def update_npc_work_sub_tasks(world, npc) -> bool:
    """Advance one NPC through profession work sub-task transitions."""
    if not npc.schedule.work_building_id or not npc.economic.profession:
        return False

    retry_after = getattr(npc, "_work_validation_retry_after_tick", 0)
    if retry_after and getattr(world, "game_time", 0) < retry_after:
        return True

    work_building = world.buildings_by_id.get(npc.schedule.work_building_id)
    if not work_building:
        _warn(
            world,
            "missing_workplace",
            (getattr(npc, "id", None), npc.schedule.work_building_id),
            "NPC work schedule references a missing workplace.",
            actor=npc,
            metadata={"work_building_id": npc.schedule.work_building_id, "profession": npc.economic.profession},
        )
        npc.schedule.current_task = "idle_confused"
        return True

    profession_data_original = get_profession_data(npc.economic.profession)
    if not profession_data_original:
        return world._attempt_workplace_supply_chain_actions(npc, work_building)

    new_data = dict(profession_data_original)
    if "sub_tasks" in new_data:
        new_data["sub_tasks"] = list(new_data["sub_tasks"])
    if "default_sub_task_sequence" in new_data:
        new_data["default_sub_task_sequence"] = list(new_data["default_sub_task_sequence"])
    profession_data = new_data

    sub_task_sequence = profession_data.get("default_sub_task_sequence", [])

    if not profession_data.get("sub_tasks") or not sub_task_sequence:
        if getattr(work_building, "owner_id", None) != npc.id:
            return world._attempt_workplace_supply_chain_actions(npc, work_building)

    # Delegated Labor: Owners do management if they have workers
    if getattr(work_building, "owner_id", None) == npc.id:
        current_workers = world._count_active_workers_for_building(work_building)
        if npc.schedule.work_building_id == work_building.id:
            current_workers -= 1
        if current_workers > 0:
            # Inject management sub-tasks instead
            sub_task_sequence = ["manage_business_inspect", "manage_business_supervise"]

            if "sub_tasks" not in profession_data:
                profession_data["sub_tasks"] = []
            # Ensure these tasks exist in profession_data or we inject them temporarily
            if not any(st.get("id") == "manage_business_inspect" for st in profession_data.get("sub_tasks", [])):
                profession_data["sub_tasks"].extend([
                    {
                        "id": "manage_business_inspect",
                        "display_name": "Inspecting",
                        "duration_ticks": 40,
                        "target_zone_tag": "manager_spot",
                        "action_verb": "inspecting workers"
                    },
                    {
                        "id": "manage_business_supervise",
                        "display_name": "Supervising",
                        "duration_ticks": 60,
                        "target_zone_tag": "manager_spot",
                        "action_verb": "supervising production"
                    }
                ])

    if not sub_task_sequence:

        return False

    is_at_station = False
    if npc.sub_task_target_coords:
        dist_to_station = abs(npc.x - npc.sub_task_target_coords[0]) + abs(npc.y - npc.sub_task_target_coords[1])
        is_at_station = (dist_to_station <= 1)

    if not npc.current_sub_task or (is_at_station and npc.sub_task_timer <= 0):
        if npc.current_sub_task and npc.sub_task_timer <= 0 and is_at_station:
            completed_sub_task_id = npc.current_sub_task
            completed_sub_task_data = next((st for st in profession_data.get("sub_tasks", []) if st.get("id") == completed_sub_task_id), None)
            if not completed_sub_task_data:
                completed_sub_task_data = get_sub_task_data(npc.economic.profession, completed_sub_task_id)
            if completed_sub_task_data:
                world._execute_completed_work_sub_task(npc, work_building, completed_sub_task_id, completed_sub_task_data)
            npc.current_sub_task = None
            # Step past what was just finished. The search below starts at this
            # index and only walks forward when a step is not viable, so a
            # completed step was simply re-selected - and a profession's first
            # step (fetching, tending) is always viable because it consumes
            # nothing. A blacksmith therefore fetched ore forever and never
            # smelted it, which is why every workshop's later steps and their
            # outputs never appeared on screen.
            npc.current_sub_task_sequence_index = (
                npc.current_sub_task_sequence_index + 1
            ) % len(sub_task_sequence)

        if not npc.current_sub_task:
            found_viable_task = False
            for i in range(len(sub_task_sequence)):
                next_task_index = (npc.current_sub_task_sequence_index + i) % len(sub_task_sequence)
                next_sub_task_id = sub_task_sequence[next_task_index]
                current_sub_task_data = next((st for st in profession_data.get("sub_tasks", []) if st.get("id") == next_sub_task_id), None)
                if not current_sub_task_data:
                    current_sub_task_data = get_sub_task_data(npc.economic.profession, next_sub_task_id)
                if not current_sub_task_data:
                    _warn(
                        world,
                        "invalid_subtask",
                        (npc.economic.profession, next_sub_task_id, "undefined"),
                        "Profession sub-task sequence references an undefined sub-task.",
                        actor=npc,
                        metadata={"profession": npc.economic.profession, "sub_task_id": next_sub_task_id, "building_id": getattr(work_building, "id", None)},
                    )
                    continue

                consumes = current_sub_task_data.get("consumes_item_from_workplace", {})
                b_inv = getattr(work_building, "building_inventory", {}) or {}
                if consumes and any(b_inv.get(k, 0) < v for k, v in consumes.items()):
                    continue

                target_coords = world._find_target_coords_for_sub_task(npc, work_building, current_sub_task_data)
                if not target_coords:
                    continue

                npc.current_sub_task_sequence_index = next_task_index
                npc.current_sub_task = next_sub_task_id
                npc.sub_task_zone_target = current_sub_task_data.get("target_zone_tag")
                npc.sub_task_target_coords = target_coords
                npc.schedule.current_path = []
                npc.sub_task_timer = current_sub_task_data.get("duration_ticks", 10)
                npc.production_blocked_reason = None
                found_viable_task = True
                break

            if not found_viable_task:
                # Check if there are defined subtasks that are blocked by missing resources or facilities
                blocked_dependencies = []
                for st_id in sub_task_sequence:
                    st_data = next((st for st in profession_data.get("sub_tasks", []) if st.get("id") == st_id), None)
                    if not st_data:
                        st_data = get_sub_task_data(npc.economic.profession, st_id)
                    if st_data and (st_data.get("consumes_item_from_workplace") or st_data.get("target_zone_tag") is not None or st_data.get("produces_item_at_workplace")):
                        consumes = st_data.get("consumes_item_from_workplace", {})
                        b_inv = getattr(work_building, "building_inventory", {}) or {}
                        missing = {k: v - b_inv.get(k, 0) for k, v in consumes.items() if b_inv.get(k, 0) < v}
                        target_coords = world._find_target_coords_for_sub_task(npc, work_building, st_data)
                        if missing:
                            blocked_dependencies.append({"sub_task": st_id, "missing_items": missing})
                        elif not target_coords and st_data.get("target_zone_tag"):
                            blocked_dependencies.append({"sub_task": st_id, "missing_facility": st_data.get("target_zone_tag")})

                if blocked_dependencies:
                    # Explicitly record honest production block status
                    npc.production_blocked_reason = {
                        "profession": npc.economic.profession,
                        "building_id": getattr(work_building, "id", None),
                        "blocked_dependencies": blocked_dependencies,
                        "blocked_at_tick": getattr(world, "game_time", 0)
                    }
                    # Non-productive workplace maintenance fallback
                    maintenance_coords = None
                    if hasattr(world, "_find_unclaimed_tile_near"):
                        ox = work_building.global_origin_x + random.randint(1, max(1, work_building.width - 2))
                        oy = work_building.global_origin_y + random.randint(1, max(1, work_building.height - 2))
                        maintenance_coords = world._find_unclaimed_tile_near(ox, oy, claimed=set(), prefer=(npc.x, npc.y), radius=2)
                    npc.current_sub_task = "tidying_workplace"
                    npc.sub_task_zone_target = "workplace_floor"
                    npc.sub_task_target_coords = maintenance_coords or (work_building.global_center_x, work_building.global_center_y)
                    npc.schedule.current_path = []
                    npc.sub_task_timer = 60
                    npc.schedule.current_task = TaskType.AT_WORK
                    return True
                else:
                    _abandon_invalid_task(
                        world,
                        npc,
                        reason="no_viable_work_subtask",
                        metadata={"profession": npc.economic.profession, "building_id": getattr(work_building, "id", None), "sequence": list(sub_task_sequence)},
                    )
                    npc.schedule.current_task = TaskType.AT_WORK
                    return True

    if npc.current_sub_task and npc.sub_task_target_coords:
        tx, ty = npc.sub_task_target_coords
        dest_tile = world.get_tile_at(tx, ty) if hasattr(world, "get_tile_at") else None
        if dest_tile and not getattr(dest_tile, "passable", True):
            if hasattr(world, "_find_best_adjacent_tile"):
                adj = world._find_best_adjacent_tile(tx, ty, npc)
                if adj and adj != (None, None):
                    tx, ty = adj

        if (npc.x, npc.y) != (tx, ty) and (npc.x, npc.y) != npc.sub_task_target_coords:
            if not npc.schedule.current_path:
                path = world.calculate_path(npc.x, npc.y, tx, ty)
                if path:
                    npc.schedule.current_path = path
                    npc.schedule.current_destination_coords = (tx, ty)
                    npc.schedule.current_task = TaskType.AT_WORK
                else:
                    _abandon_invalid_task(
                        world,
                        npc,
                        reason="path_unreachable",
                        sub_task_data=get_sub_task_data(npc.economic.profession, npc.current_sub_task) or {"id": npc.current_sub_task},
                        metadata={"target_coords": npc.sub_task_target_coords, "building_id": getattr(work_building, "id", None)},
                    )
                    npc.schedule.current_task = TaskType.AT_WORK
            else:
                npc.schedule.current_task = TaskType.AT_WORK
        else:
            npc.schedule.current_path = []
            npc.schedule.current_destination_coords = None
            npc.schedule.current_task = TaskType.AT_WORK
            activity_type = f"work:{npc.current_sub_task}"
            current_activity = getattr(npc, "current_activity", None)
            if current_activity is None and npc.sub_task_timer > 0:
                sub_task_data = get_sub_task_data(npc.economic.profession, npc.current_sub_task) or {}
                start_activity(
                    npc,
                    activity_type,
                    npc.sub_task_timer,
                    world=world,
                    location=(npc.x, npc.y),
                    anchor_coords=npc.sub_task_target_coords,
                    allows_conversation=bool(sub_task_data.get("allows_conversation", True)),
                    allows_observation=True,
                    allows_social_sharing=True,
                    interruptible=True,
                    metadata={"profession": npc.economic.profession, "sub_task_id": npc.current_sub_task},
                )
                current_activity = getattr(npc, "current_activity", None)
                advance_activity(npc, world)
                current_activity = getattr(npc, "current_activity", None)

            if current_activity is not None and getattr(current_activity, "activity_type", None) == activity_type:
                npc.sub_task_timer = max(0, current_activity.duration_ticks - current_activity.progress_ticks)

            # Emit a visual sub-task action randomly while performing it
            if npc.sub_task_timer > 0 and getattr(world, "game_time", 0) % 30 == 0:
                sub_task_data = next((st for st in profession_data.get("sub_tasks", []) if st.get("id") == npc.current_sub_task), None)
                if not sub_task_data:
                    sub_task_data = get_sub_task_data(npc.economic.profession, npc.current_sub_task)
                if sub_task_data:
                    action_verb = sub_task_data.get("action_verb")
                    if action_verb and hasattr(world, "visual_effects"):
                        from engine import FloatingTextEffect
                        world.visual_effects.append(
                            FloatingTextEffect(npc.x, npc.y, f"*{action_verb}*", color=(200, 200, 200))
                        )

            if npc.sub_task_timer <= 0:
                performance_ceiling = get_age_work_performance_ceiling(getattr(npc, "age", None))
                npc.economic.work_performance = min(performance_ceiling, npc.economic.work_performance + 5)
                if hasattr(getattr(npc, "skills", None), "gain_experience"):
                    npc.skills.gain_experience("labor", 3)
        return True

    if npc.schedule.current_task == TaskType.AT_WORK:
        npc.economic.work_performance = max(0, npc.economic.work_performance - 1)

    return False
