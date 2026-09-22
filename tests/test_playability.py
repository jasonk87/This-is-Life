"""Actual event routing, bounded frame work, fair walking and exact social choices."""
import pickle
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import main
from config import GAME_TICKS_PER_SECOND, SECONDS_PER_GAME_TICK
from presentation.realtime import MovementInput, RealtimeClock
from simulation.systems.tick import advance_player_auto_movement
from simulation.systems import ambient_info
from tests.world_cache import fresh_world


class InputWorld:
    def __init__(self, cost=1):
        self.game_state, self.game_time = "PLAYING", 0
        self.is_paused, self.simulation_speed = False, 1.0
        self.interaction_context = {"active": False}
        self.player = SimpleNamespace(x=0, y=0, combat=SimpleNamespace(hp=20),
            physical=SimpleNamespace(is_dead=False),
            state=SimpleNamespace(current_path=[], move_ready_tick=0, move_cooldown=0))
        self.needs_text_input = False
        self.moves, self.cost = [], cost
        self.ensure_player_surroundings_generated = Mock()
        self.update_animations = Mock()

    def handle_player_movement(self, dx, dy):
        self.player.x += dx
        self.player.y += dy
        self.moves.append((self.game_time, dx, dy))
        return self.cost

    def update(self):
        self.game_time += 1

    def add_message_to_chat_log(self, *args, **kwargs):
        pass


def down(key=main.tcod.event.KeySym.RIGHT, repeat=False):
    return main.tcod.event.KeyDown(scancode=0, sym=key, mod=0, repeat=repeat)


def up(key=main.tcod.event.KeySym.RIGHT):
    return main.tcod.event.KeyUp(scancode=0, sym=key, mod=0)


def events(world, sequence):
    with patch("main.tcod.event.get", return_value=sequence), patch("main.apply_ui_requests"):
        return main.handle_events(world, SimpleNamespace(convert_event=lambda event: event))


def test_calm_clock_runs_four_complete_ticks_per_second():
    clock = RealtimeClock()
    assert GAME_TICKS_PER_SECOND == 4
    assert sum(clock.tick_due(1/60) for _ in range(60)) == 4


@pytest.mark.parametrize("speed", [1, 2, 4])
def test_hitch_never_creates_a_multi_tick_burst_or_future_catch_up_debt(speed):
    clock = RealtimeClock()
    assert clock.tick_due(3.0, speed=speed)
    assert clock.accumulator == 0
    assert not clock.tick_due(0.0, speed=speed)
    assert not clock.tick_due(SECONDS_PER_GAME_TICK/speed/2, speed=speed)


@pytest.mark.parametrize("speed,active", [(1, False), (0, True)])
def test_paused_clock_does_not_bank_time(speed, active):
    clock = RealtimeClock(SECONDS_PER_GAME_TICK/2)
    assert not clock.tick_due(10, speed=speed, active=active)
    assert clock.accumulator == 0
    assert not clock.tick_due(.01)


def test_real_loop_presents_input_before_running_one_tick_and_resets_loaded_fast_forward():
    world = InputWorld()
    world.simulation_speed = 4.0
    order = []
    original_move, original_update = world.handle_player_movement, world.update
    def move(dx, dy):
        order.append("input")
        return original_move(dx, dy)
    def update():
        order.append("tick")
        original_update()
    world.handle_player_movement, world.update = move, update
    context = SimpleNamespace(convert_event=lambda e: e, present=lambda c: order.append("present"))
    with patch("main.tcod.event.get", side_effect=[[down()], [main.tcod.event.Quit()]]), \
            patch("main.time.perf_counter", side_effect=[0.0, 1.0, 1.01, 1.04]), \
            patch("main.time.sleep"), patch("main._ensure_zoom_state"), \
            patch("main._get_camera_origin", return_value=(0, 0)), patch("main.apply_ui_requests"), \
            patch("main.draw", side_effect=lambda *a, **kw: order.append("draw")):
        with pytest.raises(SystemExit):
            main.start_game(context, SimpleNamespace(), world_state=world)
    assert order == ["input", "draw", "present", "tick"]
    assert world.player.x == 1 and world.game_time == 1
    assert world.simulation_speed == 1.0


def test_first_press_is_immediate_and_holding_does_not_wait_for_os_repeat():
    world = InputWorld()
    assert events(world, [down()])
    assert world.player.x == 1 and world.game_time == 0
    assert not main.service_movement_input(world, None)
    world.update()
    assert main.service_movement_input(world, None)
    assert world.player.x == 2
    events(world, [up()])
    world.update()
    assert not main.service_movement_input(world, None)
    assert world.player.x == 2


def test_early_second_tap_is_buffered_once_instead_of_discarded():
    world = InputWorld(cost=2)
    events(world, [down(), up(), down(), up()])
    assert world.player.x == 1
    world.update()
    assert not main.service_movement_input(world, None)
    world.update()
    assert main.service_movement_input(world, None)
    assert world.player.x == 2
    for _ in range(8):
        world.update()
        assert not main.service_movement_input(world, None)


