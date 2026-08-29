"""Daily humanoid schedule-policy transitions (work/home/leisure/social)."""

from __future__ import annotations
from simulation.activity import start_activity
from simulation.systems.task_types import TaskType

import random
from types import SimpleNamespace

from config import DAY_LENGTH_TICKS, WORK_END_TIME_RATIO, WORK_START_TIME_RATIO
from data.items import ITEM_DEFINITIONS
from simulation.systems.economy import process_traveling_merchant_village_trade
from simulation.systems.incidents import run_town_crier_broadcast
from simulation.systems.social_reaction import (
    _calculate_presence_score,
    apply_known_history_fact_reactions,
    evaluate_social_reaction_stance,
)
from simulation.systems.utility_ai import evaluate_needs_utility


def _is_coordinate_pair(coords) -> bool:
    return (
        isinstance(coords, (tuple, list))
        and len(coords) == 2
        and all(isinstance(value, int) for value in coords)
    )


def run_npc_presence_micro_reactions(world, npc) -> bool:
    """Subtle, non-disruptive reactions (facing/pausing) to high-presence nearby entities."""
    if not hasattr(npc, "task_context_data") or not isinstance(npc.task_context_data, dict):
        npc.task_context_data = {}

    last_reaction = npc.task_context_data.get("last_presence_reaction_tick", 0)

    # Cooldown check: 20-50 ticks to prevent spam/jitter
    if world.game_time < last_reaction + 35: # Use a fixed average or random baseline
        return False

    # Only react if in a low-priority, non-critical state
    if npc.schedule.current_task not in {TaskType.IDLE, TaskType.WANDERING, "socializing", "gathering_social", TaskType.AT_HOME}:
        return False

    max_presence = 0.0
    target_entity = None

    if hasattr(world, "get_entities_in_radius"):
        nearby = world.get_entities_in_radius(npc.x, npc.y, 8)
        for entity in nearby:
            if entity.id == npc.id:
                continue
            presence = _calculate_presence_score(world, entity)
            if presence > max_presence:
                max_presence = presence
                target_entity = entity

    if max_presence >= 15.0 and target_entity:
        # Prevent everyone reacting simultaneously (staggering)
        if random.random() < 0.3:
            npc.task_context_data["last_presence_reaction_tick"] = world.game_time

            # 1. Brief Pause (1-3 ticks)
            # We don't clear the path, we just set a pause timer
            npc.task_context_data["pause_until_tick"] = world.game_time + random.randint(1, 3)

            # 2. Facing Adjustment (conceptual, stores the target they are looking at)
            npc.task_context_data["look_target_id"] = target_entity.id
            npc.task_context_data["look_duration_ticks"] = random.randint(3, 8)

            return True

    return False


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
            npc.schedule.current_task = TaskType.IDLE
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


def run_npc_item_pickup_policy(world, npc) -> bool:
    """Decide whether a humanoid should interrupt idle flow to pick up a perceived item."""
    if not npc.knowledge.perceived_item_tiles or npc.schedule.current_task not in [TaskType.IDLE, TaskType.WANDERING, TaskType.AT_HOME, TaskType.AT_WORK]:
        return False

    best_item_score = 0
    best_item_action = None

    for item_x, item_y in npc.knowledge.perceived_item_tiles:
        if (item_x, item_y) in world.items_on_map and world.items_on_map[(item_x, item_y)]:
            item_key = next(iter(world.items_on_map[(item_x, item_y)]), None)
            if not item_key:
                continue
            item_def = ITEM_DEFINITIONS.get(item_key, {})

            score = 0

            value = item_def.get("value", 1)
            greed_factor = 1.0
            if npc.social.personality == "Greedy":
                greed_factor = 2.0
            elif npc.social.personality == "Generous":
                greed_factor = 0.5
            score += value * greed_factor

            if item_def.get("on_use", {}).get("reduces_hunger", 0) > 0:
                hunger_percent = npc.physical.hunger
                if hunger_percent > 50:
                    score += (hunger_percent - 50) * 0.5

            profession = npc.economic.profession.lower()
            item_name_lower = item_key.lower()
            if profession == "blacksmith" and ("ore" in item_name_lower or "ingot" in item_name_lower):
                score += 20
            if profession == "carpenter" and ("wood" in item_name_lower or "log" in item_name_lower):
                score += 20
            if profession == "fletcher" and ("feather" in item_name_lower or "arrow" in item_name_lower):
                score += 20
            if profession == "miller" and "wheat" in item_name_lower:
                score += 20
            if profession == "baker" and "flour" in item_name_lower:
                score += 20

            dist = abs(npc.x - item_x) + abs(npc.y - item_y)
            score -= dist * 0.2

            if score > 5 and score > best_item_score:
                best_item_score = score
                best_item_action = {
                    "target_coords": (item_x, item_y),
                    "item_key": item_key,
                }

    if not best_item_action:
        return False

    npc.schedule.current_task = "task_going_to_pickup_item"
    npc.task_target_coords = best_item_action["target_coords"]
    npc.task_target_item_details = {"item_key": best_item_action["item_key"]}
    npc.schedule.current_path = []
    if random.random() < 0.1:
        world.add_message_to_chat_log(
            f"({world.get_entity_display_name(npc)} spots {best_item_action['item_key']} and decides to take it.)"
        )
    return True


