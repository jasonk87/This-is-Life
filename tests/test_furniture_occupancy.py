"""Native overlap, picking and attachment contracts, without simulation rewrites."""

import copy
import random
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest

import main
from config import MAP_HEIGHT, MAP_WIDTH
from data.decorations import DECORATION_ITEM_DEFINITIONS as DECOR
from data.tiles import TILE_DEFINITIONS
from rendering import furniture_occupancy as occupancy, interior_art as interiors
from rendering import people_art as people, pixel_scene as pixels, room_scene
from rendering import console_renderer as cr
from runtime_compat import np
from simulation.activity import start_activity
from simulation.systems.interaction import ActionIntent, InteractionResolver
from tests.test_world_art import native_art, clear_composites
from tools.street_review import activity_actor


def occupied_room(key="wooden_chair", zoom=3, npc=False):
    world, actor = activity_actor("idle")
    actor.x, actor.y = 5, 5
    actor.render_x, actor.render_y = 5, 5
    actor.state = NS(is_sitting=False, current_path=[], last_dx=0, last_dy=0)
    world.npcs, world.village_npcs = [], []
    world.zoom_levels, world.zoom_index = (zoom,), 0
    world.player_fov_map = np.ones((90, 90), dtype=bool)
    world.items_on_map = {}
    fixture = NS(**copy.deepcopy(DECOR[key]))
    floor = NS(**TILE_DEFINITIONS["wood_floor"])
    world.get_tile_at = lambda x, y: fixture if (x, y) == (6, 5) else floor
    world.add_message_to_chat_log = Mock()
    if npc:
        world.player = NS(x=3, y=5, render_disabled=True)
        world.npcs = [actor]
    return world, actor, fixture


def sit(world, actor):
    intent = ActionIntent(actor.id, "sit_on_chair", target_pos=(6, 5))
    result = InteractionResolver()._resolve_sit_or_sleep(intent, world, actor)
    assert result.success


def test_real_npc_sitting_contract_attaches_art_not_logical_position(native_art):
    world, actor, _ = occupied_room(npc=True)
    sit(world, actor)
    before = copy.deepcopy(actor.__dict__)
    assert occupancy.render_anchor(world, actor) == (6, 5)
    assert occupancy.attachment_for(world, actor).kind == "seated"
    people.body_frame(world, actor, 3)
    room_scene.draw(main.create_console(), world, 0, 0)
    assert (actor.x, actor.y) == (5, 5)
    assert actor.__dict__ == before


def test_real_player_sit_and_stand_contract(native_art):
    from engine import World

    world, actor, _ = occupied_room()
    assert World.player_attempt_sit(world, 6, 5)
    assert occupancy.render_anchor(world, actor) == (6, 5)
    assert (actor.x, actor.y) == (5, 5)
    World.player_attempt_stand_up(world)
    assert occupancy.attachment_for(world, actor) is None
    assert occupancy.render_anchor(world, actor) == (5, 5)


@pytest.mark.parametrize(
    "invalid",
    [
        "removed",
        "far",
        "hidden",
        "origin_hidden",
        "path",
        "state_path",
        "moved",
        "completed",
        "dead",
        "disabled",
        "no_flag",
    ],
)
def test_invalid_chair_attachment_is_rejected(native_art, invalid):
    world, actor, fixture = occupied_room()
    sit(world, actor)
    if invalid == "removed":
        fixture.name = "Wood Floor"
    elif invalid == "far":
        actor.sitting_on_object_at = (60, 5)
    elif invalid == "hidden":
        world.player_fov_map[5, 6] = False
    elif invalid == "origin_hidden":
        world.player_fov_map[5, 5] = False
    elif invalid == "path":
        actor.schedule.current_path = [(5, 6)]
    elif invalid == "state_path":
        actor.state.current_path = [(5, 6)]
    elif invalid == "moved":
        actor.y = 6
    elif invalid == "completed":
        actor.current_activity.completed = True
    elif invalid == "dead":
        actor.physical.is_dead = True
    elif invalid == "disabled":
        actor.render_disabled = True
    elif invalid == "no_flag":
        actor.is_sitting = False
    assert occupancy.attachment_for(world, actor) is None


