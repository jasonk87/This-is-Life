"""Medical-domain task transitions for injured NPCs and healer behavior."""

from __future__ import annotations
from simulation.systems.task_types import TaskType

import math
import random

from config import WORLD_HEIGHT, WORLD_WIDTH
from simulation.systems.illness import SICK_STATUS_EFFECT, recover_from_sickness

# Status effects that route an NPC into the seeking-healer/treatment flow.
# broken_leg and "sick" (illness.py) share this pipeline; each is cured with
# its own remedy item (healing_salve / herbal_remedy respectively) in the
# treating_patient completion block below.
TREATABLE_STATUS_EFFECTS = ("broken_leg", SICK_STATUS_EFFECT)


def _needs_treatment(entity) -> bool:
    return any(effect in entity.physical.status_effects for effect in TREATABLE_STATUS_EFFECTS)


def _settle_finished_forage(world, npc) -> bool:
    """Pay out a foraging walk that has finished, whatever state it ended in.

    This used to be keyed on catching the healer mid-flight: current_task still
    "foraging_for_herbs" and the remaining path down to one step. Movement
    consumes that last step and sets the task to IDLE itself, and it runs first,
    so the window was never observed. Traced on a healer, they walked the full
    twenty tiles, arrived, went idle, and their medicinal_herb count stayed at
    zero - whereupon the policy sent them straight back out to a fresh random
    spot. Foraging never once produced a herb, and herbs are the only input to
    both remedies, so every salve and every herbal remedy in the game came from
    a clinic's starting stock and could never be replaced.

    It also has to run before the healer picks their next task, not after: on
    the arrival tick that chooser would otherwise overwrite the target with a
    new random one, and the arrival would be lost again.
    """
    forage_target = getattr(npc, "forage_target_coords", None)
    if forage_target is None:
        return False
    reached = (npc.x, npc.y) == tuple(forage_target)
    walk_finished = not npc.schedule.current_path
    if not (reached or walk_finished):
        return False

    world.add_message_to_chat_log(
        f"{world.get_entity_display_name(npc)} foraged some medicinal herbs."
    )
    gathered = random.randint(2, 4)
    inventory = npc.economic.npc_inventory
    inventory["medicinal_herb"] = inventory.get("medicinal_herb", 0) + gathered
    npc.forage_target_coords = None
    if npc.schedule.current_task == "foraging_for_herbs":
        npc.schedule.current_task = TaskType.IDLE
        npc.schedule.current_destination_coords = None
    return True


