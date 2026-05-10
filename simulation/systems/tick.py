"""World tick orchestration and control-layer stepping."""

from __future__ import annotations

from entities.social import MEMORY_DECAY_INTERVAL_TICKS, decay_known_facts
from simulation.activity import advance_activity
from simulation.systems import survival


def advance_player_auto_movement(world) -> None:
    """Drive input-layer auto movement without embedding it in engine.World.update."""
    player = world.player
    if not player.state.current_path:
        return
    if player.state.move_cooldown > 0:
        player.state.move_cooldown -= 1
        return

    next_x, next_y = player.state.current_path[0]
    dx = next_x - player.x
    dy = next_y - player.y
    player.state.current_path.pop(0)

    action_cost = world.handle_player_movement(dx, dy)
    if action_cost == 0 and (dx != 0 or dy != 0):
        player.state.current_path = []
        return

    player.state.move_cooldown = 5
    if "broken_leg" in player.physical.status_effects:
        player.state.move_cooldown += 5
    if action_cost > 1:
        world.game_time += action_cost - 1


def run_world_tick(world) -> None:
    """Run one simulation tick; engine.World only orchestrates through this entry point."""
    world._update_spatial_partitioning()
    world.ensure_player_surroundings_generated()
    advance_player_auto_movement(world)

    world.game_time += 1
    world._update_season()
    world._update_weather()
    world._update_light_level_and_fov()
    world._update_player_fov()
    survival.update_entity_temperature(world, world.player, update_world_ambient=True)
    survival.apply_temperature_effects(world, world.player, is_player=True)
    survival.update_player_wetness(world)
    survival.update_player_needs(world)
    for actor in [world.player, *world.all_npcs]:
        if not getattr(getattr(actor, "physical", None), "is_dead", False):
            advance_activity(actor, world)
    if world.game_time % max(1, MEMORY_DECAY_INTERVAL_TICKS) == 0:
        for actor in [world.player, *world.all_npcs]:
            decay_known_facts(getattr(actor, "knowledge", None), world.game_time)
    for npc in world.all_npcs:
        if not npc.physical.is_dead:
            survival.update_npc_survival(world, npc)
    world._tick_world_item_inventories()
    world.process_abstract_simulation()
    world.process_macro_daily_tick()
    world._update_npc_schedules()
    world._update_npc_movement()
    world._update_world_environment()
    world._update_economy()
    world._run_daily_governance()
    world._update_npc_ages()
    world._update_npc_careers()
    world._update_player_career()
    if hasattr(world, "ecology"):
        world.ecology.process_tick(world)
    world._update_abstract_simulation()
    world._update_political_warrants()
    world._drain_gossip_flavor_text_queue()
    world._process_npc_witness_events()
    world._process_npc_gossip_reaction()
    world._trigger_event_driven_conversation()
    world._handle_npc_speech()
    world._handle_npc_conversations()
    if hasattr(world, "_handle_ambient_activity_interactions"):
        world._handle_ambient_activity_interactions()
    world._update_entity_titles()
    world._update_npc_reputations()
    world._handle_reputation_based_reactions()
    world._cleanup_dead_entities()
