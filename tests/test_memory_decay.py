from config import DAY_LENGTH_TICKS
from entities.social import (
    KnownHistoryFact,
    KnowledgeComponent,
    compute_memory_profile,
    decay_known_facts,
    reinforce_known_fact,
    should_forget_fact,
)
from simulation.history import HistoryLedger


def test_overheard_rumor_decays_faster_than_witnessed_fact():
    history = HistoryLedger()
    crime = history.record_crime(
        crime_kind="theft",
        suspect_id=1,
        victim_id=2,
        description="A theft happened.",
        game_time=0,
    )
    overheard = KnowledgeComponent()
    witnessed = KnowledgeComponent()
    overheard.learn_history_record(crime, "overheard", 0.7, 0)
    witnessed.learn_history_record(crime, "witnessed", 0.7, 0)

    decay_known_facts(overheard, DAY_LENGTH_TICKS * 2)
    decay_known_facts(witnessed, DAY_LENGTH_TICKS * 2)

    overheard_fact = overheard.known_history_facts[crime.record_id]
    witnessed_fact = witnessed.known_history_facts[crime.record_id]
    assert overheard_fact.memory_strength < witnessed_fact.memory_strength
    assert overheard_fact.decay_rate > witnessed_fact.decay_rate


def test_family_death_persists_longer_than_casual_gossip():
    history = HistoryLedger()
    death = history.record_death(
        deceased_id=10,
        cause_of_death="illness",
        description="A family member died.",
        game_time=0,
    )
    marriage = history.record_marriage(
        spouse_ids=(20, 21),
        description="A casual wedding rumor spread.",
        game_time=0,
    )
    family = KnowledgeComponent()
    gossip = KnowledgeComponent()
    family.learn_history_record(death, "family", 1.0, 0)
    gossip.learn_history_record(marriage, "overheard", 0.6, 0)

    decay_known_facts(family, DAY_LENGTH_TICKS * 20)
    decay_known_facts(gossip, DAY_LENGTH_TICKS * 20)

    assert death.record_id in family.known_history_facts
    assert family.known_history_facts[death.record_id].memory_strength >= family.known_history_facts[death.record_id].permanence
    assert marriage.record_id not in gossip.known_history_facts


def test_repeated_discussion_reinforces_memory():
    history = HistoryLedger()
    migration = history.record_migration(
        traveler_id=30,
        migration_kind="arrived",
        description="Someone arrived.",
        game_time=0,
    )
    knowledge = KnowledgeComponent()
    knowledge.learn_history_record(migration, "told", 0.7, 0)
    before = knowledge.known_history_facts[migration.record_id]

    reinforced = reinforce_known_fact(knowledge, migration.record_id, tick=20, source_type="direct_conversation")
    after = knowledge.known_history_facts[migration.record_id]

    assert reinforced is True
    assert after.memory_strength > before.memory_strength
    assert after.reinforcement_count == before.reinforcement_count + 1
    assert after.last_reinforced_tick == 20


def test_forgotten_weak_rumor_is_removed():
    knowledge = KnowledgeComponent()
    fact = KnownHistoryFact(
        source_record_id="rumor-1",
        record_type="npc_migrated",
        subject_entity_ids=(1,),
        known_at_tick=0,
        source_type="overheard",
        confidence=0.2,
        memory_strength=0.09,
        permanence=0.0,
        decay_rate=0.25,
    )
    knowledge.known_history_facts[fact.source_record_id] = fact

    removed = decay_known_facts(knowledge, DAY_LENGTH_TICKS)

    assert removed == 1
    assert fact.source_record_id not in knowledge.known_history_facts
    assert should_forget_fact(fact) is False


def test_official_book_public_record_knowledge_resists_decay():
    history = HistoryLedger()
    crime = history.record_crime(
        crime_kind="murder",
        suspect_id=40,
        victim_id=41,
        description="A major crime entered the chronicle.",
        game_time=0,
    )
    knowledge = KnowledgeComponent()
    knowledge.learn_history_record(crime, "book", 1.0, 0)

    decay_known_facts(knowledge, DAY_LENGTH_TICKS * 120)

    fact = knowledge.known_history_facts[crime.record_id]
    assert fact.memory_strength >= fact.permanence
    assert fact.permanence >= 0.7
    assert fact.decay_rate < 0.02


def test_backward_compatible_known_history_fact_defaults_decay_safely():
    old_fact = KnownHistoryFact(
        source_record_id="old-1",
        record_type="npc_birth",
        subject_entity_ids=(1,),
        known_at_tick=0,
        source_type="told",
        confidence=0.5,
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
    knowledge = KnowledgeComponent(known_history_facts={old_fact.source_record_id: old_fact})

    decay_known_facts(knowledge, DAY_LENGTH_TICKS)
    decayed = knowledge.known_history_facts[old_fact.source_record_id]

    assert hasattr(decayed, "memory_strength")
    assert hasattr(decayed, "permanence")
    assert decayed.memory_strength >= decayed.permanence


def test_compute_memory_profile_identifies_traumatic_and_public_profiles():
    history = HistoryLedger()
    crime = history.record_crime(
        crime_kind="assault",
        suspect_id=50,
        victim_id=51,
        description="A violent public accusation spread.",
        game_time=0,
    )

    rumor_profile = compute_memory_profile(crime, source_type="overheard", confidence=0.6)
    traumatic_profile = compute_memory_profile(crime, source_type="traumatic", confidence=1.0)
    public_profile = compute_memory_profile(crime, source_type="public_record", confidence=1.0)

    assert traumatic_profile.emotional_weight > rumor_profile.emotional_weight
    assert public_profile.permanence > rumor_profile.permanence
    assert traumatic_profile.decay_rate < rumor_profile.decay_rate
