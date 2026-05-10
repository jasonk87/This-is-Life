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
    speaker.social.relationships[listener.id] = 85
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
        buildings_by_id={},
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
    assert not getattr(world, "active_ambient_speech", [])

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

from simulation.history import HistoryLedger
from simulation.systems.ambient_info import (
    can_share_known_fact,
    choose_ambient_conversation_pair,
    choose_shareable_fact,
    mark_ambient_conversation_started,
    mark_share_cooldowns,
    score_ambient_conversation_pair,
    share_known_fact,
)
from presentation.dialogue_surface import build_dialogue_topic_from_fact
from simulation.social_scene import (
    SCENE_INACTIVE_TICKS,
    choose_scene_interaction_pair,
    record_scene_topic,
    share_fact_with_scene_overhearers,
    update_social_scenes,
)


def _ambient_share_world(history, speaker, listener, *, game_time=20, overhear=True):
    chat_log = []
    player = SimpleNamespace(id=999, x=speaker.x, y=speaker.y, physical=SimpleNamespace(hearing_radius=12))
    return SimpleNamespace(
        game_state="PLAYING",
        chat_ui_active=False,
        game_time=game_time,
        history=history,
        village_npcs=[speaker, listener],
        player=player,
        npcs=[],
        visual_effects=[],
        chat_log=chat_log,
        _can_player_overhear=lambda _speaker: overhear,
        add_message_to_chat_log=lambda message: chat_log.append(message),
        get_entity_display_name=lambda entity: entity.name,
        get_entity_by_id=lambda entity_id: {speaker.id: speaker, listener.id: listener, player.id: player}.get(entity_id),
    )


def _speaker_listener_with_crime(*, confidence=0.95):
    history = HistoryLedger()
    speaker = NPC(1, 1, name="Witness")
    listener = NPC(2, 1, name="Neighbor")
    speaker.id = 1
    listener.id = 2
    speaker.social.relationships[listener.id] = 90
    crime = history.record_crime(
        crime_kind="assault",
        suspect_id=101,
        victim_id=102,
        description="A structured crime record.",
        game_time=5,
    )
    speaker.knowledge.learn_history_record(crime, "witnessed", confidence, 10)
    fact = speaker.knowledge.known_history_facts[crime.id]
    return history, speaker, listener, crime, fact


def test_ambient_share_known_crime_fact_teaches_listener_with_told_source_and_dialogue_line():
    history, speaker, listener, crime, fact = _speaker_listener_with_crime()
    world = _ambient_share_world(history, speaker, listener)
    start_activity(
        speaker,
        "sitting",
        10,
        world=world,
        allows_conversation=True,
        allows_observation=True,
        allows_social_sharing=True,
    )

    assert can_share_known_fact(speaker, listener, fact, world)
    World._handle_ambient_activity_interactions(world)

    learned = listener.knowledge.known_history_facts[crime.id]
    assert learned.source_type == "told"
    assert learned.confidence < fact.confidence
    assert world.active_ambient_speech
    assert "assault" in world.active_ambient_speech[-1].text
    assert not world.chat_log
    assert speaker.knowledge.last_spoken_topic_tick


def test_already_known_structured_facts_are_skipped():
    history, speaker, listener, crime, fact = _speaker_listener_with_crime()
    world = _ambient_share_world(history, speaker, listener)
    listener.knowledge.learn_history_record(crime, "official_record", 1.0, 11)

    assert not can_share_known_fact(speaker, listener, fact, world)
    assert choose_shareable_fact(speaker, listener, world) is None


def test_low_confidence_fact_decays_when_shared():
    _history, speaker, listener, _crime, fact = _speaker_listener_with_crime(confidence=0.35)

    assert share_known_fact(speaker, listener, fact, source_type="told")

    learned = listener.knowledge.known_history_facts[fact.source_record_id]
    assert learned.source_type == "told"
    assert learned.confidence == max(0.05, fact.confidence * 0.85)


def test_fact_share_cooldown_prevents_repeated_sharing():
    history, speaker, listener, _crime, fact = _speaker_listener_with_crime()
    world = _ambient_share_world(history, speaker, listener)

    mark_share_cooldowns(speaker, listener, world)

    assert not can_share_known_fact(speaker, listener, fact, world)


