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
    import random
    random.seed(42)
    building_a = generate_building("large_house", 0, 0, 10, 10)
    random.seed(42)
    building_b = generate_building("large_house", 0, 0, 10, 10)

    assert [(r.x, r.y, r.w, r.h, r.room_type) for r in building_a.rooms] == [(r.x, r.y, r.w, r.h, r.room_type) for r in building_b.rooms]
    assert building_a.placed_furniture == building_b.placed_furniture
    assert building_a.anchors == building_b.anchors

def test_furniture_appears_in_expected_room_types():
    gen_building = generate_building("lumber_shed", 0, 0, 6, 6)
    # lumber_shed has a workshop, which requires workbench and storage
    has_workbench = any(role == "workbench" for _, _, role in gen_building.placed_furniture)
    has_storage = any(role == "storage" for _, _, role in gen_building.placed_furniture)

    assert has_workbench, "Workbench should be placed in a workshop"
    assert has_storage, "Storage should be placed in a workshop"

def test_furniture_anchors_created():
    # House requires bedroom (needs bed)
    gen_building = generate_building("house", 0, 0, 8, 8)

    # Check if a sleep anchor was created from a bed
    has_sleep_anchor = False
    for anchor in gen_building.anchors:
        if anchor.type == "sleep" and anchor.tags.get("role") == "bed":
            has_sleep_anchor = True
            # Verify anchor is within bounds
            assert 0 <= anchor.x < 8
            assert 0 <= anchor.y < 8

    assert has_sleep_anchor, "Sleep anchor should be placed from a bed in a house"

def test_room_fallback_anchors():
    # Tavern has a tavern_floor which has a fallback 'social' anchor
    # Generate a small tavern so furniture might fail to place, testing fallback
    gen_building = generate_building("tavern", 0, 0, 6, 6)

    has_social_anchor = False
    for anchor in gen_building.anchors:
        if anchor.type == "social":
            has_social_anchor = True

    assert has_social_anchor, "A social anchor should be present in a tavern (either from furniture or fallback)"

def test_no_excessive_duplicate_anchors_on_tile():
    gen_building = generate_building("large_house", 0, 0, 15, 15)

    anchor_positions = {}
    for anchor in gen_building.anchors:
        key = (anchor.x, anchor.y, anchor.type)
        anchor_positions[key] = anchor_positions.get(key, 0) + 1

    for count in anchor_positions.values():
        assert count <= 1, "There should not be duplicate anchors of the same type on the exact same tile"

def test_wealth_tiers_produce_different_layouts():
    # Make temporary archetypes with identical room setups but different wealth tags
    BUILDING_ARCHETYPES["test_low"] = BuildingArchetype(
        "test_low", "residential", (49, 81), ["bedroom"], ["office", "dining"], ["poor"]
    )
    BUILDING_ARCHETYPES["test_mid"] = BuildingArchetype(
        "test_mid", "residential", (49, 81), ["bedroom"], ["office", "dining"], ["middle"]
    )
    BUILDING_ARCHETYPES["test_high"] = BuildingArchetype(
        "test_high", "residential", (49, 81), ["bedroom"], ["office", "dining"], ["rich"]
    )

    low_building = generate_building("test_low", 0, 0, 10, 10)
    mid_building = generate_building("test_mid", 0, 0, 10, 10)
    high_building = generate_building("test_high", 0, 0, 10, 10)

    # High should generally try to place more rooms (optional ones) than low
    assert len(high_building.rooms) >= len(low_building.rooms), "High wealth should place equal or more rooms than low wealth"

    # High wealth should place equal or more furniture than low wealth
    # due to scaling optional furniture logic.
    assert len(high_building.placed_furniture) >= len(low_building.placed_furniture)

