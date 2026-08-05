"""Behavior strategy objects for animal AI."""
from __future__ import annotations
from simulation.systems.task_types import TaskType

import math
import random
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Protocol

from config import DAY_LENGTH_TICKS, WORLD_HEIGHT, WORLD_WIDTH
from data.animals import ANIMAL_DEFINITIONS
from data.decorations import DECORATION_ITEM_DEFINITIONS
from data.tiles import TILE_DEFINITIONS


class BaseBehavior(Protocol):
    """Interface for composable animal AI behaviors."""

    def take_turn(self, entity, world) -> bool:
        """Run this behavior for one turn.

        Returns ``True`` when the behavior consumed the entity's turn and the
        caller should stop evaluating lower-priority behaviors.
        """


class NoOpBehavior:
    def take_turn(self, entity, world) -> bool:
        return False


@dataclass
class CompositeBehavior:
    """Runs child behaviors in priority order."""

    behaviors: list[BaseBehavior] = field(default_factory=list)

    def take_turn(self, entity, world) -> bool:
        for behavior in self.behaviors:
            if behavior.take_turn(entity, world):
                return True
        return False


class StarvationBehavior:
    def take_turn(self, entity, world) -> bool:
        if entity.physical.hunger < entity.physical.max_hunger * 0.95:
            return False
        if random.random() >= 0.1:
            return False

        entity.combat.hp -= 1
        if entity.combat.hp > 0:
            return False

        world.log_event("entity_death", f"A {entity.name} died of starvation.", entity.id, location=(entity.x, entity.y))
        world.handle_npc_death(entity)
        return True


class HerdingBehavior:
    def take_turn(self, entity, world) -> bool:
        if entity.combat.combat_behavior != "herd_defensive":
            return False
        if entity.schedule.current_task not in [TaskType.IDLE, TaskType.WANDERING]:
            return False

        herd_members = [
            other for other in world.get_entities_in_radius(entity.x, entity.y, 15)
            if getattr(other, "animal_type", None) == entity.animal_type and other.id != entity.id
        ]
        if not herd_members:
            return False

        cx = sum(member.x for member in herd_members) // len(herd_members)
        cy = sum(member.y for member in herd_members) // len(herd_members)
        if math.sqrt((entity.x - cx) ** 2 + (entity.y - cy) ** 2) <= 5:
            return False

        cx += random.randint(-2, 2)
        cy += random.randint(-2, 2)
        path = world.calculate_path(entity.x, entity.y, cx, cy)
        if not path:
            return False

        entity.schedule.current_path = path
        entity.schedule.current_destination_coords = (cx, cy)
        entity.schedule.current_task = "migrating_with_herd"
        return False


