from types import SimpleNamespace

from config import DAY_LENGTH_TICKS
from entities.social import KnowledgeComponent
from presentation.dialogue_surface import (
    DialogueContext,
    DialogueTopic,
    build_dialogue_topics_from_npc,
    get_contextual_dialogue_lines,
    render_dialogue_line,
)
from simulation.history import HistoryLedger


def _entity(entity_id, name):
    return SimpleNamespace(id=entity_id, name=name)


def _speaker(entity_id=1, name="Speaker"):
    return SimpleNamespace(
        id=entity_id,
        name=name,
        knowledge=KnowledgeComponent(),
        social=SimpleNamespace(
            recent_social_reactions=[],
            opinion_modifiers={},
        ),
    )


def _world(history, *, day=0, entities=()):
    entities_by_id = {entity.id: entity for entity in entities}
    return SimpleNamespace(
        history=history,
        game_time=day * DAY_LENGTH_TICKS,
        player=entities_by_id.get(100, _entity(100, "Player")),
        village_npcs=list(entities),
        npcs=[],
        get_entity_by_id=lambda entity_id: entities_by_id.get(entity_id),
    )


def test_crime_fact_produces_varied_factual_line():
    history = HistoryLedger()
    speaker = _speaker(10)
    listener = _entity(11, "Listener")
    suspect = _entity(100, "Rook")
    victim = _entity(101, "Mira")
    crime = history.record_crime(
        crime_kind="assault",
        suspect_id=suspect.id,
        victim_id=victim.id,
        description="Raw description should not be needed.",
        game_time=5,
    )
    speaker.knowledge.learn_history_record(crime, "witnessed", 0.95, 10)

    day_one = _world(history, day=1, entities=[speaker, listener, suspect, victim])
    day_two = _world(history, day=2, entities=[speaker, listener, suspect, victim])
    first = get_contextual_dialogue_lines(speaker, listener, day_one, limit=1)[0]
    second = get_contextual_dialogue_lines(speaker, listener, day_two, limit=1)[0]

    assert first.topic_type == "crime"
    assert first.tone == "angry"
    assert "Rook" in first.text
    assert "Mira" in first.text
    assert "assault" in first.text
    assert first.text != second.text


def test_death_grief_reaction_produces_sad_line():
    speaker = _speaker(20)
    listener = _entity(21, "Listener")
    deceased = _entity(22, "Alda")
    speaker.social.recent_social_reactions.append(
        {
            "source_record_id": "death-1",
            "reaction_type": "grief",
            "target_entity_id": deceased.id,
            "score": -25,
            "reason": "known_close_death",
        }
    )

    line = get_contextual_dialogue_lines(
        speaker,
        listener,
        _world(HistoryLedger(), day=3, entities=[speaker, listener, deceased]),
        limit=1,
    )[0]

    assert line.topic_type == "grief"
    assert line.tone == "sad"
    assert "Alda" in line.text


def test_fear_reaction_produces_fearful_line():
    speaker = _speaker(30)
    listener = _entity(31, "Listener")
    threat = _entity(32, "Bran")
    speaker.social.recent_social_reactions.append(
        {
            "source_record_id": "crime-1",
            "reaction_type": "fear",
            "target_entity_id": threat.id,
            "score": -20,
            "reason": "known_violent_crime",
        }
    )

    line = get_contextual_dialogue_lines(
        speaker,
        listener,
        _world(HistoryLedger(), day=4, entities=[speaker, listener, threat]),
        limit=1,
    )[0]

    assert line.topic_type == "fear"
    assert line.tone == "fearful"
    assert "Bran" in line.text


def test_same_context_gives_stable_output():
    topic = DialogueTopic(
        "crime",
        "angry",
        "fact-1",
        confidence=1.0,
        subject_id=1,
        target_id=2,
        detail="assault",
    )
    context = DialogueContext(
        speaker_id=10,
        listener_id=11,
        current_day=2,
        entity_names={1: "Rook", 2: "Mira"},
    )

    first = render_dialogue_line(topic, context)
    second = render_dialogue_line(topic, context)

    assert first == second


def test_different_day_or_speaker_can_change_output():
    topic = DialogueTopic(
        "death",
        "sad",
        "fact-2",
        confidence=1.0,
        subject_id=1,
    )
    day_one = DialogueContext(10, 11, 1, {1: "Alda"})
    day_two = DialogueContext(10, 11, 2, {1: "Alda"})
    other_speaker = DialogueContext(11, 12, 1, {1: "Alda"})

    first = render_dialogue_line(topic, day_one).text

    assert render_dialogue_line(topic, day_two).text != first
    assert render_dialogue_line(topic, other_speaker).text != first


def test_low_confidence_fact_uses_uncertain_phrasing():
    history = HistoryLedger()
    speaker = _speaker(40)
    listener = _entity(41, "Listener")
    suspect = _entity(42, "Pella")
    victim = _entity(43, "Toma")
    crime = history.record_crime(
        crime_kind="theft",
        suspect_id=suspect.id,
        victim_id=victim.id,
        description="A theft was reported.",
        game_time=7,
    )
    speaker.knowledge.learn_history_record(crime, "told", 0.2, 12)

    line = get_contextual_dialogue_lines(
        speaker,
        listener,
        _world(history, day=5, entities=[speaker, listener, suspect, victim]),
        limit=1,
    )[0]

    assert line.tone == "uncertain"
    assert line.text.startswith("People say")
    assert "Pella" in line.text


