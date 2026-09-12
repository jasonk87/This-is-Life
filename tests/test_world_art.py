"""Native world art must preserve visibility, simulation truth and UI bounds."""

import random
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

import main
from config import MAP_HEIGHT, MAP_WIDTH
from runtime_compat import np
from tcod_compat import tcod, TCOD_AVAILABLE
from rendering import console_renderer as cr, people_art as people
from rendering import pixel_scene as pixels, village_art as village
from rendering import sprite_atlas, terrain_art
from rendering import actor_motion, interior_art, character_layers
from simulation.world_model import Building
from tools.street_review import activity_actor


@pytest.fixture(scope="module")
def native_art():
    if not TCOD_AVAILABLE:
        pytest.skip("Native tcod required")
    old_tiles, old_people, old_trees = pixels._tileset, people._people, village._trees
    old_views, old_interiors = people._views.copy(), interior_art._sources
    old_postures = people._postures.copy()
    old_parts = character_layers._parts.copy()
    old_zoom = sprite_atlas._zoomed_sprite_codepoints.copy()
    old_terrain = terrain_art._registered
    tiles = main.load_custom_tileset()
    yield tiles
    pixels.install(old_tiles)
    people._people, village._trees = old_people, old_trees
    people._views.clear()
    people._views.update(old_views)
    people._postures.clear()
    people._postures.update(old_postures)
    character_layers._parts.clear()
    character_layers._parts.update(old_parts)
    character_layers.rig.cache_clear()
    character_layers.part.cache_clear()
    character_layers.identity_head.cache_clear()
    from rendering import character_pose
    character_pose.clear()
    interior_art._sources = old_interiors
    interior_art.object_pixels.cache_clear()
    interior_art.foreground_pixels.cache_clear()
    actor_motion.reset()
    people.character_pixels.cache_clear()
    sprite_atlas._zoomed_sprite_codepoints.clear()
    sprite_atlas._zoomed_sprite_codepoints.update(old_zoom)
    terrain_art._registered = old_terrain


@pytest.fixture(autouse=True)
def clear_composites():
    actor_motion.reset()
    pixels.set_lightfield(None, None)
    pixels._composites.clear()
    pixels._parts.clear()
    pixels._pixels.clear()


def solid(color, width=16, height=16):
    result = np.empty((height, width, 4), dtype=np.uint8)
    result[:] = color
    return result


def test_original_sources_and_normalized_cells_have_real_transparency(native_art):
    assert len(people._people) == 32
    assert len(village._trees) == 4
    for sprite in people._people:
        assert sprite.shape == (48, 32, 4)
        assert sprite[:, :, 3].any()
        assert (sprite[:, :, 3] == 0).any()
    for sprite in village._trees:
        assert sprite.shape == (80, 64, 4)
        assert sprite[:, :, 3].any()


def test_alpha_compositing_retains_the_floor(native_art):
    console = main.create_console()
    console.clear(bg=(20, 40, 60))
    source = solid((200, 100, 40, 128))
    source[0, 0] = (0, 0, 0, 0)
    pixels.stamp(console, source, 0, 0, token="half-alpha")
    result = native_art.get_tile(int(console.ch[0, 0]))
    assert tuple(result[0, 0, :3]) == (20, 40, 60)
    expected = (np.array([200, 100, 40]) * 128 + np.array([20, 40, 60]) * 127) // 255
    assert tuple(result[1, 1, :3]) == tuple(expected)
    assert np.all(result[:, :, 3] == 255)


@pytest.mark.parametrize("x,y", [(-8, -8), (MAP_WIDTH * 16 - 8, 0), (0, MAP_HEIGHT * 16 - 8)])
def test_partial_sprites_never_paint_sidebar_or_log(native_art, x, y):
    console = main.create_console()
    before = console.ch.copy()
    pixels.stamp(console, solid((170, 120, 70, 255), 32, 32), x, y, token=("edge", x, y))
    assert np.array_equal(console.ch[:, MAP_WIDTH:], before[:, MAP_WIDTH:])
    assert np.array_equal(console.ch[MAP_HEIGHT:], before[MAP_HEIGHT:])
    assert not np.array_equal(console.ch[:MAP_HEIGHT, :MAP_WIDTH], before[:MAP_HEIGHT, :MAP_WIDTH])