def test_activity_record_can_supply_anchor_but_never_sitting_intent_alone(native_art):
    world, actor, _ = occupied_room()
    start_activity(actor, "sitting", 40, world=world, anchor_coords=(6, 5))
    assert occupancy.attachment_for(world, actor) is None
    actor.is_sitting = True
    assert occupancy.attachment_for(world, actor).x == 6


@pytest.mark.parametrize("key", ["wooden_bed", "bed_simple"])
def test_real_sleep_interaction_anchors_to_actual_bed(native_art, key):
    world, actor, _ = occupied_room(key, npc=True)
    intent = ActionIntent(actor.id, "sleep_in_bed", target_pos=(6, 5))
    assert InteractionResolver()._resolve_sit_or_sleep(intent, world, actor).success
    assert (actor.x, actor.y) == (6, 5)
    before = copy.deepcopy(actor.__dict__)
    assert occupancy.attachment_for(world, actor).kind == "reclining"
    assert occupancy.render_anchor(world, actor) == (6, 5)  # old interpolation remains at 5,5
    room_scene.draw(main.create_console(), world, 0, 0)
    assert actor.__dict__ == before


def test_sleeping_near_a_bed_never_claims_occupancy(native_art):
    world, actor, _ = occupied_room("wooden_bed")
    actor.is_sleeping = True
    assert occupancy.attachment_for(world, actor) is None
    actor.schedule.current_task = "sleeping"
    assert occupancy.attachment_for(world, actor) is None


@pytest.mark.parametrize("legacy", [False, True])
def test_macro_suspended_npc_is_neither_drawn_nor_picked(native_art, legacy):
    world, actor, _ = occupied_room("wooden_bed", npc=True)
    actor.x = 6
    actor.is_sleeping = actor.render_disabled = True
    if legacy:
        world.world_art_style = "legacy"
    assert people.activity_for(world, actor).kind == "idle"
    with patch.object(pixels, "stamp") as stamp:
        cr._draw_entities(main.create_console(), world, 0, 0)
    stamp.assert_not_called()
    assert people.hit_test(world, 0, 0, 19, 14) is None


def test_seated_speech_keeps_pose_and_uses_real_speech_expiry(native_art):
    world, actor, _ = occupied_room()
    sit(world, actor)
    world.active_ambient_speech = [NS(speaker_id=actor.id, created_tick=0, expires_tick=10)]
    image, activity, token = people.body_frame(world, actor, 3)
    assert activity.kind == "talk"
    assert token[-1] == "seated"
    world.game_time = 10
    assert people.body_frame(world, actor, 3)[1].kind == "sit"


def test_sitting_ignores_old_interpolation_and_retains_seated_eating(native_art):
    world, actor, _ = occupied_room()
    sit(world, actor)
    actor.render_x = 4.5
    actor.schedule.current_task = "eating"
    actor.task_timer = 10
    _, activity, token = people.body_frame(world, actor, 3)
    assert activity.kind == "eat"
    assert token[-1] == "seated" and not token[7]