def test_non_conversational_activity_blocks_structured_fact_sharing():
    history, speaker, listener, _crime, fact = _speaker_listener_with_crime()
    world = _ambient_share_world(history, speaker, listener)
    start_activity(
        speaker,
        "eating",
        10,
        world=world,
        allows_conversation=False,
        allows_observation=True,
        allows_social_sharing=False,
    )

    assert not can_share_known_fact(speaker, listener, fact, world)
    assert choose_shareable_fact(speaker, listener, world) is None


def test_generic_ambient_dialogue_still_emits_when_no_shareable_facts_exist():
    speaker = NPC(1, 1, name="Speaker")
    listener = NPC(2, 1, name="Listener")
    speaker.id = 1
    listener.id = 2
    speaker.social.relationships[listener.id] = 85
    world = _ambient_share_world(HistoryLedger(), speaker, listener)
    start_activity(
        speaker,
        "sitting",
        10,
        world=world,
        allows_conversation=True,
        allows_observation=True,
        allows_social_sharing=True,
    )

    assert choose_shareable_fact(speaker, listener, world) is None
    World._handle_ambient_activity_interactions(world)

    assert world.active_ambient_speech
    ambient_text = world.active_ambient_speech[-1].text
    assert "ordinary" in ambient_text or "heard anything" in ambient_text or "Nothing" in ambient_text
    assert not world.chat_log



def _conversation_world(history, npcs, *, game_time=100):
    return SimpleNamespace(
        game_state="PLAYING",
        chat_ui_active=False,
        game_time=game_time,
        history=history,
        village_npcs=npcs,
        player=SimpleNamespace(id=999, x=0, y=0, physical=SimpleNamespace(hearing_radius=12)),
        npcs=[],
        visual_effects=[],
        buildings_by_id={},
        _can_player_overhear=lambda _speaker: False,
        add_message_to_chat_log=lambda message: None,
        get_entity_display_name=lambda entity: entity.name,
        get_entity_by_id=lambda entity_id: next((npc for npc in npcs if npc.id == entity_id), None),
    )


def _talk_ready_npc(entity_id, x, y, *, name="NPC", age=30, profession="Unemployed", title=""):
    npc = NPC(x, y, name=name)
    npc.id = entity_id
    npc.age = age
    npc.economic.profession = profession
    npc.social.title = title
    return npc


def test_close_npcs_initiate_more_than_strangers():
    history = HistoryLedger()
    speaker = _talk_ready_npc(301, 1, 1, name="Speaker")
    close_listener = _talk_ready_npc(302, 2, 1, name="Friend")
    stranger = _talk_ready_npc(303, 2, 2, name="Stranger")
    speaker.social.relationships[close_listener.id] = 90
    speaker.social.relationships[stranger.id] = 35
    world = _conversation_world(history, [speaker, close_listener, stranger])

    close_score = score_ambient_conversation_pair(speaker, close_listener, world)
    stranger_score = score_ambient_conversation_pair(speaker, stranger, world)

    assert close_score > stranger_score
    assert choose_ambient_conversation_pair(world) == (speaker, close_listener)


def test_non_conversational_activity_blocks_conversation_initiation():
    history = HistoryLedger()
    speaker = _talk_ready_npc(311, 1, 1, name="Eating")
    listener = _talk_ready_npc(312, 2, 1, name="Friend")
    speaker.social.relationships[listener.id] = 95
    world = _conversation_world(history, [speaker, listener])
    start_activity(
        speaker,
        "eating",
        10,
        world=world,
        allows_conversation=False,
        allows_observation=True,
        allows_social_sharing=False,
    )

    assert score_ambient_conversation_pair(speaker, listener, world) == 0.0
    assert choose_ambient_conversation_pair(world) is None


def test_elder_speaker_prefers_reflective_history_topics():
    history = HistoryLedger()
    elder = _talk_ready_npc(321, 1, 1, name="Elder", age=72)
    listener = _talk_ready_npc(322, 2, 1, name="Neighbor")
    elder.social.relationships[listener.id] = 75
    death = history.record_death(
        deceased_id=901,
        cause_of_death="illness",
        description="An elder reflects on a death.",
        game_time=10,
    )
    elder.knowledge.learn_history_record(death, "witnessed", 0.9, 20)
    reflective_world = _conversation_world(history, [elder, listener])

    young_topic_speaker = _talk_ready_npc(323, 1, 1, name="Birth Teller", age=72)
    young_topic_listener = _talk_ready_npc(324, 2, 1, name="Neighbor")
    young_topic_speaker.social.relationships[young_topic_listener.id] = 75
    birth_history = HistoryLedger()
    birth = birth_history.record_birth(child_id=902, child_name="Mira", parent_ids=(), description="A child was born.", game_time=10)
    young_topic_speaker.knowledge.learn_history_record(birth, "witnessed", 0.9, 20)
    birth_world = _conversation_world(birth_history, [young_topic_speaker, young_topic_listener])

    assert score_ambient_conversation_pair(elder, listener, reflective_world) > score_ambient_conversation_pair(
        young_topic_speaker, young_topic_listener, birth_world
    )