def test_no_facts_returns_generic_small_talk_fallback():
    speaker = _speaker(50)
    listener = _entity(51, "Listener")

    lines = get_contextual_dialogue_lines(
        speaker,
        listener,
        _world(HistoryLedger(), day=6, entities=[speaker, listener]),
        limit=3,
    )

    assert len(lines) == 1
    assert lines[0].topic_type == "small_talk"
    assert lines[0].tone == "neutral"


def test_missing_entity_name_uses_generic_label_not_record_name():
    history = HistoryLedger()
    speaker = _speaker(60)
    listener = _entity(61, "Listener")
    birth = history.record_birth(
        child_id=999,
        parent_ids=(),
        child_name="Hidden Name",
        description="Hidden Name was born.",
        game_time=8,
    )
    speaker.knowledge.learn_history_record(birth, "official_record", 1.0, 13)

    topics = build_dialogue_topics_from_npc(speaker, _world(history, entities=[speaker, listener]))
    line = render_dialogue_line(
        topics[0],
        DialogueContext(speaker.id, listener.id, 0, {speaker.id: speaker.name, listener.id: listener.name}),
    )

    assert "Entity 999" in line.text
    assert "Hidden Name" not in line.text


def test_recent_topic_is_not_reselected_when_alternative_exists():
    history = HistoryLedger()
    speaker = _speaker(70)
    listener = _entity(71, "Listener")
    suspect = _entity(72, "Rook")
    victim = _entity(73, "Mira")
    child = _entity(74, "Lio")
    crime = history.record_crime(
        crime_kind="assault",
        suspect_id=suspect.id,
        victim_id=victim.id,
        description="Rook assaulted Mira.",
        game_time=4,
    )
    birth = history.record_birth(
        child_id=child.id,
        parent_ids=(),
        child_name="Lio",
        description="Lio was born.",
        game_time=5,
    )
    speaker.knowledge.learn_history_record(crime, "witnessed", 1.0, 10)
    speaker.knowledge.learn_history_record(birth, "official_record", 1.0, 11)
    world = _world(history, day=2, entities=[speaker, listener, suspect, victim, child])

    first = get_contextual_dialogue_lines(speaker, listener, world, limit=1)[0]
    second = get_contextual_dialogue_lines(speaker, listener, world, limit=1)[0]

    assert first.topic_type == "crime"
    assert second.topic_type == "birth"
    assert first.source_id != second.source_id


def test_topic_cooldown_expires_after_enough_time():
    history = HistoryLedger()
    speaker = _speaker(80)
    listener = _entity(81, "Listener")
    suspect = _entity(82, "Rook")
    victim = _entity(83, "Mira")
    child = _entity(84, "Lio")
    crime = history.record_crime(
        crime_kind="assault",
        suspect_id=suspect.id,
        victim_id=victim.id,
        description="Rook assaulted Mira.",
        game_time=4,
    )
    birth = history.record_birth(
        child_id=child.id,
        parent_ids=(),
        child_name="Lio",
        description="Lio was born.",
        game_time=5,
    )
    speaker.knowledge.learn_history_record(crime, "witnessed", 1.0, 10)
    speaker.knowledge.learn_history_record(birth, "official_record", 1.0, 11)

    day_two = _world(history, day=2, entities=[speaker, listener, suspect, victim, child])
    first = get_contextual_dialogue_lines(speaker, listener, day_two, limit=1)[0]
    get_contextual_dialogue_lines(speaker, listener, day_two, limit=1)

    day_three = _world(history, day=3, entities=[speaker, listener, suspect, victim, child])
    after_cooldown = get_contextual_dialogue_lines(speaker, listener, day_three, limit=1)[0]

    assert first.topic_type == "crime"
    assert after_cooldown.topic_type == "crime"
    assert after_cooldown.source_id == first.source_id


def test_high_priority_crime_overrides_small_talk_when_available():
    history = HistoryLedger()
    speaker = _speaker(90)
    listener = _entity(91, "Listener")
    suspect = _entity(92, "Rook")
    victim = _entity(93, "Mira")
    crime = history.record_crime(
        crime_kind="assault",
        suspect_id=suspect.id,
        victim_id=victim.id,
        description="Rook assaulted Mira.",
        game_time=4,
    )
    speaker.knowledge.learn_history_record(crime, "witnessed", 1.0, 10)

    line = get_contextual_dialogue_lines(
        speaker,
        listener,
        _world(history, day=2, entities=[speaker, listener, suspect, victim]),
        limit=1,
    )[0]

    assert line.topic_type == "crime"
    assert line.topic_type != "small_talk"


def test_topic_selection_remains_deterministic_with_same_memory_state():
    history = HistoryLedger()
    listener = _entity(101, "Listener")
    suspect = _entity(102, "Rook")
    victim = _entity(103, "Mira")
    crime = history.record_crime(
        crime_kind="assault",
        suspect_id=suspect.id,
        victim_id=victim.id,
        description="Rook assaulted Mira.",
        game_time=4,
    )
    left = _speaker(100)
    right = _speaker(100)
    left.knowledge.learn_history_record(crime, "witnessed", 1.0, 10)
    right.knowledge.learn_history_record(crime, "witnessed", 1.0, 10)
    world = _world(history, day=2, entities=[left, listener, suspect, victim])

    left_line = get_contextual_dialogue_lines(left, listener, world, limit=1)[0]
    right_line = get_contextual_dialogue_lines(right, listener, world, limit=1)[0]

    assert left_line == right_line
    assert (
        left.knowledge.recently_spoken_topic_ids
        == right.knowledge.recently_spoken_topic_ids
    )
    assert left.knowledge.spoken_topic_counts == right.knowledge.spoken_topic_counts
