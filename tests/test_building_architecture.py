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
