"""Perception-domain simulation systems (sound-driven NPC reactions)."""

from __future__ import annotations

import math


def expire_sounds(world):
    """Sound lifetime belongs to simulation time, not the player's footsteps."""
    now = world.game_time
    events = getattr(world, "sound_events", None)
    if events is not None:
        events[:] = [sound for sound in events if now-sound.setdefault("created_tick", now) <= 2]


def update_npc_sound_perception(world, npc) -> None:
    """Process immediate sound reactions and investigation pathing for one NPC."""
    if npc.schedule.current_task in {"treating_patient", "seeking_healer", "waiting_for_treatment",
                                     "recovering_from_injury", "collecting_medical_supplies"}:
        return  # Immediate witnessed threats have their own higher-priority response.
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
