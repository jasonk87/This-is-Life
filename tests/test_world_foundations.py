from simulation.history import (
    BirthRecord,
    Book,
    DeathRecord,
    EmploymentRecord,
    HistoryLedger,
    MarriageRecord,
    MigrationRecord,
)
from simulation.world_model import Building, Village, WorldAtlas


def test_history_ledger_caps_events_and_keeps_lookup():
    ledger = HistoryLedger(event_limit=2)
    first = ledger.add_event("alpha", "First", 1, game_time=1)
    second = ledger.add_event("beta", "Second", 2, game_time=2)
    third = ledger.add_event("gamma", "Third", 3, game_time=3)

    assert [event.id for event in ledger.events] == [second.id, third.id]
    assert ledger.get_event(first.id) is None
    assert ledger.get_event(third.id) is third


def test_world_atlas_registers_regions_villages_and_buildings():
    atlas = WorldAtlas()
    region = atlas.get_or_create_region_for_chunk(0, 0, "plains")
    village = Village(primary_biome="plains", chunk_coords=(0, 0), region_id=region.id)
    building = Building(1, 2, 3, 4, building_type="house", global_chunk_x_start=10, global_chunk_y_start=20)
    village.add_building(building)

    atlas.add_village(village, chunk_coords=(0, 0), region=region)

    assert atlas.villages == [village]
    assert atlas.buildings_by_id[building.id] is building
    assert building.settlement_id == village.id
    assert building.region_id == region.id
    assert village.id in region.village_ids


def test_history_books_are_owned_by_ledger():
    ledger = HistoryLedger()
    book = Book("Chronicle", 7, "Scribe", 1, "Content")

    ledger.add_book(book)

    assert ledger.books == [book]
    assert ledger.get_book(book.id) is book


def test_history_ledger_creates_typed_records_and_indexes_participants():
    ledger = HistoryLedger(event_limit=10)

    birth = ledger.record_birth(
        child_id=10,
        parent_ids=(1, 2),
        child_name="Mira",
        description="Mira was born.",
        game_time=5,
        location=(3, 4),
        settlement_id="village_1",
        region_id="region_1",
    )
    marriage = ledger.record_marriage(
        spouse_ids=(1, 2),
        description="Two villagers married.",
        game_time=6,
        location=(3, 4),
    )
    death = ledger.record_death(
        deceased_id=2,
        killer_id=99,
        description="A villager died.",
        game_time=7,
        location=(5, 6),
        cause_of_death="wolf attack",
    )
    job = ledger.record_employment_change(
        worker_id=1,
        profession="Farmer",
        employment_action="hired",
        description="A villager became a farmer.",
        game_time=8,
        location=(7, 8),
        building_id="farm_1",
    )
    migration = ledger.record_migration(
        traveler_id=3,
        migration_kind="emigrated",
        description="A villager left.",
        game_time=9,
        location=(9, 10),
        origin_label="Oak Hollow",
    )

    assert isinstance(birth, BirthRecord)
    assert isinstance(marriage, MarriageRecord)
    assert isinstance(death, DeathRecord)
    assert isinstance(job, EmploymentRecord)
    assert isinstance(migration, MigrationRecord)

    entity_one_events = ledger.get_events_for_entity(1)
    assert [event.id for event in entity_one_events] == [birth.id, marriage.id, job.id]
    assert ledger.get_events_by_type("npc_hired") == [job]
    assert ledger.get_events_at_location((3, 4)) == [birth, marriage]
    assert ledger.get_event(death.id) is death
    assert death.metadata["cause_of_death"] == "wolf attack"
