"""Furniture and direction are presentation; schedules/physics remain authoritative."""

import copy
import random
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest

import main
from config import MAP_WIDTH, MAP_HEIGHT
from data.decorations import DECORATION_ITEM_DEFINITIONS as DECOR
from data.tiles import TILE_DEFINITIONS
from rendering import actor_motion as motion, atlas_regions, interior_art as interiors
from rendering import people_art as people, pixel_scene as pixels, console_renderer as cr
from runtime_compat import np
from tests.test_world_art import native_art, clear_composites
from tools.street_review import activity_actor


def room(key="wooden_bed", zoom=3):
    placed = NS(**DECOR[key])
    floor = NS(**TILE_DEFINITIONS["wood_floor"])
    world = NS(
        player=NS(x=4, y=5),
        zoom_levels=(zoom,),
        zoom_index=0,
        game_time=0,
        current_light_level_name="DAY",
        items_on_map={},
        player_fov_map=np.ones((90, 90), dtype=bool),
        get_tile_at=lambda x, y: placed if (x, y) == (5, 5) else floor,
        get_building_at=lambda x, y: None,
    )
    return world, placed


def test_all_new_atlases_have_alpha_and_full_silhouettes(native_art):
    assert len(interiors._sources) == 16
    assert set(people._views) == {"north", "east"}
    for images in (interiors._sources, *people._views.values()):
        for image in images:
            assert (image[:, :, 3] == 0).any()
            assert (image[:, :, 3] > 200).any()
    assert all(len(images) == 32 for images in people._views.values())


def test_connected_components_keep_gutter_crossing_objects_whole():
    alpha = np.zeros((40, 80), dtype=np.uint8)
    alpha[8:25, 5:44] = 255  # left object extends beyond its nominal 40px cell
    alpha[10:30, 53:73] = 255
    alpha[2, 2] = 255  # ignore tiny export speck
    assert atlas_regions.silhouette_bounds(alpha, 2, 1) == ((5, 8, 44, 25), (53, 10, 73, 30))


def test_missing_atlas_cells_fail_loudly():
    alpha = np.zeros((40, 80), dtype=np.uint8)
    alpha[8:25, 5:30] = 255
    with pytest.raises(ValueError, match="missing or touching"):
        atlas_regions.silhouette_bounds(alpha, 2, 1)


def test_normalizing_does_not_mutate_original_pixels():
    source = np.full((10, 20, 4), 255, dtype=np.uint8)
    before = source.copy()
    result = atlas_regions.normalize(source, 32, 48)
    assert result.shape == (48, 32, 4)
    assert not result[-2:, :, 3].any()
    assert np.array_equal(source, before)


@pytest.mark.parametrize("key", sorted(set(interiors.SPECS) & set(DECOR)))
def test_placed_furniture_is_identified_by_definition_not_shared_glyph(key):
    assert interiors.furniture_key(NS(**DECOR[key])) == key


def test_work_zone_floor_is_never_invented_furniture(native_art):
    world, _ = room()
    world.get_tile_at = lambda x, y: NS(**TILE_DEFINITIONS["wood_floor"])
    world.work_zone_tiles = {"oven": [(5, 5)]}
    with patch.object(pixels, "stamp") as stamp:
        interiors.draw_furniture(main.create_console(), world, 0, 0)
    stamp.assert_not_called()


@pytest.mark.parametrize("zoom", [1, 2, 3, 4])
def test_furniture_and_flames_do_not_paint_ui(native_art, zoom):
    world, tile = room("fireplace", zoom)
    x, y = MAP_WIDTH // zoom - 1, MAP_HEIGHT // zoom - 1
    floor = NS(**TILE_DEFINITIONS["wood_floor"])
    world.get_tile_at = lambda tx, ty: tile if (tx, ty) == (x, y) else floor
    console = main.create_console()
    before = console.ch.copy()
    interiors.draw_furniture(console, world, 0, 0)
    assert np.array_equal(console.ch[:, MAP_WIDTH:], before[:, MAP_WIDTH:])
    assert np.array_equal(console.ch[MAP_HEIGHT:], before[MAP_HEIGHT:])
    assert not np.array_equal(console.ch, before)


