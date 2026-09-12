"""Capture the native layered rig, real equipment swaps and simulation-time growth.

Identity/outfit sheets are explicitly controlled fixtures, not village events.
The optional village captures use a disposable seeded world with normal FOV.
No save files or external dialogue services are read/written.
"""

from pathlib import Path
import argparse
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import engine
import main as game
from entities.base import Appearance, NPC
from config import DAY_LENGTH_TICKS
from rendering import character_layers as layers, pixel_scene as pixels
from rendering.console_renderer import draw, draw_inventory_menu
from simulation.systems.appearance import advance_actor_appearance
from tools.capture_ui_font_check import _save
from tools.interior_review import stand_inside
from tools.street_review import stand_outside


def put(console, actor, x, y, direction="south", size=2):
    state = layers.signature(actor)
    source = layers.rig(state, direction)
    sprite = pixels.resize(source, 56 * size, round(source.shape[0] * 56 * size / source.shape[1]))
    pixels.stamp(
        console, sprite, x * 16, y * 16, token=("character-review", state, direction, size)
    )


def text(console, x, y, label):
    console.print(x, y, label, fg=(222, 196, 143))


def sheet(console, title):
    pixels._composites.clear()
    pixels._parts.clear()
    console.clear(bg=(22, 29, 29))
    text(console, 3, 1, title)


def wear(npc, key):
    npc.add_item(key, 1)
    ref = npc.economic.npc_inventory.get_item_reference(key)
    assert npc.equip_item_reference("weapon" if ref.equip_slot == "main_hand" else ref.equip_slot, ref)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="artifacts/dynamic-characters")
    parser.add_argument("--world", action="store_true")
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    engine.ENABLE_LLM_CONNECTION = engine.ENABLE_OLLAMA_CONNECTION = False
    tiles, console = game.load_custom_tileset(), game.create_console()
    assert len(layers._parts) >= 7
    npc = NPC(0, 0, "Elias")
    npc.gender, npc.age = "male", 35
    npc.appearance = Appearance(
        hairstyle="short",
        hair_color="brown",
        facial_hair="short_beard",
        skin_tone="light",
        face_variant=0,
    )
    sheet(console, "IDENTITY FIXTURE / same linen clothes, different people")
    for row, sex in enumerate(("male", "female")):
        npc.gender = sex
        for col in range(4):
            npc.appearance.face_variant = col
            npc.appearance.hairstyle = ("short", "long", "curly", "braided")[col]
            npc.appearance.facial_hair = (
                ("short_beard", "none", "mustache", "full_beard")[col] if sex == "male" else "none"
            )
            npc.appearance.hair_color = ("brown", "red", "black", "gray")[col]
            npc.appearance.skin_tone = ("light", "pale", "dark", "tan")[col]
            put(console, npc, 5 + col * 18, 5 + row * 15, size=2)
            text(console, 5 + col * 18, 14 + row * 15, f"{sex} / face {col+1}")
    _save(console, tiles, str(out / "identity-fixture.png"))
    npc.gender = "male"
    npc.appearance = Appearance(
        hairstyle="short",
        hair_color="brown",
        facial_hair="short_beard",
        skin_tone="light",
        face_variant=0,
    )
    sheet(console, "WARDROBE FIXTURE / one person, actual owned item swaps")
    for col, keys in enumerate(
        (
            (),
            ("wool_shirt", "wool_trousers", "leather_boots", "wool_cap"),
            ("leather_jerkin", "linen_trousers", "leather_shoes", "hooded_cowl"),
            ("iron_breastplate", "wool_trousers", "leather_boots", "iron_helmet"),
        )
    ):
        for slot in ("head", "body", "legs", "feet"):
            npc.unequip_item(slot)
        for key in keys:
            wear(npc, key)
        for row, direction in enumerate(("south", "east", "north", "west")):
            put(console, npc, 5 + col * 18, 4 + row * 9, direction=direction, size=2)
        text(
            console,
            5 + col * 18,
            42,
            ("Underlayer", "Wool + boots", "Jerkin + cowl", "Iron + boots")[col],
        )
    _save(console, tiles, str(out / "wardrobe-fixture.png"))
    sheet(console, "GROWTH FIXTURE / same person at day 0, 2, 7, 21")
    for slot in ("head", "body", "legs", "feet"):
        npc.unequip_item(slot)
    wear(npc, "fur_cloak")
    npc.appearance.facial_hair = "none"
    for col, day in enumerate((0, 2, 7, 21)):
        advance_actor_appearance(npc, day * DAY_LENGTH_TICKS)
        put(console, npc, 5 + col * 18, 7, size=3)
        text(console, 5 + col * 18, 21, f"Day {day}")
        text(console, 5 + col * 18, 23, npc.appearance.facial_hair)
    _save(console, tiles, str(out / "beard-growth-fixture.png"))
    if args.world:
        world = engine.World(seed=123, player_first_name="Mara")
        world._pre_simulate_world()
        world.is_paused = True
        world.mouse_x = world.mouse_y = -1
        world.game_state = "PLAYING"
        game._ensure_zoom_state(world)
        for kind in ("tavern", "house"):
            building = next(b for b in world.buildings_by_id.values() if b.building_type == kind)
            stand_inside(world, building)
            world.zoom_index = 2
            draw(console, world, *game._get_camera_origin(world))
            _save(console, tiles, str(out / f"village-{kind}.png"))
        building = next(b for b in world.buildings_by_id.values() if b.building_type == "tavern")
        stand_outside(world, building)
        draw(console, world, *game._get_camera_origin(world))
        _save(console, tiles, str(out / "village-street.png"))
        for key in ("wool_shirt", "wool_cap", "linen_trousers", "leather_boots", "knife_stone"):
            world.player.add_item(key, 1)
            if key != "knife_stone":
                world.use_item(key)
        world.game_state = "INVENTORY_MENU"
        draw(console, world, *game._get_camera_origin(world))
        _save(console, tiles, str(out / "inventory-wardrobe.png"))
    print(f"Native character captures: {out.resolve()}")


if __name__ == "__main__":
    main()
