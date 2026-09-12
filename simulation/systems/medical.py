"""Medical-domain task transitions for injured NPCs and healer behavior."""

from __future__ import annotations
from simulation.systems.task_types import TaskType

import math
import random

from config import WORLD_HEIGHT, WORLD_WIDTH
from data.items import ITEM_DEFINITIONS
from simulation.systems.illness import SICK_STATUS_EFFECT, recover_from_sickness
from simulation.systems.body_combat import can_act, functions_for, needs_wound_treatment, treat

# Status effects that route an NPC into the seeking-healer/treatment flow.
# broken_leg and "sick" (illness.py) share this pipeline; each is cured with
# its own remedy item (healing_salve / herbal_remedy respectively) in the
# treating_patient completion block below.
TREATABLE_STATUS_EFFECTS = ("broken_leg", SICK_STATUS_EFFECT)


def _needs_treatment(entity) -> bool:
    if entity.combat.anatomy.body_plan:
        return needs_wound_treatment(entity) or SICK_STATUS_EFFECT in entity.physical.status_effects
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
    if getattr(npc, "animal_type", None):
        return  # Injured wildlife does not know to walk into a human clinic.
    if not can_act(npc):
        return
    body = npc.combat.anatomy
    if body.body_plan:
        if (needs_wound_treatment(npc) and world.game_time >= body.treatment_ready_tick
                and world.game_time-body.last_attacked_tick > 10):
            if treat(world, npc, npc):
                body.treatment_ready_tick = world.game_time + 20
                _cancel_work_for_care(world, npc)
        if not _needs_treatment(npc) and needs_recovery(npc):
            _rest_for_recovery(world, npc)
            return
        if npc.schedule.current_task == "recovering_from_injury" and not needs_recovery(npc):
            npc.schedule.current_task = TaskType.IDLE
            npc.schedule.current_path = []
            npc.schedule.current_destination_coords = None
    if "broken_leg" in npc.physical.status_effects and not npc.combat.anatomy.body_plan:
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
        _cancel_work_for_care(world, npc)
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
        if npc.schedule.current_task == "collecting_medical_supplies":
            _collect_wound_supply(world, npc, getattr(npc, "medical_supply_key", "bandage"))
            return

    if npc.economic.profession == "Healer":
        if npc.schedule.current_task not in ["treating_patient", "foraging_for_herbs", "crafting_medical_supplies"]:
            patients = [p for p in [*world.all_npcs, world.player] if p is not npc and not getattr(p, "animal_type", None) and not p.physical.is_dead and _needs_treatment(p)]
            if patients:
                patients = [p for p in patients if abs(npc.x-p.x)+abs(npc.y-p.y) < 15]
            if patients and not any(_safe_to_approach_patient(world, npc, p) for p in patients):
                npc.schedule.current_task = "waiting_for_safe_treatment"
                npc.schedule.current_path = []
                npc.schedule.current_destination_coords = None
                return
            patients = [p for p in patients if _safe_to_approach_patient(world, npc, p)]
            if patients:
                closest_patient = min(patients, key=lambda p: (
                    can_act(p), getattr(p.combat.anatomy, "blood", 1),
                    abs(npc.x - p.x) + abs(npc.y - p.y)))
                if abs(npc.x - closest_patient.x) + abs(npc.y - closest_patient.y) < 15:
                    if needs_wound_treatment(closest_patient):
                        wounds = closest_patient.combat.anatomy.wounds
                        bleeding = any(w.bleeding and not w.dressed and w.healing < .9 for w in wounds)
                        key = "bandage" if bleeding else "splint"
                        ready = npc.economic.npc_inventory.get(key, 0) > 0 or (bleeding and npc.economic.npc_inventory.get("healing_salve", 0) > 0)
                        if not ready and not _collect_wound_supply(world, npc, key):
                            return
                    npc.schedule.current_task = "treating_patient"
                    npc.task_target_entity_id = closest_patient.id
                    npc.task_timer = 20
                    npc.schedule.current_path = []
                    if abs(npc.x - closest_patient.x) + abs(npc.y - closest_patient.y) > 1:
                        if closest_patient.combat.anatomy.body_plan:
                            from simulation.systems.combat_response import approach
                            approach(world, npc, closest_patient.x, closest_patient.y)
                        else:
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
                if patient.combat.anatomy.body_plan and needs_wound_treatment(patient):
                    treated = treat(world, npc, patient)
                    if treated and patient is not npc and patient.economic.money >= 10:
                        patient.economic.money -= 10
                        npc.economic.money += 10
                    npc.task_timer = 20
                    npc.schedule.current_task = TaskType.IDLE
                    return
                # Instant, full cure per visit (first-pass design: no
                # partial/multi-session recovery) - treats every treatable
                # ailment the patient currently has in one visit.
                treated = []
                if "broken_leg" in patient.physical.status_effects and not patient.combat.anatomy.body_plan:
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
                if patient.combat.anatomy.body_plan:
                    from simulation.systems.combat_response import approach
                    approach(world, npc, patient.x, patient.y)
                else:
                    path = world.calculate_path(npc.x, npc.y, patient.x, patient.y)
                    if path:
                        npc.schedule.current_path = path