def test_worker_speaker_prefers_employment_and_work_chatter():
    employment_history = HistoryLedger()
    worker = _talk_ready_npc(331, 1, 1, name="Worker", profession="Blacksmith")
    listener = _talk_ready_npc(332, 2, 1, name="Coworker", profession="Blacksmith")
    worker.social.relationships[listener.id] = 70
    employment = employment_history.record_employment_change(
        worker_id=777,
        profession="Blacksmith",
        employment_action="hired",
        description="A blacksmith was hired.",
        game_time=10,
    )
    worker.knowledge.learn_history_record(employment, "witnessed", 0.9, 20)
    employment_world = _conversation_world(employment_history, [worker, listener])

    birth_history = HistoryLedger()
    idle_worker = _talk_ready_npc(333, 1, 1, name="Worker", profession="Blacksmith")
    idle_listener = _talk_ready_npc(334, 2, 1, name="Coworker", profession="Blacksmith")
    idle_worker.social.relationships[idle_listener.id] = 70
    birth = birth_history.record_birth(child_id=778, child_name="Rowan", parent_ids=(), description="A child was born.", game_time=10)
    idle_worker.knowledge.learn_history_record(birth, "witnessed", 0.9, 20)
    birth_world = _conversation_world(birth_history, [idle_worker, idle_listener])

    assert score_ambient_conversation_pair(worker, listener, employment_world) > score_ambient_conversation_pair(
        idle_worker, idle_listener, birth_world
    )


def test_fear_reduces_initiation_toward_dangerous_actor():
    history = HistoryLedger()
    speaker = _talk_ready_npc(341, 1, 1, name="Wary")
    dangerous = _talk_ready_npc(342, 2, 1, name="Threat")
    safe = _talk_ready_npc(343, 2, 2, name="Safe")
    speaker.social.relationships[dangerous.id] = 80
    speaker.social.relationships[safe.id] = 80
    speaker.social.recent_social_reactions.append(
        {"reaction_type": "fear", "target_entity_id": dangerous.id, "score": -30, "source_record_id": "crime-1"}
    )
    world = _conversation_world(history, [speaker, dangerous, safe])

    assert score_ambient_conversation_pair(speaker, dangerous, world) < score_ambient_conversation_pair(speaker, safe, world)


def test_ambient_initiation_cooldown_prevents_chatter_spam():
    history = HistoryLedger()
    speaker = _talk_ready_npc(351, 1, 1, name="Speaker")
    listener = _talk_ready_npc(352, 2, 1, name="Listener")
    speaker.social.relationships[listener.id] = 90
    world = _conversation_world(history, [speaker, listener])

    assert score_ambient_conversation_pair(speaker, listener, world) > 0
    mark_ambient_conversation_started(speaker, listener, world)

    assert score_ambient_conversation_pair(speaker, listener, world) == 0.0
    assert choose_ambient_conversation_pair(world) is None



def test_nearby_npcs_in_same_tavern_and_worksite_form_scenes():
    history = HistoryLedger()
    tavern_a = _talk_ready_npc(401, 10, 10, name="Tavern A")
    tavern_b = _talk_ready_npc(402, 11, 10, name="Tavern B")
    tavern_a.current_building_id = tavern_b.current_building_id = "tavern-1"
    work_a = _talk_ready_npc(403, 20, 20, name="Smith A")
    work_b = _talk_ready_npc(404, 21, 20, name="Smith B")
    work_a.schedule.work_building_id = work_b.schedule.work_building_id = "forge-1"
    work_a.schedule.current_task = work_b.schedule.current_task = TaskType.AT_WORK
    world = _conversation_world(history, [tavern_a, tavern_b, work_a, work_b])
    world.buildings_by_id = {
        "tavern-1": SimpleNamespace(id="tavern-1", building_type="tavern", category="commercial"),
        "forge-1": SimpleNamespace(id="forge-1", building_type="blacksmith_shop", category="workplace"),
    }

    scenes = update_social_scenes(world, force=True)
    scene_types = {scene.scene_type for scene in scenes}

    assert "tavern" in scene_types
    assert "worksite" in scene_types
    assert any(set(scene.participant_ids) == {401, 402} for scene in scenes)
    assert any(set(scene.participant_ids) == {403, 404} for scene in scenes)