def run_npc_follower_catch_up_policy(world, npc) -> bool:
    """Catch up to follow target if too far, and track shared experience when near."""
    target_id = getattr(getattr(npc, "social", None), "follow_target_id", None)
    if target_id is None:
        return False

    target = world.get_entity_by_id(target_id)
    if target is None or getattr(getattr(target, "physical", None), "is_dead", False):
        npc.social.follow_target_id = None
        return False

    dist = abs(npc.x - target.x) + abs(npc.y - target.y)

    if dist <= 6:
        npc_hostile = getattr(getattr(npc, "combat", None), "is_hostile_to_player", False) or getattr(npc, "is_frightened", False)
        target_hostile = getattr(getattr(target, "combat", None), "is_hostile_to_player", False) or getattr(target, "is_frightened", False)
        if not npc_hostile and not target_hostile:
            current_ticks = npc.social.shared_experience_ticks.get(target.id, 0)
            npc.social.shared_experience_ticks[target.id] = current_ticks + 1
            if hasattr(target, "social"):
                target_ticks = target.social.shared_experience_ticks.get(npc.id, 0)
                target.social.shared_experience_ticks[npc.id] = target_ticks + 1

    role = getattr(getattr(npc, "social", None), "follow_role", None)
    catch_up_dist = 2 if role == "guard" else 4

    if dist > catch_up_dist:
        if npc.schedule.current_task == "following_target" and npc.schedule.current_path:
            dest = npc.schedule.current_destination_coords
            if dest and abs(dest[0] - target.x) + abs(dest[1] - target.y) <= 2:
                return True

        dest_x, dest_y = world._find_best_adjacent_tile(target.x, target.y, npc)
        if dest_x is not None:
            path = world.calculate_path(npc.x, npc.y, dest_x, dest_y)
            if path:
                npc.schedule.current_task = "following_target"
                npc.schedule.current_path = path
                npc.schedule.current_destination_coords = (dest_x, dest_y)
                return True

    if npc.schedule.current_task == "following_target":
        npc.schedule.current_task = TaskType.IDLE
        npc.schedule.current_path = []
        npc.schedule.current_destination_coords = None

    return False


def run_npc_follower_envelope_policy(world, npc) -> bool:
    """Keep follower in a local behavior envelope around target instead of doing daily goals."""
    target_id = getattr(getattr(npc, "social", None), "follow_target_id", None)
    if target_id is None:
        return False

    target = world.get_entity_by_id(target_id)
    if target is None:
        return False

    dist = abs(npc.x - target.x) + abs(npc.y - target.y)
    role = getattr(getattr(npc, "social", None), "follow_role", None)
    envelope_dist = 2 if role == "guard" else 4

    # If within envelope distance, we block daily goals but allow minimal movement if in the way
    if dist <= envelope_dist:
        _try_companion_conversation_trigger(world, npc, target)

        if npc.schedule.current_task not in {TaskType.IDLE, TaskType.WANDERING, "avoiding_crowding"}:
            return False

        if dist == 0:
            dest_x, dest_y = world._find_best_adjacent_tile(npc.x, npc.y, npc)
            if dest_x is not None:
                path = world.calculate_path(npc.x, npc.y, dest_x, dest_y)
                if path:
                    npc.schedule.current_task = "avoiding_crowding"
                    npc.schedule.current_path = path
                    npc.schedule.current_destination_coords = (dest_x, dest_y)
                    return True

        if random.random() < 0.05 and npc.schedule.current_task != "avoiding_crowding":
            threat = None
            if role == "guard":
                # Find the most threatening nearby entity to the target
                nearby_targets = [
                    entity for entity in [world.player, *world.village_npcs]
                    if getattr(entity, "id", None) not in {npc.id, target.id}
                    and not getattr(getattr(entity, "physical", None), "is_dead", False)
                    and abs(target.x - entity.x) + abs(target.y - entity.y) <= 8
                ]
                assessed = [(entity, evaluate_social_reaction_stance(world, target, entity)) for entity in nearby_targets]
                assessed = [item for item in assessed if item[1].stance in {"hostile", "fearful", "wary"}]
                if assessed:
                    def _stance_priority(stance: str) -> int:
                        return {"hostile": 3, "fearful": 2, "wary": 1}.get(stance, 0)
                    assessed.sort(key=lambda item: (_stance_priority(item[1].stance), item[1].threat_score), reverse=True)
                    threat = assessed[0][0]

            candidates = [
                (npc.x + dx, npc.y + dy)
                for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0))
                if abs((npc.x + dx) - target.x) + abs((npc.y + dy) - target.y) <= envelope_dist
            ]
            if candidates:
                if threat:
                    # Guard bias: pick the candidate closest to the threat, putting guard between target and threat
                    candidates.sort(key=lambda pos: abs(pos[0] - threat.x) + abs(pos[1] - threat.y))
                    dest = candidates[0]
                else:
                    dest = random.choice(candidates)

                tile = world.get_tile_at(dest[0], dest[1])
                if tile and getattr(tile, "passable", False):
                    npc.schedule.current_task = TaskType.WANDERING
                    npc.schedule.current_path = [dest]
                    npc.schedule.current_destination_coords = dest

        return True

    return False


def _try_companion_conversation_trigger(world, npc, target) -> None:
    """Modestly bias conversation frequency for companions traveling/idling together."""
    if getattr(npc, "conversation_partner_id", None) is not None:
        return
    if getattr(target, "conversation_partner_id", None) is not None:
        return
    if getattr(npc, "conversation_cooldown", 0) > 0 or getattr(target, "conversation_cooldown", 0) > 0:
        return
    if random.random() < 0.005:  # ~0.5% chance per tick when near
        npc.conversation_partner_id = target.id
        target.conversation_partner_id = npc.id
        if hasattr(world, "game_time"):
            npc.last_conversation_time = world.game_time
            target.last_conversation_time = world.game_time


