from types import SimpleNamespace

from engine import NPC, World
from entities.items import Inventory
from simulation.activity import (
    advance_activity,
    can_actor_observe_nearby_events,
    is_actor_available_for_conversation,
    start_activity,
)
from simulation.systems.task_types import TaskType
from simulation.systems.work import update_npc_work_sub_tasks
from presentation.dialogue_surface import _build_context


def _world_stub(game_time=0):
    return SimpleNamespace(game_time=game_time)


def test_activity_progresses_over_ticks_and_completes_after_duration():
    actor = SimpleNamespace(id=1, x=2, y=3, physical=SimpleNamespace(is_dead=False))
    activity = start_activity(actor, "testing", 2, world=_world_stub(10), allows_conversation=True)

    assert activity.progress_ticks == 0
    advance_activity(actor, _world_stub(11))
    assert actor.current_activity.progress_ticks == 1
    advance_activity(actor, _world_stub(12))

    assert actor.current_activity is None
    assert actor.recent_completed_activities[-1].activity_type == "testing"
    assert actor.recent_completed_activities[-1].completed is True


def test_activity_conversation_and_observation_flags_gate_availability():
    actor = SimpleNamespace(id=1, x=0, y=0, physical=SimpleNamespace(is_dead=False))
    start_activity(actor, "quiet_work", 5, allows_conversation=False, allows_observation=False)

    assert not is_actor_available_for_conversation(actor)
    assert not can_actor_observe_nearby_events(actor)

    actor.current_activity = None
    start_activity(actor, "bench_rest", 5, allows_conversation=True, allows_observation=True)

    assert is_actor_available_for_conversation(actor)
    assert can_actor_observe_nearby_events(actor)


def test_blacksmith_work_sub_task_starts_activity_instance():
    npc = NPC(5, 5, name="Smith")
    npc.id = 101
    npc.economic.profession = "Blacksmith"
    npc.schedule.work_building_id = "forge-1"
    npc.schedule.current_task = TaskType.AT_WORK
    building = SimpleNamespace(id="forge-1")
    world = SimpleNamespace(
        game_time=42,
        buildings_by_id={"forge-1": building},
        _find_target_coords_for_sub_task=lambda _npc, _building, _sub_task: (5, 5),
        calculate_path=lambda *args: [],
        _execute_completed_work_sub_task=lambda *args: None,
        visual_effects=[],
    )

    assert update_npc_work_sub_tasks(world, npc)

    assert npc.current_activity is not None
    assert npc.current_activity.activity_type.startswith("work:")
    assert npc.current_activity.anchor_coords == (5, 5)
    assert npc.current_activity.allows_conversation is True


def test_eating_starts_non_conversational_activity_and_preserves_instant_need_reduction():
    npc = NPC(1, 1, name="Hungry")
    npc.id = 102
    npc.physical.hunger = 80
    inventory = Inventory({"apple": 1})
    world = SimpleNamespace(game_time=7)
    world._consume_npc_inventory_item = lambda actor, inv, key: World._consume_npc_inventory_item(world, actor, inv, key)

    found, consumed = World._npc_consume_from_inventory(world, npc, inventory, need_type="hunger", desperate=True)

    assert found is True
    assert consumed is True
    assert npc.current_activity is not None
    assert npc.current_activity.activity_type == "eating"
    assert npc.current_activity.allows_conversation is False
    assert npc.physical.hunger < 80
    reduced_hunger = npc.physical.hunger

    for _ in range(npc.current_activity.duration_ticks):
        advance_activity(npc, world)

    assert npc.current_activity is None
    assert npc.physical.hunger == reduced_hunger


def test_ambient_activity_talk_uses_conversational_activity_and_blocks_quiet_activity():
    speaker = NPC(1, 1, name="Speaker")
    listener = NPC(2, 1, name="Listener")
    speaker.id = 1
    listener.id = 2
    speaker.knowledge.known_memories = []
    listener.knowledge.known_memories = []
    world = SimpleNamespace(
        game_state="PLAYING",
        chat_ui_active=False,
        game_time=20,
        village_npcs=[speaker, listener],
        player=SimpleNamespace(id=999, x=99, y=99, physical=SimpleNamespace(hearing_radius=0)),
        npcs=[],
        visual_effects=[],
        _can_player_overhear=lambda _speaker: False,
        add_message_to_chat_log=lambda message: None,
        get_entity_display_name=lambda entity: entity.name,
        get_entity_by_id=lambda entity_id: None,
    )

    start_activity(
        speaker,
        "sitting",
        10,
        world=world,
        allows_conversation=True,
        allows_observation=True,
        allows_social_sharing=True,
    )
    World._handle_ambient_activity_interactions(world)

    assert speaker.conversation_cooldown > 0
    assert world.visual_effects

    speaker.conversation_cooldown = 0
    listener.conversation_cooldown = 0
    world.visual_effects.clear()
    start_activity(
        speaker,
        "eating",
        10,
        world=world,
        allows_conversation=False,
        allows_observation=True,
        allows_social_sharing=False,
    )
    World._handle_ambient_activity_interactions(world)

    assert speaker.conversation_cooldown == 0
    assert not world.visual_effects


def test_dialogue_context_receives_activity_profession_age_status_and_relationship():
    speaker = NPC(0, 0, name="Elder Smith")
    listener = NPC(0, 1, name="Neighbor")
    speaker.id = 201
    listener.id = 202
    speaker.age = 70
    speaker.economic.profession = "Blacksmith"
    speaker.social.title = "Guild Elder"
    speaker.social.relationships[listener.id] = 80
    start_activity(speaker, "forging", 12, allows_conversation=True)
    world = SimpleNamespace(game_time=0, player=listener, village_npcs=[speaker, listener], npcs=[])

    context = _build_context(speaker, listener, world, [])

    assert context.current_activity_type == "forging"
    assert context.speaker_age_group == "elder"
    assert context.speaker_profession == "Blacksmith"
    assert context.speaker_status == "Guild Elder"
    assert context.relationship_hint == "friendly"