def test_fire_is_controlled_by_actual_lit_property(native_art):
    world, tile = room("fireplace")
    tile.properties = tile.properties.copy()
    for lit in (False, True):
        tile.properties["is_lit"] = lit
        with patch.object(pixels, "stamp") as stamp:
            interiors.draw_furniture(main.create_console(), world, 0, 0)
        tokens = [c.kwargs["token"][0] for c in stamp.call_args_list]
        assert ("hearth-flame" in tokens) == lit


def test_hidden_furniture_neither_draws_nor_can_be_picked(native_art):
    world, _ = room()
    world.player_fov_map[:] = False
    with patch.object(pixels, "stamp") as stamp:
        interiors.draw_furniture(main.create_console(), world, 0, 0)
    stamp.assert_not_called()
    assert interiors.hit_test(world, 0, 0, 16, 14) is None


def test_headboard_hit_returns_real_bed_tile(native_art):
    world, _ = room()
    assert interiors.hit_test(world, 0, 0, 16, 14) == (5, 5)
    world.player_fov_map[4, 5] = False
    assert interiors.hit_test(world, 0, 0, 16, 14) is None
    assert interiors.hit_test(world, 0, 0, 16, 1) is None


def test_right_click_headboard_inspects_the_original_occupied_tile(native_art):
    from tcod_compat import tcod

    world, _ = room()
    world.game_state = "PLAYING"
    world.chat_ui_active = False
    world.interaction_context = {"active": False}
    world.player.state = NS(current_path=[])
    world.inspect_tile = Mock(return_value="A bed")
    world.add_message_to_chat_log = Mock()
    event = tcod.event.MouseButtonDown(position=(16, 14), button=tcod.event.MouseButton.RIGHT)
    with patch.object(main.tcod.event, "get", return_value=[event]), patch.object(
        main, "_get_camera_origin", return_value=(0, 0)
    ), patch.object(main, "apply_ui_requests"), patch.object(
        people, "hit_test", return_value=None
    ), patch.object(
        main, "open_interaction_menu"
    ) as menu:
        main.handle_events(world, NS(convert_event=lambda e: e))
    world.inspect_tile.assert_called_once_with(5, 5)
    menu.assert_called_once_with(world, 5, 5)


def test_floor_material_is_sampled_without_changing_tile(native_art):
    world, tile = room()
    stone = NS(**TILE_DEFINITIONS["stone_floor"])
    world.get_tile_at = lambda x, y: tile if (x, y) == (5, 5) else stone
    before = copy.deepcopy(tile.__dict__)
    assert interiors.floor_beneath(world, 5, 5, None) == "stone_floor"
    assert interiors.draw_floor(main.create_console(), world, 0, 0, 5, 5, tile, None)
    assert tile.__dict__ == before


def test_surface_goods_require_actual_positive_loose_map_stock(native_art):
    world, _ = room("wooden_table")
    world.building_inventory = {"bread": 100}
    with patch.object(pixels, "stamp", return_value=True) as stamp:
        assert not interiors.draw_surface_item(main.create_console(), world, 0, 0, 5, 5, "bread")
        world.items_on_map[(5, 5)] = {"bread": 0}
        assert not interiors.draw_surface_item(main.create_console(), world, 0, 0, 5, 5, "bread")
        stamp.assert_not_called()
        world.items_on_map[(5, 5)]["bread"] = 2
        assert interiors.draw_surface_item(main.create_console(), world, 0, 0, 5, 5, "bread")
        stamp.assert_called_once()


def test_closed_storage_does_not_display_surface_items(native_art):
    world, _ = room("chest_wooden")
    world.items_on_map[(5, 5)] = {"bread": 2}
    assert not interiors.draw_surface_item(main.create_console(), world, 0, 0, 5, 5, "bread")


def test_disabled_interior_art_keeps_legacy_render_path(native_art):
    world, tile = room()
    world.interior_art_enabled = False
    assert not interiors.draw_floor(main.create_console(), world, 0, 0, 5, 5, tile, None)
    assert interiors.hit_test(world, 0, 0, 16, 14) is None