def run_npc_humanoid_scheduling_flow(world, npc, current_time_in_day: int) -> None:
    """Run humanoid scheduling policies in their existing priority order."""
    run_town_crier_broadcast(world, npc)

    # Check for micro-reactions (like facing/pausing) to nearby presence
    run_npc_presence_micro_reactions(world, npc)

    # Known structured history facts can create lightweight social pressure.
    apply_known_history_fact_reactions(world, npc)

    current_day = world.game_time // DAY_LENGTH_TICKS
    if run_npc_grudge_suspicion_policy(world, npc, current_day):
        return
    if run_npc_grudge_escalation_policy(world, npc, current_day):
        return
    if run_npc_social_reaction_policy(world, npc):
        return

    # Utility-based needs can override routine schedules, but not immediate
    # social-threat reactions or other critical state set before scheduling.
    if evaluate_needs_utility(world, npc):
        return
    if run_npc_follower_catch_up_policy(world, npc):
        return
    if run_npc_social_gathering_policy(world, npc):
        return
    run_npc_proactive_help_seeking_policy(world, npc)
    run_npc_crime_reporting_policy(world, npc)
    run_npc_item_pickup_policy(world, npc)
    if run_npc_follower_envelope_policy(world, npc):
        return
    if run_npc_mobile_conversation_policy(world, npc):
        return
    if run_npc_furniture_interaction_policy(world, npc):
        return
    update_npc_daily_goal_policy(world, npc, current_time_in_day)


def run_npc_furniture_interaction_policy(world, npc) -> bool:
    """Occasionally have idle/at_home/at_work NPCs sit on chairs or work at anvils/desks."""
    if npc.schedule.current_task in {TaskType.SITTING, TaskType.FORGING}:
        current_activity = getattr(npc, "current_activity", None)
        if current_activity is not None:
            npc.leisure_timer = max(0, current_activity.duration_ticks - current_activity.progress_ticks)
            if getattr(world, "game_time", 0) % 40 != 0:
                return True
        if getattr(world, "game_time", 0) % 40 == 0:
            from engine import FloatingTextEffect
            if npc.schedule.current_task == TaskType.SITTING:
                world.visual_effects.append(FloatingTextEffect(npc.x, npc.y, "*resting*", color=(150, 200, 150)))
            else:
                world.visual_effects.append(FloatingTextEffect(npc.x, npc.y, "*hammering*", color=(200, 200, 200)))
        if npc.leisure_timer > 0:
            npc.leisure_timer -= 1
            if getattr(npc, "is_sitting", False) and npc.schedule.current_task != TaskType.SITTING:
                 # Stand up if task interrupted
                 npc.is_sitting = False
                 npc.sitting_on_object_at = None
            return True
        else:
            npc.schedule.current_task = TaskType.IDLE
            npc.is_sitting = False
            npc.sitting_on_object_at = None
            return False

    if getattr(npc, "is_sitting", False) and npc.schedule.current_task not in {TaskType.SITTING, TaskType.FORGING}:
        npc.is_sitting = False
        npc.sitting_on_object_at = None

    if npc.schedule.current_task not in {TaskType.IDLE, TaskType.AT_HOME, TaskType.AT_WORK} or npc.schedule.current_path:
        return False

    if random.random() >= 0.05:
        return False

    # Look for adjacent furniture to interact with
    candidate_offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    for dx, dy in candidate_offsets:
        target_x, target_y = npc.x + dx, npc.y + dy
        tile = world.get_tile_at(target_x, target_y)
        if not tile or not hasattr(tile, "properties"):
            continue
        hint = tile.properties.get("interaction_hint")
        if hint == "sit":
            npc.schedule.current_task = TaskType.SITTING
            npc.is_sitting = True
            npc.sitting_on_object_at = (target_x, target_y)
            npc.leisure_timer = random.randint(30, 80)
            start_activity(
                npc,
                "sitting",
                npc.leisure_timer,
                world=world,
                location=(npc.x, npc.y),
                anchor_coords=(target_x, target_y),
                allows_conversation=True,
                allows_observation=True,
                allows_social_sharing=True,
                interruptible=True,
                metadata={"clear_sitting_on_complete": True, "set_task_on_complete": TaskType.IDLE},
            )
            return True
        elif hint == "forge" and npc.schedule.current_task == TaskType.AT_WORK:
            npc.schedule.current_task = TaskType.FORGING
            npc.leisure_timer = random.randint(20, 50)
            start_activity(
                npc,
                "forging",
                npc.leisure_timer,
                world=world,
                location=(npc.x, npc.y),
                anchor_coords=(target_x, target_y),
                allows_conversation=True,
                allows_observation=True,
                allows_social_sharing=True,
                interruptible=True,
                metadata={"set_task_on_complete": TaskType.AT_WORK},
            )
            return True
        elif hint == "read" and npc.schedule.current_task in {TaskType.IDLE, TaskType.AT_HOME}:
            # Simulating reading by looking at it for a while
            npc.schedule.current_task = TaskType.IDLE # Just pause essentially
            npc.leisure_timer = random.randint(20, 50)
            return True

    return False


