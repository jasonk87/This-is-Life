from types import SimpleNamespace

from entities.base import NPC
from entities.social import (
    KnownHistoryFact,
    KnowledgeComponent,
    clear_fact_dependent_memory,
    is_transient_known_fact,
    reset_transient_knowledge,
    should_clear_fact_for_reset,
)
from presentation.dialogue_surface import build_dialogue_topics_from_npc
from simulation.history import HistoryLedger
from simulation.knowledge import KnowledgeSystem
from simulation.records import ChronicleArchive
from simulation.systems.ambient_info import can_share_known_fact
from simulation.systems.social_reaction import apply_known_history_fact_reactions


def _holder():
    return SimpleNamespace(
        knowledge=KnowledgeComponent(),
        social=SimpleNamespace(
            reacted_history_fact_ids=set(),
            reacted_history_fact_state={},
            recent_social_reactions=[],
        ),
    )


def _world(history, *entities, game_time=100):
    by_id = {getattr(entity, "id", None): entity for entity in entities}
    return SimpleNamespace(
        history=history,
        game_time=game_time,
        player=SimpleNamespace(id=999),
        village_npcs=list(entities),
        npcs=[],
        get_entity_by_id=lambda entity_id: by_id.get(entity_id),
    )


def test_reset_clears_legacy_known_events():
    holder = _holder()
    holder.knowledge.known_events["event-1"] = object()
    system = KnowledgeSystem(ChronicleArchive(HistoryLedger()))

    cleared = system.reset_known_events(holder)

    assert holder.knowledge.known_events == {}
    assert cleared == set()


def test_reset_clears_transient_known_history_facts_and_dependent_memory():
    history = HistoryLedger()
    crime = history.record_crime(
        crime_kind="theft",
        suspect_id=1,
        victim_id=2,
        description="A theft rumor spread.",
        game_time=0,
    )
    holder = _holder()
    holder.knowledge.learn_history_record(crime, "overheard", 0.4, 0)
    topic_id = f"crime:{crime.record_id}"
    holder.knowledge.recently_spoken_topic_ids.append(topic_id)
    holder.knowledge.last_spoken_topic_tick[topic_id] = 10
    holder.knowledge.spoken_topic_counts[topic_id] = 2
    holder.knowledge.shared_fact_listener_ids[crime.record_id] = {5}
    holder.social.reacted_history_fact_ids.add(crime.record_id)
    holder.social.reacted_history_fact_state[crime.record_id] = object()
    holder.social.recent_social_reactions.append({"source_record_id": crime.record_id, "reaction_type": "fear"})

    cleared = reset_transient_knowledge(holder)

    assert cleared == {crime.record_id}
    assert crime.record_id not in holder.knowledge.known_history_facts
    assert holder.knowledge.recently_spoken_topic_ids == []
    assert holder.knowledge.last_spoken_topic_tick == {}
    assert holder.knowledge.spoken_topic_counts == {}
    assert holder.knowledge.shared_fact_listener_ids == {}
    assert crime.record_id not in holder.social.reacted_history_fact_ids
    assert crime.record_id not in holder.social.reacted_history_fact_state
    assert holder.social.recent_social_reactions == []


def test_reset_preserves_family_death_public_book_and_official_facts():
    history = HistoryLedger()
    death = history.record_death(deceased_id=10, description="Family died.", game_time=0)
    public_crime = history.record_crime(
        crime_kind="murder",
        suspect_id=11,
        victim_id=12,
        description="A public murder record.",
        game_time=0,
    )
    book_birth = history.record_birth(
        child_id=13,
        parent_ids=(),
        child_name="Lio",
        description="A child was chronicled.",
        game_time=0,
    )
    official_job = history.record_employment_change(
        worker_id=14,
        profession="Guard",
        employment_action="hired",
        description="Official hiring record.",
        game_time=0,
    )
    holder = _holder()
    holder.knowledge.learn_history_record(death, "family", 1.0, 0)
    holder.knowledge.learn_history_record(public_crime, "public_record", 1.0, 0)
    holder.knowledge.learn_history_record(book_birth, "book", 1.0, 0)
    holder.knowledge.learn_history_record(official_job, "official_record", 1.0, 0)

    cleared = reset_transient_knowledge(holder)

    assert cleared == set()
    assert set(holder.knowledge.known_history_facts) == {
        death.record_id,
        public_crime.record_id,
        book_birth.record_id,
        official_job.record_id,
    }


