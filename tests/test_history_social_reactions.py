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