def _safe_to_approach_patient(world, healer, patient):
    emergency = getattr(healer, "wildlife_emergency", None)
    if not emergency or world.game_time > emergency["expires"]:
        return True
    threat = world.get_entity_by_id(emergency["threat_id"])
    if threat is None or threat.physical.is_dead:
        return True
    # Use what the healer last saw, not an unseen animal's current position.
    x, y = emergency["last_seen"]
    return max(abs(patient.x-x), abs(patient.y-y)) >= 8


def needs_recovery(actor):
    body = actor.combat.anatomy
    if not body.body_plan or (not body.wounds and body.blood >= .85):
        return False
    caps = functions_for(actor)
    return body.blood < .85 or caps["movement"] < .7 or caps["grip"] < .6


def _cancel_work_for_care(world, npc):
    resolver = getattr(world, "interaction_resolver", None)
    if resolver and getattr(npc.schedule, "active_interaction_id", None):
        resolver.cancel_actor_interaction(npc.id, world, reason="injury_treatment")
        npc.schedule.active_interaction_id = None


def _rest_for_recovery(world, npc):
    _cancel_work_for_care(world, npc)
    if npc.schedule.current_task == "recovering_from_injury":
        return
    npc.schedule.current_task = "recovering_from_injury"
    npc.schedule.current_path = []
    npc.schedule.current_destination_coords = None
    home = world.buildings_by_id.get(npc.schedule.home_building_id)
    if home and functions_for(npc)["movement"] > .2:
        destination = (home.global_center_x, home.global_center_y)
        path = world.calculate_path(npc.x, npc.y, *destination)
        if path:
            npc.schedule.current_path = path
            npc.schedule.current_destination_coords = destination
    from simulation.systems.body_combat import say
    say(world, f"{npc.name} stops working to recover from their injuries.", npc)


def _collect_wound_supply(world, healer, key):
    """Craft from owned materials, or fetch real stock from the healer's clinic."""
    inventory = healer.economic.npc_inventory
    clinic = world.buildings_by_id.get(healer.schedule.work_building_id)
    # Pre-existing saves may have salves/herbs but no newly introduced linen
    # bandages. Those are still valid dressing supplies, not a dead-end task.
    if key == "bandage" and inventory.get("bandage", 0) == 0:
        if inventory.get("healing_salve", 0) or inventory.get("medicinal_herb", 0) >= 2:
            key = "healing_salve"
        elif clinic and clinic.building_inventory.get("bandage", 0) == 0 and clinic.building_inventory.get("healing_salve", 0):
            key = "healing_salve"
    if inventory.get(key, 0) > 0:
        healer.schedule.current_task = TaskType.IDLE
        return True
    recipe = ITEM_DEFINITIONS[key]["crafting_recipe"]
    if all(inventory.get(item, 0) >= quantity for item, quantity in recipe.items()):
        for item, quantity in recipe.items():
            healer.remove_item(item, quantity)
        healer.craft_item(key, 1)
        healer.schedule.current_task = TaskType.IDLE
        return True
    if clinic and clinic.building_inventory.get(key, 0) > 0:
        destination = (clinic.global_center_x, clinic.global_center_y)
        if max(abs(healer.x-destination[0]), abs(healer.y-destination[1])) <= 2:
            ref = clinic.building_inventory.pop_item_reference(key)
            if ref is not None:
                inventory.add_item_reference(ref)
                healer.schedule.current_task = TaskType.IDLE
                return True
        else:
            path = world.calculate_path(healer.x, healer.y, *destination)
            if path:
                healer.medical_supply_key = key
                healer.schedule.current_task = "collecting_medical_supplies"
                healer.schedule.current_path = path
                healer.schedule.current_destination_coords = destination
    elif healer.schedule.current_task == "collecting_medical_supplies":
        healer.schedule.current_task = TaskType.IDLE
        healer.schedule.current_path = []
        healer.schedule.current_destination_coords = None
    return False