def run_npc_mobile_conversation_policy(world, npc) -> bool:
    """Allow active conversations to gently continue while moving, without fixed destinations."""
    if npc.schedule.current_task == "mobile_conversation_follow":
        if not getattr(npc.schedule, "current_path", None):
            npc.schedule.current_task = TaskType.IDLE

    partner_id = getattr(npc, "conversation_partner_id", None)
    if partner_id is None:
        return False

    partner = world.get_entity_by_id(partner_id)
    if partner is None or getattr(getattr(partner, "physical", None), "is_dead", False):
        return False

    dist = abs(npc.x - partner.x) + abs(npc.y - partner.y)

    if dist > 6:
        return False

    if dist > 2:
        if npc.schedule.current_task in {TaskType.IDLE, TaskType.WANDERING, "socializing", "avoiding_crowding", "gathering_social", "socializing_at_focal_point", "mobile_conversation_follow"}:
            rel = getattr(getattr(npc, "social", None), "relationships", {}).get(partner_id, 50)
            shared = getattr(getattr(npc, "social", None), "shared_experience_ticks", {}).get(partner_id, 0)

            is_companion = getattr(getattr(npc, "social", None), "follow_target_id", None) == partner_id or \
                           getattr(getattr(partner, "social", None), "follow_target_id", None) == npc.id

            keep_up_chance = 0.5
            if is_companion:
                keep_up_chance = 0.9
            elif rel > 60 or shared > 50:
                keep_up_chance = 0.8

            context = getattr(npc, "task_context_data", None)
            if isinstance(context, dict) and context.get("social_context") == "gathering":
                keep_up_chance = min(1.0, keep_up_chance * 1.2)

            if random.random() < keep_up_chance:
                dest_x, dest_y = world._find_best_adjacent_tile(partner.x, partner.y, npc)
                if dest_x is not None:
                    if not npc.schedule.current_path or getattr(npc.schedule, "current_destination_coords", None) != (dest_x, dest_y):
                        path = world.calculate_path(npc.x, npc.y, dest_x, dest_y)
                        if path:
                            npc.schedule.current_task = "mobile_conversation_follow"
                            npc.schedule.current_path = path
                            npc.schedule.current_destination_coords = (dest_x, dest_y)
                            return True

    return False


def run_npc_social_reaction_policy(world, npc) -> bool:
    """React to nearby visible social threats in an entity-agnostic way."""
    if npc.schedule.current_task not in [TaskType.IDLE, TaskType.WANDERING, TaskType.AT_HOME, TaskType.AT_WORK] or npc.schedule.current_path:
        return False

    # Check if guarding someone
    target_id = getattr(getattr(npc, "social", None), "follow_target_id", None)
    role = getattr(getattr(npc, "social", None), "follow_role", None)
    guarded_target = None
    if target_id is not None and role == "guard":
        guarded_target = world.get_entity_by_id(target_id)
        if guarded_target and getattr(getattr(guarded_target, "physical", None), "is_dead", False):
            guarded_target = None

    nearby_targets = [
        entity
        for entity in [world.player, *world.village_npcs]
        if getattr(entity, "id", None) not in {npc.id, getattr(guarded_target, "id", None)}
        and not getattr(getattr(entity, "physical", None), "is_dead", False)
        and abs(npc.x - entity.x) + abs(npc.y - entity.y) <= 6
    ]
    if not nearby_targets:
        return False

    def _stance_priority(stance: str) -> int:
        return {"hostile": 3, "fearful": 2, "wary": 1}.get(stance, 0)

    assessed = []
    for entity in nearby_targets:
        assessment = evaluate_social_reaction_stance(world, npc, entity)

        # If guarding, also evaluate threat towards the guarded target
        if guarded_target:
            target_assessment = evaluate_social_reaction_stance(world, guarded_target, entity)
            if _stance_priority(target_assessment.stance) > _stance_priority(assessment.stance):
                # Upgrade guard's reaction to match the threat level towards their target
                # A guard becomes hostile to anyone their target finds hostile, and wary of those their target fears/is wary of
                if target_assessment.stance == "hostile":
                    assessment.stance = "hostile"
                elif target_assessment.stance in {"fearful", "wary"}:
                    assessment.stance = "wary"
                assessment.threat_score = max(assessment.threat_score, target_assessment.threat_score)

        assessed.append((entity, assessment))

    assessed.sort(key=lambda item: (_stance_priority(item[1].stance), item[1].threat_score), reverse=True)
    target, assessment = assessed[0]

    if assessment.stance == "wary":
        _emit_social_signal(world, npc, target, assessment.stance)
        # Lightweight hesitation: consume this tick to make attention shifts legible.
        return True
    if assessment.stance == "hostile":
        _emit_social_signal(world, npc, target, assessment.stance)
        if abs(npc.x - target.x) + abs(npc.y - target.y) <= 2:
            # Tension pause: hold position briefly when close to the target.
            return True
    if assessment.stance not in {"fearful", "hostile"}:
        return False

    _emit_social_signal(world, npc, target, assessment.stance)
    safe_spot = world.buildings_by_id.get(npc.schedule.home_building_id) or world._find_nearest_tavern(npc)
    if not safe_spot:
        return False
    dest_x, dest_y = world._find_best_adjacent_tile(safe_spot.global_center_x, safe_spot.global_center_y, npc)
    if dest_x is None:
        dest_x, dest_y = safe_spot.global_center_x, safe_spot.global_center_y
    path = world.calculate_path(npc.x, npc.y, dest_x, dest_y)
    if not path:
        return False
    npc.schedule.current_task = "avoiding_social_threat"
    npc.task_target_entity_id = getattr(target, "id", None)
    npc.schedule.current_path = path
    npc.schedule.current_destination_coords = (dest_x, dest_y)
    return True


def run_npc_social_gathering_policy(world, npc) -> bool:
    """Gather nearby NPCs around readable social focal points."""
    if npc.schedule.current_task == "socializing_at_focal_point":
        if npc.leisure_timer > 0:
            npc.leisure_timer -= 1
            if random.random() < 0.15:
                world._start_npc_socialization(npc)
            return True
        npc.schedule.current_task = TaskType.IDLE
        npc.task_context_data = None
        return False

    if npc.schedule.current_task not in {TaskType.IDLE, TaskType.WANDERING, TaskType.AT_HOME} or npc.schedule.current_path:
        return False
    if random.random() >= 0.08:
        return False
    focal = _select_social_focal_point(world, npc)
    if focal is None:
        return False
    dest = _select_gathering_slot(world, npc, focal["coords"])
    if dest is None:
        return False
    path = world.calculate_path(npc.x, npc.y, dest[0], dest[1])
    if not path:
        return False
    npc.schedule.current_task = "gathering_social"
    npc.schedule.current_destination_coords = dest
    npc.schedule.current_path = path
    npc.task_context_data = {"social_context": "gathering", "focal_kind": focal["kind"], "focal_coords": focal["coords"]}
    npc.leisure_timer = random.randint(40, 90)
    return True