def test_repeat_event_backlog_does_not_make_player_keep_walking_after_release():
    world = InputWorld()
    events(world, [down(), *[down(repeat=True) for _ in range(80)], up()])
    assert world.player.x == 1
    world.update()
    assert not main.service_movement_input(world, None)


@pytest.mark.parametrize("transition", ["focus", "menu", "pause", "interaction"])
def test_stale_controls_are_cleared_when_leaving_world_control(transition):
    world = InputWorld()
    events(world, [down()])
    if transition == "focus":
        events(world, [Mock(spec=main.tcod.event.WindowEvent, type="WindowFocusLost")])
    elif transition == "menu":
        world.game_state = "INVENTORY_MENU"
    elif transition == "pause":
        world.is_paused = True
    else:
        world.interaction_context["active"] = True
    main.service_movement_input(world, None)
    world.game_state, world.is_paused, world.interaction_context["active"] = "PLAYING", False, False
    world.update()
    assert not main.service_movement_input(world, None)
    assert world.player.x == 1


def test_input_state_does_not_restore_held_keys_from_a_save():
    controls = MovementInput()
    controls.press(123)
    assert pickle.loads(pickle.dumps(controls)).next_key() is None


@pytest.mark.parametrize("paused", [False, True])
def test_click_begins_on_the_input_frame_but_respects_pause(paused):
    world = InputWorld()
    world.is_paused = paused
    world.calculate_path = lambda *args: [(0, 0), (1, 0), (2, 0)]
    click = main.tcod.event.MouseButtonDown(position=(10, 10), button=main.tcod.event.MouseButton.LEFT)
    with patch("main.handle_menu_mouse_click", return_value=False), \
            patch("main._get_camera_origin", return_value=(0, 0)), \
            patch("main._screen_to_world_position", return_value=(2, 0)):
        events(world, [click])
    assert world.player.x == (0 if paused else 1)
    assert world.game_time == 0


def test_click_continues_on_first_frame_after_recovery_without_an_extra_tick_wait():
    world = InputWorld()
    world.player.state.current_path = [(1, 0), (2, 0), (3, 0)]
    assert main.service_movement_input(world, None)
    assert world.player.x == 1
    assert not main.service_movement_input(world, None)
    world.update()
    assert main.service_movement_input(world, None)
    assert world.player.x == 2


def test_click_outside_an_open_interaction_menu_does_not_start_walking():
    world = InputWorld()
    world.interaction_context["active"] = True
    world.calculate_path = Mock()
    click = main.tcod.event.MouseButtonDown(position=(10, 10), button=main.tcod.event.MouseButton.LEFT)
    with patch("main.handle_menu_mouse_click", return_value=False):
        events(world, [click])
    world.calculate_path.assert_not_called()


@pytest.mark.parametrize("cost", [1, 2, 4])
def test_click_walk_uses_exactly_the_same_recovery_as_keyboard(cost):
    auto, manual = InputWorld(cost), InputWorld(cost)
    auto.player.state.current_path = [(i, 0) for i in range(1, 12)]
    auto.player.state.move_cooldown = 10  # Obsolete saved UI delay must not linger.
    events(manual, [down()])
    advance_player_auto_movement(auto)
    for _ in range(8):
        auto.update()
        manual.update()
        advance_player_auto_movement(auto)
        main.service_movement_input(manual, None)
    assert auto.moves == manual.moves
    assert auto.player.state.move_ready_tick == manual.player.state.move_ready_tick
    assert auto.player.state.move_cooldown == 0


def brute_pair(world):
    candidates = []
    for speaker in world.village_npcs:
        for listener in world.village_npcs:
            if speaker.id == listener.id:
                continue
            score = ambient_info.score_ambient_conversation_pair(speaker, listener, world)
            if score >= ambient_info.MIN_INITIATION_SCORE:
                score += ambient_info._stable_fraction(f"ambient-init:{world.game_time}:{speaker.id}:{listener.id}")
                candidates.append((score, -speaker.id, -listener.id, speaker, listener))
    best = max(candidates, key=lambda row: row[:3]) if candidates else None
    return (best[3], best[4]) if best else None


def test_spatial_conversation_selection_matches_the_original_exhaustive_rules():
    world = fresh_world(seed=451, pre_simulate=False)
    for offset in range(10):
        world.game_time += 71
        assert ambient_info.choose_ambient_conversation_pair(world) == brute_pair(world)
        for index, npc in enumerate(world.village_npcs):
            npc.x, npc.y = (index % 8)*3 - offset, (index//8)*3
            npc.conversation_cooldown = 5 if index % 7 == offset % 7 else 0


def test_far_apart_people_do_not_trigger_quadratic_social_scoring():
    npcs = [SimpleNamespace(id=i, x=i*20, y=0) for i in range(100)]
    npcs[-1].x = 1
    world = SimpleNamespace(village_npcs=npcs, game_time=0)
    with patch.object(ambient_info, "score_ambient_conversation_pair", return_value=0) as score:
        assert ambient_info.choose_ambient_conversation_pair(world) is None
    assert score.call_count == 2  # Both directions of the only nearby pair.
