"""Offline UI font-check capture harness (capture-only; no game source modified).

Replicates the game's boot + per-frame draw path (main.py) and renders each
UI surface to a PNG directly via tcod's tileset.render() -> Image.save_as(),
so no window, screen capture, or input simulation is needed. This is how the
SDS_8x8 DawnLike UI font verification screenshots are produced deterministically.

Surfaces captured:
  1. main-game-view   - world + sidebar/log/top bar (draw() with PLAYING state)
  2. dialogue-window  - dialogue overlay over the world
  3. main-menu        - title screen (New Game / Load Game / Exit)
  4. character-create - new-player name prompt screen
"""
from __future__ import annotations

import os
import sys

# Allow running as `python tools/capture_ui_font_check.py` from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tcod
import tcod.image
from tcod import libtcodpy

from config import SCREEN_WIDTH_TILES, SCREEN_HEIGHT_TILES
from engine import World
from main import (
    _ensure_zoom_state,
    _get_camera_origin,
    draw_main_menu,
    load_custom_tileset,
    normalize_player_first_name,
)
from rendering.console_renderer import draw


def _save(console: tcod.console.Console, tileset: tcod.tileset.Tileset, path: str) -> int:
    """Render console to a PNG at path. Returns the file size in bytes."""
    console.tileset = tileset
    pixels = tileset.render(console)  # RGBA (H, W, 4)
    if pixels.shape[2] == 4:
        # tcod.image.Image.from_array expects RGB in this version.
        pixels = pixels[:, :, :3].copy()
    image = tcod.image.Image.from_array(pixels)
    image.save_as(path)
    return os.path.getsize(path)


def _new_console() -> tcod.console.Console:
    return tcod.console.Console(SCREEN_WIDTH_TILES, SCREEN_HEIGHT_TILES, order="C")


def capture_main_menu(console, tileset, out_dir: str) -> str:
    console.clear()
    options = ["New Game", "Load Game", "Exit"]
    draw_main_menu(console, options, selected_index=0)
    path = os.path.join(out_dir, "ui-font-check-main-menu.png")
    size = _save(console, tileset, path)
    print(f"[menu] {path} ({size} bytes)")
    return path


def capture_character_create(console, tileset, out_dir: str) -> str:
    """Replicate prompt_for_new_player_name's name-entry screen (main.py:84-159)."""
    console.clear()
    cx = console.width // 2
    cy = console.height // 3
    console.print(cx, cy, "NEW CHARACTER", alignment=libtcodpy.CENTER, fg=(255, 255, 0))
    console.print(cx, cy + console.height // 6, "Enter your first name", alignment=libtcodpy.CENTER)
    console.print(cx, cy + console.height // 3 + 1, "Mara", alignment=libtcodpy.CENTER, fg=(255, 255, 255))
    console.print(cx, cy + console.height // 3 + 4, "Last name is chosen by your in-game family.",
                  alignment=libtcodpy.CENTER, fg=(160, 160, 160))
    console.print(cx, console.height - 4, "Enter = start   Esc = cancel", alignment=libtcodpy.CENTER,
                  fg=(160, 160, 160))
    path = os.path.join(out_dir, "ui-font-check-character-create.png")
    size = _save(console, tileset, path)
    print(f"[char] {path} ({size} bytes)")
    return path


def capture_main_game_view(console, tileset, out_dir: str) -> tuple[str, World]:
    console.clear()
    world = World(player_first_name=normalize_player_first_name("Mara"))
    world._pre_simulate_world()
    _ensure_zoom_state(world)
    camera_x, camera_y = _get_camera_origin(world)
    draw(console, world, camera_x, camera_y, menu_fade_ratio=1.0)
    path = os.path.join(out_dir, "ui-font-check-main-game-view.png")
    size = _save(console, tileset, path)
    print(f"[game] {path} ({size} bytes)")
    return path, world


def capture_dialogue_window(console, tileset, out_dir: str, world: World) -> str:
    # Find an NPC to talk to so the portrait + dialogue panel render.
    npc = None
    npcs = getattr(world, "all_npcs", None)
    if npcs is not None:
        for candidate in npcs:
            if getattr(candidate, "name", None):
                npc = candidate
                break
    if npc is None:
        population = getattr(world, "population", None)
        if population:
            npc = population[0]
    if npc is None:
        print("[dialogue] no NPC available; skipping portrait, drawing bare dialogue panel")
    world.chat_ui_active = True
    world.chat_ui_target_npc = npc
    world.chat_ui_history = [
        ("Mara", "Hello! What brings you to this town?"),
        (getattr(npc, "name", "Stranger") if npc else "Stranger",
         "I've lived here for years. The mines keep us fed."),
        ("Mara", "The mines? Are they safe?"),
        (getattr(npc, "name", "Stranger") if npc else "Stranger",
         "Safe enough, if you mind the cave spiders."),
    ]
    world.chat_ui_input_line = "Tell me more about the mines"
    _ensure_zoom_state(world)
    camera_x, camera_y = _get_camera_origin(world)
    console.clear()
    draw(console, world, camera_x, camera_y, menu_fade_ratio=1.0)
    path = os.path.join(out_dir, "ui-font-check-dialogue-window.png")
    size = _save(console, tileset, path)
    print(f"[dialogue] {path} ({size} bytes)")
    return path


def main() -> None:
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts")
    os.makedirs(out_dir, exist_ok=True)

    tileset = load_custom_tileset()
    console = _new_console()

    capture_main_menu(console, tileset, out_dir)
    capture_character_create(console, tileset, out_dir)
    _, world = capture_main_game_view(console, tileset, out_dir)
    capture_dialogue_window(console, tileset, out_dir, world)

    print("Done. All PNGs written to:", out_dir)


if __name__ == "__main__":
    main()