@pytest.mark.parametrize(
    "dx,dy,facing", [(1, 0, "east"), (-1, 0, "west"), (0, -1, "north"), (0, 1, "south")]
)
def test_actual_npc_step_sets_direction_and_stops_after_settling(dx, dy, facing):
    world, actor = activity_actor("idle")
    world.player = None
    assert motion.observe(world, actor) == ("south", False)
    actor.x += dx
    actor.y += dy
    world.game_time = 1
    assert motion.observe(world, actor) == (facing, True)
    world.game_time = 6
    assert motion.observe(world, actor) == (facing, False)


def test_a_queued_or_blocked_path_does_not_walk_in_place():
    world, actor = activity_actor("idle")
    actor.schedule.current_path = [(1, 0)]
    for tick in (0, 1, 5, 20):
        world.game_time = tick
        assert not motion.observe(world, actor)[1]
        assert people.activity_for(world, actor).kind == "idle"


def test_teleport_is_not_a_step_and_rewind_resets_history():
    world, actor = activity_actor("idle")
    motion.observe(world, actor)
    actor.x = 40
    assert not motion.observe(world, actor)[1]
    world.game_time = 20
    actor.x = 41
    assert motion.observe(world, actor) == ("east", True)
    world.game_time = 0
    assert motion.observe(world, actor) == ("south", False)


def test_player_input_can_turn_without_claiming_a_step():
    world, actor = activity_actor("idle")
    actor.state = NS(last_dx=-1, last_dy=0)
    assert motion.observe(world, actor) == ("west", False)


def test_west_is_matching_profile_mirrored(native_art):
    for index in (0, 4, 5, 16, 20, 21):
        east = people.character_pixels(index, 2, "idle", 0, "east", False)
        west = people.character_pixels(index, 2, "idle", 0, "west", False)
        north = people.character_pixels(index, 2, "idle", 0, "north", False)
        assert np.array_equal(east[:, ::-1], west)
        assert not np.array_equal(east, north)


@pytest.mark.parametrize("direction", ["north", "east", "south", "west"])
def test_walk_has_distinct_phases_without_mutating_source(native_art, direction):
    source = people._views.get(direction, people._people)[5]
    before = source.copy()
    frames = [people.character_pixels(5, 3, "walk", phase, direction, False) for phase in range(4)]
    assert not np.array_equal(frames[0], frames[1])
    assert not np.array_equal(frames[1], frames[3])
    assert np.array_equal(source, before)


def test_animation_freezes_with_simulation_and_never_writes_actor_state(native_art):
    world, actor = activity_actor("hammer")
    before = copy.deepcopy(actor.__dict__)
    rng = random.getstate()
    first, _, first_token = people.body_frame(world, actor, 3)
    for _ in range(10):
        frame, _, token = people.body_frame(world, actor, 3)
        assert token == first_token
        assert np.array_equal(frame, first)
    assert actor.__dict__ == before
    assert random.getstate() == rng
    assert first_token[5] == "east"  # real interaction target, not profession


def test_limb_translation_never_wraps_pixels():
    source = np.zeros((4, 4, 4), dtype=np.uint8)
    source[:, 0] = 255
    assert not people.shifted(source, dx=-1).any()
    assert (people.shifted(source, dx=1)[:, 1] == 255).all()


@pytest.mark.parametrize("dy,carried_first", [(-1, True), (1, False)])
def test_held_item_is_occluded_by_back_not_painted_on_it(native_art, dy, carried_first):
    world, actor = activity_actor("carry")
    world.dynamic_characters_enabled = False  # Old external-item painter contract.
    actor.state = NS(last_dx=0, last_dy=dy)
    with patch.object(pixels, "stamp") as stamp:
        people.draw_person(main.create_console(), world, actor, 0, 0, 5, 5)
    tokens = [call.kwargs["token"][0] for call in stamp.call_args_list]
    assert (tokens.index("carry32-small") < tokens.index("person32")) == carried_first


def test_speech_bubble_is_above_the_face(native_art):
    world, actor = activity_actor("talk")
    with patch.object(pixels, "stamp") as stamp:
        people.draw_person(main.create_console(), world, actor, 0, 0, 5, 5)
    body = next(call for call in stamp.call_args_list if call.kwargs["token"][0] == "person32")
    bubble = next(call for call in stamp.call_args_list if call.kwargs["token"][0] == "activity32")
    assert bubble.args[3] < body.args[3]