def _select_social_focal_point(world, npc):
    tavern = world._find_nearest_tavern(npc)
    if tavern and abs(npc.x - tavern.global_center_x) + abs(npc.y - tavern.global_center_y) <= 24:
        return {"kind": "tavern", "coords": (tavern.global_center_x, tavern.global_center_y)}
    if npc.schedule.home_building_id:
        home = world.buildings_by_id.get(npc.schedule.home_building_id)
        if home:
            return {"kind": "home", "coords": (home.global_center_x, home.global_center_y)}
    village = world._get_village_for_npc(npc)
    if village and village.interaction_points.get("town_square_center"):
        return {"kind": "campfire", "coords": village.interaction_points["town_square_center"][0]}
    return None


def _select_gathering_slot(world, npc, focal_coords):
    fx, fy = focal_coords
    candidate_offsets = [(-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, -1), (-1, 1), (1, 1)]
    occupied = {
        (other.x, other.y)
        for other in world.village_npcs
        if not other.physical.is_dead and other.id != npc.id and other.schedule.current_task in {"gathering_social", "socializing_at_focal_point"}
    }
    for dx, dy in candidate_offsets:
        x, y = fx + dx, fy + dy
        if (x, y) in occupied:
            continue
        tile = world.get_tile_at(x, y)
        if tile is None or not tile.passable:
            continue
        return (x, y)
    return None


def _emit_social_signal(world, npc, target, stance: str) -> None:
    """Emit tiny observable social cues without introducing persistent state."""
    if not hasattr(world, "add_message_to_chat_log"):
        return
    player = getattr(world, "player", None)
    if player is None or getattr(player, "physical", None) is None or player.physical.is_dead:
        return
    distance_to_player = abs(npc.x - player.x) + abs(npc.y - player.y)
    if distance_to_player > 10:
        return
    if stance == "wary":
        world.add_message_to_chat_log(f"{world.get_entity_display_name(npc)} *glances uneasily* at {world.get_entity_display_name(target)}.")
    elif stance == "fearful":
        world.add_message_to_chat_log(f"{world.get_entity_display_name(npc)} *steps back* from {world.get_entity_display_name(target)}.")
    elif stance == "hostile":
        world.add_message_to_chat_log(f"{world.get_entity_display_name(npc)} *squares up* to {world.get_entity_display_name(target)}.")


def run_npc_grudge_suspicion_policy(world, npc, current_day: int) -> bool:
    """Apply grudge-driven suspicion behavior (avoidance/reporting) against known offenders."""
    npc.decay_grudges(current_day)
    player_id = getattr(getattr(world, "player", None), "id", None)
    if player_id is None:
        return False

    grudge = npc.social.grudges.get(player_id)
    if not grudge or getattr(grudge, "severity", 0) < 25:
        return False

    if npc.schedule.current_task in ["going_to_report_crime", "attacking_player", "combat_action_flee_from_player"]:
        return False

    player_visible = npc.id in world.npc_fov_maps and world.npc_fov_maps[npc.id][world.player.y, world.player.x]
    if not player_visible:
        return False

    if grudge.severity >= 70:
        sheriff_office = world._find_nearest_building_of_type(npc, "sheriff_office")
        if sheriff_office:
            npc.schedule.current_task = "going_to_report_crime"
            npc.task_target_coords = (sheriff_office.global_center_x, sheriff_office.global_center_y)
            npc.schedule.current_path = []
            return True
        return False

    safe_spot = world.buildings_by_id.get(npc.schedule.home_building_id) or world._find_nearest_tavern(npc)
    if not safe_spot:
        return False
    dest_x, dest_y = world._find_best_adjacent_tile(safe_spot.global_center_x, safe_spot.global_center_y, npc)
    if dest_x is None:
        return False
    path = world.calculate_path(npc.x, npc.y, dest_x, dest_y)
    if not path:
        return False
    npc.schedule.current_task = "avoiding_suspected_criminal"
    npc.schedule.current_path = path
    npc.schedule.current_destination_coords = (dest_x, dest_y)
    return True


# --- Grudge escalation (NPC-on-NPC) ---
# run_npc_grudge_suspicion_policy above only ever acts on a grudge held
# against the PLAYER (avoidance / reporting to the sheriff). Grudges held
# against other NPCs (e.g. from unpaid wages, witnessed crimes, or fear
# reactions to known history facts - see World.add_grudge's callers)
# previously just sat there passively affecting distrust/stance checks -
# they never actually did anything. This adds a real, deliberately rare
# escalation path for the worst, longest-held NPC-on-NPC grudges: spreading
# targeted negative gossip, or in rarer/more severe cases, a small act of
# sabotage (a bit of stolen/ruined money). Conservative by design - a high
# severity+age bar, low per-check odds, and at most one action per NPC per
# scheduling check - this should read as occasional, memorable friction
# between villagers, not constant NPC-vs-NPC warfare.
GRUDGE_ESCALATION_SEVERITY_THRESHOLD = 70   # matches the existing player-grudge "report to sheriff" bar
GRUDGE_ESCALATION_MIN_AGE_DAYS = 5          # a grudge needs to have simmered a while, not fire on day one
GRUDGE_ESCALATION_CHANCE_PER_CHECK = 0.03   # rare - most eligible grudges never escalate on any given check
GRUDGE_SABOTAGE_SEVERITY_THRESHOLD = 90     # only the very worst grudges risk sabotage rather than gossip
GRUDGE_SABOTAGE_CHANCE_MULTIPLIER = 0.25    # sabotage is rarer still than gossip, even once eligible
GRUDGE_SABOTAGE_MAX_MONEY_STOLEN = 15


