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
