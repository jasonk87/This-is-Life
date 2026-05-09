from simulation.history import Event, HistoryLedger
from simulation.records import CensusSnapshot, ChronicleArchive


def test_chronicle_archive_registers_books_and_transfers_knowledge():
    history = HistoryLedger()
    archive = ChronicleArchive(history)
    event = history.add_event(
        "npc_birth",
        "A child was born.",
        1,
        game_time=10,
        location=(2, 3),
    )

    book = archive.compile_chronicle(
        title="Year 1 Chronicle",
        author_id=7,
        author_name="Scribe",
        year_written=1,
        events=[event],
    )
    archive.add_book(book)

    known_events = {}
    learned = archive.transfer_book_knowledge(book, known_events)

    assert archive.get_book(book.id) is book
    assert learned == 1
    assert known_events[event.id] is event


def test_chronicle_archive_compiles_biography_and_census_report():
    archive = ChronicleArchive(HistoryLedger())
    deed = Event("entity_death", "Hero slew the beast.", 4, 20)

    biography = archive.compile_biography(
        title="Biography: Hero",
        author_id=8,
        author_name="Scholar",
        year_written=2,
        subject_name="Hero",
        subject_title="Champion",
        fame=50,
        infamy=0,
        subject_events=[deed],
    )
    snapshot = archive.record_census_snapshot(
        CensusSnapshot(
            village_name="Oak Hollow",
            year=2,
            population=5,
            total_wealth=100,
            average_wealth=20,
            richest_name="Alda",
            richest_wealth=40,
            poorest_name="Bren",
            poorest_wealth=5,
            profession_counts={"Farmer": 3, "Smith": 1, "Scribe": 1},
        )
    )
    census = archive.compile_census_report(
        title="Census Report 2",
        author_id=8,
        author_name="Scholar",
        snapshot=snapshot,
    )

    assert "Hero slew the beast." in biography.content
    assert biography.referenced_event_ids == [deed.id]
    assert "Total Population: 5" in census.content
    assert archive.census.snapshots == [snapshot]


def test_chronicle_compiles_typed_history_records_with_factual_sections():
    history = HistoryLedger()
    archive = ChronicleArchive(history)
    records = [
        archive.record_birth(
            child_id=10,
            parent_ids=(1, 2),
            child_name="Mira",
            description="RAW birth description",
            game_time=1,
        ),
        archive.record_death(
            deceased_id=11,
            killer_id=12,
            cause_of_death="injury",
            description="RAW death description",
            game_time=2,
        ),
        archive.record_marriage(
            spouse_ids=(13, 14),
            description="RAW marriage description",
            game_time=3,
        ),
        archive.record_migration(
            traveler_id=15,
            migration_kind="migrated",
            origin_label="North Farm",
            destination_label="Oak Hollow",
            description="RAW migration description",
            game_time=4,
        ),
        archive.record_crime(
            crime_kind="theft",
            suspect_id=16,
            victim_id=17,
            witness_ids=(18,),
            description="RAW crime description",
            game_time=5,
        ),
        archive.record_employment_change(
            worker_id=19,
            profession="Farmer",
            employment_action="hired",
            description="RAW employment description",
            game_time=6,
        ),
    ]

    book = archive.compile_chronicle(
        title="Typed Chronicle",
        author_id=99,
        author_name="Archivist",
        year_written=3,
        events=records,
    )

    assert "Births:\n- Mira was born to Entity 1, Entity 2." in book.content
    assert "Deaths:\n- Entity 11 died from injury; killer: Entity 12." in book.content
    assert "Marriages:\n- Entity 13 and Entity 14 married." in book.content
    assert "Migration:\n- Entity 15 migrated from North Farm to Oak Hollow." in book.content
    assert (
        "Criminal Activity:\n"
        "- Theft recorded; suspect: Entity 16; victim: Entity 17; witnesses: Entity 18."
        in book.content
    )
    assert "Employment:\n- Entity 19 was hired as Farmer." in book.content
    assert "RAW" not in book.content
    assert book.referenced_event_ids == [record.id for record in records]


def test_biography_prefers_typed_records_and_archive_retrieves_them():
    history = HistoryLedger()
    archive = ChronicleArchive(history)
    employment = archive.record_employment_change(
        worker_id=42,
        profession="Smith",
        employment_action="quit",
        description="RAW employment description",
        game_time=2,
        settlement_id="settlement_1",
    )
    generic = history.add_event(
        "public_notice",
        "Entity 42 received a public notice.",
        42,
        game_time=1,
        metadata={"settlement_id": "settlement_1"},
    )

    biography = archive.compile_biography(
        title="Biography: Toma",
        author_id=7,
        author_name="Scholar",
        year_written=4,
        subject_name="Toma",
        subject_title="Smith",
        fame=0,
        infamy=0,
        subject_events=archive.get_records_for_entity(42),
    )

    assert archive.get_record(employment.id) is employment
    assert archive.get_records_by_type(type(employment)) == [employment]
    assert archive.get_typed_records() == [employment]
    assert archive.get_records_by_settlement("settlement_1") == [employment, generic]
    assert "- Entity 42 received a public notice." in biography.content
    assert "- Entity 42 quit work as Smith." in biography.content
    assert "RAW employment description" not in biography.content
    assert biography.referenced_event_ids == [generic.id, employment.id]
