"""Daily humanoid schedule-policy transitions (work/home/leisure/social)."""

from __future__ import annotations

import random
from types import SimpleNamespace

from config import DAY_LENGTH_TICKS, WORK_END_TIME_RATIO, WORK_START_TIME_RATIO


def run_npc_proactive_help_seeking_policy(world, npc) -> bool:
    """Generate desperate-need quests and approach-player paths when NPCs need help."""
    needs_based_action_taken = False
    if not hasattr(npc, "active_quest") and random.random() < 0.1:
        critically_hungry = npc.physical.hunger >= 90
        critically_thirsty = npc.physical.thirst >= 90

        if critically_hungry or critically_thirsty:
            knows_food_source = "the tavern" in npc.knowledge.known_locations or "bakery" in npc.knowledge.known_locations
            knows_water_source = "the village well" in npc.knowledge.known_locations

            needs_help = False
            quest_item = None
            quest_count = 0

            if critically_hungry and not knows_food_source:
                npc.knowledge.help_needed = "food"
                needs_help = True
                quest_item = "raw_fish"
                quest_count = random.randint(3, 5)
            elif critically_thirsty and not knows_water_source:
                npc.knowledge.help_needed = "water"
                needs_help = True
                quest_item = "water_flask"
                quest_count = 1

            if needs_help and quest_item:
                quest_id = f"fetch_{quest_item}_{npc.id}_{world.game_time}"
                quest = SimpleNamespace(
                    id=quest_id,
                    title=f"A Desperate Need for {quest_item.replace('_', ' ').title()}",
                    description=f"{npc.name} is in dire need of {quest_count} {quest_item.replace('_', ' ')}.",
                    type="fetch",
                    quest_giver_id=npc.id,
                    progress=0,
                    item_key=quest_item,
                    required_count=quest_count,
                    target_name_prefix=None,
                    required_kills=0,
                )
                setattr(npc, "active_quest", quest)
                world.add_message_to_chat_log(f"Debug: {npc.name} generated quest '{quest.title}'.")

            if needs_help and npc.id in world.npc_fov_maps and world.npc_fov_maps[npc.id][world.player.y, world.player.x]:
                npc.schedule.current_task = "approaching_player_for_help"
                dest_x, dest_y = world._find_best_adjacent_tile(world.player.x, world.player.y, npc)
                if dest_x is not None:
                    path = world.calculate_path(npc.x, npc.y, dest_x, dest_y)
                    if path:
                        npc.schedule.current_path = path
                        npc.schedule.current_destination_coords = (dest_x, dest_y)
                        needs_based_action_taken = True
    return needs_based_action_taken


def run_npc_crime_reporting_policy(world, npc) -> bool:
    """Advance crime-reporting task flow, including routing to the sheriff's office."""
    if npc.schedule.current_task != "going_to_report_crime":
        return False

    if npc.task_target_coords:
        if (npc.x, npc.y) == npc.task_target_coords:
            world.add_message_to_chat_log(world.text.entity_reports_your_crimes(npc))
            world.player.economic.bounty += 50
            world.add_message_to_chat_log(f"Your bounty has increased by 50. Total bounty: {world.player.economic.bounty}.")
            npc.schedule.current_task = "idle"
            npc.task_target_coords = None
        else:
            if not npc.schedule.current_path or npc.schedule.current_destination_coords != npc.task_target_coords:
                path = world.calculate_path(npc.x, npc.y, npc.task_target_coords[0], npc.task_target_coords[1])
                if path:
                    npc.schedule.current_path = path
                    npc.schedule.current_destination_coords = npc.task_target_coords
                else:
                    npc.schedule.current_task = "idle_confused"
    return True


