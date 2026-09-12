"""Layout, native-pixel and input regressions for the visual refresh."""
from types import SimpleNamespace
from unittest.mock import Mock, patch
import random

import pytest
import main
from runtime_compat import np
from tcod_compat import tcod, TCOD_AVAILABLE
from config import MAP_WIDTH
from data.items import ITEM_DEFINITIONS
from data.construction import CONSTRUCTION_RECIPES
from entities.items import Inventory
from rendering import console_renderer as cr, hud, sprite_atlas, terrain_art, ui_glyphs, widgets
from rendering import ui_theme as theme
from tests.test_ui_polish import RecordingConsole


@pytest.fixture
def native_tiles():
    if not TCOD_AVAILABLE:
        pytest.skip("Real tcod required for pixel verification")
    before = sprite_atlas._zoomed_sprite_codepoints.copy()
    registered = terrain_art._registered
    tiles = tcod.tileset.Tileset(16, 16)
    ui_glyphs.register_ui_glyphs(tiles)
    terrain_art.register_terrain_tiles(tiles)
    yield tiles
    sprite_atlas._zoomed_sprite_codepoints.clear()
    sprite_atlas._zoomed_sprite_codepoints.update(before)
    terrain_art._registered = registered


def test_ui_geometry_has_real_pixels(native_tiles):
    for char in "─│┌┐└┘├┤┬┴┼█░•▲▼":
        assert native_tiles.get_tile(ord(char))[:, :, 3].sum() > 0, char
    assert np.all(native_tiles.get_tile(ord("█"))[:, :, 3] == 255)


def test_texture_generation_does_not_advance_simulation_randomness():
    state = random.getstate()
    for material in terrain_art.MATERIALS:
        for variant in range(terrain_art.VARIANTS):
            first = terrain_art._surface(material, variant)
            assert np.array_equal(first, terrain_art._surface(material, variant))
    assert random.getstate() == state


@pytest.mark.parametrize("zoom", [2, 3, 4])
def test_every_material_zoom_is_exact_nearest_neighbor(native_tiles, zoom):
    for material in terrain_art.MATERIALS:
        cp = terrain_art.terrain_codepoint(material, 7, 11)
        expected = native_tiles.get_tile(cp).repeat(zoom, axis=0).repeat(zoom, axis=1)
        for y in range(zoom):
            for x in range(zoom):
                part = sprite_atlas.zoomed_sprite_codepoint(cp, zoom, x, y)
                assert part is not None
                assert np.array_equal(native_tiles.get_tile(part), expected[y*16:(y+1)*16, x*16:(x+1)*16])


def test_partial_sprite_at_right_edge_uses_correct_quadrants(native_tiles):
    console = main.create_console()
    world = SimpleNamespace(zoom_levels=(4,), zoom_index=0)
    cp = terrain_art.terrain_codepoint("plains", 0, 0)
    assert cr._draw_zoomed_sprite(console, world, (76, 4, 77, 7), cp, fg=(255,255,255))
    for y in range(4):
        for x in range(2):
            assert console.ch[y+4, x+76] == sprite_atlas.zoomed_sprite_codepoint(cp,4,x,y)
    assert np.all(console.ch[4:8, 78:] == 32)


def inventory_world():
    bag = Inventory()
    bag.add_item("bread", 3)
    bag.add_item("raw_log", 12)
    return SimpleNamespace(
        game_state="INVENTORY_MENU", mouse_x=-1, mouse_y=-1,
        player=SimpleNamespace(economic=SimpleNamespace(inventory=bag, money=9)),
        interaction_context={"active": False},
    )


def test_inventory_selection_is_visible_and_quality_preserved():
    world = inventory_world()
    world.player.economic.inventory.add_item("healing_salve",1,quality="Masterwork")
    console = main.create_console()
    cr.draw_inventory_menu(console,world)
    selected = world.interaction_context["inventory_selectable"].index("healing_salve")
    world.interaction_context["inventory_selected_index"] = selected
    cr.draw_inventory_menu(console,world)
    record = world.menu_hit_regions["INVENTORY_MENU"]
    row = world.interaction_context["inventory_selectable_rows"][selected]
    y = record.region.y + row - record.scroll_offset
    assert tuple(console.bg[y,record.region.x]) == theme.SELECTION_BG
    assert tuple(console.fg[y,record.region.x+4]) == theme.QUALITY_COLORS["Masterwork"]


@pytest.mark.parametrize("button,confirms", [(tcod.event.MouseButton.LEFT, True), (tcod.event.MouseButton.RIGHT,False)])
def test_inventory_mouse_maps_display_rows_to_items(button, confirms):
    world = inventory_world()
    cr.draw_inventory_menu(main.create_console(),world)
    record = world.menu_hit_regions["INVENTORY_MENU"]
    row = world.interaction_context["inventory_selectable_rows"][1]
    world.mouse_x,world.mouse_y = record.region.x, record.region.y + row - record.scroll_offset
    with patch("main.handle_inventory_menu_input") as confirm:
        assert main.handle_menu_mouse_click(SimpleNamespace(button=button),world,None)
        assert confirm.called == confirms
    assert world.interaction_context["inventory_selected_index"] == 1


