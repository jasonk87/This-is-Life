"""Architectural readability must not manufacture world state or change targeting."""

import copy
import random
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import pytest

import main
from config import MAP_WIDTH, MAP_HEIGHT
from data.tiles import TILE_DEFINITIONS
from data.decorations import DECORATION_ITEM_DEFINITIONS
from rendering import (
    architecture_art as art,
    building_frontage as frontage,
    street_ground as ground,
)
from rendering import village_art as village, pixel_scene as pixels, console_renderer as cr
from rendering import people_art, interior_art
from runtime_compat import np
from simulation.world_model import Building
from tests.test_world_art import native_art, clear_composites


def fixture(kind="bakery", side="south", zoom=3):
    building = Building(10, 8, 7, 6, building_type=kind)
    entrance = {"north": (13, 8), "south": (13, 13), "west": (10, 10), "east": (16, 10)}[side]
    building.interaction_points["entrance"] = entrance
    wall = NS(**TILE_DEFINITIONS["wood_wall"])
    grass = NS(**TILE_DEFINITIONS["plains"])
    door = NS(**DECORATION_ITEM_DEFINITIONS["wooden_door_open"])

    def tile(x, y):
        if (x, y) == entrance:
            return door
        return wall if building.contains_global_coords(x, y) else grass

    world = NS(
        player=NS(id=77, x=13, y=14, state=NS(last_dx=0, last_dy=-1, current_path=[])),
        buildings_by_id={building.id: building},
        zoom_levels=(zoom,),
        zoom_index=0,
        game_time=0,
        get_tile_at=tile,
        get_building_at=lambda x, y: building if building.contains_global_coords(x, y) else None,
        player_fov_map=np.ones((90, 100), dtype=bool),
        current_light_level_name="DAY",
    )
    return world, building


@pytest.mark.parametrize("kind", sorted(art.FORMS))
@pytest.mark.parametrize("entrance", [(3, 0), (3, 5), (0, 2), (6, 2)])
def test_archetypes_keep_actual_entrance_clear_and_fit_footprint(kind, entrance):
    source = art.roof_surface(kind, 7, 6, entrance)
    x, y = entrance
    assert source.shape == (192, 224, 4)
    assert not source[y * 32 : (y + 1) * 32, x * 32 : (x + 1) * 32, 3].any()
    assert source[:, :, 3].any()
    assert (source[:, :, 3] == 0).any()


def test_roof_profiles_differ_even_without_palette_information():
    kinds = ("house", "bakery", "blacksmith_shop", "sheriff_office")
    masks = [art.roof_surface(kind, 7, 6, (3, 5))[:, :, 3].tobytes() for kind in kinds]
    assert len(set(masks)) == 4
    assert len(set(art.FORMS.values())) >= 7


def test_house_variant_not_current_owner_cash_controls_architecture():
    assert art.roof_form("house", "house_poor") == "longhouse"
    assert art.roof_form("house", "house_rich") == "cross"
    assert art.roof_form("house", None) == "hip"


@pytest.mark.parametrize("side", ["north", "south", "east", "west"])
def test_trade_sign_is_mounted_on_same_wall_beside_actual_door(native_art, side):
    world, building = fixture(side=side)
    mount = frontage.sign_mount(building)
    entrance = building.interaction_points["entrance"]
    assert mount != entrance
    assert building.contains_global_coords(*mount)
    assert abs(mount[0] - entrance[0]) + abs(mount[1] - entrance[1]) == 1
    assert (mount[1] == entrance[1]) if side in {"north", "south"} else (mount[0] == entrance[0])
    geometry = frontage.sign_geometry(world, building, 0, 0)
    assert geometry is not None
    assert frontage.hit_test(world, 0, 0, mount[0] * 3 + 1, mount[1] * 3 + 1) == entrance