def run_npc_grudge_escalation_policy(world, npc, current_day: int) -> bool:
    """Apply rare, severe NPC-on-NPC grudge escalation (targeted gossip or,
    more rarely, sabotage). Player-directed grudges are intentionally
    skipped here - those are already handled by
    run_npc_grudge_suspicion_policy just above, and mixing the two policies
    on the same grudge would risk conflicting/duplicate reactions."""
    grudges = getattr(getattr(npc, "social", None), "grudges", None)
    if not grudges:
        return False

    player = getattr(world, "player", None)
    player_id = getattr(player, "id", None)
    protected_tasks = {"going_to_report_crime", "attacking_player", "combat_action_flee_from_player", "jailed"}
    if npc.schedule.current_task in protected_tasks:
        return False

    for target_id, grudge in list(grudges.items()):
        if target_id == player_id:
            continue  # player-directed grudges: run_npc_grudge_suspicion_policy's job
        if getattr(grudge, "severity", 0) < GRUDGE_ESCALATION_SEVERITY_THRESHOLD:
            continue
        if (current_day - getattr(grudge, "created_day", current_day)) < GRUDGE_ESCALATION_MIN_AGE_DAYS:
            continue

        target = world.get_entity_by_id(target_id)
        if target is None or target is player:
            continue
        if getattr(getattr(target, "physical", None), "is_dead", False):
            continue
        if not hasattr(target, "economic") or not hasattr(target, "knowledge"):
            continue  # not a real NPC-shaped entity

        if random.random() >= GRUDGE_ESCALATION_CHANCE_PER_CHECK:
            continue

        if (
            grudge.severity >= GRUDGE_SABOTAGE_SEVERITY_THRESHOLD
            and random.random() < GRUDGE_SABOTAGE_CHANCE_MULTIPLIER
        ):
            _escalate_grudge_via_sabotage(world, npc, target)
        else:
            _escalate_grudge_via_gossip(world, npc, target)
        return True

    return False


def _escalate_grudge_via_gossip(world, npc, target) -> None:
    """The grudge-holder starts spreading unflattering rumors about the
    target - seeded as a memory in the gossiper's own knowledge, then left
    to propagate through the existing gossip-sharing machinery
    (KnowledgeComponent.choose_memories_to_share / ambient_info.py's
    sharing gate) exactly like any other memory, rather than building a
    separate propagation path just for this."""
    memory = world.create_memory_event(
        event_type="malicious_gossip",
        subject_id=target.id,
        target_id=npc.id,
        importance_score=25,
        headline=f"{world.get_entity_display_name(npc)} has been spreading unkind rumors about {world.get_entity_display_name(target)}.",
    )
    world.record_memory_event(npc, memory)
    world.add_message_to_chat_log(
        f"{world.get_entity_display_name(npc)} has been spreading unkind rumors about {world.get_entity_display_name(target)}."
    )


def _escalate_grudge_via_sabotage(world, npc, target) -> None:
    """The rarer, more severe escalation: a small, capped act of material
    sabotage (petty theft/damage) rather than just talk. The target learns
    who was responsible immediately (no separate detection/witness model
    for this first pass) so it can feed back into their own opinion of the
    saboteur via the usual reputation machinery."""
    stolen = min(GRUDGE_SABOTAGE_MAX_MONEY_STOLEN, max(0, getattr(target.economic, "money", 0)))
    if stolen > 0:
        target.economic.money -= stolen
        npc.economic.money += stolen

    memory = world.create_memory_event(
        event_type="petty_sabotage",
        subject_id=npc.id,
        target_id=target.id,
        importance_score=35,
        headline=f"{world.get_entity_display_name(target)}'s belongings were tampered with - {world.get_entity_display_name(npc)} is responsible.",
    )
    world.record_memory_event(target, memory)
    world.add_message_to_chat_log(
        f"{world.get_entity_display_name(target)}'s things have been tampered with..."
    )


