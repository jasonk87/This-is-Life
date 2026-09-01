"""World tick orchestration and control-layer stepping."""

from __future__ import annotations

from entities.social import MEMORY_DECAY_INTERVAL_TICKS, decay_known_facts
from presentation.ambient_speech import cleanup_ambient_speech
from simulation.activity import advance_activity
from simulation.systems import survival
from simulation.systems import illness


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



def _record_interaction_traces(world, interaction, interaction_id: str, result) -> None:
    if not getattr(result, "traces_to_log", None):
        return

    trace_log = getattr(world, "interaction_trace_log", None)
    if trace_log is None:
        trace_log = []
        setattr(world, "interaction_trace_log", trace_log)

    for trace_type, metadata in result.traces_to_log:
        entry = {
            "tick": getattr(world, "game_time", None),
            "interaction_id": interaction_id,
            "actor_id": getattr(interaction, "actor_id", None),
            "action_type": getattr(interaction, "action_type", None),
            "trace_type": trace_type,
            "metadata": dict(metadata or {}),
        }
        trace_log.append(entry)
        recorder = getattr(world, "record_interaction_trace", None)
        if callable(recorder):
            recorder(entry)


def _apply_interaction_cues(world, interaction, interaction_id: str, result) -> None:
    if not getattr(result, "cues_to_fire", None):
        return

    cue_log = getattr(world, "animation_cue_log", None)
    if cue_log is None:
        cue_log = []
        setattr(world, "animation_cue_log", cue_log)

    for cue in result.cues_to_fire:
        entry = {
            "tick": getattr(world, "game_time", None),
            "interaction_id": interaction_id,
            "actor_id": getattr(interaction, "actor_id", None),
            "action_type": getattr(interaction, "action_type", None),
            "cue": cue,
            "target_pos": getattr(interaction, "target_pos", None),
        }
        cue_log.append(entry)
        applier = getattr(world, "apply_animation_cue", None)
        if callable(applier):
            applier(cue, interaction=interaction, result=result)


def _clear_actor_active_interaction(world, interaction, interaction_id: str):
    get_entity = getattr(world, "get_entity_by_id", None)
    if not callable(get_entity):
        return None

    actor = get_entity(getattr(interaction, "actor_id", None))
    schedule = getattr(actor, "schedule", None)
    if schedule is None or getattr(schedule, "active_interaction_id", None) != interaction_id:
        return actor

    schedule.active_interaction_id = None
    schedule.current_path = []
    schedule.current_destination_coords = None
    if getattr(schedule, "current_task", None) == "active_interaction":
        schedule.current_task = "idle"
    return actor


def advance_active_interactions(world) -> None:
    """Advance all resolver-owned active interactions once for this world tick."""
    resolver = getattr(world, "interaction_resolver", None)
    if resolver is None:
        return

    active_interactions = getattr(resolver, "active_interactions", None)
    if not active_interactions:
        return

    for interaction_id in sorted(list(active_interactions.keys())):
        interaction = active_interactions.get(interaction_id)
        if interaction is None:
            continue

        result = resolver.advance_active_interaction(interaction_id, world)
        if result is not None:
            _record_interaction_traces(world, interaction, interaction_id, result)
            _apply_interaction_cues(world, interaction, interaction_id, result)

        if interaction_id not in active_interactions:
            actor = _clear_actor_active_interaction(world, interaction, interaction_id)
            handler = getattr(world, "on_active_interaction_finished", None)
            if callable(handler):
                handler(actor=actor, interaction=interaction, result=result)


def _emit_runtime_health_warning(world, warning_type: str, key, message: str, *, actor=None, metadata: dict | None = None) -> None:
    reporter = getattr(world, "_warn_simulation_validation", None)
    if callable(reporter):
        reporter(warning_type, key, message, actor=actor, metadata=metadata)
        return

    from simulation.validation import emit_validation_warning

    emit_validation_warning(world, warning_type, key, message, actor=actor, metadata=metadata)


def _iter_runtime_actors(world):
    seen = set()
    for actor in [getattr(world, "player", None), *getattr(world, "all_npcs", [])]:
        actor_id = getattr(actor, "id", None)
        if actor is None or actor_id in seen:
            continue
        seen.add(actor_id)
        yield actor