def test_cleared_fact_no_longer_appears_in_dialogue_topics_or_sharing():
    history = HistoryLedger()
    speaker = NPC(0, 0, name="Speaker")
    listener = NPC(1, 0, name="Listener")
    crime = history.record_crime(
        crime_kind="theft",
        suspect_id=speaker.id,
        victim_id=listener.id,
        description="A theft rumor spread.",
        game_time=0,
    )
    speaker.knowledge.learn_history_record(crime, "told", 0.5, 0)
    world = _world(history, speaker, listener)

    assert build_dialogue_topics_from_npc(speaker, world)
    assert can_share_known_fact(speaker, listener, speaker.knowledge.known_history_facts[crime.record_id], world)

    reset_transient_knowledge(speaker)

    assert build_dialogue_topics_from_npc(speaker, world) == []
    assert crime.record_id not in speaker.knowledge.known_history_facts


def test_cleared_fact_reaction_state_does_not_block_future_relearning_reaction():
    history = HistoryLedger()
    observer = NPC(0, 0, name="Observer")
    player = SimpleNamespace(id=101)
    crime = history.record_crime(
        crime_kind="assault",
        suspect_id=player.id,
        victim_id=202,
        description="The player assaulted someone.",
        game_time=0,
    )
    observer.knowledge.learn_history_record(crime, "told", 0.8, 0)
    world = _world(history, observer, game_time=10)
    world.player = player
    assert apply_known_history_fact_reactions(world, observer) == 1
    assert crime.record_id in observer.social.reacted_history_fact_ids

    reset_transient_knowledge(observer)
    assert crime.record_id not in observer.social.reacted_history_fact_ids
    assert crime.record_id not in observer.social.reacted_history_fact_state

    observer.knowledge.learn_history_record(crime, "official_record", 1.0, 20)
    assert apply_known_history_fact_reactions(world, observer) == 1
    assert crime.record_id in observer.social.reacted_history_fact_ids


def test_backward_compatible_old_known_history_fact_can_be_cleared():
    old_fact = KnownHistoryFact(
        source_record_id="old-rumor",
        record_type="npc_migrated",
        subject_entity_ids=(1,),
        known_at_tick=0,
        source_type="told",
        confidence=0.4,
    )
    for field_name in (
        "memory_strength",
        "permanence",
        "emotional_weight",
        "decay_rate",
        "reinforcement_count",
        "last_recalled_tick",
        "last_reinforced_tick",
    ):
        object.__delattr__(old_fact, field_name)
    holder = _holder()
    holder.knowledge.known_history_facts[old_fact.source_record_id] = old_fact

    assert is_transient_known_fact(old_fact)
    assert should_clear_fact_for_reset(old_fact, "transient")
    assert reset_transient_knowledge(holder) == {old_fact.source_record_id}


def test_clear_fact_dependent_memory_does_not_remove_unrelated_state():
    holder = _holder()
    holder.knowledge.recently_spoken_topic_ids.extend(["crime:clear-me", "death:keep-me"])
    holder.knowledge.last_spoken_topic_tick.update({"crime:clear-me": 1, "death:keep-me": 2})
    holder.social.reacted_history_fact_ids.update({"clear-me", "keep-me"})
    holder.social.reacted_history_fact_state.update({"clear-me": object(), "keep-me": object()})
    holder.social.recent_social_reactions.extend([
        {"source_record_id": "clear-me", "reaction_type": "fear"},
        {"source_record_id": "keep-me", "reaction_type": "grief"},
    ])

    clear_fact_dependent_memory(holder, "clear-me", social=holder.social)

    assert holder.knowledge.recently_spoken_topic_ids == ["death:keep-me"]
    assert holder.knowledge.last_spoken_topic_tick == {"death:keep-me": 2}
    assert holder.social.reacted_history_fact_ids == {"keep-me"}
    assert set(holder.social.reacted_history_fact_state) == {"keep-me"}
    assert holder.social.recent_social_reactions == [{"source_record_id": "keep-me", "reaction_type": "grief"}]
