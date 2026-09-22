"""CPU frame/tick measurements with the real renderer and generated world.

This measures console drawing, not GPU presentation or physical-key latency.
It deliberately loads the same art pipeline as main.start_game.
"""
import argparse
import cProfile
import json
from pathlib import Path
import pstats
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine
import main


def stats(values):
    ordered = sorted(values)
    return dict(median_ms=round(statistics.median(values)*1000, 2),
                p95_ms=round(ordered[min(len(ordered)-1, int(len(ordered)*.95))]*1000, 2),
                max_ms=round(max(values)*1000, 2))


def run(frames, output):
    engine.ENABLE_LLM_CONNECTION = engine.ENABLE_OLLAMA_CONNECTION = False
    world = engine.World(seed=451, player_first_name="Walker")
    world._pre_simulate_world()
    main._ensure_zoom_state(world)
    tileset = main.load_custom_tileset()
    console = main.create_console()
    ticks, draws = [], []
    profile = cProfile.Profile()
    for frame in range(frames + 5):
        start = time.perf_counter()
        world.update()
        tick_elapsed = time.perf_counter() - start
        world.update_animations(1/30)
        start = time.perf_counter()
        main.draw(console, world, *main._get_camera_origin(world))
        draw_elapsed = time.perf_counter() - start
        if frame >= 5:
            ticks.append(tick_elapsed)
            draws.append(draw_elapsed)
    profile.enable()
    for _ in range(10):
        world.update()
        world.update_animations(1/30)
        main.draw(console, world, *main._get_camera_origin(world))
    profile.disable()
    output.parent.mkdir(parents=True, exist_ok=True)
    profile.dump_stats(str(output.with_suffix(".prof")))
    result = dict(frames=frames, seed=451, zoom=main._get_zoom(world),
                  villagers=len(world.village_npcs), tick=stats(ticks), draw=stats(draws),
                  seconds_per_tick=main.SECONDS_PER_GAME_TICK,
                  cpu_only=True, tileset_loaded=tileset is not None)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
    pstats.Stats(profile).strip_dirs().sort_stats("cumulative").print_stats(25)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.frames, args.output)