def test_optional_clip_mask_is_respected(native_art):
    console = main.create_console()
    pixels.stamp(
        console, solid((90, 80, 70, 255), 32, 16), 0, 0, token="clip", clip=lambda x, y: x == 1
    )
    assert console.ch[0, 0] == 32
    assert console.ch[0, 1] != 32


def test_opaque_cache_does_not_depend_on_obscured_background(native_art):
    console = main.create_console()
    source = solid((40, 60, 80, 255))
    for bg in ((0, 0, 0), (200, 180, 160)):
        console.clear(bg=bg)
        pixels.stamp(console, source, 0, 0, token="opaque")
    assert len(pixels._composites) == 1


def test_transparent_cache_does_depend_on_underlying_pixels(native_art):
    console = main.create_console()
    source = solid((40, 60, 80, 100))
    values = []
    for bg in ((0, 0, 0), (200, 180, 160)):
        console.clear(bg=bg)
        pixels.stamp(console, source, 0, 0, token="translucent")
        values.append(native_art.get_tile(int(console.ch[0, 0])).copy())
    assert not np.array_equal(*values)


def test_capacity_never_recycles_tiles_during_a_frame(native_art):
    console = main.create_console()
    with patch.object(pixels, "CAPACITY", 1):
        pixels.stamp(console, solid((20, 40, 60, 255)), 0, 0, token="first")
        first = native_art.get_tile(int(console.ch[0, 0])).copy()
        pixels.stamp(console, solid((100, 120, 140, 255)), 16, 0, token="second")
        assert console.ch[0, 1] == 32
        assert np.array_equal(native_art.get_tile(int(console.ch[0, 0])), first)
        pixels.begin_frame()
        assert not pixels._composites


def scene():
    building = Building(10, 8, 7, 6, building_type="bakery")
    building.interaction_points["entrance"] = (13, 8)
    fov = np.zeros((32, 32), dtype=bool)
    world = NS(
        player=NS(x=13, y=7),
        player_fov_map=fov,
        explored_map=np.zeros_like(fov),
        buildings_by_id={building.id: building},
        zoom_levels=(1,),
        zoom_index=0,
        game_time=0,
    )
    return world, building


@pytest.mark.parametrize("mode", ["unseen", "exterior", "cutaway", "inside"])
def test_roof_mode_never_changes_fov_or_exploration(mode):
    world, building = scene()
    if mode != "unseen":
        world.player_fov_map[8, 13] = True
    if mode == "cutaway":
        world.player_fov_map[9, 13] = True
    if mode == "inside":
        world.player.x, world.player.y = 12, 10
    before = world.player_fov_map.copy(), world.explored_map.copy()
    assert village.roof_mode(world, building) == ("cutaway" if mode == "inside" else mode)
    assert np.array_equal(world.player_fov_map, before[0])
    assert np.array_equal(world.explored_map, before[1])


@pytest.mark.parametrize("entrance", [(3, 0), (3, 5), (0, 2), (6, 2)])
def test_roof_keeps_the_real_entrance_tile_clear(entrance):
    image = village.roof_surface("bakery", 7, 6, entrance)
    x, y = entrance
    assert not image[y * 32 : (y + 1) * 32, x * 32 : (x + 1) * 32, 3].any()
    assert image[:, :, 3].any()


def test_doors_have_different_open_and_closed_pixels():
    opened = village.wall_surface("house", "horizontal", False, "open")
    closed = village.wall_surface("house", "horizontal", False, "closed")
    assert not np.array_equal(opened, closed)


def test_buildings_and_signs_have_distinct_visual_identities():
    kinds = ("bakery", "blacksmith_shop", "tavern", "house")
    images = [village.roof_surface(kind, 7, 6, (3, 0)).tobytes() for kind in kinds]
    assert len(set(images)) == len(kinds)
    signs = [village.sign_surface(motif).tobytes() for motif in ("bread", "mug", "anvil")]
    assert len(set(signs)) == 3


