from types import SimpleNamespace

from entities.base import NPC
from simulation.history import HistoryLedger
from simulation.systems.social_reaction import apply_known_history_fact_reactions


def _world(history, player_id=1, game_time=100):
    return SimpleNamespace(
        history=history,
        player=SimpleNamespace(id=player_id),
        game_time=game_time,
    )


def _npc(name="Observer"):
    npc = NPC(0, 0, name=name)
    npc.schedule.current_path = []
    return npc


def test_known_player_violent_crime_creates_fear_and_distrust():
    history = HistoryLedger()
    player = SimpleNamespace(id=101)
    observer = _npc()
    crime = history.record_crime(
        crime_kind="assault",
        suspect_id=player.id,
        victim_id=202,
        description="The player assaulted someone.",
        game_time=10,
    )
    observer.knowledge.learn_history_record(
        crime,
        source_type="told",
        confidence=0.8,
        tick=20,
    )

    applied = apply_known_history_fact_reactions(
        SimpleNamespace(history=history, player=player, game_time=30),
        observer,
    )

    assert applied == 1
    assert player.id in observer.social.grudges
    assert observer.get_distrust_towards(player) > 0
    assert observer.social.recent_social_reactions[-1]["reaction_type"] == "fear"
    assert observer.social.recent_social_reactions[-1]["target_entity_id"] == player.id
    assert observer.social.opinion_modifiers[player.id] < 0


def test_known_close_relation_death_creates_grief_reaction():
    history = HistoryLedger()
    observer = _npc()
    deceased = _npc("Close Friend")
    observer.social.relationships[deceased.id] = 85
    death = history.record_death(
        deceased_id=deceased.id,
        cause_of_death="illness",
        description="A close friend died.",
        game_time=11,
    )
    observer.knowledge.learn_history_record(
        death,
        source_type="official_record",
        confidence=1.0,
        tick=21,
    )

    applied = apply_known_history_fact_reactions(_world(history), observer)

    assert applied == 1
    reaction = observer.social.recent_social_reactions[-1]
    assert reaction["reaction_type"] == "grief"
    assert reaction["target_entity_id"] == deceased.id
    assert reaction["score"] < 0


def test_known_history_fact_reactions_do_not_stack_for_duplicate_passes():
    history = HistoryLedger()
    observer = _npc()
    worker = _npc("Guard")
    employment = history.record_employment_change(
        worker_id=worker.id,
        profession="Guard",
        employment_action="hired",
        description="A guard was hired.",
        game_time=12,
    )
    observer.knowledge.learn_history_record(
        employment,
        source_type="read",
        confidence=1.0,
        tick=22,
    )

    world = _world(history)
    assert apply_known_history_fact_reactions(world, observer) == 1
    first_relationship = observer.social.relationships[worker.id]
    first_reaction_count = len(observer.social.recent_social_reactions)

    assert apply_known_history_fact_reactions(world, observer) == 0
    assert observer.social.relationships[worker.id] == first_relationship
    assert len(observer.social.recent_social_reactions) == first_reaction_count


def test_unknown_or_unimportant_known_facts_do_not_create_reactions():
    history = HistoryLedger()
    observer = _npc()
    event = history.add_event(
        "weather_report",
        "It rained today.",
        subject_id=303,
        game_time=13,
    )
    observer.knowledge.learn_history_record(
        event,
        source_type="read",
        confidence=1.0,
        tick=23,
    )

    applied = apply_known_history_fact_reactions(_world(history), observer)

    assert applied == 0
    assert observer.social.recent_social_reactions == []
    assert observer.social.opinion_modifiers == {}


def _violent_crime_for_confidence_tests(history, suspect_id=404):
    return history.record_crime(
        crime_kind="assault",
        suspect_id=suspect_id,
        victim_id=505,
        description="A confidence-sensitive assault record.",
        game_time=30,
    )