class PredatorBehavior:
    # Desperate-predation tuning (see _try_escalate_to_desperate_predation
    # for the full design rationale). Kept as class constants rather than
    # inline magic numbers so the thresholds are easy to find/tune later.
    DESPERATE_HUNGER_THRESHOLD_RATIO = 0.9  # above the 0.7 "start hunting" ratio, below the 0.95 starvation-damage ratio
    DESPERATE_ESCALATION_CHANCE = 0.15  # per-tick roll, once hunger/no-prey conditions are already met
    DESPERATE_TARGET_SEARCH_RADIUS = 20  # matches _find_nearest_prey's existing search radius

    def _find_nearest_prey(self, entity, world):
        nearest_prey = None
        min_dist_sq = float("inf")
        prey_types = entity.animal_definition.get("prey", [])
        for other_npc in world.npcs:
            if other_npc.id == entity.id:
                continue
            if getattr(other_npc, "animal_type", None) not in prey_types:
                continue
            dist_sq = (entity.x - other_npc.x) ** 2 + (entity.y - other_npc.y) ** 2
            if dist_sq < min_dist_sq and dist_sq < 20 ** 2:
                min_dist_sq = dist_sq
                nearest_prey = other_npc
        return nearest_prey

    def _find_nearest_desperate_npc_target(self, entity, world):
        """Nearest living human (non-animal) village NPC within search
        radius, for a starving predator with no wild prey or corpse left."""
        nearest = None
        min_dist_sq = float("inf")
        radius_sq = self.DESPERATE_TARGET_SEARCH_RADIUS ** 2
        for other in getattr(world, "village_npcs", []):
            if other.id == entity.id or other.physical.is_dead:
                continue
            if getattr(other, "animal_type", None) is not None:
                continue  # not a human NPC
            dist_sq = (entity.x - other.x) ** 2 + (entity.y - other.y) ** 2
            if dist_sq < min_dist_sq and dist_sq < radius_sq:
                min_dist_sq = dist_sq
                nearest = other
        return nearest

    def _try_escalate_to_desperate_predation(self, entity, world) -> bool:
        """
        Last-resort escalation for a genuinely starving predator that has
        already failed to find wild prey or a corpse to scavenge this tick.

        Gates (deliberately compound, so this stays rare - flagging the
        reasoning per request):
        - hunger >= 90% of max_hunger: meaningfully hungrier than the 70%
          threshold that starts ordinary wild-prey hunting, and just short
          of the 95% threshold where StarvationBehavior starts rolling
          self-damage. This is "truly starving," not "peckish."
        - Only reached after this tick's wild-prey search (_find_nearest_prey)
          and corpse search (_find_nearest_corpse) BOTH failed - a predator
          with any accessible natural food never reaches this branch.
        - A 15% per-tick roll on top of the above, so even a starving,
          prey-less predator doesn't escalate the instant conditions are
          met - it takes a few ticks on average, echoing the same
          probabilistic idiom StarvationBehavior already uses for its own
          10%-per-tick damage roll.

        Target preference: nearest human village NPC first (reuses the
        existing generic world.npc_attempt_attack_npc() combat path via the
        normal "hunting" task/current_task machinery, so this gets real
        damage, real death, corpse placement, and witness memories for
        free). Falls back to the player only if no NPC is in range, via the
        existing combat.is_hostile_to_player + pursuit-state system already
        used by every other hostile creature - no new player-attack code.
        Livestock is deliberately out of scope here: sheep predation already
        happens today via the normal wild-prey path (wolf's prey list
        already includes "sheep") and is unchanged by this feature.
        """
        is_predator = "prey" in entity.animal_definition
        if not is_predator:
            return False
        if entity.physical.hunger < entity.physical.max_hunger * self.DESPERATE_HUNGER_THRESHOLD_RATIO:
            return False
        if random.random() >= self.DESPERATE_ESCALATION_CHANCE:
            return False

        nearest_human = self._find_nearest_desperate_npc_target(entity, world)
        if nearest_human is not None:
            entity.schedule.current_task = "hunting"
            entity.task_target_entity_id = nearest_human.id
            return True

        player = getattr(world, "player", None)
        if player is not None and not getattr(entity.combat, "is_hostile_to_player", False):
            distance_to_player = abs(entity.x - player.x) + abs(entity.y - player.y)
            if distance_to_player <= self.DESPERATE_TARGET_SEARCH_RADIUS:
                entity.combat.is_hostile_to_player = True
                world.add_message_to_chat_log(
                    f"{world.get_entity_display_name(entity)}, starving, turns on you!"
                )
                return True

        return False

    def _take_player_pursuit_turn(self, entity, world) -> bool:
        if not getattr(getattr(entity, "combat", None), "is_hostile_to_player", False):
            return False
        if not hasattr(world, "_is_predator") or not world._is_predator(entity):
            return False

        pursuit_state = getattr(world, "_get_predator_pursuit_state", lambda *_args, **_kwargs: None)(entity, create=False)
        if not pursuit_state:
            return False

        if world.game_time > int(pursuit_state.get("persist_until_tick", -1)):
            if hasattr(world, "_clear_predator_pursuit_state"):
                world._clear_predator_pursuit_state(entity)
            if entity.schedule.current_task == "hunting_player":
                entity.schedule.current_task = TaskType.IDLE
                entity.schedule.current_path = []
                entity.schedule.current_destination_coords = None
            return False

        target_coords = pursuit_state.get("last_seen")
        if not target_coords:
            return False

        target_x, target_y = target_coords
        entity.task_target_entity_id = getattr(world.player, "id", None)
        entity.schedule.current_task = "hunting_player"

        if (entity.x, entity.y) == (target_x, target_y):
            entity.schedule.current_path = []
            entity.schedule.current_destination_coords = (target_x, target_y)
            return True

        if not entity.schedule.current_path or entity.schedule.current_destination_coords != (target_x, target_y):
            path = world.calculate_path(entity.x, entity.y, target_x, target_y)
            if path:
                entity.schedule.current_path = path
                entity.schedule.current_destination_coords = (target_x, target_y)
                return True
            return False
        return True

    def take_turn(self, entity, world) -> bool:
        if self._take_player_pursuit_turn(entity, world):
            return True

        is_predator = "prey" in entity.animal_definition
        is_hungry_predator = is_predator and entity.physical.hunger >= entity.physical.max_hunger * 0.7
        if not (is_hungry_predator or entity.schedule.current_task in ["hunting", "eating_corpse"]):
            return False

        if entity.schedule.current_task != "hunting" and is_predator:
            nearest_prey = self._find_nearest_prey(entity, world)
            if nearest_prey:
                entity.schedule.current_task = "hunting"
                entity.task_target_entity_id = nearest_prey.id
            elif entity.physical.hunger >= entity.physical.max_hunger * self.DESPERATE_HUNGER_THRESHOLD_RATIO:
                # No wild prey found at all, but hungry enough for desperate
                # predation to get a chance to fire below. Falls through into
                # the "hunting" task's no-target handling (tries a corpse
                # first, then desperate escalation) rather than doing
                # nothing, which is what happens today for a merely-hungry
                # (70-90%) predator with no prey - that in-between case is
                # deliberately left unchanged.
                entity.schedule.current_task = "hunting"
                entity.task_target_entity_id = None

        if entity.schedule.current_task == "hunting":
            prey = world._get_predator_target(entity)
            if prey and not prey.physical.is_dead:
                distance_to_prey = abs(entity.x - prey.x) + abs(entity.y - prey.y)
                attack_range = getattr(entity, "attack_range", entity.combat.attack_range)
                if distance_to_prey <= attack_range:
                    if attack_range > 1:
                        from engine import ProjectileEffect
                        world.visual_effects.append(ProjectileEffect(
                            start_x=entity.x,
                            start_y=entity.y,
                            end_x=prey.x,
                            end_y=prey.y,
                            char='*',
                            color=(255, 0, 0),
                        ))
                    world.npc_attempt_attack_npc(entity, prey)
                    entity.schedule.current_path = []
                    entity.schedule.current_destination_coords = None
                else:
                    if not entity.schedule.current_path or entity.schedule.current_destination_coords != (prey.x, prey.y):
                        path = world.calculate_path(entity.x, entity.y, prey.x, prey.y)
                        if path:
                            entity.schedule.current_path = path
                            entity.schedule.current_destination_coords = (prey.x, prey.y)
                return True

            corpse_x, corpse_y = world._find_nearest_corpse(entity) if hasattr(world, "_find_nearest_corpse") else (None, None)
            if corpse_x is not None:
                entity.schedule.current_task = "eating_corpse"
                entity.schedule.current_destination_coords = (corpse_x, corpse_y)
                path = world.calculate_path(entity.x, entity.y, corpse_x, corpse_y)
                if path:
                    entity.schedule.current_path = path
                else:
                    entity.schedule.current_task = TaskType.IDLE
                entity.task_target_entity_id = None
                return True

            # No wild prey and no corpse: a truly starving predator may
            # escalate to attacking a human NPC (or the player) as a last
            # resort. See _try_escalate_to_desperate_predation for the
            # gating (hunger threshold, per-tick roll, search radius).
            if self._try_escalate_to_desperate_predation(entity, world):
                return True

            entity.schedule.current_task = TaskType.IDLE
            entity.task_target_entity_id = None
            return True

        if entity.schedule.current_task == "eating_corpse":
            if entity.schedule.current_destination_coords and (entity.x, entity.y) == entity.schedule.current_destination_coords:
                tile = world.get_tile_at(entity.x, entity.y)
                if tile and tile.name == "Animal Corpse":
                    entity.physical.hunger = 0
                    world.add_message_to_chat_log(f"{world.get_entity_display_name(entity)} devours the carcass.")
                    world._change_map_tile((entity.x, entity.y), DECORATION_ITEM_DEFINITIONS["bones"])
                entity.schedule.current_task = TaskType.IDLE
                entity.schedule.current_destination_coords = None
            elif not entity.schedule.current_path:
                entity.schedule.current_task = TaskType.IDLE
            return True

        return False


