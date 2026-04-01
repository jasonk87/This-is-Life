"""Medical-domain task transitions for injured NPCs and healer behavior."""

from __future__ import annotations
from simulation.systems.task_types import TaskType

import math
import random

from config import WORLD_HEIGHT, WORLD_WIDTH


def update_npc_medical_state(world, npc) -> None:
    """Advance one NPC's medical/injury/treatment task logic."""
    if "broken_leg" in npc.physical.status_effects:
        if not hasattr(npc, "original_speed"):
            npc.original_speed = getattr(npc, "speed", 1)
        npc.speed = max(0.5, getattr(npc, "original_speed", 1) / 2.0)

        if npc.schedule.current_task not in ["seeking_healer", "waiting_for_treatment", "resting_in_bed"]:
            npc.schedule.current_task = "seeking_healer"

            clinic = world._find_nearest_building_of_type(npc, "clinic")
            if clinic:
                dest_x, dest_y = clinic.global_center_x, clinic.global_center_y
                npc.schedule.current_destination_coords = (dest_x, dest_y)
                path = world.calculate_path(npc.x, npc.y, dest_x, dest_y)
                if path:
                    npc.schedule.current_path = path
                else:
                    npc.schedule.current_task = "waiting_for_treatment"
                    npc.schedule.current_path = []
            elif npc.schedule.home_building_id:
                home = world.buildings_by_id.get(npc.schedule.home_building_id)
                if home:
                    npc.schedule.current_destination_coords = (home.global_center_x, home.global_center_y)
                    path = world.calculate_path(npc.x, npc.y, home.global_center_x, home.global_center_y)
                    if path:
                        npc.schedule.current_path = path
                    else:
                        npc.schedule.current_task = "resting_in_bed"
                        npc.schedule.current_path = []
            else:
                npc.schedule.current_task = "resting_in_bed"
                npc.schedule.current_path = []

    if npc.schedule.current_task == "seeking_healer":
        if not npc.schedule.current_path or len(npc.schedule.current_path) <= 1:
            if npc.schedule.current_destination_coords:
                if abs(npc.x - npc.schedule.current_destination_coords[0]) + abs(npc.y - npc.schedule.current_destination_coords[1]) <= 3:
                    npc.schedule.current_task = "waiting_for_treatment"
                    npc.schedule.current_path = []
                    npc.schedule.current_destination_coords = None

    if npc.economic.profession == "Healer":
        if npc.schedule.current_task not in ["treating_patient", "foraging_for_herbs", "crafting_medical_supplies"]:
            patients = [p for p in world.all_npcs if not p.physical.is_dead and "broken_leg" in p.physical.status_effects]
            if patients:
                closest_patient = min(patients, key=lambda p: abs(npc.x - p.x) + abs(npc.y - p.y))
                if abs(npc.x - closest_patient.x) + abs(npc.y - closest_patient.y) < 15:
                    npc.schedule.current_task = "treating_patient"
                    npc.task_target_entity_id = closest_patient.id
                    npc.task_timer = 20
                    npc.schedule.current_path = []
                    if abs(npc.x - closest_patient.x) + abs(npc.y - closest_patient.y) > 1:
                        path = world.calculate_path(npc.x, npc.y, closest_patient.x, closest_patient.y)
                        if path:
                            npc.schedule.current_path = path
            else:
                salves_count = npc.economic.npc_inventory.get("healing_salve", 0)
                if salves_count < 5:
                    herbs_count = npc.economic.npc_inventory.get("medicinal_herb", 0)
                    if herbs_count < 2:
                        npc.schedule.current_task = "foraging_for_herbs"
                        angle = random.uniform(0, 2 * math.pi)
                        dist = random.uniform(10, 20)
                        target_x = max(0, min(WORLD_WIDTH - 1, int(npc.x + math.cos(angle) * dist)))
                        target_y = max(0, min(WORLD_HEIGHT - 1, int(npc.y + math.sin(angle) * dist)))
                        npc.schedule.current_destination_coords = (target_x, target_y)
                        path = world.calculate_path(npc.x, npc.y, target_x, target_y)
                        if path:
                            npc.schedule.current_path = path
                        else:
                            npc.schedule.current_task = TaskType.IDLE
                    else:
                        npc.schedule.current_task = "crafting_medical_supplies"
                        clinic = world._find_nearest_building_of_type(npc, "clinic")
                        if clinic and "alchemy_station" in clinic.work_zone_tiles and clinic.work_zone_tiles["alchemy_station"]:
                            dest = clinic.work_zone_tiles["alchemy_station"][0]
                            npc.schedule.current_destination_coords = dest
                            if (npc.x, npc.y) != dest:
                                path = world.calculate_path(npc.x, npc.y, dest[0], dest[1])
                                if path:
                                    npc.schedule.current_path = path
                                else:
                                    npc.schedule.current_task = TaskType.IDLE
                        else:
                            npc.task_timer = 5
                            npc.schedule.current_destination_coords = (npc.x, npc.y)

    if npc.economic.profession == "Healer":
        if npc.schedule.current_task == "foraging_for_herbs":
            if not npc.schedule.current_path or len(npc.schedule.current_path) <= 1:
                world.add_message_to_chat_log(f"{world.get_entity_display_name(npc)} foraged some medicinal herbs.")
                amt = random.randint(2, 4)
                npc.economic.npc_inventory["medicinal_herb"] = npc.economic.npc_inventory.get("medicinal_herb", 0) + amt
                npc.schedule.current_task = TaskType.IDLE
                npc.schedule.current_destination_coords = None

        elif npc.schedule.current_task == "crafting_medical_supplies":
            if npc.schedule.current_destination_coords and (npc.x, npc.y) == npc.schedule.current_destination_coords:
                if not hasattr(npc, "task_timer") or npc.task_timer <= 0:
                    npc.task_timer = 5

                npc.task_timer -= 1
                if npc.task_timer <= 0:
                    if npc.economic.npc_inventory.get("medicinal_herb", 0) >= 2:
                        npc.economic.npc_inventory["medicinal_herb"] -= 2
                        if npc.economic.npc_inventory["medicinal_herb"] <= 0:
                            del npc.economic.npc_inventory["medicinal_herb"]
                        npc.craft_item("healing_salve", 1)
                        world.add_message_to_chat_log(f"{world.get_entity_display_name(npc)} crafted a healing salve.")
                    npc.schedule.current_task = TaskType.IDLE
                    npc.schedule.current_destination_coords = None

    if npc.schedule.current_task == "treating_patient":
        patient = world.get_entity_by_id(npc.task_target_entity_id)
        if not patient or patient.physical.is_dead or "broken_leg" not in patient.physical.status_effects:
            npc.schedule.current_task = TaskType.IDLE
            npc.task_target_entity_id = None
            return

        if abs(npc.x - patient.x) + abs(npc.y - patient.y) <= 1:
            if npc.task_timer > 0:
                npc.task_timer -= 1
            else:
                patient.physical.status_effects.remove("broken_leg")
                if patient.combat.body_parts_hp.get("left_leg", 0) <= 0:
                    patient.combat.body_parts_hp["left_leg"] = max(1, patient.combat.body_parts_max_hp.get("left_leg", 5))
                if patient.combat.body_parts_hp.get("right_leg", 0) <= 0:
                    patient.combat.body_parts_hp["right_leg"] = max(1, patient.combat.body_parts_max_hp.get("right_leg", 5))

                if patient.economic.money >= 10:
                    patient.economic.money -= 10
                    npc.economic.money += 10
                elif npc.economic.npc_inventory.get("healing_salve", 0) >= 1:
                    npc.economic.npc_inventory["healing_salve"] -= 1
                    if npc.economic.npc_inventory["healing_salve"] <= 0:
                        del npc.economic.npc_inventory["healing_salve"]

                world.add_message_to_chat_log(
                    f"{world.get_entity_display_name(npc)} successfully treats {world.get_entity_display_name(patient)}'s broken leg."
                )
                npc.schedule.current_task = TaskType.IDLE
                patient.schedule.current_task = TaskType.IDLE
                patient.speed = getattr(patient, "original_speed", 1)
        else:
            if not npc.schedule.current_path or len(npc.schedule.current_path) <= 1:
                path = world.calculate_path(npc.x, npc.y, patient.x, patient.y)
                if path:
                    npc.schedule.current_path = path