def update_npc_daily_goal_policy(world, npc, current_time_in_day: int) -> None:
    """Apply branch-heavy daily goal selection and path assignment for one humanoid NPC."""
    new_task_label = None
    destination_coords = None

    is_at_home = False
    if npc.schedule.home_building_id:
        home_coords = world._get_building_global_center_coords(npc.schedule.home_building_id)
        if home_coords and (npc.x, npc.y) == home_coords:
            is_at_home = True

    is_at_work = False
    if npc.schedule.work_building_id:
        work_building = world.buildings_by_id.get(npc.schedule.work_building_id)
        if work_building:
            work_coords = (work_building.global_center_x, work_building.global_center_y)
            if work_coords and (npc.x, npc.y) == work_coords:
                is_at_work = True

    work_start_tick = DAY_LENGTH_TICKS * WORK_START_TIME_RATIO
    work_end_tick = DAY_LENGTH_TICKS * WORK_END_TIME_RATIO
    sleep_start_tick = DAY_LENGTH_TICKS * 0.85
    sleep_end_tick = DAY_LENGTH_TICKS * 0.15
    is_night_time = current_time_in_day >= sleep_start_tick or current_time_in_day < sleep_end_tick
    is_leisure_time = work_end_tick <= current_time_in_day < sleep_start_tick

    if work_start_tick <= current_time_in_day < work_end_tick:
        if npc.schedule.work_building_id and not is_at_work and npc.schedule.current_task != "going_to_work":
            dest_coords_temp = world._get_building_global_center_coords(npc.schedule.work_building_id)
            if dest_coords_temp:
                new_task_label = "going_to_work"
                destination_coords = dest_coords_temp
        elif npc.schedule.work_building_id and is_at_work:
            npc.schedule.current_task = "at work"
        elif npc.economic.profession.lower() == "unemployed" and npc.schedule.current_task != "looking_for_work":
            if random.random() < 0.02:
                npc_village = world._get_village_for_npc(npc)
                if npc_village:
                    workplaces = [b for b in npc_village.buildings if "workplace" in b.category]
                    if workplaces:
                        target_workplace = random.choice(workplaces)
                        dest_coords = (target_workplace.global_center_x, target_workplace.global_center_y)
                        if (npc.x, npc.y) != dest_coords:
                            new_task_label = "looking_for_work"
                            destination_coords = dest_coords
                            npc.leisure_timer = random.randint(50, 100)

    elif is_leisure_time and npc.schedule.current_task not in ["at_leisure", "going_to_tavern", "socializing", "going_home", "visiting_friend"]:
        if npc.leisure_timer > 0:
            npc.leisure_timer -= 1
        elif random.random() < 0.05:
            tavern = world._find_nearest_tavern(npc)
            if tavern:
                new_task_label = "going_to_tavern"
                destination_coords = (tavern.global_center_x, tavern.global_center_y)
        elif npc.economic.profession == "Town Official" and random.random() < 0.1:
            village = world._get_village_for_npc(npc)
            if village and "town_square_center" in village.interaction_points and npc.knowledge.known_events:
                event_to_shout = world._get_most_interesting_known_event(npc)
                if event_to_shout:
                    new_task_label = "crying_news"
                    destination_coords = village.interaction_points["town_square_center"][0]
                    npc.clear_work_sub_task_state(reset_sequence=True)
                    npc.task_target_entity_id = None
                    npc.task_context_data = event_to_shout.id
        elif random.random() < 0.1:
            potential_partners = [
                p for p in world.village_npcs
                if p.id != npc.id and not p.physical.is_dead and abs(npc.x - p.x) + abs(npc.y - p.y) < 20
            ]
            if potential_partners:
                weights = [max(1, npc.social.relationships.get(p.id, 50)) for p in potential_partners]
                chat_partner = random.choices(potential_partners, weights=weights, k=1)[0]
                new_task_label = "socializing"
                dest_x, dest_y = world._find_best_adjacent_tile(chat_partner.x, chat_partner.y, npc)
                if dest_x is not None:
                    destination_coords = (dest_x, dest_y)
                    npc.task_target_entity_id = chat_partner.id
                    npc.leisure_timer = random.randint(50, 150)
        elif random.random() < 0.1:
            world._start_npc_socialization(npc)
        elif random.random() < 0.05:
            friends = [n for n in world.village_npcs if n.id != npc.id and npc.social.relationships.get(n.id, 50) > 60]
            if friends:
                friend_to_visit = random.choice(friends)
                if friend_to_visit.schedule.home_building_id:
                    friend_home = world.buildings_by_id.get(friend_to_visit.schedule.home_building_id)
                    if friend_home:
                        new_task_label = "visiting_friend"
                        destination_coords = (friend_home.global_center_x, friend_home.global_center_y)
                        npc.task_target_entity_id = friend_to_visit.id
                        npc.leisure_timer = random.randint(100, 300)
        elif random.random() < 0.1 and npc.knowledge.known_locations:
            location_name, location_coords = random.choice(list(npc.knowledge.known_locations.items()))
            if location_coords != (npc.x, npc.y):
                new_task_label = "acting_on_knowledge"
                destination_coords = location_coords
                npc.leisure_timer = random.randint(100, 200)
                npc.task_context_data = {
                    "knowledge_target_name": location_name,
                    "knowledge_target_coords": location_coords,
                }
        elif random.random() < 0.05 or npc.economic.profession == "Fisherman":
            npc_village = world._get_village_for_npc(npc)
            if npc_village and "fishing_spot" in npc_village.interaction_points:
                fishing_spot = random.choice(npc_village.interaction_points["fishing_spot"])
                new_task_label = "working_fishing" if npc.economic.profession == "Fisherman" else "leisure_fishing"
                destination_coords = fishing_spot
                npc.leisure_timer = random.randint(100, 300)

    if npc.schedule.current_task == "working_fishing" and (npc.x, npc.y) == destination_coords:
        world.npc_attempt_fish(npc, npc.x, npc.y)
    elif npc.schedule.current_task == "crying_news" and (npc.x, npc.y) == destination_coords:
        event_id_to_shout = npc.task_context_data
        event_to_shout = npc.knowledge.known_events.get(event_id_to_shout)
        if not event_to_shout and npc.knowledge.known_events:
            event_to_shout = list(npc.knowledge.known_events.values())[-1]
        if event_to_shout:
            world.broadcast_news(npc, 15, event_to_shout)
        npc.schedule.current_task = "idle"
        npc.leisure_timer = 50
        npc.task_context_data = None
    elif is_night_time and npc.schedule.home_building_id and npc.schedule.current_task not in ["sleeping", "going_home_to_sleep"]:
        home_building_obj = world.buildings_by_id.get(npc.schedule.home_building_id)
        if home_building_obj:
            sleep_spot_coords = home_building_obj.interaction_points.get("sleep_spot")
            if is_at_home:
                if sleep_spot_coords and (npc.x, npc.y) == sleep_spot_coords:
                    npc.schedule.current_task = "sleeping"
                elif sleep_spot_coords and (npc.x, npc.y) != sleep_spot_coords:
                    new_task_label = "going_to_bed"
                    destination_coords = sleep_spot_coords
                elif not sleep_spot_coords and world._building_contains_item_with_interaction(home_building_obj, "sleep"):
                    npc.schedule.current_task = "sleeping"
            else:
                if sleep_spot_coords:
                    new_task_label = "going_home_to_sleep"
                    destination_coords = sleep_spot_coords
                else:
                    dest_coords_temp = world._get_building_global_center_coords(npc.schedule.home_building_id)
                    if dest_coords_temp:
                        new_task_label = "going_home"
                        destination_coords = dest_coords_temp
    elif npc.schedule.home_building_id and not is_at_home and npc.schedule.current_task not in ["going_home", "going_home_to_sleep", "sleeping"]:
        dest_coords_temp = world._get_building_global_center_coords(npc.schedule.home_building_id)
        if dest_coords_temp:
            new_task_label = "going_home"
            destination_coords = dest_coords_temp

    if npc.schedule.current_task == "sleeping" and not is_night_time:
        npc.schedule.current_task = "at_home"
    elif npc.schedule.current_task == "seeking_partner":
        potential_partners = [
            p for p in world.village_npcs
            if p.id != npc.id and not p.physical.is_dead and p.age > 18 and not p.social.family_ties.get("partner_id")
            and world._get_village_for_npc(p) == world._get_village_for_npc(npc)
        ]
        if potential_partners:
            weights = [max(1, npc.social.relationships.get(p.id, 50)) for p in potential_partners]
            chosen_partner = random.choices(potential_partners, weights=weights, k=1)[0]
            world.add_message_to_chat_log(f"Debug: {npc.name} is considering courting {chosen_partner.name}.")
            dest_x, dest_y = world._find_best_adjacent_tile(chosen_partner.x, chosen_partner.y, npc)
            if dest_x is not None:
                destination_coords = (dest_x, dest_y)
                new_task_label = "courting"
                npc.task_target_entity_id = chosen_partner.id
        else:
            npc.schedule.current_task = "idle"
    elif is_leisure_time and npc.age > 18 and not npc.social.family_ties.get("partner_id"):
        if random.random() < 0.01:
            npc.schedule.current_task = "seeking_partner"

    is_day_leisure_time = not is_night_time and not (work_start_tick <= current_time_in_day < work_end_tick)
    if not new_task_label and is_day_leisure_time and random.random() < 0.01:
        npc_village = None
        for row in world.chunks:
            for chk in row:
                if chk.village and npc.schedule.home_building_id and world.buildings_by_id.get(npc.schedule.home_building_id) in chk.village.buildings:
                    npc_village = chk.village
                    break
            if npc_village:
                break

        if npc_village and "well" in npc_village.interaction_points and npc_village.interaction_points["well"]:
            well_coords = random.choice(npc_village.interaction_points["well"])
            if (npc.x, npc.y) != well_coords:
                new_task_label = "fetching water"
                destination_coords = well_coords
            else:
                npc.schedule.current_task = "at_well"

    if new_task_label and destination_coords:
        if (npc.x, npc.y) == destination_coords:
            if new_task_label == "going_to_work":
                npc.schedule.current_task = "at work"
            elif new_task_label == "going_home":
                npc.schedule.current_task = "at_home"
            else:
                npc.schedule.current_task = "idle"
        else:
            path = world.calculate_path(npc.x, npc.y, destination_coords[0], destination_coords[1])
            if path:
                npc.schedule.current_path = path
                npc.schedule.current_destination_coords = destination_coords
                npc.schedule.current_task = new_task_label
                if new_task_label not in ["going_to_work", "at work"]:
                    npc.clear_work_sub_task_state(reset_sequence=True)
            else:
                npc.schedule.current_task = "idle_confused"
