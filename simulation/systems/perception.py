"""Perception-domain simulation systems (sound-driven NPC reactions)."""

from __future__ import annotations

import math


def update_npc_sound_perception(world, npc) -> None:
    """Process immediate sound reactions and investigation pathing for one NPC."""
    heard_compelling_sound = False
    if world.sound_events:
        for sound in world.sound_events:
            if sound.get("source_id") and sound["source_id"] == npc.id:
                continue

            dist_to_sound = math.sqrt((npc.x - sound["x"])**2 + (npc.y - sound["y"])**2)
            if dist_to_sound <= npc.hearing_radius and dist_to_sound <= sound["volume"]:
                if npc.schedule.current_task not in ["combat_action_attack_player", "combat_action_flee_from_player", "combat_action_move_to_attack_player", "investigating_sound"]:
                    sound_type = sound["type"]
                    if sound_type in ["combat_attack", "tree_fall"]:
                        npc.schedule.current_task = "investigating_sound"
                        npc.schedule.current_destination_coords = (sound["x"], sound["y"])
                        npc.schedule.current_path = []
                        world.add_message_to_chat_log(
                            f"{world.get_entity_display_name(npc)} heard a {sound_type} and looks towards it."
                        )
                        heard_compelling_sound = True
                        break

    if heard_compelling_sound:
        if npc.schedule.current_task == "investigating_sound" and npc.schedule.current_destination_coords and not npc.schedule.current_path:
            path = world.calculate_path(npc.x, npc.y, npc.schedule.current_destination_coords[0], npc.schedule.current_destination_coords[1])
            if path:
                npc.schedule.current_path = path
            else:
                from simulation.systems.task_types import TaskType
                npc.schedule.current_task = TaskType.IDLE
                npc.schedule.current_destination_coords = None
