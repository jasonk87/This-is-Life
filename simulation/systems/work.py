"""Work-task progression system for structured NPC profession sub-tasks."""

from __future__ import annotations
from simulation.activity import advance_activity, start_activity
from simulation.systems.task_types import TaskType

from data.professions import get_profession_data, get_sub_task_data


def update_npc_work_sub_tasks(world, npc) -> bool:
    """Advance one NPC through profession work sub-task transitions."""
    if not npc.schedule.work_building_id or not npc.economic.profession:
        return False

    work_building = world.buildings_by_id.get(npc.schedule.work_building_id)
    if not work_building:
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
        current_workers = sum(1 for n in world.village_npcs if getattr(n.schedule, "work_building_id", None) == work_building.id and n.id != npc.id and not n.physical.is_dead)
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

    if not npc.current_sub_task or (npc.sub_task_target_coords and (npc.x, npc.y) == npc.sub_task_target_coords and npc.sub_task_timer <= 0):
        if npc.current_sub_task and npc.sub_task_timer <= 0 and npc.sub_task_target_coords and (npc.x, npc.y) == npc.sub_task_target_coords:
            completed_sub_task_id = npc.current_sub_task
            completed_sub_task_data = next((st for st in profession_data.get("sub_tasks", []) if st.get("id") == completed_sub_task_id), None)
            if not completed_sub_task_data:
                completed_sub_task_data = get_sub_task_data(npc.economic.profession, completed_sub_task_id)
            if completed_sub_task_data:
                world._execute_completed_work_sub_task(npc, work_building, completed_sub_task_id, completed_sub_task_data)
            npc.current_sub_task = None

        if not npc.current_sub_task:
            found_viable_task = False
            for i in range(len(sub_task_sequence)):
                next_task_index = (npc.current_sub_task_sequence_index + i) % len(sub_task_sequence)
                next_sub_task_id = sub_task_sequence[next_task_index]
                current_sub_task_data = next((st for st in profession_data.get("sub_tasks", []) if st.get("id") == next_sub_task_id), None)
                if not current_sub_task_data:
                    current_sub_task_data = get_sub_task_data(npc.economic.profession, next_sub_task_id)
                if not current_sub_task_data:
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
                found_viable_task = True
                break

            if not found_viable_task:
                npc.schedule.current_task = TaskType.AT_WORK
                return True

    if npc.current_sub_task and npc.sub_task_target_coords:
        if (npc.x, npc.y) != npc.sub_task_target_coords:
            if not npc.schedule.current_path:
                path = world.calculate_path(npc.x, npc.y, npc.sub_task_target_coords[0], npc.sub_task_target_coords[1])
                if path:
                    npc.schedule.current_path = path
                    npc.schedule.current_destination_coords = npc.sub_task_target_coords
                    npc.schedule.current_task = TaskType.AT_WORK
                else:
                    npc.clear_work_sub_task_state()
                    npc.schedule.current_path = []
                    npc.schedule.current_destination_coords = None
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
                npc.economic.work_performance = min(100, npc.economic.work_performance + 5)
                if hasattr(getattr(npc, "skills", None), "gain_experience"):
                    npc.skills.gain_experience("labor", 3)
        return True

    if npc.schedule.current_task == TaskType.AT_WORK:
        npc.economic.work_performance = max(0, npc.economic.work_performance - 1)

    return False