class PackHunterBehavior(PredatorBehavior):
    """Predator behavior for animals coordinated by pack or fearless traits."""


class WanderFleeBehavior:
    def take_turn(self, entity, world) -> bool:
        flee_radius = 15
        should_flee = False
        threat = None
        distance_to_player = math.sqrt((entity.x - world.player.x) ** 2 + (entity.y - world.player.y) ** 2)
        if distance_to_player < flee_radius and not entity.animal_definition.get("fearless"):
            should_flee = True
            threat = world.player

        if not should_flee:
            for other_npc in world.npcs:
                if other_npc.id == entity.id:
                    continue
                if getattr(other_npc, "animal_type", None) not in entity.animal_definition.get("predators", []):
                    continue
                distance_to_predator = math.sqrt((entity.x - other_npc.x) ** 2 + (entity.y - other_npc.y) ** 2)
                if distance_to_predator < flee_radius:
                    should_flee = True
                    threat = other_npc
                    break

        if should_flee and threat:
            if entity.schedule.current_task != "fleeing":
                threat_name = world.get_entity_display_name(threat) if hasattr(threat, "name") else "player"
                world.add_message_to_chat_log(f"{world.get_entity_display_name(entity)} spots {threat_name} and bolts!")
                entity.schedule.current_task = "fleeing"
                entity.current_sub_task = "Fleeing"
                entity.fear_state = "startled"
                entity.stress = min(100, int(getattr(entity, "stress", 0)) + 25)

            dx = entity.x - threat.x
            dy = entity.y - threat.y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > 0:
                flee_x = entity.x + int(dx / dist * flee_radius)
                flee_y = entity.y + int(dy / dist * flee_radius)
                flee_x = max(0, min(WORLD_WIDTH - 1, flee_x))
                flee_y = max(0, min(WORLD_HEIGHT - 1, flee_y))
                path = world.calculate_path(entity.x, entity.y, flee_x, flee_y)
                if path:
                    entity.schedule.current_path = path
                    entity.schedule.current_destination_coords = (flee_x, flee_y)
            return True

        if entity.schedule.current_task == "fleeing":
            entity.schedule.current_task = TaskType.IDLE
            entity.current_sub_task = "Roaming"
            entity.fear_state = "calm"
            entity.stress = max(0, int(getattr(entity, "stress", 0)) - 5)
        return False


