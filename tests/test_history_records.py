from simulation.history import (
    BirthRecord,
    Book,
    CrimeRecord,
    DeathRecord,
    EmploymentRecord,
    Event,
    HistoryLedger,
    MarriageRecord,
    MigrationRecord,
)


def test_typed_records_can_be_added_and_retrieved_by_entity():
    ledger = HistoryLedger()
    death = ledger.record_death(
        deceased_id=10,
        killer_id=20,
        description="A villager died.",
        game_time=42,
        location=(5, 6),
        cause_of_death="wolf_attack",
        settlement_id="settlement_1",
        region_id="region_1",
    )

    assert isinstance(death, DeathRecord)
    assert death.record_id == death.id
    assert death.tick == 42
    assert death in ledger.get_records_by_entity(10)
    assert death in ledger.get_records_by_entity(20)


def test_typed_records_can_be_retrieved_by_type_name_or_class():
    ledger = HistoryLedger()
    birth = ledger.record_birth(
        child_id=3,
        parent_ids=(1, 2),
        child_name="Mira",
        description="Mira was born.",
        game_time=5,
    )
    crime = ledger.record_crime(
        crime_kind="theft",
        suspect_id=9,
        victim_id=10,
        witness_ids=(11,),
        description="A theft was witnessed.",
        game_time=6,
    )

    assert ledger.get_records_by_type(BirthRecord) == [birth]
    assert ledger.get_records_by_type(CrimeRecord) == [crime]
    assert ledger.get_records_by_type("npc_birth") == [birth]
    assert ledger.get_records_by_type("crime_recorded") == [crime]


def test_settlement_and_region_filtering_work_for_typed_records_and_metadata_events():
    ledger = HistoryLedger()
    job = ledger.record_employment_change(
        worker_id=12,
        profession="Baker",
        employment_action="hired",
        description="A baker was hired.",
        game_time=7,
        building_id="bakery_1",
        settlement_id="settlement_1",
        region_id="region_1",
    )
    migration = ledger.record_migration(
        traveler_id=13,
        migration_kind="migrated",
        description="A villager moved.",
        game_time=8,
        origin_label="Old Town",
        destination_label="New Town",
        settlement_id="settlement_2",
        region_id="region_1",
    )
    generic = ledger.add_event(
        "festival",
        "A festival happened.",
        99,
        game_time=9,
        metadata={"settlement_id": "settlement_1", "region_id": "region_2"},
    )

    assert ledger.get_records_by_settlement("settlement_1") == [job, generic]
    assert ledger.get_records_by_settlement("settlement_2") == [migration]
    assert ledger.get_records_by_region("region_1") == [job, migration]
    assert ledger.get_records_by_region("region_2") == [generic]


def test_all_typed_record_classes_preserve_participants_and_scope_fields():
    ledger = HistoryLedger()
    records = [
        ledger.record_birth(child_id=1, parent_ids=(2, 3), child_name="Child", description="Birth", game_time=1, settlement_id="s", region_id="r"),
        ledger.record_death(deceased_id=4, killer_id=5, description="Death", game_time=2, cause_of_death="age", settlement_id="s", region_id="r"),
        ledger.record_marriage(spouse_ids=(6, 7), description="Marriage", game_time=3, settlement_id="s", region_id="r"),
        ledger.record_crime(crime_kind="assault", suspect_id=8, victim_id=9, witness_ids=(10,), description="Crime", game_time=4, settlement_id="s", region_id="r"),
        ledger.record_migration(traveler_id=11, migration_kind="emigrated", description="Migration", game_time=5, settlement_id="s", region_id="r"),
        ledger.record_employment_change(worker_id=12, profession="Miller", employment_action="hired", description="Job", game_time=6, settlement_id="s", region_id="r"),
    ]

    assert [type(record) for record in records] == [
        BirthRecord,
        DeathRecord,
        MarriageRecord,
        CrimeRecord,
        MigrationRecord,
        EmploymentRecord,
    ]
    assert all(record.settlement_id == "s" for record in records)
    assert all(record.region_id == "r" for record in records)
    assert records[0].participant_ids == (1, 2, 3)
    assert records[3].participant_ids == (8, 9, 10)


def test_existing_generic_events_and_books_remain_compatible():
    ledger = HistoryLedger()
    event = Event("rumor", "A rumor spread.", 77, 12, metadata={"participant_ids": [78]})
    book = Book("Chronicle", 1, "Scribe", 1, "A year in review.")

    ledger.add_record(event)
    ledger.add_book(book)

    assert ledger.events == [event]
    assert ledger.get_event(event.id) is event
    assert ledger.get_records_by_entity(77) == [event]
    assert ledger.get_records_by_entity(78) == [event]
    assert ledger.get_records_by_type("rumor") == [event]
    assert ledger.books == [book]
    assert ledger.get_book(book.id) is book