def test_inventory_header_click_never_uses_an_item():
    world = inventory_world()
    cr.draw_inventory_menu(main.create_console(),world)
    region = world.menu_hit_regions["INVENTORY_MENU"].region
    world.mouse_x,world.mouse_y = region.x,region.y
    with patch("main.handle_inventory_menu_input") as confirm:
        assert main.handle_menu_mouse_click(SimpleNamespace(button=tcod.event.MouseButton.LEFT),world,None)
        confirm.assert_not_called()


def test_converted_mouse_click_uses_its_own_tile_position():
    world = SimpleNamespace(game_state="PLAYING", mouse_x=70,mouse_y=30,
                            interaction_context={"active":False}, chat_ui_active=False)
    raw = tcod.event.MouseButtonDown(position=(80,16),button=tcod.event.MouseButton.LEFT)
    converted = tcod.event.MouseButtonDown(position=(5,1),button=tcod.event.MouseButton.LEFT)
    context = SimpleNamespace(convert_event=Mock(return_value=converted))
    with patch("main.tcod.event.get",return_value=[raw]), patch("main.apply_ui_requests"), \
            patch("main.handle_playing_input") as action:
        main.handle_events(world,context)
    assert (world.mouse_x,world.mouse_y) == (5,1)
    assert action.call_args.args[0].sym == tcod.event.KeySym.SPACE


def test_toolbar_actions_have_nonoverlapping_hit_targets():
    world = SimpleNamespace(is_paused=True)
    actions = []
    for x,width,text,action in hud.toolbar_buttons(world):
        assert x+width <= MAP_WIDTH
        assert hud.toolbar_action_at(world,x,1) == action
        assert hud.toolbar_action_at(world,x,3) is None
        actions.append(action)
    assert "SLASH" in actions
    assert len(actions) == len(set(actions))


def test_sidebar_wheel_does_not_change_map_zoom():
    world = SimpleNamespace(game_state="PLAYING",mouse_x=80,mouse_y=25,
                            field_guide_scroll=0,field_guide_max_scroll=12,zoom_index=2)
    assert main.handle_mouse_wheel(world,SimpleNamespace(y=-1))
    assert world.field_guide_scroll == 3
    assert world.zoom_index == 2


def test_log_wheel_scrolls_back_and_does_not_change_zoom():
    from presentation.message_log import entries_from_plain_log
    world = SimpleNamespace(game_state="PLAYING",mouse_x=10,mouse_y=53,
                            chat_log_entries=entries_from_plain_log([str(i) for i in range(20)]),
                            chat_log_scroll=0,zoom_index=2)
    assert main.handle_mouse_wheel(world,SimpleNamespace(y=1))
    assert world.chat_log_scroll == 3
    assert world.zoom_index == 2


def test_dialogue_long_input_and_history_stay_inside_frame():
    world = SimpleNamespace(player=SimpleNamespace(name="Mara"),chat_ui_target_npc=None,
                            chat_ui_history=[("Player","Tell me about your work. "*15)]*12,
                            chat_ui_input_line="where "*150)
    console = RecordingConsole()
    cr.draw_dialogue_menu(console,world)
    frame = widgets.centered_menu(68,26)
    assert world.dialogue_max_scroll > 0
    for call in console.print_calls:
        assert frame.x <= call["x"] < frame.x+frame.width
        assert call["x"]+len(call["string"]) <= frame.x+frame.width
        assert frame.y <= call["y"] < frame.y+frame.height


def recipe_world():
    return SimpleNamespace(player=SimpleNamespace(has_item=lambda *_:False),
        player_can_craft=lambda _:False, _is_player_near_workstation=lambda _:False,
        crafting_menu_context={"all_recipes":[],"selected_recipe_index":0},
        building_menu_context={"all_recipes":[],"selected_recipe_index":0})


def test_every_recipe_detail_fits_without_covering_sidebar():
    world = recipe_world()
    for context,draw,keys in [
        (world.crafting_menu_context,cr.draw_crafting_menu,[k for k,v in ITEM_DEFINITIONS.items() if v.get("crafting_recipe")]),
        (world.building_menu_context,cr.draw_building_menu,list(CONSTRUCTION_RECIPES)),
    ]:
        context["all_recipes"] = keys
        for index in range(len(keys)):
            context["selected_recipe_index"] = index
            console = RecordingConsole()
            draw(console,world)
            for frame in console.frames:
                assert 0 <= frame["x"] and frame["x"]+frame["width"] <= MAP_WIDTH
            for call in console.print_calls:
                assert 0 <= call["x"] and call["x"]+call.get("width",len(call.get("string",""))) <= MAP_WIDTH
                assert 10 <= call["y"] < 46