class WanderAggressiveBehavior:
    def take_turn(self, entity, world) -> bool:
        return False


class WanderWaterBehavior:
    def take_turn(self, entity, world) -> bool:
        return False


class NeutralBehavior:
    def take_turn(self, entity, world) -> bool:
        dist_to_player = math.sqrt((entity.x - world.player.x) ** 2 + (entity.y - world.player.y) ** 2)
        if dist_to_player < 3 and not entity.combat.is_hostile_to_player:
            world.add_message_to_chat_log(f"{world.get_entity_display_name(entity)} feels threatened and becomes hostile!")
            entity.combat.is_hostile_to_player = True
        return False


class TerritorialBehavior:
    def take_turn(self, entity, world) -> bool:
        if not entity.den_location:
            entity.den_location = (entity.x, entity.y)

        dist_to_den = math.sqrt((world.player.x - entity.den_location[0]) ** 2 + (world.player.y - entity.den_location[1]) ** 2)
        if dist_to_den < 10 and not entity.combat.is_hostile_to_player:
            world.add_message_to_chat_log(f"{world.get_entity_display_name(entity)} becomes aggressive as you approach its den!")
            entity.combat.is_hostile_to_player = True
        return False


class GrazingBehavior:
    def _finish_grazing(self, entity, world, tile) -> None:
        entity.physical.hunger = max(0, entity.physical.hunger - 50)
        world.add_message_to_chat_log(world.text.entity_grazes_on(entity, tile.name))
        if tile.name == "Tall Grass":
            world._change_map_tile((entity.x, entity.y), TILE_DEFINITIONS["plains"])
        elif tile.name == "Growing Wheat":
            world._change_map_tile((entity.x, entity.y), TILE_DEFINITIONS["tilled_soil"])
        elif tile.name == "Flower":
            world._change_map_tile((entity.x, entity.y), TILE_DEFINITIONS["plains"])
        entity.schedule.current_task = TaskType.IDLE

    def _search_for_food(self, entity, world) -> bool:
        food_sources = entity.animal_definition.get("food_sources", [])
        search_radius = 10
        for y in range(entity.y - search_radius, entity.y + search_radius + 1):
            for x in range(entity.x - search_radius, entity.x + search_radius + 1):
                if not (0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT):
                    continue
                tile = world.get_tile_at(x, y)
                if not tile or tile.name not in food_sources:
                    continue
                path = world.calculate_path(entity.x, entity.y, x, y)
                if path:
                    entity.schedule.current_path = path
                    entity.schedule.current_destination_coords = (x, y)
                    entity.schedule.current_task = "grazing"
                    return True
        return False

    def take_turn(self, entity, world) -> bool:
        if entity.animal_definition.get("diet_type") != "herbivore" or entity.physical.hunger < 30:
            return False

        if entity.schedule.current_task == "grazing" and entity.schedule.current_destination_coords == (entity.x, entity.y):
            tile = world.get_tile_at(entity.x, entity.y)
            if tile and tile.name in entity.animal_definition.get("food_sources", []):
                self._finish_grazing(entity, world, tile)
            else:
                entity.schedule.current_task = TaskType.IDLE
            return entity.schedule.current_task == "grazing"

        if entity.schedule.current_task != "grazing":
            if self._search_for_food(entity, world):
                return True
        return entity.schedule.current_task == "grazing"