@pytest.mark.parametrize("kind", ["tall_grass", "flower"])
def test_understory_is_visible_but_leaves_most_ground_clear(kind):
    image = village.understory_surface(kind, 0)
    occupied = int((image[:, :, 3] > 0).sum())
    assert 30 < occupied < 300


def test_unseen_buildings_do_not_stamp_anything(native_art):
    world, _ = scene()
    with patch.object(pixels, "stamp") as stamp:
        village.draw_buildings(main.create_console(), world, 0, 0)
    stamp.assert_not_called()


def test_doorway_cutaway_leaves_visible_interior_uncovered(native_art):
    world, building = scene()
    world.player_fov_map[8:11, 13] = True
    with patch.object(pixels, "stamp") as stamp, patch.object(
        cr, "is_visible", side_effect=lambda w, x, y: bool(w.player_fov_map[y, x])
    ):
        village.draw_buildings(main.create_console(), world, 0, 0)
    roof = next(call for call in stamp.call_args_list if call.kwargs["token"][0] == "roof")
    assert not roof.kwargs["clip"](13, 10)
    assert roof.kwargs["clip"](14, 10)


def test_roof_fully_disappears_when_player_is_inside(native_art):
    world, building = scene()
    world.player.x, world.player.y = 12, 10
    world.player_fov_map[10, 12] = True
    with patch.object(pixels, "stamp") as stamp:
        village.draw_buildings(main.create_console(), world, 0, 0)
    assert all(call.kwargs["token"][0] != "roof" for call in stamp.call_args_list)


def test_chimneys_require_a_real_thermal_workstation():
    world, building = scene()
    assert village.thermal_station(building) is None
    building.work_zone_tiles = {"oven": [(13, 9)]}
    assert village.thermal_station(building) == (13, 9)
    work_world, actor = activity_actor("idle")
    actor.x, actor.y = 13, 9
    world.village_npcs = [actor]
    assert not village.station_is_working(world, building, (13, 9))
    actor.task_timer, actor.current_sub_task = 10, "bake_bread"
    assert village.station_is_working(world, building, (13, 9))


@pytest.mark.parametrize(
    "kind", ["idle", "chop", "hammer", "prepare", "carry", "eat", "sleep", "talk"]
)
def test_activity_uses_real_state(kind):
    world, actor = activity_actor(kind)
    assert people.activity_for(world, actor).kind == kind


def test_an_idle_blacksmith_does_not_hammer():
    world, actor = activity_actor("idle")
    actor.schedule.current_task = "at_work"
    assert people.activity_for(world, actor).kind == "idle"


@pytest.mark.parametrize("invalid", ["wrong_actor", "finished", "cancelled"])
def test_invalid_active_interaction_cannot_animate(invalid):
    world, actor = activity_actor("chop")
    interaction = world.interaction_resolver.active_interactions["work"]
    if invalid == "wrong_actor":
        interaction.actor_id = "someone_else"
    elif invalid == "finished":
        interaction.remaining_work = 0
    else:
        world.interaction_resolver.active_interactions.clear()
    assert people.activity_for(world, actor).kind == "idle"


@pytest.mark.parametrize("invalid", ["empty_inventory", "going_to_source", "no_item_context"])
def test_hauling_does_not_invent_carried_items(invalid):
    world, actor = activity_actor("carry")
    if invalid == "empty_inventory":
        actor.economic.npc_inventory.clear()
    elif invalid == "going_to_source":
        actor.schedule.current_task = "hauling_to_source"
    else:
        actor.task_context_data.clear()
    assert people.activity_for(world, actor).item is None


def test_talking_stops_when_actual_speech_expires():
    world, actor = activity_actor("talk")
    world.game_time = 20
    assert people.activity_for(world, actor).kind == "idle"