def run_runtime_health_checks(world) -> None:
    """Lightweight cleanup for orphaned runtime ownership state."""
    resolver = getattr(world, "interaction_resolver", None)
    active = getattr(resolver, "active_interactions", {}) if resolver is not None else {}
    get_entity = getattr(world, "get_entity_by_id", None)

    if resolver is not None and callable(get_entity):
        for interaction_id, interaction in sorted(list(active.items())):
            actor = get_entity(getattr(interaction, "actor_id", None))
            actor_dead = bool(actor is None or getattr(getattr(actor, "physical", None), "is_dead", False))
            if not actor_dead:
                continue
            result = resolver.cancel_active_interaction(interaction_id, world, "actor_unavailable")
            if result is not None:
                _record_interaction_traces(world, interaction, interaction_id, result)
            _emit_runtime_health_warning(
                world,
                "orphaned_active_interaction",
                (interaction_id, getattr(interaction, "actor_id", None)),
                "ActiveInteraction actor is missing or unavailable; cancelled interaction.",
                actor=actor,
                metadata={"interaction_id": interaction_id, "action_type": getattr(interaction, "action_type", None)},
            )

    active = getattr(resolver, "active_interactions", {}) if resolver is not None else {}
    for actor in _iter_runtime_actors(world):
        schedule = getattr(actor, "schedule", None)
        interaction_id = getattr(schedule, "active_interaction_id", None)
        if not interaction_id or interaction_id in active:
            continue
        schedule.active_interaction_id = None
        schedule.current_path = []
        schedule.current_destination_coords = None
        if getattr(schedule, "current_task", None) == "active_interaction":
            schedule.current_task = "idle"
        _emit_runtime_health_warning(
            world,
            "stuck_active_interaction",
            (getattr(actor, "id", None), interaction_id),
            "Actor referenced a missing active interaction; cleared schedule state.",
            actor=actor,
            metadata={"interaction_id": interaction_id},
        )

    expire_claim = getattr(world, "_expire_component_claim_if_needed", None)
    if callable(expire_claim):
        for blueprint in list(getattr(world, "blueprints_by_id", {}).values()):
            for component in getattr(blueprint, "components", []):
                expire_claim(blueprint, component)

    clear_construction = getattr(world, "_clear_npc_construction_task", None)
    blueprints = getattr(world, "blueprints_by_id", {})
    if callable(clear_construction):
        for actor in _iter_runtime_actors(world):
            if getattr(actor, "task_context", None) != "construction":
                continue
            task_data = getattr(actor, "task_context_data", None) if isinstance(getattr(actor, "task_context_data", None), dict) else {}
            blueprint = blueprints.get(task_data.get("blueprint_id"))
            component_id = task_data.get("component_id")
            component_missing = component_id and blueprint is not None and not any(c.id == component_id for c in getattr(blueprint, "components", []))
            if blueprint is not None and not component_missing:
                continue
            clear_construction(actor, blueprint)
            _emit_runtime_health_warning(
                world,
                "stale_construction_task",
                (getattr(actor, "id", None), task_data.get("blueprint_id"), component_id),
                "Actor construction task referenced missing construction state; cleared task.",
                actor=actor,
                metadata={"blueprint_id": task_data.get("blueprint_id"), "component_id": component_id},
            )

def run_world_tick(world) -> None:
    """Run one simulation tick; engine.World only orchestrates through this entry point."""
    world._update_spatial_partitioning()
    world.ensure_player_surroundings_generated()
    advance_player_auto_movement(world)

    world.game_time += 1
    cleanup_ambient_speech(world)
    world._update_season()
    world._run_scheduled_events()
    world._update_weather()
    world._update_light_level_and_fov()
    world._update_player_fov()
    survival.update_entity_temperature(world, world.player, update_world_ambient=True)
    survival.apply_temperature_effects(world, world.player, is_player=True)
    survival.update_player_wetness(world)
    survival.update_player_needs(world)
    illness.update_entity_illness(world, world.player)
    for actor in [world.player, *world.all_npcs]:
        if not getattr(getattr(actor, "physical", None), "is_dead", False):
            advance_activity(actor, world)
    if world.game_time % max(1, MEMORY_DECAY_INTERVAL_TICKS) == 0:
        for actor in [world.player, *world.all_npcs]:
            decay_known_facts(getattr(actor, "knowledge", None), world.game_time)
    for npc in world.all_npcs:
        if not npc.physical.is_dead:
            survival.update_npc_survival(world, npc)
            illness.update_entity_illness(world, npc)
    illness.spread_contagion(world)
    world._tick_world_item_inventories()
    world.process_abstract_simulation()
    world.process_macro_daily_tick()
    world._update_npc_schedules()
    world._update_npc_movement()
    advance_active_interactions(world)
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
    run_runtime_health_checks(world)
    advance_campfires = getattr(world, "advance_campfires", None)
    if callable(advance_campfires):
        advance_campfires()
    advance_temperature_exposure = getattr(world, "advance_temperature_exposure", None)
    if callable(advance_temperature_exposure):
        advance_temperature_exposure()
    advance_hunger = getattr(world, "advance_actor_hunger", None)
    if callable(advance_hunger):
        advance_hunger()
    advance_survival_overrides = getattr(world, "advance_survival_overrides", None)
    if callable(advance_survival_overrides):
        advance_survival_overrides()
    advance_reserves = getattr(world, "advance_reserve_targets", None)
    if callable(advance_reserves):
        advance_reserves()
    emit_environmental_sensory_cues(world)


def emit_environmental_sensory_cues(world) -> None:
    """Emit periodic, diegetic sensory messages for nearby environmental features."""
    player = getattr(world, "player", None)
    if not player or getattr(world, "game_time", 0) % 80 != 0:
        return

    px, py = player.x, player.y
    for dy in range(-4, 5):
        for dx in range(-4, 5):
            tx, ty = px + dx, py + dy
            tile = world.get_tile_at(tx, ty)
            if not tile:
                continue
            props = getattr(tile, "properties", {})
            ws = props.get("workstation_type")
            tname = getattr(tile, "name", "")
            if ws == "oven" or "Oven" in tname:
                world.add_message_to_chat_log("The warm, sweet aroma of baking bread drifts from the oven.")
                return
            elif ws == "forge" or "Forge" in tname:
                world.add_message_to_chat_log("The rhythmic clinking of hammer against iron rings out from the forge.")
                return
            elif ws == "grinding_stone" or "Mill" in tname:
                world.add_message_to_chat_log("The low, rumbling groan of the millstone grinding grain echoes nearby.")
                return
            elif (ws == "fire" or "Fire" in tname) and props.get("heat_source"):
                phys = getattr(player, "physical", None)
                if phys and getattr(phys, "body_temperature", 37.0) < 36.5:
                    world.add_message_to_chat_log("The glowing warmth of the hearth eases the chill in the air.")
                    return
    advance_tasks = getattr(world, "advance_production_tasks", None)
    if callable(advance_tasks):
        advance_tasks()
    advance_active_interactions(world)
    if hasattr(world, "_handle_ambient_activity_interactions"):
        world._handle_ambient_activity_interactions()
    world._update_entity_titles()
    world._update_npc_reputations()
    world._handle_reputation_based_reactions()
    world._cleanup_dead_entities()