def update_npc_medical_state(world, npc) -> None:
    """Advance one NPC's medical/injury/treatment task logic."""
    if "broken_leg" in npc.physical.status_effects:
        if not hasattr(npc, "original_speed"):
            npc.original_speed = getattr(npc, "speed", 1)
        npc.speed = max(0.5, getattr(npc, "original_speed", 1) / 2.0)
        if npc.schedule.current_task in ["resting_in_bed", TaskType.SLEEPING]:
            rest_ticks = getattr(npc, "_bed_rest_recovery_ticks", 0) + 1
            npc._bed_rest_recovery_ticks = rest_ticks
            if rest_ticks >= 2400:
                npc.physical.status_effects.remove("broken_leg")
                npc.speed = getattr(npc, "original_speed", 1)
                npc._bed_rest_recovery_ticks = 0

    if _needs_treatment(npc):
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
    elif npc.schedule.current_task in ["seeking_healer", "waiting_for_treatment", "resting_in_bed"]:
        npc.schedule.current_task = TaskType.IDLE
        npc.schedule.current_path = []
        npc.schedule.current_destination_coords = None

    if npc.schedule.current_task == "seeking_healer":
        if not npc.schedule.current_path or len(npc.schedule.current_path) <= 1:
            if npc.schedule.current_destination_coords:
                if abs(npc.x - npc.schedule.current_destination_coords[0]) + abs(npc.y - npc.schedule.current_destination_coords[1]) <= 3:
                    npc.schedule.current_task = "waiting_for_treatment"
                    npc.schedule.current_path = []
                    npc.schedule.current_destination_coords = None

    if npc.economic.profession == "Healer":
        _settle_finished_forage(world, npc)

    if npc.economic.profession == "Healer":
        if npc.schedule.current_task not in ["treating_patient", "foraging_for_herbs", "crafting_medical_supplies"]:
            patients = [p for p in world.all_npcs if not p.physical.is_dead and _needs_treatment(p)]
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
                # Keep both remedies stocked - healing_salve (broken_leg) and
                # herbal_remedy (sick) share the same forage-then-craft loop.
                needed_remedy = None
                if npc.economic.npc_inventory.get("healing_salve", 0) < 5:
                    needed_remedy = "healing_salve"
                elif npc.economic.npc_inventory.get("herbal_remedy", 0) < 5:
                    needed_remedy = "herbal_remedy"

                if needed_remedy:
                    herbs_count = npc.economic.npc_inventory.get("medicinal_herb", 0)
                    if herbs_count < 2:
                        npc.schedule.current_task = "foraging_for_herbs"
                        angle = random.uniform(0, 2 * math.pi)
                        dist = random.uniform(10, 20)
                        target_x = max(0, min(WORLD_WIDTH - 1, int(npc.x + math.cos(angle) * dist)))
                        target_y = max(0, min(WORLD_HEIGHT - 1, int(npc.y + math.sin(angle) * dist)))
                        npc.schedule.current_destination_coords = (target_x, target_y)
                        # Remembered separately from the task, because the task
                        # is not what the payout can be keyed on - see below.
                        npc.forage_target_coords = (target_x, target_y)
                        path = world.calculate_path(npc.x, npc.y, target_x, target_y)
                        if path:
                            npc.schedule.current_path = path
                        else:
                            npc.schedule.current_task = TaskType.IDLE
                    else:
                        npc.schedule.current_task = "crafting_medical_supplies"
                        npc.task_context_data = {"remedy": needed_remedy}
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

        elif npc.schedule.current_task == "crafting_medical_supplies":
            if npc.schedule.current_destination_coords and (npc.x, npc.y) == npc.schedule.current_destination_coords:
                if not hasattr(npc, "task_timer") or npc.task_timer <= 0:
                    npc.task_timer = 5

                npc.task_timer -= 1
                if npc.task_timer <= 0:
                    if npc.economic.npc_inventory.get("medicinal_herb", 0) >= 2:
                        remedy = getattr(npc, "task_context_data", None) or {}
                        remedy_item = remedy.get("remedy", "healing_salve")
                        remedy_label = "herbal remedy" if remedy_item == "herbal_remedy" else "healing salve"
                        # Inventory drops a key the moment it reaches zero, so
                        # reading it back after the decrement raises. Third time
                        # this pattern has bitten (the bakery's last sack of
                        # flour, the healer's last salve, now the last two
                        # herbs); it was unreachable until foraging started
                        # producing herbs at all.
                        npc.economic.npc_inventory["medicinal_herb"] -= 2
                        if npc.economic.npc_inventory.get("medicinal_herb", 0) <= 0:
                            npc.economic.npc_inventory.pop("medicinal_herb", None)
                        npc.craft_item(remedy_item, 1)
                        world.add_message_to_chat_log(f"{world.get_entity_display_name(npc)} crafted a {remedy_label}.")
                    npc.schedule.current_task = TaskType.IDLE
                    npc.schedule.current_destination_coords = None
                    npc.task_context_data = None

    if npc.schedule.current_task == "treating_patient":
        patient = world.get_entity_by_id(npc.task_target_entity_id)
        if not patient or patient.physical.is_dead or not _needs_treatment(patient):
            npc.schedule.current_task = TaskType.IDLE
            npc.task_target_entity_id = None
            return

        if abs(npc.x - patient.x) + abs(npc.y - patient.y) <= 1:
            if npc.task_timer > 0:
                npc.task_timer -= 1
            else:
                # Instant, full cure per visit (first-pass design: no
                # partial/multi-session recovery) - treats every treatable
                # ailment the patient currently has in one visit.
                treated = []
                if "broken_leg" in patient.physical.status_effects:
                    patient.physical.status_effects.remove("broken_leg")
                    if patient.combat.body_parts_hp.get("left_leg", 0) <= 0:
                        patient.combat.body_parts_hp["left_leg"] = max(1, patient.combat.body_parts_max_hp.get("left_leg", 5))
                    if patient.combat.body_parts_hp.get("right_leg", 0) <= 0:
                        patient.combat.body_parts_hp["right_leg"] = max(1, patient.combat.body_parts_max_hp.get("right_leg", 5))
                    treated.append(("broken leg", "healing_salve"))
                if SICK_STATUS_EFFECT in patient.physical.status_effects:
                    recover_from_sickness(patient)
                    treated.append(("sickness", "herbal_remedy"))
                    drift = getattr(world, "_apply_illness_recovery_trait_drift", None)
                    if callable(drift):
                        drift(patient)

                if patient.economic.money >= 10:
                    patient.economic.money -= 10
                    npc.economic.money += 10
                else:
                    for _, remedy_item in treated:
                        if npc.economic.npc_inventory.get(remedy_item, 0) >= 1:
                            npc.economic.npc_inventory[remedy_item] -= 1
                            # Read it back with .get. Inventory drops a key the
                            # moment its quantity reaches zero, so spending the
                            # healer's last salve removed the key and the next
                            # line raised KeyError - crashing the tick that
                            # treated the patient. The same fault was fixed in
                            # World._produce_sub_task_output; this copy only
                            # became reachable once villages generated a clinic
                            # and could employ a Healer to spend anything.
                            if npc.economic.npc_inventory.get(remedy_item, 0) <= 0:
                                npc.economic.npc_inventory.pop(remedy_item, None)
                            break

                ailment_summary = " and ".join(name for name, _ in treated) if treated else "ailment"
                world.add_message_to_chat_log(
                    f"{world.get_entity_display_name(npc)} successfully treats {world.get_entity_display_name(patient)}'s {ailment_summary}."
                )
                npc.schedule.current_task = TaskType.IDLE
                patient.schedule.current_task = TaskType.IDLE
                patient.speed = getattr(patient, "original_speed", 1)
        else:
            if not npc.schedule.current_path or len(npc.schedule.current_path) <= 1:
                path = world.calculate_path(npc.x, npc.y, patient.x, patient.y)
                if path:
                    npc.schedule.current_path = path
