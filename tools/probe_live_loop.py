"""Exercise start_game with real art/SDL presentation and synthetic key events.

The diagnostic window is hidden. This is not a human playtest or a hardware
keyboard latency measurement. No map edits, teleports or special loadout.
"""
import argparse
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine
import main


def run(frames, output):
    engine.ENABLE_LLM_CONNECTION = engine.ENABLE_OLLAMA_CONNECTION = False
    world = engine.World(seed=451, player_first_name="Walker")
    world._pre_simulate_world()
    main._ensure_zoom_state(world)
    tileset, console = main.load_custom_tileset(), main.create_console()
    keys = main.tcod.event.KeySym
    directions = [(keys.RIGHT, keys.LEFT, 1, 0), (keys.LEFT, keys.RIGHT, -1, 0),
                  (keys.DOWN, keys.UP, 0, 1), (keys.UP, keys.DOWN, 0, -1)]
    forward, backward, dx, dy = next(row for row in directions
        if (tile := world.get_tile_at(world.player.x+row[2], world.player.y+row[3])) and tile.passable)
    frame, ticks_this_frame, maximum_batch = 0, 0, 0
    receipts, frame_times = [], []
    key_time = None
    previous_present = None
    tick_start = world.game_time
    original_move, original_update = world.handle_player_movement, world.update

    def move(x, y):
        result = original_move(x, y)
        if result > 0 and key_time is not None:
            receipts.append(dict(key_time=key_time, move_time=time.perf_counter(), tick=world.game_time))
        return result

    def update():
        nonlocal ticks_this_frame
        ticks_this_frame += 1
        original_update()

    def events():
        nonlocal key_time
        key_time = None
        if frame >= frames:
            return [main.tcod.event.Quit()]
        if frame in (1, 20, 40, 60):
            key_time = time.perf_counter()
            key = forward if frame in (1, 40) else backward
            return [main.tcod.event.KeyDown(scancode=0, sym=key, mod=0, repeat=False)]
        if frame in (8, 27, 47, 67):
            key = forward if frame in (8, 47) else backward
            return [main.tcod.event.KeyUp(scancode=0, sym=key, mod=0)]
        return []

    with main.tcod.context.new(console=console, tileset=tileset, vsync=False,
            sdl_window_flags=main.tcod.context.SDL_WINDOW_HIDDEN, title="This Is Life timing check", argv=[]) as native:
        main.draw(console, world, *main._get_camera_origin(world))
        native.present(console)  # Warm atlas upload; report gameplay, not startup.

        class Context:
            convert_event = native.convert_event

            def present(self, canvas):
                nonlocal frame, ticks_this_frame, maximum_batch, previous_present
                native.present(canvas)
                now = time.perf_counter()
                for receipt in receipts:
                    if "present_time" not in receipt:
                        receipt["present_time"] = now
                        receipt["input_to_present_ms"] = round((now-receipt["key_time"])*1000, 2)
                if previous_present is not None:
                    frame_times.append((now-previous_present)*1000)
                previous_present = now
                maximum_batch = max(maximum_batch, ticks_this_frame)
                ticks_this_frame = 0
                frame += 1

        world.handle_player_movement, world.update = move, update
        with patch("main.tcod.event.get", side_effect=events):
            try:
                main.start_game(Context(), console, world_state=world)
            except SystemExit:
                pass
    ordered = sorted(frame_times)
    result = dict(frames=frame, world_ticks=world.game_time-tick_start,
        max_ticks_between_presentations=maximum_batch,
        frame_median_ms=round(ordered[len(ordered)//2], 2),
        frame_p95_ms=round(ordered[min(len(ordered)-1, int(len(ordered)*.95))], 2),
        input_to_present_ms=[r["input_to_present_ms"] for r in receipts],
        living_villagers=sum(not n.physical.is_dead for n in world.village_npcs),
        hidden_sdl=True, synthetic_events=True, no_map_edits=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
    assert maximum_batch <= 1
    assert len(receipts) >= 2, "Did not observe enough actual player movements"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=90)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.frames, args.output)