def run_npc_traveling_merchant_policy(world, npc) -> None:
    """Run schedule-time travel and village trading behavior for traveling merchants."""
    if npc.economic.profession != "Traveling Merchant":
        return

    if npc.schedule.current_task == "traveling_to_village" and not npc.schedule.current_path:
        all_villages = []
        for y_chunk in range(world.chunk_height):
            for x_chunk in range(world.chunk_width):
                chunk = world.chunks[y_chunk][x_chunk]
                if chunk.village:
                    all_villages.append(chunk.village)

        if len(all_villages) > 1:
            current_village = world._get_village_for_npc(npc)
            target_village = random.choice([v for v in all_villages if v != current_village])

            if target_village and target_village.buildings:
                target_building = random.choice(target_village.buildings)
                dest_x = target_building.global_center_x
                dest_y = target_building.global_center_y

                path = world.calculate_path(npc.x, npc.y, dest_x, dest_y)
                if path:
                    npc.schedule.current_path = path
                    npc.schedule.current_destination_coords = (dest_x, dest_y)
                    current_village_id = getattr(current_village, "id", None) if current_village else None
                    npc.travel.is_traveling = True
                    npc.travel.origin_settlement_id = current_village_id
                    npc.travel.destination_settlement_id = getattr(target_village, "id", None)
                    npc.travel.eta_days = max(1, len(path) // max(1, DAY_LENGTH_TICKS // 4))
                    world.add_message_to_chat_log(f"{world.get_entity_display_name(npc)} is traveling to a new village.")
    elif npc.schedule.current_task == "lingering_in_village":
        if npc.leisure_timer > 0:
            npc.leisure_timer -= 1

            current_village = world._get_village_for_npc(npc, by_coords=True)
            if current_village and random.random() < 0.1:
                process_traveling_merchant_village_trade(world, npc, current_village)
        else:
            npc.schedule.current_task = "traveling_to_village"
    elif npc.schedule.current_task == TaskType.IDLE and random.random() < 0.1:
        npc.schedule.current_task = "traveling_to_village"


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
        if npc.economic.profession == "Child":
            # Ideation-audit item 4: children used to run the exact same
            # idle/wander loop as a jobless adult during work hours, since
            # "Child" falls into build_job_behavior's IdleBehavior bucket
            # (entities/human_behaviors.py) with no distinct behavior of
            # its own. Per Jason's design decision: follow a trackable
            # parent during work hours (reusing the family_ties data
            # already set at birth), re-checked by distance each tick
            # rather than a timer, so the child naturally trails behind as
            # the parent moves through their own workday. A child with no
            # trackable parent (deceased/migrated/pre-dates family_ties)
            # just falls through to this function's later logic (going
            # home, idling) instead of getting stuck.
            parent = world._find_trackable_parent(npc)
            if parent is not None:
                distance_to_parent = abs(npc.x - parent.x) + abs(npc.y - parent.y)
                if distance_to_parent > 3:
                    dest_x, dest_y = world._find_best_adjacent_tile(parent.x, parent.y, npc)
                    if dest_x is not None:
                        new_task_label = "following_parent"
                        destination_coords = (dest_x, dest_y)
        elif npc.schedule.work_building_id and not is_at_work and npc.schedule.current_task != TaskType.GOING_TO_WORK:
            dest_coords_temp = world._get_building_global_center_coords(npc.schedule.work_building_id)
            if dest_coords_temp:
                work_building_obj = world.buildings_by_id.get(npc.schedule.work_building_id)
                if work_building_obj:
                    # Guess ideal role based on profession
                    ideal_role = "workbench"
                    if npc.economic.profession in {"Mayor", "Scribe", "Town Official", "Sheriff"}:
                        ideal_role = "desk"
                    elif npc.economic.profession in {"Merchant", "Tavern Keeper", "Traveling Merchant"}:
                        ideal_role = "counter"

                    work_anchor = work_building_obj.get_anchor_coordinates(["work", "service"], world=world, requesting_entity=npc, ideal_role=ideal_role)
                    if work_anchor:
                        dest_coords_temp = work_building_obj.refine_anchor_coordinates(world, work_anchor[0], work_anchor[1], requesting_entity=npc)
                new_task_label = TaskType.GOING_TO_WORK
                destination_coords = dest_coords_temp
        elif npc.schedule.work_building_id and is_at_work:
            npc.schedule.current_task = TaskType.AT_WORK
        elif npc.economic.profession.lower() == "unemployed" and npc.schedule.current_task != TaskType.LOOKING_FOR_WORK:
            if random.random() < 0.02:
                npc_village = world._get_village_for_npc(npc)
                if npc_village:
                    workplaces = [b for b in npc_village.buildings if "workplace" in b.category]
                    if workplaces:
                        target_workplace = random.choice(workplaces)
                        dest_coords = (target_workplace.global_center_x, target_workplace.global_center_y)
                        if (npc.x, npc.y) != dest_coords:
                            new_task_label = TaskType.LOOKING_FOR_WORK
                            destination_coords = dest_coords
                            npc.leisure_timer = random.randint(50, 100)

    elif is_leisure_time and npc.economic.profession == "Child" and npc.schedule.current_task not in ["at_leisure", "playing_at_town_square", "following_parent", TaskType.GOING_HOME]:
        # Ideation-audit item 4, leisure half: town-square play during
        # leisure hours. Mirrors the existing tavern-going idiom directly
        # below (leisure_timer countdown, then a per-tick chance to head
        # to a shared social hub) rather than any of the adult
        # tavern/courting/social branches, none of which fit a child NPC
        # thematically. No dedicated "playing" activity system exists (or
        # is being built here) - the child simply occupies the town
        # square, which is enough for it to read as present and social
        # rather than invisible/idle during leisure hours.
        if npc.leisure_timer > 0:
            npc.leisure_timer -= 1
        elif random.random() < 0.1:
            village = world._get_village_for_npc(npc)
            if village and "town_square_center" in village.interaction_points:
                new_task_label = "playing_at_town_square"
                destination_coords = village.interaction_points["town_square_center"][0]
                npc.leisure_timer = random.randint(50, 100)
    elif (
        is_leisure_time
        and npc.economic.profession != "Child"
        and world._is_crowd_drawing_event_active()
        and npc.schedule.current_task not in ["at_leisure", "attending_festival", "going_to_tavern", "socializing", TaskType.GOING_HOME, "visiting_friend", "gathering_social", "socializing_at_focal_point"]
    ):
        # Ideation-audit item 6: while a 'draws_crowd' scheduled event (e.g.
        # Harvest Festival) is active, adults get an elevated per-tick
        # chance of heading to the town square instead of the ordinary
        # tavern/courting/social leisure branches below - a bigger draw
        # than the everyday 0.05 tavern chance, since a festival is
        # supposed to read as a village-wide event, not a background one.
        if npc.leisure_timer > 0:
            npc.leisure_timer -= 1
        elif random.random() < 0.25:
            village = world._get_village_for_npc(npc)
            if village and "town_square_center" in village.interaction_points:
                new_task_label = "attending_festival"
                destination_coords = village.interaction_points["town_square_center"][0]
                npc.leisure_timer = random.randint(30, 60)
    elif (
        is_leisure_time
        and npc.economic.profession != "Child"
        and npc.schedule.current_task not in ["at_leisure", "going_to_tavern", "socializing", TaskType.GOING_HOME, "visiting_friend", "gathering_social", "socializing_at_focal_point"]
    ):
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

    if npc.schedule.current_task == "going_to_social_anchor" and (npc.x, npc.y) == destination_coords:
        npc.schedule.current_task = TaskType.AT_HOME
        npc.leisure_timer = random.randint(50, 150)
    elif npc.schedule.current_task == "working_fishing" and (npc.x, npc.y) == destination_coords:
        world.npc_attempt_fish(npc, npc.x, npc.y)
    elif npc.schedule.current_task == "crying_news" and (npc.x, npc.y) == destination_coords:
        event_id_to_shout = npc.task_context_data
        event_to_shout = npc.knowledge.known_events.get(event_id_to_shout)
        if not event_to_shout and npc.knowledge.known_events:
            event_to_shout = list(npc.knowledge.known_events.values())[-1]
        if event_to_shout:
            world.broadcast_news(npc, 15, event_to_shout)
        npc.schedule.current_task = TaskType.IDLE
        npc.leisure_timer = 50
        npc.task_context_data = None
    elif is_night_time and npc.schedule.home_building_id and npc.schedule.current_task not in [TaskType.SLEEPING, TaskType.GOING_HOME_TO_SLEEP]:
        home_building_obj = world.buildings_by_id.get(npc.schedule.home_building_id)
        if home_building_obj:
            sleep_spot_coords = home_building_obj.interaction_points.get("sleep_spot")
            if not sleep_spot_coords:
                sleep_spot_coords = home_building_obj.get_anchor_coordinates("sleep", world=world, requesting_entity=npc, ideal_role="bed")
                if _is_coordinate_pair(sleep_spot_coords):
                    refined_sleep_spot = home_building_obj.refine_anchor_coordinates(world, sleep_spot_coords[0], sleep_spot_coords[1], requesting_entity=npc)
                    sleep_spot_coords = tuple(refined_sleep_spot) if _is_coordinate_pair(refined_sleep_spot) else tuple(sleep_spot_coords)
                elif not _is_coordinate_pair(sleep_spot_coords):
                    sleep_spot_coords = None
            if is_at_home:
                if sleep_spot_coords and (npc.x, npc.y) == sleep_spot_coords:
                    npc.schedule.current_task = TaskType.SLEEPING
                elif sleep_spot_coords and (npc.x, npc.y) != sleep_spot_coords:
                    new_task_label = TaskType.GOING_TO_BED
                    destination_coords = sleep_spot_coords
                elif not sleep_spot_coords and world._building_contains_item_with_interaction(home_building_obj, "sleep"):
                    npc.schedule.current_task = TaskType.SLEEPING
            else:
                if sleep_spot_coords:
                    new_task_label = TaskType.GOING_HOME_TO_SLEEP
                    destination_coords = sleep_spot_coords
                else:
                    dest_coords_temp = world._get_building_global_center_coords(npc.schedule.home_building_id)
                    if dest_coords_temp:
                        new_task_label = TaskType.GOING_HOME
                        destination_coords = dest_coords_temp
    elif npc.schedule.home_building_id and not is_at_home and npc.schedule.current_task not in [TaskType.GOING_HOME, TaskType.GOING_HOME_TO_SLEEP, TaskType.SLEEPING]:
        dest_coords_temp = world._get_building_global_center_coords(npc.schedule.home_building_id)
        if dest_coords_temp:
            home_building_obj = world.buildings_by_id.get(npc.schedule.home_building_id)
            if home_building_obj:
                sleep_anchor = home_building_obj.get_anchor_coordinates("sleep", world=world, requesting_entity=npc, ideal_role="bed")
                if _is_coordinate_pair(sleep_anchor):
                    refined_home_coords = home_building_obj.refine_anchor_coordinates(world, sleep_anchor[0], sleep_anchor[1], requesting_entity=npc)
                    if _is_coordinate_pair(refined_home_coords):
                        dest_coords_temp = tuple(refined_home_coords)
            new_task_label = TaskType.GOING_HOME
            destination_coords = dest_coords_temp

    if npc.schedule.current_task == TaskType.SLEEPING:
        if not is_night_time:
            npc.schedule.current_task = TaskType.AT_HOME
        elif getattr(world, "game_time", 0) % 50 == 0 and hasattr(world, "visual_effects"):
            from engine import FloatingTextEffect
            world.visual_effects.append(FloatingTextEffect(npc.x, npc.y, "Zzz", color=(100, 100, 255)))
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
            npc.schedule.current_task = TaskType.IDLE
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
            if new_task_label == TaskType.GOING_TO_WORK:
                npc.schedule.current_task = TaskType.AT_WORK
            elif new_task_label == TaskType.GOING_HOME:
                npc.schedule.current_task = TaskType.AT_HOME
            else:
                npc.schedule.current_task = TaskType.IDLE
        else:
            path = world.calculate_path(npc.x, npc.y, destination_coords[0], destination_coords[1])
            if not path and hasattr(world, "_find_best_adjacent_tile"):
                adj = world._find_best_adjacent_tile(destination_coords[0], destination_coords[1], npc)
                if adj and adj != (None, None):
                    destination_coords = adj
                    path = world.calculate_path(npc.x, npc.y, destination_coords[0], destination_coords[1])
            if path:
                npc.schedule.current_path = path
                npc.schedule.current_destination_coords = destination_coords
                npc.schedule.current_task = new_task_label
                if new_task_label not in [TaskType.GOING_TO_WORK, TaskType.AT_WORK]:
                    npc.clear_work_sub_task_state(reset_sequence=True)
            else:
                npc.schedule.current_task = "idle_confused"
