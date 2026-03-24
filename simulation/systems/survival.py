"""Shared survival and environmental simulation systems."""

from __future__ import annotations

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

    if "Freezing" in entity.physical.status_effects:
        if is_player:
            world.add_message_to_chat_log("You are freezing cold!")
        entity.take_damage(1, world=world)
    elif "Overheating" in entity.physical.status_effects:
        if is_player:
            world.add_message_to_chat_log("You are burning up!")
        entity.take_damage(1, world=world)


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