@pytest.mark.parametrize("hidden", ["door", "sign"])
def test_hidden_sign_or_entrance_cannot_reveal_a_target(native_art, hidden):
    world, building = fixture()
    mount = frontage.sign_mount(building)
    x, y = mount if hidden == "sign" else building.interaction_points["entrance"]
    world.player_fov_map[y, x] = False
    assert frontage.sign_geometry(world, building, 0, 0) is None
    assert frontage.hit_test(world, 0, 0, mount[0] * 3 + 1, mount[1] * 3 + 1) is None


def test_unbuilt_or_demolished_wall_has_no_floating_sign(native_art):
    world, building = fixture()
    world.get_tile_at = lambda x, y: NS(**TILE_DEFINITIONS["plains"])
    assert frontage.sign_geometry(world, building, 0, 0) is None


def test_no_entrance_metadata_means_no_invented_sign(native_art):
    world, building = fixture()
    building.interaction_points.clear()
    assert frontage.sign_mount(building) is None
    with patch.object(pixels, "stamp") as stamp:
        frontage.draw(main.create_console(), world, building, 0, 0)
    stamp.assert_not_called()


def test_removed_door_has_no_canopy_or_sign(native_art):
    world, building = fixture()
    world.get_tile_at = lambda x, y: NS(**TILE_DEFINITIONS["wood_wall"])
    with patch.object(pixels, "stamp") as stamp:
        frontage.draw(main.create_console(), world, building, 0, 0)
    stamp.assert_not_called()
    assert frontage.sign_geometry(world, building, 0, 0) is None


def test_exterior_signs_and_canopies_do_not_show_on_interior_wall(native_art):
    world, building = fixture()
    world.player.x, world.player.y = 13, 10
    with patch.object(pixels, "stamp") as stamp:
        frontage.draw(main.create_console(), world, building, 0, 0)
    stamp.assert_not_called()
    assert frontage.sign_geometry(world, building, 0, 0) is None


def test_interior_plaster_is_quieter_than_exterior_bracing():
    inside = village.wall_surface("house", "horizontal", False, None, True)
    outside = village.wall_surface("house", "horizontal", False, None, False)
    assert not np.array_equal(inside, outside)
    assert len(np.unique(inside[6:24, 4:28, :3].reshape(-1, 3), axis=0)) == 1


def test_an_unknown_owner_never_becomes_player_property(native_art):
    world, building = fixture("house")
    world.player.id = None
    assert not frontage.is_players_property(world, building)
    assert frontage.sign_geometry(world, building, 0, 0) is None
    world.player.id = 77
    building.owner_id = 88
    assert not frontage.is_players_property(world, building)
    building.owner_id = 77
    assert frontage.is_players_property(world, building)
    assert frontage.sign_geometry(world, building, 0, 0) is not None


def test_hovering_your_home_sign_reports_real_property(native_art):
    world, building = fixture("house")
    building.owner_id = world.player.id
    mx, my = frontage.sign_mount(building)
    world.mouse_x, world.mouse_y = mx * 3 + 1, my * 3 + 1
    with patch.object(people_art, "hit_test", return_value=None), patch.object(
        interior_art, "hit_test", return_value=None
    ):
        inspection = cr._get_hover_inspect(world, 0, 0)
    assert inspection["coords"] == building.interaction_points["entrance"]
    assert inspection["property"] == "Your property"