def test_crafting_displays_item_recipe_and_workstation():
    world = recipe_world()
    world.crafting_menu_context["all_recipes"] = ["anvil"]
    console = RecordingConsole()
    cr.draw_crafting_menu(console,world)
    text = " ".join(console.strings())
    for expected in ("Anvil", "Iron Ingot: 5", "Needs: Workbench"):
        assert expected in text


def test_help_key_columns_do_not_overlap_action_names():
    console = RecordingConsole()
    cr.draw_help_menu(console)
    for action,key in cr.HELP_CONTROLS:
        label = next(c for c in console.print_calls if c["string"] == action)
        binding = next(c for c in console.print_calls if c["string"] == key and c["y"] == label["y"])
        assert label["x"]+len(action)+2 <= binding["x"]


def test_stale_actor_interpolation_draws_at_logical_position():
    actor = SimpleNamespace(x=10,y=10,render_x=400,render_y=300,
                            state=SimpleNamespace(is_riding=False),color=(255,255,255))
    world = SimpleNamespace(player=actor,zoom_levels=(1,),zoom_index=0)
    console = RecordingConsole()
    with patch.object(cr,"_iter_render_entities",return_value=[actor]), \
            patch.object(cr,"is_visible",return_value=True), \
            patch.object(cr,"get_entity_sprite",return_value=ord("@")):
        cr._draw_entities(console,world,0,0)
    assert any(c["x"] == 10 and c["y"] == 10 for c in console.print_calls)
    assert (actor.render_x,actor.render_y) == (400,300)  # UI does not mutate simulation.


def test_field_guide_overflow_keeps_vitals_pinned():
    player = SimpleNamespace(
        name="Mara",x=5,y=5,
        economic=SimpleNamespace(profession="Farmer",money=9,inventory={}),
        physical=SimpleNamespace(hunger=30,max_hunger=100,thirst=20,max_thirst=100,status_effects=[]),
        combat=SimpleNamespace(hp=25,max_hp=35),social=SimpleNamespace(reputation={}),
        knowledge=SimpleNamespace(active_quests={str(i):{"title":f"Task {i}"} for i in range(40)}),
    )
    world = SimpleNamespace(player=player,game_time=0,weather="clear",mouse_x=-1,mouse_y=-1,
                            seasons=["Spring"],current_season_index=0,
                            get_tile_at=lambda *_:SimpleNamespace(name="Plains"))
    console = main.create_console()
    with patch.object(cr,"_get_focus_target",return_value={"label":""}), \
            patch.object(cr,"_get_visible_nearby_entities",return_value=[]), \
            patch.object(cr,"_draw_minimap_panel"):
        cr.draw_status_panel(console,world,0,0)
        before = console.ch[2:14,MAP_WIDTH:].copy()
        assert world.field_guide_max_scroll > 20
        world.field_guide_scroll = world.field_guide_max_scroll
        cr.draw_status_panel(console,world,0,0)
    assert np.array_equal(before,console.ch[2:14,MAP_WIDTH:])
    assert "Task 39" in " ".join("".join(chr(v) for v in row) for row in console.ch)


def test_weather_layer_precedes_actors_and_menus():
    from contextlib import ExitStack
    world = SimpleNamespace(player_fov_map=None,explored_map=[],chunks=[],
                            player=SimpleNamespace(state=SimpleNamespace(current_path=[])),
                            visual_effects=[],interaction_context={"active":False})
    order = []
    names = ["_apply_lighting_and_depth","draw_weather_overlay","_draw_items","_draw_entities",
             "_draw_body_condition_labels","_draw_entity_markers","_draw_world_markers",
             "_draw_ambient_speech","draw_look_cursor","_draw_focus_badge","draw_status_panel",
             "_draw_log_panel","_draw_active_game_state_menu_with_fade"]
    with ExitStack() as stack:
        stack.enter_context(patch.object(cr,"_get_world_view_dimensions",return_value=(0,0)))
        stack.enter_context(patch.object(cr,"_get_focus_target",return_value={}))
        stack.enter_context(patch.object(cr,"_get_visible_nearby_entities",return_value=[]))
        stack.enter_context(patch.object(hud,"draw_toolbar"))
        for name in names:
            stack.enter_context(patch.object(cr,name,side_effect=lambda *args,_name=name:order.append(_name)))
        cr.draw(Mock(),world,0,0)
    assert order.index("draw_weather_overlay") < order.index("_draw_entities")
    assert order.index("_draw_entities") < order.index("draw_status_panel")
    assert order.index("_draw_log_panel") < order.index("_draw_active_game_state_menu_with_fade")