def test_walking_and_sitting_follow_actual_states():
    world, actor = activity_actor("idle")
    actor.state = NS(is_sitting=True)
    assert people.activity_for(world, actor).kind == "sit"
    actor.schedule.current_path = [(1, 1)]
    actor.state.is_sitting = False
    assert people.activity_for(world, actor).kind == "idle"
    actor.render_x, actor.render_y = actor.x - 0.5, actor.y
    assert people.activity_for(world, actor).kind == "walk"


@pytest.mark.parametrize("zoom", [1, 2, 3, 4])
def test_all_zooms_support_tall_people_without_changing_ui(native_art, zoom):
    world, actor = activity_actor("idle")
    del actor.gender  # The real player does not have the NPC gender field.
    world.zoom_levels = (zoom,)
    console = main.create_console()
    before = console.ch.copy()
    assert people.draw_person(
        console, world, actor, 0, 0, MAP_WIDTH / zoom - 1, MAP_HEIGHT / zoom - 1
    )
    assert np.array_equal(console.ch[:, MAP_WIDTH:], before[:, MAP_WIDTH:])
    assert np.array_equal(console.ch[MAP_HEIGHT:], before[MAP_HEIGHT:])
    assert (console.ch[:MAP_HEIGHT, :MAP_WIDTH] != before[:MAP_HEIGHT, :MAP_WIDTH]).any()


def test_rendering_never_advances_simulation_randomness(native_art):
    world, actor = activity_actor("hammer")
    state = random.getstate()
    console = main.create_console()
    for phase in range(4):
        world.game_time = phase * 2
        people.draw_person(console, world, actor, 0, 0, 5, 5)
        village.roof_surface("tavern", 9, 9, (4, 8))
        village.road_surface(15, phase)
    assert random.getstate() == state


def test_taller_people_still_respect_actor_visibility(native_art):
    world, actor = activity_actor("idle")
    with patch.object(cr, "_iter_render_entities", return_value=[actor]), patch.object(
        cr, "is_visible", return_value=False
    ), patch.object(people, "draw_person") as draw_person:
        cr._draw_entities(main.create_console(), world, 0, 0)
    draw_person.assert_not_called()


def test_animals_with_npc_gender_fields_keep_animal_art(native_art):
    from entities.animal import Animal

    animal = Animal(5, 5, animal_type="wolf")
    world = NS(player=NS(x=1, y=1))
    assert hasattr(animal, "gender")
    assert not people.draw_person(main.create_console(), world, animal, 0, 0, 5, 5)


def test_tall_body_hit_test_selects_the_actor_not_the_floor_behind(native_art):
    world, actor = activity_actor("idle")
    actor.x, actor.y = 5, 5
    # At zoom 3 the head extends into console row 13, above the occupied tile.
    with patch.object(cr, "is_visible", return_value=True):
        assert people.hit_test(world, 0, 0, 16, 13) is actor
        assert people.hit_test(world, 0, 0, 30, 13) is None
        assert people.hit_test(world, 0, 0, 16, 1) is None
    with patch.object(cr, "is_visible", return_value=False):
        assert people.hit_test(world, 0, 0, 16, 13) is None


def test_right_click_head_inspects_actual_actor_tile(native_art):
    from unittest.mock import Mock

    world, actor = activity_actor("idle")
    actor.x, actor.y = 5, 5
    actor.state = NS(current_path=[])
    world.game_state = "PLAYING"
    world.chat_ui_active = False
    world.interaction_context = {"active": False}
    world.inspect_tile = Mock(return_value="A person")
    world.add_message_to_chat_log = Mock()
    event = tcod.event.MouseButtonDown(position=(16, 13), button=tcod.event.MouseButton.RIGHT)
    context = NS(convert_event=lambda event: event)
    with patch.object(main.tcod.event, "get", return_value=[event]), patch.object(
        main, "_get_camera_origin", return_value=(0, 0)
    ), patch.object(main, "apply_ui_requests"), patch.object(
        cr, "is_visible", return_value=True
    ), patch.object(
        main, "open_interaction_menu"
    ) as menu:
        main.handle_events(world, context)
    world.inspect_tile.assert_called_once_with(5, 5)
    menu.assert_called_once_with(world, 5, 5)