class ReproductionBehavior:
    def _is_night_time(self, world) -> bool:
        current_time_in_day = world.game_time % DAY_LENGTH_TICKS
        sleep_start_tick = DAY_LENGTH_TICKS * 0.85
        sleep_end_tick = DAY_LENGTH_TICKS * 0.15
        return current_time_in_day >= sleep_start_tick or current_time_in_day < sleep_end_tick

    def take_turn(self, entity, world) -> bool:
        if entity.is_pregnant:
            entity.pregnancy_timer -= 1
            if entity.pregnancy_timer > 0:
                return False

            entity.is_pregnant = False
            spawn_x, spawn_y = world._find_best_adjacent_tile(entity.x, entity.y, entity)
            if spawn_x is None:
                entity.pregnancy_timer = 1
                return False

            baby = entity.__class__(
                spawn_x,
                spawn_y,
                name=f"Baby {entity.animal_type}",
                animal_type=entity.animal_type,
                animal_definition=deepcopy(entity.animal_definition),
            )
            baby.combat.max_hp = max(1, entity.animal_definition.get("max_hp", 10) // 2)
            baby.combat.hp = baby.combat.max_hp
            baby.behavior = "Wander-Flee"
            baby.gender = random.choice(["male", "female"])
            world.npcs.append(baby)
            world._mark_entity_positions_dirty()
            world.add_message_to_chat_log(f"A baby {entity.animal_type} has been born!")
            return False

        if entity.behavior == "Follow-Owner" and entity.owner == world.player:
            distance_to_player = math.sqrt((entity.x - world.player.x) ** 2 + (entity.y - world.player.y) ** 2)
            if distance_to_player > 3 and not entity.schedule.current_path:
                target_x, target_y = world._find_best_adjacent_tile(world.player.x, world.player.y, entity)
                if target_x is not None:
                    path = world.calculate_path(entity.x, entity.y, target_x, target_y)
                    if path:
                        entity.schedule.current_path = path
                        entity.schedule.current_destination_coords = (target_x, target_y)
                        entity.schedule.current_task = "following"
                return True

            if entity.den_location and (self._is_night_time(world) or entity.combat.hp < entity.combat.max_hp * 0.3) and entity.schedule.current_task not in [TaskType.SLEEPING, "returning_to_den"]:
                den_x, den_y = entity.den_location
                if (entity.x, entity.y) == (den_x, den_y):
                    entity.schedule.current_task = TaskType.SLEEPING
                else:
                    entity.schedule.current_task = "returning_to_den"
                    path = world.calculate_path(entity.x, entity.y, den_x, den_y)
                    if path:
                        entity.schedule.current_path = path
                        entity.schedule.current_destination_coords = (den_x, den_y)
                    else:
                        entity.schedule.current_task = TaskType.WANDERING
                return True

            if entity.schedule.current_task == "returning_to_den" and entity.den_location and (entity.x, entity.y) == entity.den_location:
                entity.schedule.current_task = TaskType.SLEEPING
                return True
            return False

        if not entity.animal_definition.get("can_mate"):
            return False
        if entity.animal_definition.get("mating_season") != world.seasons[world.current_season_index]:
            return False
        if entity.is_pregnant:
            return False

        if entity.schedule.current_task not in ["seeking_mate", "mating"]:
            for other_npc in world.npcs:
                if getattr(other_npc, "animal_type", None) != entity.animal_type or other_npc.id == entity.id:
                    continue
                if other_npc.gender == entity.gender or other_npc.is_pregnant:
                    continue
                distance_to_mate = math.sqrt((entity.x - other_npc.x) ** 2 + (entity.y - other_npc.y) ** 2)
                if distance_to_mate < 20:
                    entity.schedule.current_task = "seeking_mate"
                    entity.task_target_entity_id = other_npc.id
                    break

        if entity.schedule.current_task != "seeking_mate" or not entity.task_target_entity_id:
            return False

        mate = next((candidate for candidate in world.npcs if candidate.id == entity.task_target_entity_id), None)
        if not mate:
            entity.schedule.current_task = TaskType.IDLE
            entity.task_target_entity_id = None
            return False

        distance_to_mate = math.sqrt((entity.x - mate.x) ** 2 + (entity.y - mate.y) ** 2)
        if distance_to_mate <= 1:
            if entity.gender == "female":
                entity.is_pregnant = True
                entity.pregnancy_timer = entity.animal_definition.get("gestation_period_days", 7) * DAY_LENGTH_TICKS
                world.add_message_to_chat_log(f"A wild {entity.animal_type} has become pregnant.")
            entity.schedule.current_task = TaskType.IDLE
            return True

        target_x, target_y = world._find_best_adjacent_tile(mate.x, mate.y, entity)
        if target_x is not None:
            path = world.calculate_path(entity.x, entity.y, target_x, target_y)
            if path:
                entity.schedule.current_path = path
                entity.schedule.current_destination_coords = (target_x, target_y)
                return True
        return False


class RandomWanderBehavior:
    def take_turn(self, entity, world) -> bool:
        if entity.schedule.current_task not in [TaskType.IDLE, TaskType.WANDERING] or entity.schedule.current_path:
            return False

        if entity.physical.hunger < entity.physical.max_hunger:
            entity.physical.hunger += 1

        if random.random() >= 0.2:
            return False

        dx, dy = random.choice([(0, 1), (0, -1), (1, 0), (-1, 0)])
        potential_x, potential_y = entity.x + dx, entity.y + dy
        target_tile = world.get_tile_at(potential_x, potential_y)
        if not target_tile or not target_tile.passable:
            return False
        if entity.behavior == "Wander-Water" and target_tile.name not in ["Water", "Deep Water"]:
            return False

        entity.schedule.current_path = [(entity.x, entity.y), (potential_x, potential_y)]
        entity.schedule.current_destination_coords = (potential_x, potential_y)
        entity.schedule.current_task = TaskType.WANDERING
        return True


class AnimalBehaviorController:
    """High-level coordinator for shared animal systems plus mode behaviors."""

    def __init__(self, definition: dict | None = None):
        self.definition = definition or {}
        self.starvation = StarvationBehavior()
        self.herding = HerdingBehavior()
        self.grazing = GrazingBehavior()
        self.reproduction = ReproductionBehavior()
        self.predator = PackHunterBehavior() if (self.definition.get("pack_animal") or self.definition.get("fearless")) else PredatorBehavior()
        self.mode_behaviors = {
            "Wander-Flee": WanderFleeBehavior(),
            "Wander-Aggressive": WanderAggressiveBehavior(),
            "Wander-Water": WanderWaterBehavior(),
            "Wander-Neutral": NeutralBehavior(),
            "Territorial": TerritorialBehavior(),
            "Follow-Owner": NoOpBehavior(),
        }
        self.random_wander = RandomWanderBehavior()

    def take_turn(self, entity, world) -> bool:
        if self.starvation.take_turn(entity, world):
            return True
        self.herding.take_turn(entity, world)
        if self.predator.take_turn(entity, world):
            return True
        mode_behavior = self.mode_behaviors.get(entity.behavior, NoOpBehavior())
        if mode_behavior.take_turn(entity, world):
            return True
        if self.grazing.take_turn(entity, world):
            return True
        if self.reproduction.take_turn(entity, world):
            return True
        return self.random_wander.take_turn(entity, world)


def create_behavior(definition: dict | None) -> BaseBehavior:
    """Factory for assembling a composable animal brain from definition data."""
    return AnimalBehaviorController(definition or {})
