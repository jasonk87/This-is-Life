from simulation.history import Book, HistoryLedger
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
