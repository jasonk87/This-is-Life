from types import SimpleNamespace

from entities.social import KnowledgeComponent
from simulation.history import (
    BirthRecord,
    Book,
    CrimeRecord,
    DeathRecord,
    Event,
    HistoryLedger,
)
from simulation.knowledge import KnowledgeSystem
from simulation.records import ChronicleArchive


def _holder():
    return SimpleNamespace(
        knowledge=SimpleNamespace(
            known_events={},
            known_books=set(),
        )
    )


def test_knowledge_system_shares_remote_and_local_events():
    history = HistoryLedger()
    knowledge = KnowledgeSystem(ChronicleArchive(history))
    source = _holder()
    recipient = _holder()

    remote_event = Event("remote", "Remote news", 1, 10, location=(80, 80))
    local_event = Event("local", "Local news", 2, 10, location=(5, 5))
    knowledge.learn_event(source, remote_event)
    knowledge.learn_event(source, local_event)

    shared = knowledge.share_remote_events(
        source,
        recipient,
        current_coords=(4, 4),
        chunk_size=40,
    )

    assert shared == 1
    assert remote_event.id in recipient.knowledge.known_events
    assert local_event.id not in recipient.knowledge.known_events


def test_knowledge_system_learns_from_books_and_local_event_refresh():
    history = HistoryLedger()
    archive = ChronicleArchive(history)
    knowledge = KnowledgeSystem(archive)
    holder = _holder()

    nearby = history.add_event("nearby", "Nearby event", 1, game_time=4, location=(12, 12))
    distant = history.add_event("far", "Far event", 2, game_time=4, location=(200, 200))
    book = Book(
        "Chronicle",
        7,
        "Scribe",
        1,
        "Content",
        "chronicle",
        referenced_event_ids=[nearby.id],
    )
    archive.add_book(book)

    learned = knowledge.learn_from_book(holder, book, book_item_key=f"book_{book.id}")
    knowledge.reset_known_events(holder)
    relearned = knowledge.learn_local_events(
        holder,
        history.events,
        center=(10, 10),
        radius_sq=30 ** 2,
    )

    assert learned == 1
    assert f"book_{book.id}" in holder.knowledge.known_books
    assert relearned == 1
    assert nearby.id in holder.knowledge.known_events
    assert distant.id not in holder.knowledge.known_events


def _structured_holder():
    return SimpleNamespace(knowledge=KnowledgeComponent())


def test_knowledge_component_learns_typed_history_facts_with_source_and_confidence():
    history = HistoryLedger()
    knowledge = KnowledgeSystem(ChronicleArchive(history))
    holder = _structured_holder()

    birth = history.record_birth(
        child_id=10,
        parent_ids=(1, 2),
        child_name="Mira",
        description="Mira was born.",
        game_time=4,
        settlement_id="settlement_1",
    )
    death = history.record_death(
        deceased_id=20,
        killer_id=21,
        cause_of_death="injury",
        description="Entity 20 died.",
        game_time=5,
    )
    crime = history.record_crime(
        crime_kind="theft",
        suspect_id=30,
        victim_id=31,
        witness_ids=(32,),
        description="Theft was recorded.",
        game_time=6,
        region_id="region_1",
    )

    assert knowledge.learn_history_record(
        holder,
        birth,
        source_type="witnessed",
        confidence=0.9,
        tick=100,
    )
    knowledge.learn_history_record(
        holder, death, source_type="told", confidence=0.6, tick=101
    )
    knowledge.learn_history_record(
        holder, crime, source_type="official_record", confidence=1.0, tick=102
    )

    birth_fact = holder.knowledge.known_history_facts[birth.id]
    assert holder.knowledge.knows_record(birth.id)
    assert birth_fact.source_record_id == birth.id
    assert birth_fact.record_type == "npc_birth"
    assert birth_fact.record_class_name == "BirthRecord"
    assert birth_fact.subject_entity_ids == (10, 1, 2)
    assert birth_fact.source_type == "witnessed"
    assert birth_fact.confidence == 0.9
    assert birth_fact.known_at_tick == 100
    assert birth_fact.settlement_id == "settlement_1"
    assert holder.knowledge.get_known_records_by_type(BirthRecord) == [birth_fact]
    assert holder.knowledge.get_known_records_by_type("npc_birth") == [birth_fact]
    assert (
        holder.knowledge.get_known_records_by_type(DeathRecord)[0].source_type
        == "told"
    )
    assert (
        holder.knowledge.get_known_records_by_type(CrimeRecord)[0].region_id
        == "region_1"
    )
    assert (
        holder.knowledge.get_known_records_about_entity(31)[0].source_record_id
        == crime.id
    )


def test_chronicle_archive_transfer_teaches_typed_record_facts_from_book():
    history = HistoryLedger()
    archive = ChronicleArchive(history)
    holder = _structured_holder()
    birth = history.record_birth(
        child_id=44,
        parent_ids=(),
        child_name="Lio",
        description="Lio was born.",
        game_time=8,
    )
    book = Book(
        "Birth Register",
        7,
        "Clerk",
        1,
        "Content",
        "chronicle",
        referenced_event_ids=[birth.id],
    )

    learned = archive.transfer_book_knowledge(
        book,
        holder.knowledge,
        source_type="official_record",
        confidence=0.95,
        tick=120,
    )

    assert learned == 1
    assert holder.knowledge.known_events[birth.id] is birth
    fact = holder.knowledge.get_known_records_by_type(BirthRecord)[0]
    assert fact.source_record_id == birth.id
    assert fact.source_type == "official_record"
    assert fact.confidence == 0.95
    assert fact.known_at_tick == 120


def test_book_reading_teaches_typed_facts_and_generic_event_knowledge_still_works():
    history = HistoryLedger()
    archive = ChronicleArchive(history)
    knowledge = KnowledgeSystem(archive)
    holder = _structured_holder()
    birth = history.record_birth(
        child_id=50,
        parent_ids=(51,),
        child_name="Ari",
        description="Ari was born.",
        game_time=10,
    )
    generic = history.add_event(
        "festival",
        "A harvest festival was held.",
        60,
        game_time=11,
    )
    book = Book(
        "Town Chronicle",
        8,
        "Scribe",
        1,
        "Content",
        "chronicle",
        referenced_event_ids=[birth.id, generic.id],
    )
    archive.add_book(book)

    learned = knowledge.learn_from_book(
        holder, book, book_item_key=f"book_{book.id}", tick=130
    )

    assert learned == 2
    assert f"book_{book.id}" in holder.knowledge.known_books
    assert holder.knowledge.known_events[birth.id] is birth
    assert holder.knowledge.known_events[generic.id] is generic
    assert (
        holder.knowledge.get_known_records_by_type(BirthRecord)[0].source_type
        == "read"
    )
    assert (
        holder.knowledge.get_known_records_by_type("festival")[0].source_record_id
        == generic.id
    )
    assert (
        holder.knowledge.get_known_records_about_entity(60)[0].source_record_id
        == generic.id
    )