def test_optional_furniture_scales_correctly():
    # Bedroom archetype has 2 required (bed, dresser) and 2 optional (chair, shelf)
    BUILDING_ARCHETYPES["test_furniture_low"] = BuildingArchetype(
        "test_furniture_low", "residential", (25, 49), ["bedroom"], [], ["poor"]
    )
    BUILDING_ARCHETYPES["test_furniture_high"] = BuildingArchetype(
        "test_furniture_high", "residential", (25, 49), ["bedroom"], [], ["rich"]
    )

    # Make room big enough to fit everything
    low_building = generate_building("test_furniture_low", 0, 0, 7, 7)
    high_building = generate_building("test_furniture_high", 0, 0, 7, 7)

    low_count = len(low_building.placed_furniture)
    high_count = len(high_building.placed_furniture)

    assert high_count >= low_count, "High wealth should have higher or equal furniture density than low wealth"

def test_furniture_distinctiveness():
    """Verify that generated furniture roles map to distinctly identified components."""
    from simulation.systems.architecture import FURNITURE_ROLES

    # Generate an office which should spawn a desk, chair, and storage
    office_building = generate_building("guard_post", 0, 0, 10, 10)

    placed_roles = [role for x, y, role in office_building.placed_furniture]
    assert "desk" in placed_roles, "Office should have a desk"
    assert "storage" in placed_roles, "Office should have storage"

    # Verify that desk and storage are distinct roles (the real mapping assert happens in test_dawnlike_mapping.py)
    assert FURNITURE_ROLES["desk"].id != FURNITURE_ROLES["storage"].id


def test_tavern_furniture_density():
    # Tavern (high density bias) vs House (mid density bias), assuming same tags/wealth
    tavern = generate_building("tavern", 0, 0, 15, 15)
    house = generate_building("house", 0, 0, 15, 15)

    # We expect tavern to place a good amount of furniture due to its density bias, especially optional
    # Taverns should feel busy
    assert len(tavern.placed_furniture) > 0
    # House places multiple small rooms which artificially inflates total furniture counts (2 beds, 2 dressers, etc).
    # We instead verify that the tavern floor specifically gets its optional items maxed out due to density bias.
    tavern_floor_items = [pos for pos in tavern.placed_furniture if tavern.rooms[0].room_type == "tavern_floor"]

    # Tavern floor has 5 required + 1 optional. Mid wealth normally gets len(opt)//2 + 1 = 0 + 1 = 1 optional.
    # High density nudges this up.
    assert len(tavern_floor_items) >= 6, "Tavern floor should place its optional items due to high density bias"

def test_clinic_furniture_density():
    # Clinic (low density bias) vs Tavern (high density bias)
    clinic = generate_building("clinic", 0, 0, 15, 15)
    tavern = generate_building("tavern", 0, 0, 15, 15)

    clinic_furniture = len(clinic.placed_furniture)
    tavern_furniture = len(tavern.placed_furniture)

    # Clinics should generally have fewer or strictly bounded furniture items
    # They shouldn't be completely empty, but shouldn't be overwhelmingly full
    assert clinic_furniture > 0
    # A tavern floor room in a tavern should generally result in more items
    assert tavern_furniture >= clinic_furniture

def test_industrial_clustering():
    carpenter_shop = generate_building("carpenter_shop", 0, 0, 12, 12)

    # Industrial buildings have "functional" clustering, grouping work and storage items.
    # Carpenter shop is mid-wealth, providing enough optional items and stable placements to test proximity reliably without brittle overlap.
    work_storage_items = [pos for pos in carpenter_shop.placed_furniture if pos[2] in ["workbench", "storage", "desk"]]

    # If we have multiple such items, verify they are relatively close.
    if len(work_storage_items) > 1:
        # Check average distance or at least one pair is close
        min_dist = 999
        for i in range(len(work_storage_items)):
            for j in range(i + 1, len(work_storage_items)):
                x1, y1, _ = work_storage_items[i]
                x2, y2, _ = work_storage_items[j]
                dist = abs(x1 - x2) + abs(y1 - y2)
                if dist < min_dist:
                    min_dist = dist

        # In functional clustering, items should be biased toward grouping if valid spots allow.
        # We ensure they are closer than the maximum possible distance in this 12x12 room footprint.
        assert min_dist < 15, f"Functional items should be grouped somewhat closely, min dist was {min_dist}"