def test_npcs_in_separate_locations_do_not_form_scene():
    history = HistoryLedger()
    left = _talk_ready_npc(411, 1, 1, name="Left")
    right = _talk_ready_npc(412, 30, 30, name="Right")
    left.current_building_id = "tavern-1"
    right.current_building_id = "tavern-2"
    world = _conversation_world(history, [left, right])
    world.buildings_by_id = {
        "tavern-1": SimpleNamespace(id="tavern-1", building_type="tavern", category="commercial"),
        "tavern-2": SimpleNamespace(id="tavern-2", building_type="tavern", category="commercial"),
    }

    assert update_social_scenes(world, force=True) == []


def test_scene_overhearing_teaches_third_participant_with_reduced_confidence():
    history, speaker, listener, crime, fact = _speaker_listener_with_crime()
    bystander = _talk_ready_npc(413, 1, 2, name="Bystander")
    speaker.current_building_id = listener.current_building_id = bystander.current_building_id = "tavern-1"
    world = _conversation_world(history, [speaker, listener, bystander])
    world.buildings_by_id = {"tavern-1": SimpleNamespace(id="tavern-1", building_type="tavern", category="commercial")}
    scene = update_social_scenes(world, force=True)[0]

    assert share_known_fact(speaker, listener, fact, source_type="told")
    overheard_count = share_fact_with_scene_overhearers(world, scene, speaker, listener, fact)

    assert overheard_count == 1
    told_fact = listener.knowledge.known_history_facts[crime.id]
    overheard_fact = bystander.knowledge.known_history_facts[crime.id]
    assert overheard_fact.source_type == "overheard"
    assert overheard_fact.confidence < told_fact.confidence
    assert crime.id in scene.overheard_record_ids


def test_non_observing_activity_blocks_scene_overhearing():
    history, speaker, listener, crime, fact = _speaker_listener_with_crime()
    bystander = _talk_ready_npc(423, 1, 2, name="Distracted")
    speaker.current_building_id = listener.current_building_id = bystander.current_building_id = "tavern-1"
    world = _conversation_world(history, [speaker, listener, bystander])
    world.buildings_by_id = {"tavern-1": SimpleNamespace(id="tavern-1", building_type="tavern", category="commercial")}
    start_activity(
        bystander,
        "private_work",
        20,
        world=world,
        allows_conversation=True,
        allows_observation=False,
        allows_social_sharing=False,
    )
    scene = update_social_scenes(world, force=True)[0]

    assert share_known_fact(speaker, listener, fact, source_type="told")
    assert share_fact_with_scene_overhearers(world, scene, speaker, listener, fact) == 0
    assert crime.id not in bystander.knowledge.known_history_facts


def test_social_scenes_expire_after_inactivity():
    history = HistoryLedger()
    left = _talk_ready_npc(431, 1, 1, name="Left")
    right = _talk_ready_npc(432, 2, 1, name="Right")
    left.current_building_id = right.current_building_id = "tavern-1"
    world = _conversation_world(history, [left, right], game_time=10)
    world.buildings_by_id = {"tavern-1": SimpleNamespace(id="tavern-1", building_type="tavern", category="commercial")}

    assert update_social_scenes(world, force=True)
    world.village_npcs = []
    world.game_time = 10 + SCENE_INACTIVE_TICKS + 1

    assert update_social_scenes(world, force=True) == []


def test_scene_tone_updates_from_shared_topic():
    history, speaker, listener, _crime, fact = _speaker_listener_with_crime()
    speaker.current_building_id = listener.current_building_id = "tavern-1"
    world = _conversation_world(history, [speaker, listener])
    world.buildings_by_id = {"tavern-1": SimpleNamespace(id="tavern-1", building_type="tavern", category="commercial")}
    scene = update_social_scenes(world, force=True)[0]
    topic = build_dialogue_topic_from_fact(fact, world)

    record_scene_topic(scene, topic, world)

    assert scene.tone == "tense"
    assert scene.active_topic_ids
