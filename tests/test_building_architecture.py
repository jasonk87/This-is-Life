from simulation.systems.architecture import (
    generate_building,
    BuildingArchetype,
    ROOM_ARCHETYPES,
    BUILDING_ARCHETYPES,
    FURNITURE_ROLES
)

def test_building_generates_valid_structure():
    gen_building = generate_building("house", 0, 0, 7, 7)

    assert gen_building.footprint == (0, 0, 7, 7)

    # rooms exist
    assert len(gen_building.rooms) > 0

    # no overlapping furniture
    placed_positions = set()
    for x, y, role in gen_building.placed_furniture:
        assert (x, y) not in placed_positions, "Found overlapping furniture!"
        placed_positions.add((x, y))

def test_required_furniture_always_placed():
    gen_building = generate_building("house", 10, 10, 8, 8)

    # "house" archetype requires a bedroom and a dining room
    # Check if a bed was placed. A bed is required in the bedroom room archetype.
    has_bed = any(role == "bed" for _, _, role in gen_building.placed_furniture)
    has_table = any(role == "table" for _, _, role in gen_building.placed_furniture)

    assert has_bed, "Bed should be placed in a house"
    assert has_table, "Table should be placed in a house"

def test_different_archetypes_produce_different_layouts():
    house = generate_building("house", 0, 0, 8, 8)
    tavern = generate_building("tavern", 0, 0, 10, 10)

    # Tavern should have a tavern_floor, house should have a bedroom
    assert any(r.room_type == "bedroom" for r in house.rooms)
    assert not any(r.room_type == "tavern_floor" for r in house.rooms)

    assert any(r.room_type == "tavern_floor" for r in tavern.rooms)
    assert not any(r.room_type == "bedroom" for r in tavern.rooms) # House vs tavern distinction

def test_furniture_respects_placement_rules():
    gen_building = generate_building("house", 0, 0, 7, 7)

    for x, y, role_id in gen_building.placed_furniture:
        role = FURNITURE_ROLES.get(role_id)
        if not role:
            continue

        # Verify it falls inside the footprint bounds
        assert 0 <= x < 7
        assert 0 <= y < 7

        # Verify 'wall' placement falls near boundary
        if role.placement_type == "wall":
            # In our simple generation logic, rooms are subdivided.
            # We can check if it touches the edge of ANY room.
            is_near_room_edge = False
            for r in gen_building.rooms:
                if x == r.x + 1 or x == r.x + r.w - 2 or y == r.y + 1 or y == r.y + r.h - 2:
                    is_near_room_edge = True

            assert is_near_room_edge, f"Wall furniture ({role_id}) should be near a room wall"

def test_extensibility_test():
    # Adding a new archetype
    BUILDING_ARCHETYPES["custom_hut"] = BuildingArchetype(
        "custom_hut", "residential", (10, 10), ["bedroom"], [], []
    )

    gen_building = generate_building("custom_hut", 0, 0, 4, 4)
    assert gen_building.footprint == (0, 0, 4, 4)
    assert len(gen_building.rooms) > 0
    assert gen_building.rooms[0].room_type == "bedroom"

def test_new_archetypes_generate_valid_layouts():
    # Test a few newly added archetypes
    guard_post = generate_building("guard_post", 0, 0, 6, 6)
    assert any(r.room_type == "office" for r in guard_post.rooms)

    lumber_shed = generate_building("lumber_shed", 0, 0, 7, 7)
    assert any(r.room_type == "workshop" for r in lumber_shed.rooms)

    barracks = generate_building("barracks", 0, 0, 8, 8)
    assert any(r.room_type == "shared_sleeping" for r in barracks.rooms)
    assert any(r.room_type == "storage" for r in barracks.rooms)

def test_determinism():
    # Generation must remain deterministic for same inputs
    building_a = generate_building("large_house", 0, 0, 10, 10)
    building_b = generate_building("large_house", 0, 0, 10, 10)

    assert [(r.x, r.y, r.w, r.h, r.room_type) for r in building_a.rooms] == [(r.x, r.y, r.w, r.h, r.room_type) for r in building_b.rooms]
    assert building_a.placed_furniture == building_b.placed_furniture

def test_furniture_appears_in_expected_room_types():
    gen_building = generate_building("lumber_shed", 0, 0, 6, 6)
    # lumber_shed has a workshop, which requires workbench and storage
    has_workbench = any(role == "workbench" for _, _, role in gen_building.placed_furniture)
    has_storage = any(role == "storage" for _, _, role in gen_building.placed_furniture)

    assert has_workbench, "Workbench should be placed in a workshop"
    assert has_storage, "Storage should be placed in a workshop"