def test_legacy_style_can_still_be_selected(native_art):
    world, actor = activity_actor("idle")
    world.world_art_style = "legacy"
    assert not people.draw_person(main.create_console(), world, actor, 0, 0, 1, 1)


def test_night_and_season_tints_are_not_bypassed():
    world = NS(current_light_level_name="DAY", seasons=["Summer", "Winter"], current_season_index=0)
    summer = pixels.world_tint(world)
    world.current_season_index = 1
    winter = pixels.world_tint(world)
    world.current_light_level_name = "NIGHT"
    night = pixels.world_tint(world)
    assert summer != winter
    assert sum(night) < sum(winter)


def test_women_keep_their_profession_clothing(native_art):
    world, actor = activity_actor("idle")
    actor.gender = "female"
    smith = people.outfit_index(actor)
    actor.economic.profession = "Baker"
    baker = people.outfit_index(actor)
    assert smith == 16 + 5
    assert baker == 16 + 4
    assert not np.array_equal(people._people[smith], people._people[baker])


def test_guard_art_does_not_invent_equipped_armor(native_art):
    world, actor = activity_actor("idle")
    actor.economic.profession = "Guard"
    assert people.outfit_index(actor) != 10
    actor.equipment = NS(head=NS(item_key="iron_helmet"))
    assert people.outfit_index(actor) == 10


def test_sleep_schedule_uses_a_sleeping_pose():
    world, actor = activity_actor("idle")
    actor.schedule.current_task = "sleeping"
    assert people.activity_for(world, actor).kind == "sleep"


def test_frontmost_person_is_drawn_last(native_art):
    back = NS(x=3, y=2)
    front = NS(x=3, y=3)
    world = NS(npcs=[front], village_npcs=[back], player=NS(x=4, y=4))
    assert cr._iter_render_entities(world) == [back, front, world.player]


def test_actor_can_sample_existing_local_firelight(native_art):
    world = NS(current_light_level_name="NIGHT")
    tint = np.full((5, 5, 3), 150, dtype=np.uint8)
    tint[2, 2] = (230, 181, 115)
    pixels.set_lightfield(tint, np.ones((5, 5), dtype=bool))
    assert pixels.world_tint(world, 2, 2) == (230, 181, 115)
    pixels.begin_frame()
    assert pixels.world_tint(world, 2, 2) != (230, 181, 115)


def test_cached_tile_lookup_accepts_changed_definitions():
    tile = NS(name="Temporary Wall", char=123)
    with patch.dict(cr.TILE_DEFINITIONS, {"test_wall": {"name": tile.name, "char": tile.char}}):
        assert cr._get_tile_key(tile) == "test_wall"
        cr.TILE_DEFINITIONS["test_wall"] = {"name": "New Wall", "char": 124}
        assert cr._get_tile_key(tile) is None


def test_ticked_world_with_native_art_at_every_zoom(native_art, monkeypatch):
    import engine
    from simulation.systems.tick import run_world_tick

    monkeypatch.setattr(engine, "ENABLE_LLM_CONNECTION", False)
    monkeypatch.setattr(engine, "ENABLE_OLLAMA_CONNECTION", False)
    world = engine.World(seed=321, player_first_name="ArtCheck")
    world._pre_simulate_world()
    main._ensure_zoom_state(world)
    world.mouse_x = world.mouse_y = -1
    console = main.create_console()
    for tick in range(40):
        run_world_tick(world)
        if tick % 10:
            continue
        world.zoom_index = tick // 10
        fov, explored = world.player_fov_map.copy(), world.explored_map.copy()
        before = random.getstate()
        cr.draw(console, world, *main._get_camera_origin(world))
        assert (console.ch[:MAP_HEIGHT, :MAP_WIDTH] != 32).any()
        assert np.array_equal(fov, world.player_fov_map)
        assert np.array_equal(explored, world.explored_map)
        assert random.getstate() == before
