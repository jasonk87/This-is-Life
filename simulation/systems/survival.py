"""Shared survival and environmental simulation systems."""

from __future__ import annotations
from simulation.systems.task_types import TaskType

from config import (
    BIOME_TEMPERATURE_MODIFIERS,
    CHUNK_SIZE,
    DAY_LENGTH_TICKS,
    SEASON_TEMPERATURE_MODIFIERS,
    TIME_OF_DAY_TEMPERATURE_MODIFIERS,
    WORLD_HEIGHT,
    WORLD_WIDTH,
)


def update_entity_temperature(world, entity, *, search_radius: int | None = None, update_world_ambient: bool = False) -> None:
    """Calculate ambient temperature and advance one entity's thermal state."""
    season_name = world.seasons[world.current_season_index]
    base_temp = SEASON_TEMPERATURE_MODIFIERS.get(season_name, 20)

    entity_chunk = world.chunks[entity.y // CHUNK_SIZE][entity.x // CHUNK_SIZE]
    biome_temp_mod = BIOME_TEMPERATURE_MODIFIERS.get(entity_chunk.biome, 0)
    time_of_day_mod = TIME_OF_DAY_TEMPERATURE_MODIFIERS.get(world.current_light_level_name, 0)
    ambient_temp = base_temp + biome_temp_mod + time_of_day_mod

    heat_source_bonus = 0.0
    radius = search_radius if search_radius is not None else (5 if update_world_ambient else 3)
    for y in range(entity.y - radius, entity.y + radius + 1):
        for x in range(entity.x - radius, entity.x + radius + 1):
            if 0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT:
                tile = world.get_tile_at(x, y)
                if tile and getattr(tile, "properties", None) and tile.properties.get("heat_source"):
                    source_radius = tile.properties.get("heat_source_radius", 0)
                    intensity = tile.properties.get("heat_intensity", 0)
                    distance = max(abs(entity.x - x), abs(entity.y - y))
                    if distance <= source_radius:
                        heat_bonus = intensity * (1 - (distance / source_radius))
                        if heat_bonus > heat_source_bonus:
                            heat_source_bonus = heat_bonus

    ambient_temp_at_entity = ambient_temp + heat_source_bonus
    if update_world_ambient:
        world.ambient_temperature = ambient_temp_at_entity

    entity.recalculate_stats()
    if hasattr(entity.physical, "process_tick"):
        entity.physical.process_tick(
            ambient_temperature=ambient_temp_at_entity,
            wet_penalty=bool(getattr(entity.physical, "is_wet", False)),
        )
        return

    total_insulation = entity.physical.base_temperature_resistance + entity.physical.clothing_insulation
    if getattr(entity.physical, "is_wet", False):
        total_insulation *= 0.5

    target_temp_equilibrium = ambient_temp_at_entity + total_insulation
    temp_diff = target_temp_equilibrium - entity.physical.temperature
    entity.physical.temperature += temp_diff * 0.05

    if "Freezing" in entity.physical.status_effects:
        entity.physical.status_effects.remove("Freezing")
    if "Overheating" in entity.physical.status_effects:
        entity.physical.status_effects.remove("Overheating")

    if entity.physical.temperature < 35.0:
        entity.physical.status_effects.append("Freezing")
    elif entity.physical.temperature > 38.5:
        entity.physical.status_effects.append("Overheating")


def apply_temperature_effects(world, entity, *, is_player: bool = False) -> None:
    """Apply periodic thermal damage and messaging."""
    ticks_for_temp_damage = DAY_LENGTH_TICKS // 25
    if world.game_time % ticks_for_temp_damage != 0:
        return

    # apply_hostility=False on both: this is environmental/status-effect
    # damage, not an attack - Player.take_damage doesn't have a hostility
    # flag at all so this only actually matters for NPCs, but is applied to
    # both calls uniformly since take_damage is a shared entry point.
    if "Freezing" in entity.physical.status_effects:
        if is_player:
            world.add_message_to_chat_log("You are freezing cold!")
        entity.take_damage(1, world=world, apply_hostility=False)
    elif "Overheating" in entity.physical.status_effects:
        if is_player:
            world.add_message_to_chat_log("You are burning up!")
        entity.take_damage(1, world=world, apply_hostility=False)


def update_player_wetness(world) -> None:
    """Keep the player wetness state in sync with weather and shelter."""
    player = world.player
    player.physical.is_sheltered = world._check_for_shelter(player.x, player.y)

    if world.weather == "rain" and not player.physical.is_sheltered:
        if not player.physical.is_wet:
            world.add_message_to_chat_log("You are getting wet from the rain.")
        player.physical.is_wet = True
        player.physical.wetness_timer = max(player.physical.wetness_timer, DAY_LENGTH_TICKS // 10)

    if player.physical.is_wet and world.game_time % (DAY_LENGTH_TICKS // 20) == 0:
        if world.weather != "rain" or player.physical.is_sheltered:
            player.physical.wetness_timer -= 1
            if player.physical.wetness_timer <= 0:
                player.physical.is_wet = False
                world.add_message_to_chat_log("You have dried off.")


def update_player_needs(world, *, initial_setup: bool = False) -> None:
    """Advance player hunger/thirst using the same physical component model as NPCs."""
    player = world.player
    ticks_for_hunger_increase = DAY_LENGTH_TICKS // 10
    ticks_for_thirst_increase = DAY_LENGTH_TICKS // 15
    ticks_for_starvation_damage = DAY_LENGTH_TICKS // 20

    if not initial_setup:
        if world.game_time % ticks_for_hunger_increase == 0:
            player.physical.hunger = min(player.physical.max_hunger, player.physical.hunger + 5)
        if world.game_time % ticks_for_thirst_increase == 0:
            player.physical.thirst = min(player.physical.max_thirst, player.physical.thirst + 7)

    if player.physical.hunger >= player.physical.max_hunger * 0.9:
        player.physical.hunger_level_msg = "Starving"
        if not initial_setup and world.game_time % ticks_for_starvation_damage == 0:
            world.add_message_to_chat_log("You are weak from starvation!")
            player.take_damage(1)
    elif player.physical.hunger >= player.physical.max_hunger * 0.7:
        player.physical.hunger_level_msg = "Very Hungry"
    elif player.physical.hunger >= player.physical.max_hunger * 0.5:
        player.physical.hunger_level_msg = "Hungry"
    elif player.physical.hunger >= player.physical.max_hunger * 0.25:
        player.physical.hunger_level_msg = "Peckish"
    else:
        player.physical.hunger_level_msg = ""

    if player.physical.thirst >= player.physical.max_thirst * 0.9:
        player.physical.thirst_level_msg = "Dehydrated"
        if not initial_setup and world.game_time % ticks_for_starvation_damage == 0:
            world.add_message_to_chat_log("You are faint from thirst!")
            player.take_damage(1)
    elif player.physical.thirst >= player.physical.max_thirst * 0.7:
        player.physical.thirst_level_msg = "Very Thirsty"
    elif player.physical.thirst >= player.physical.max_thirst * 0.5:
        player.physical.thirst_level_msg = "Thirsty"
    else:
        player.physical.thirst_level_msg = ""


def update_npc_survival(world, npc) -> None:
    """Advance NPC thermal and metabolism state using shared component logic."""
    update_entity_temperature(world, npc, update_world_ambient=False)
    if npc.economic.profession != "Creature":
        npc.physical.process_tick(hunger_delta=2, thirst_delta=3)
    apply_temperature_effects(world, npc, is_player=False)


def update_npc_environmental_tasks(world, npc) -> None:
    """Handle high-priority weather/temperature task transitions for one NPC."""
    if "Freezing" in npc.physical.status_effects and npc.schedule.current_task != "seeking_warmth":
        npc.schedule.previous_task = npc.schedule.current_task if npc.schedule.current_task not in [TaskType.IDLE, TaskType.WANDERING] else TaskType.IDLE
        npc.schedule.current_task = "seeking_warmth"
        heat_source_coords = world._find_nearest_heat_source(npc)
        if heat_source_coords:
            dest_x, dest_y = world._find_best_adjacent_tile(heat_source_coords[0], heat_source_coords[1], npc)
            if dest_x is not None:
                path = world.calculate_path(npc.x, npc.y, dest_x, dest_y)
                if path:
                    npc.schedule.current_path = path
                    npc.schedule.current_destination_coords = (dest_x, dest_y)
        else:
            home_building = world.buildings_by_id.get(npc.schedule.home_building_id)
            if home_building:
                home_coords = (home_building.global_center_x, home_building.global_center_y)
                path = world.calculate_path(npc.x, npc.y, home_coords[0], home_coords[1])
                if path:
                    npc.schedule.current_path = path
                    npc.schedule.current_destination_coords = home_coords
                    npc.schedule.current_task = "huddling_indoors"

    is_bad_weather = world.weather in ["rain", "snow"]
    npc_is_sheltered = world._check_for_shelter(npc.x, npc.y)

    if is_bad_weather and not npc_is_sheltered and npc.schedule.current_task != "seeking_shelter":
        npc.schedule.previous_task = npc.schedule.current_task if npc.schedule.current_task not in [TaskType.IDLE, TaskType.WANDERING] else TaskType.IDLE
        npc.schedule.current_task = "seeking_shelter"
        shelter_building = world.buildings_by_id.get(npc.schedule.home_building_id)
        if not shelter_building:
            shelter_building = world._find_nearest_tavern(npc)

        if shelter_building:
            shelter_coords = (shelter_building.global_center_x, shelter_building.global_center_y)
            path = world.calculate_path(npc.x, npc.y, shelter_coords[0], shelter_coords[1])
            if path:
                npc.schedule.current_path = path
                npc.schedule.current_destination_coords = shelter_coords
    elif not is_bad_weather and npc.schedule.current_task == "seeking_shelter":
        npc.schedule.current_task = npc.schedule.previous_task or TaskType.IDLE
        npc.schedule.previous_task = None
        npc.schedule.current_path = []
        npc.schedule.current_destination_coords = None