@pytest.mark.parametrize("zoom", [1, 2, 3, 4])
def test_body_uses_chair_anchor_for_draw_and_pick(native_art, zoom):
    world, actor, _ = occupied_room(zoom=zoom)
    sit(world, actor)
    image, _, _, px, py = people.placement(world, actor, zoom, 0, 0)
    hits = []
    for sy in range(max(3, py // 16), (py + image.shape[0] + 15) // 16):
        for sx in range(px // 16, (px + image.shape[1] + 15) // 16):
            if people.hit_test(world, 0, 0, sx, sy) is actor:
                hits.append((sx, sy))
    assert hits
    assert all(sx // zoom == 6 for sx, _ in hits)
    with patch.object(pixels, "stamp") as stamp:
        cr._draw_entities(main.create_console(), world, 0, 0)
    body = next(call for call in stamp.call_args_list if call.kwargs["token"][0] == "person32")
    assert body.args[2:4] == (px, py)


def test_shared_painter_order_keeps_surface_items_with_their_table(native_art):
    world, actor, _ = occupied_room("wooden_table")
    world.items_on_map[(6, 5)] = {"bread": 2}
    actor.y = actor.render_y = 4
    kinds = [entry.kind for entry in room_scene.entries(world, 0, 0)]
    assert kinds == ["actor", "furniture", "items"]
    actor.y = actor.render_y = 6
    assert [entry.kind for entry in room_scene.entries(world, 0, 0)] == [
        "furniture",
        "items",
        "actor",
    ]


def test_entities_listed_in_two_collections_are_only_drawn_once(native_art):
    world, actor, _ = occupied_room(npc=True)
    world.village_npcs = [actor]
    assert sum(e.kind == "actor" for e in room_scene.entries(world, 0, 0)) == 1


@pytest.mark.parametrize("zoom", [1, 2, 3, 4])
def test_opaque_furniture_occludes_body_pixels_and_picking(native_art, zoom):
    world, actor, fixture = occupied_room("bookshelf", zoom)
    actor.x = actor.render_x = 6
    actor.y = actor.render_y = 4
    # Deliberately solid fixture isolates the painter contract from art details.
    block = np.full((zoom * 32, zoom * 16, 4), (150, 90, 40, 255), dtype=np.uint8)
    with patch.object(interiors, "object_pixels", return_value=block):
        console = main.create_console()
        room_scene.draw(console, world, 0, 0)
        sx, sy = 6 * zoom + zoom // 2, 4 * zoom + zoom // 2
        assert np.all(native_art.get_tile(int(console.ch[sy, sx]))[:, :, :3] == (150, 90, 40))
        assert people.hit_test(world, 0, 0, sx, sy) is None
        fixture.name = "Wood Floor"
        assert people.hit_test(world, 0, 0, sx, sy) is actor


@pytest.mark.parametrize("key", ["wooden_chair", "wooden_bed", "bed_simple"])
def test_foreground_is_only_a_mask_of_original_furniture(native_art, key):
    source = interiors.object_pixels(key, 3)
    before = source.copy()
    cover = interiors.foreground_pixels(key, 3)
    mask = cover[:, :, 3] > 0
    assert mask.any() and not mask.all()
    assert np.array_equal(cover[mask], source[mask])
    assert np.array_equal(source, before)


@pytest.mark.parametrize("zoom", [1, 2, 3, 4])
def test_occupied_furniture_never_paints_sidebar_or_log(native_art, zoom):
    world, actor, fixture = occupied_room("wooden_bed", zoom)
    actor.x, actor.y = MAP_WIDTH // zoom - 1, MAP_HEIGHT // zoom - 1
    actor.is_sleeping = True
    world.get_tile_at = lambda x, y: fixture if (x, y) == (actor.x, actor.y) else None
    console = main.create_console()
    before, rng, fov = console.ch.copy(), random.getstate(), world.player_fov_map.copy()
    room_scene.draw(console, world, 0, 0)
    assert np.array_equal(console.ch[:, MAP_WIDTH:], before[:, MAP_WIDTH:])
    assert np.array_equal(console.ch[MAP_HEIGHT:], before[MAP_HEIGHT:])
    assert random.getstate() == rng
    assert np.array_equal(world.player_fov_map, fov)


def test_overlay_anchor_follows_chair_but_not_in_legacy_mode(native_art):
    world, actor, _ = occupied_room()
    sit(world, actor)
    assert occupancy.overlay_anchor(world, actor) == (6, 5)
    world.world_art_style = "legacy"
    assert occupancy.overlay_anchor(world, actor) == (5, 5)


def test_posture_atlases_are_complete_and_distinct_from_standing(native_art):
    assert set(people._postures) == {"seated", "reclining"}
    for kind, sources in people._postures.items():
        assert len(sources) == 32
        for index, source in enumerate(sources):
            before = source.copy()
            for zoom in (1, 2, 3, 4):
                for child in (False, True):
                    image = people.character_pixels(
                        index, zoom, "sit", 0, "south", child, posture=kind
                    )
                    assert (image[:, :, 3] == 0).any()
                    assert (image[:, :, 3] > 200).any()
            assert np.array_equal(before, source)


@pytest.mark.parametrize("key", ["wooden_bed", "bed_simple"])
@pytest.mark.parametrize("zoom", [1, 2, 3, 4])
def test_bed_head_is_pickable_but_covered_lower_body_is_not(native_art, key, zoom):
    world, actor, _ = occupied_room(key, zoom, npc=True)
    actor.x = 6
    actor.is_sleeping = True
    image, _, _, px, py = people.placement(world, actor, zoom, 0, 0)
    head_hits, covered = [], []
    for sy in range(max(3, py // 16), (py + image.shape[0] + 15) // 16):
        for sx in range(px // 16, (px + image.shape[1] + 15) // 16):
            if not (room_scene.cell_alpha(image, px, py, sx, sy) > 32).any():
                continue
            hit = people.hit_test(world, 0, 0, sx, sy)
            (head_hits if hit is actor else covered).append((sx, sy))
    assert head_hits
    if zoom > 1:
        assert covered
        assert min(y for _, y in head_hits) < max(y for _, y in covered)
    # At 1x the tiny face and blanket can share a 16px console input cell;
    # that cell remains inspectable whenever any uncovered face pixel survives.


def test_visible_sleepers_appear_in_nearby_but_suspended_npcs_do_not(native_art):
    world, actor, _ = occupied_room("wooden_bed", npc=True)
    actor.is_sleeping = True
    assert cr._get_visible_nearby_entities(world)[0][1] is actor
    actor.render_disabled = True
    assert cr._get_visible_nearby_entities(world) == []


def test_equipment_is_scaled_with_the_attached_body_before_bedcover(native_art):
    world, actor, _ = occupied_room("wooden_bed")
    world.dynamic_characters_enabled = False  # Legacy overlay placement contract.
    actor.x = 6
    actor.is_sleeping = True
    with patch.object(
        cr, "_get_equipment_overlays", return_value=[(65, 0.5, 0.3, 2)]
    ), patch.object(pixels, "stamp") as stamp:
        people.draw_person(main.create_console(), world, actor, 0, 0, 5, 5)
    calls = stamp.call_args_list
    body = next(c for c in calls if c.kwargs["token"][0] == "person32")
    item = next(c for c in calls if c.kwargs["token"][0] == "equipment32")
    cover_index = next(i for i, c in enumerate(calls) if c.kwargs["token"][0] == "furniture-front")
    item_index = next(i for i, c in enumerate(calls) if c.kwargs["token"][0] == "equipment32")
    assert item_index < cover_index
    assert (
        body.args[2] <= item.args[2] <= body.args[2] + body.args[1].shape[1] - item.args[1].shape[1]
    )


def test_right_click_seated_body_keeps_logical_interaction_target(native_art):
    from tcod_compat import tcod

    world, actor, _ = occupied_room(npc=True)
    sit(world, actor)
    world.game_state, world.chat_ui_active = "PLAYING", False
    world.interaction_context = {"active": False}
    world.player.state = NS(current_path=[])
    world.inspect_tile = Mock(return_value="A seated villager")
    image, _, _, px, py = people.placement(world, actor, 3, 0, 0)
    hits = [
        (sx, sy)
        for sy in range(py // 16, (py + image.shape[0]) // 16 + 1)
        for sx in range(px // 16, (px + image.shape[1]) // 16 + 1)
        if people.hit_test(world, 0, 0, sx, sy) is actor
    ]
    event = tcod.event.MouseButtonDown(position=hits[0], button=tcod.event.MouseButton.RIGHT)
    with patch.object(main.tcod.event, "get", return_value=[event]), patch.object(
        main, "_get_camera_origin", return_value=(0, 0)
    ), patch.object(main, "apply_ui_requests"), patch.object(main, "open_interaction_menu") as menu:
        main.handle_events(world, NS(convert_event=lambda e: e))
    world.inspect_tile.assert_called_once_with(5, 5)
    menu.assert_called_once_with(world, 5, 5)


def test_animal_never_uses_a_human_furniture_attachment(native_art):
    world, actor, _ = occupied_room()
    sit(world, actor)
    actor.animal_type = "cat"
    assert occupancy.attachment_for(world, actor) is None


def test_attached_name_follows_actual_head_and_keeps_health_bar_clear(native_art):
    world, actor, _ = occupied_room()
    sit(world, actor)
    image, _, _, px, py = people.placement(world, actor, 3, 0, 0)
    head = ((px + image.shape[1] // 2) // 16, py // 16 - 1)
    assert cr._attached_overlay_point(world, actor, 0, 0, (0, 0)) == head
    assert cr._attached_overlay_point(world, actor, 0, 0, (0, 0), 1) == (head[0], head[1] - 1)
    actor.is_sitting = False
    assert cr._attached_overlay_point(world, actor, 0, 0, (0, 0)) == (0, 0)
