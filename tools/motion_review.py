"""Capture native-renderer animation fixtures, explicitly not recorded village events."""

from pathlib import Path
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as game
from rendering import people_art as people, pixel_scene as pixels
from tools.street_review import activity_actor
from tools.capture_ui_font_check import _save


def draw_fixture(console, kind, direction, phase, col, row, gender="male"):
    world, actor = activity_actor(kind)
    world.game_time = phase * 2
    actor.gender = gender
    vectors = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}
    dx, dy = vectors[direction]
    actor.state = NS(last_dx=dx, last_dy=dy)
    if kind in {"walk", "carry"}:
        actor.render_x, actor.render_y = actor.x - dx * 0.5, actor.y - dy * 0.5
    if kind in {"chop", "hammer"}:
        world.interaction_resolver.active_interactions["work"].target_pos = (dx, dy)
    people.draw_person(console, world, actor, 0, 0, col / 3, row / 3)


def main():
    from PIL import Image

    out = Path("artifacts/interiors-final")
    out.mkdir(parents=True, exist_ok=True)
    console, tiles = game.create_console(), game.load_custom_tileset()
    frames = []
    for phase in range(16):
        console.clear(bg=(24, 33, 29))
        pixels.begin_frame()
        console.print(3, 1, "DIRECTION + ACTIVITY / NATIVE RENDER FIXTURES", fg=(230, 211, 160))
        console.print(
            3, 2, "Explicit test states, not recorded village events.", fg=(151, 170, 160)
        )
        for column, direction in enumerate(("north", "east", "south", "west")):
            col = 13 + column * 17
            console.print(col - 2, 4, direction.upper(), fg=(220, 192, 127))
            for row, (kind, gender) in enumerate(
                (
                    ("idle", "female"),
                    ("walk", "male"),
                    ("carry", "female"),
                    ("hammer", "male"),
                    ("talk", "female"),
                )
            ):
                top = 8 + row * 8
                if column == 0:
                    console.print(2, top, kind.upper(), fg=(173, 182, 155))
                draw_fixture(console, kind, direction, phase, col, top, gender)
        if phase < 4:
            _save(console, tiles, str(out / f"motion-phase-{phase}.png"))
        frames.append(Image.fromarray(tiles.render(console)))
    frames[0].save(
        out / "motion-preview.gif",
        save_all=True,
        append_images=frames[1:],
        duration=200,
        loop=0,
        disposal=2,
    )
    print(f"Captured four stills + 16 timed renderer frames to {out.resolve()}")


if __name__ == "__main__":
    main()