def test_low_confidence_rumor_causes_mild_reaction_state():
    history = HistoryLedger()
    observer = _npc()
    crime = _violent_crime_for_confidence_tests(history)
    observer.knowledge.learn_history_record(crime, source_type="told", confidence=0.2, tick=31)

    applied = apply_known_history_fact_reactions(_world(history, game_time=40), observer)

    assert applied == 1
    reaction = observer.social.recent_social_reactions[-1]
    assert reaction["reaction_type"] == "fear"
    assert reaction["score"] == -7.0
    state = observer.social.reacted_history_fact_state[crime.id]
    assert state.reacted_confidence == 0.2
    assert state.reacted_source_type == "told"
    assert state.last_reaction_tick == 40
    assert state.applied_reaction_strength == 7.0


def test_later_high_confidence_confirmation_strengthens_only_delta():
    history = HistoryLedger()
    observer = _npc()
    crime = _violent_crime_for_confidence_tests(history)
    observer.knowledge.learn_history_record(crime, source_type="told", confidence=0.2, tick=31)
    world = _world(history, game_time=40)

    assert apply_known_history_fact_reactions(world, observer) == 1
    first_opinion = observer.social.opinion_modifiers[404]
    first_relationship = observer.social.relationships[404]

    observer.knowledge.learn_history_record(crime, source_type="official_record", confidence=1.0, tick=45)
    world.game_time = 50
    assert apply_known_history_fact_reactions(world, observer) == 1

    assert first_opinion == -7.0
    assert observer.social.opinion_modifiers[404] == -35.0
    assert observer.social.recent_social_reactions[-1]["score"] == -28.0
    assert observer.social.relationships[404] == first_relationship
    state = observer.social.reacted_history_fact_state[crime.id]
    assert state.reacted_confidence == 1.0
    assert state.reacted_source_type == "official_record"
    assert state.last_reaction_tick == 50
    assert state.applied_reaction_strength == 35.0


def test_equal_confidence_confirmation_does_not_stack():
    history = HistoryLedger()
    observer = _npc()
    crime = _violent_crime_for_confidence_tests(history)
    observer.knowledge.learn_history_record(crime, source_type="told", confidence=0.8, tick=31)
    world = _world(history, game_time=40)

    assert apply_known_history_fact_reactions(world, observer) == 1
    first_opinion = observer.social.opinion_modifiers[404]
    first_reaction_count = len(observer.social.recent_social_reactions)
    observer.knowledge.learn_history_record(crime, source_type="official_record", confidence=0.8, tick=45)
    world.game_time = 50

    assert apply_known_history_fact_reactions(world, observer) == 0
    assert observer.social.opinion_modifiers[404] == first_opinion
    assert len(observer.social.recent_social_reactions) == first_reaction_count


def test_lower_confidence_confirmation_does_not_weaken_existing_reaction():
    history = HistoryLedger()
    observer = _npc()
    crime = _violent_crime_for_confidence_tests(history)
    observer.knowledge.learn_history_record(crime, source_type="official_record", confidence=0.9, tick=31)
    world = _world(history, game_time=40)

    assert apply_known_history_fact_reactions(world, observer) == 1
    first_opinion = observer.social.opinion_modifiers[404]
    first_state = observer.social.reacted_history_fact_state[crime.id]
    observer.knowledge.learn_history_record(crime, source_type="told", confidence=0.4, tick=45)
    world.game_time = 50

    assert apply_known_history_fact_reactions(world, observer) == 0
    assert observer.social.opinion_modifiers[404] == first_opinion
    assert observer.social.reacted_history_fact_state[crime.id].reacted_confidence == first_state.reacted_confidence
    assert observer.social.reacted_history_fact_state[crime.id].applied_reaction_strength == first_state.applied_reaction_strength


def test_legacy_reacted_history_fact_ids_remain_duplicate_protection():
    history = HistoryLedger()
    observer = _npc()
    crime = _violent_crime_for_confidence_tests(history)
    observer.knowledge.learn_history_record(crime, source_type="official_record", confidence=1.0, tick=31)
    observer.social.reacted_history_fact_ids.add(crime.id)

    applied = apply_known_history_fact_reactions(_world(history, game_time=40), observer)

    assert applied == 0
    assert observer.social.recent_social_reactions == []
    assert observer.social.opinion_modifiers == {}
    state = observer.social.reacted_history_fact_state[crime.id]
    assert state.reacted_source_type == "legacy_reacted_id"
    assert state.reacted_confidence == 1.0