def test_sign_right_click_inspects_door_but_left_click_still_targets_ground(native_art):
    from tcod_compat import tcod

    world, building = fixture()
    world.game_state = "PLAYING"
    world.chat_ui_active = False
    world.interaction_context = {"active": False}
    world.inspect_tile = Mock(return_value="Bakery entrance")
    world.add_message_to_chat_log = Mock()
    world.calculate_path = Mock(return_value=[])
    mount = frontage.sign_mount(building)
    context = NS(convert_event=lambda e: e)
    for button in (tcod.event.MouseButton.RIGHT, tcod.event.MouseButton.LEFT):
        event = tcod.event.MouseButtonDown(
            position=(mount[0] * 3 + 1, mount[1] * 3 + 1), button=button
        )
        with patch.object(main.tcod.event, "get", return_value=[event]), patch.object(
            main, "_get_camera_origin", return_value=(0, 0)
        ), patch.object(main, "apply_ui_requests"), patch.object(
            main, "open_interaction_menu"
        ), patch.object(
            people_art, "hit_test", return_value=None
        ), patch.object(
            interior_art, "hit_test", return_value=None
        ):
            main.handle_events(world, context)
    world.inspect_tile.assert_called_once_with(*building.interaction_points["entrance"])
    world.calculate_path.assert_called_once_with(world.player.x, world.player.y, *mount)


@pytest.mark.parametrize("zoom", [1, 2, 3, 4])
def test_architecture_never_overwrites_sidebar_or_log(native_art, zoom):
    world, building = fixture(zoom=zoom)
    camera_x = building.global_origin_x - 2
    camera_y = building.global_origin_y - 2
    console = main.create_console()
    before = console.ch.copy()
    village.draw_buildings(console, world, camera_x, camera_y)
    assert np.array_equal(console.ch[:, MAP_WIDTH:], before[:, MAP_WIDTH:])
    assert np.array_equal(console.ch[MAP_HEIGHT:], before[MAP_HEIGHT:])


@pytest.mark.parametrize("bit", [1, 2, 4, 8])
def test_road_shoulders_leave_most_of_ground_untouched(bit):
    image = ground.edge_surface(bit, 0, 0, 0, 0)
    assert 50 < (image[:, :, 3] > 0).sum() < 250


def test_unseen_neighbor_cannot_hint_at_a_road(native_art):
    world, _ = fixture()
    road = NS(**TILE_DEFINITIONS["road"])
    grass = NS(**TILE_DEFINITIONS["plains"])
    world.get_tile_at = lambda x, y: road if (x, y) == (4, 5) else grass
    world.player_fov_map[5, 4] = False
    with patch.object(pixels, "stamp") as stamp:
        assert not ground.draw(main.create_console(), world, 0, 0, 5, 5, "plains")
    stamp.assert_not_called()


def test_threshold_comes_from_real_door_not_a_bare_work_zone(native_art):
    world, building = fixture()
    with patch.object(pixels, "stamp", return_value=True) as stamp:
        assert ground.draw(main.create_console(), world, 0, 0, 13, 14, "plains")
        assert stamp.call_args.kwargs["token"][3] == 1  # north-facing door mask
    world.get_tile_at = lambda x, y: NS(**TILE_DEFINITIONS["plains"])
    building.work_zone_tiles = {"oven": [(13, 13)]}
    with patch.object(pixels, "stamp") as stamp:
        assert not ground.draw(main.create_console(), world, 0, 0, 13, 14, "plains")
    stamp.assert_not_called()


def test_shoreline_and_road_wear_are_distinct():
    assert not np.array_equal(
        ground.edge_surface(1, 0, 0, 0, 0), ground.edge_surface(0, 0, 0, 1, 0)
    )


def test_rendering_leaves_simulation_and_rng_unchanged(native_art):
    world, building = fixture()
    before = copy.deepcopy(building.__dict__)
    fov = world.player_fov_map.copy()
    rng = random.getstate()
    console = main.create_console()
    for tick in (0, 2, 8):
        world.game_time = tick
        village.draw_buildings(console, world, 0, 0)
        ground.draw(console, world, 0, 0, 13, 14, "plains")
    assert building.__dict__ == before
    assert np.array_equal(world.player_fov_map, fov)
    assert random.getstate() == rng


def test_new_trade_motifs_are_not_the_same_fallback_lines():
    motifs = ("crate", "timber", "grain", "civic", "badge", "bars", "cleaver", "antler")
    assert len({village.sign_surface(m).tobytes() for m in motifs}) == len(motifs)
