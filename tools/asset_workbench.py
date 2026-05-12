#!/usr/bin/env python3
"""Headless DawnLike asset preview utility for sandbox visual inspection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data.construction import CONSTRUCTION_RECIPES  # noqa: E402
from simulation.animation_cues import get_cue

from data.dawnlike import (  # noqa: E402
    ANIMAL_SPRITES,
    HUMAN_SPRITES,
    ITEM_SPRITES,
    PROFESSION_SPRITES,
    WORLD_DECORATION_SPRITES,
    WORLD_TILE_SPRITES,
    get_human_sprite,
)
from tools.simulation_snapshot import SnapshotCanvas, _asset_color, write_canvas_png  # noqa: E402


PREVIEW_SCALE_CELLS = 16


def _default_output(kind: str, key: str) -> Path:
    safe_key = key.strip().lower().replace(" ", "_") or "preview"
    return Path("out") / "asset_previews" / f"{kind}_{safe_key}.png"


def _draw_center_tile(canvas: SnapshotCanvas, char: str, color: tuple[int, int, int], *, badge: str | None = None) -> None:
    cx = canvas.width // 2
    cy = canvas.height // 2
    canvas.rect(cx - 2, cy - 2, 5, 5, char, color)
    if badge:
        canvas.set(cx + 4, cy - 2, badge[:1], (245, 245, 245))


def preview_character(gender: str, profession: str, output: str | None = None, *, child: bool = False) -> dict:
    output_path = Path(output) if output else _default_output("character", f"{gender}_{profession}")
    age = 10 if child else 30
    body_key = f"{gender}_child" if child else f"{gender}_commoner"
    body_sprite = HUMAN_SPRITES.get(body_key) or get_human_sprite(gender=gender, age=age)
    profession_sprite = PROFESSION_SPRITES.get(profession)
    canvas = SnapshotCanvas(PREVIEW_SCALE_CELLS, PREVIEW_SCALE_CELLS)
    _draw_center_tile(canvas, "N", _asset_color(profession_sprite or body_sprite), badge=(profession[:1] or "?"))
    if profession_sprite and profession_sprite != body_sprite:
        canvas.set(canvas.width // 2 - 3, canvas.height // 2 + 3, "p", _asset_color(profession_sprite))
    write_canvas_png(output_path, canvas)
    return {
        "preview": "character",
        "output": str(output_path),
        "gender": gender,
        "profession": profession,
        "asset_keys": {
            "body": body_key,
            "profession": profession if profession_sprite else None,
        },
        "codepoints": {
            "body": body_sprite,
            "profession": profession_sprite,
        },
        "notes": "Uses whole-body profession sprite when available plus compact badge; no layered composition is attempted.",
    }


def preview_animal(animal: str, output: str | None = None) -> dict:
    output_path = Path(output) if output else _default_output("animal", animal)
    sprite = ANIMAL_SPRITES.get(animal)
    canvas = SnapshotCanvas(PREVIEW_SCALE_CELLS, PREVIEW_SCALE_CELLS)
    _draw_center_tile(canvas, "W", _asset_color(sprite, fallback=(170, 70, 210)), badge=(animal[:1] or "?"))
    write_canvas_png(output_path, canvas)
    return {
        "preview": "animal",
        "output": str(output_path),
        "animal": animal,
        "asset_keys": {"animal": animal if sprite else None},
        "codepoints": {"animal": sprite},
        "missing_assets": [] if sprite else [animal],
    }


def preview_blueprint(recipe_key: str, output: str | None = None) -> dict:
    output_path = Path(output) if output else _default_output("blueprint", recipe_key)
    recipe = CONSTRUCTION_RECIPES.get(recipe_key, {})
    width = int(recipe.get("width", 8))
    height = int(recipe.get("height", 6))
    canvas = SnapshotCanvas(max(PREVIEW_SCALE_CELLS, width + 6), max(PREVIEW_SCALE_CELLS, height + 6))
    start_x = (canvas.width - width) // 2
    start_y = (canvas.height - height) // 2
    materials = dict(recipe.get("materials", {}))
    material_key = next(iter(materials), "raw_log")
    canvas.rect(start_x, start_y, width, height, "C", _asset_color(ITEM_SPRITES.get(material_key)))
    for tx in range(start_x, start_x + width):
        canvas.set(tx, start_y, "C", (245, 220, 75))
        canvas.set(tx, start_y + height - 1, "C", (245, 220, 75))
    for ty in range(start_y, start_y + height):
        canvas.set(start_x, ty, "C", (245, 220, 75))
        canvas.set(start_x + width - 1, ty, "C", (245, 220, 75))
    canvas.set(start_x + width // 2, start_y + height - 1, "+", _asset_color(WORLD_DECORATION_SPRITES.get("wooden_door_closed")))
    canvas.set(start_x + 1, start_y + 1, "a", (90, 220, 240))
    write_canvas_png(output_path, canvas)
    return {
        "preview": "blueprint",
        "output": str(output_path),
        "blueprint": recipe_key,
        "dimensions": {"width": width, "height": height},
        "materials": materials,
        "asset_keys": {
            "primary_material": material_key if material_key in ITEM_SPRITES else None,
            "wall": "wood_wall" if "wood_wall" in WORLD_TILE_SPRITES else None,
            "door": "wooden_door_closed",
            "interaction_anchor": "a",
        },
        "missing_assets": [] if recipe else [recipe_key],
    }



def preview_animation(cue_id: str, output: str | None = None) -> dict:
    output_path = Path(output) if output else _default_output("animation", cue_id)
    cue = get_cue(cue_id)
    if not cue:
        return {
            "preview": "animation",
            "output": str(output_path),
            "cue_id": cue_id,
            "error": "Cue not found",
            "missing_assets": [cue_id],
        }

    # Render a simple strip: actor and target next to each other
    # For a strip, we'll draw frames horizontally
    cell_width = 5
    cell_height = 5
    padding = 2
    canvas = SnapshotCanvas((cell_width + padding) * cue.frame_count, cell_height + padding)

    for i, frame in enumerate(cue.frames):
        cx = (i * (cell_width + padding)) + cell_width // 2
        cy = canvas.height // 2

        # Draw Target (always at cx+1)
        tx = cx + 1 + frame.target_offset[0]
        ty = cy + frame.target_offset[1]

        target_char = "T"
        target_color = (150, 150, 150)

        if frame.target_state == "open":
            target_char = "_"
        elif frame.target_state == "stump":
            target_char = "."

        canvas.set(tx, ty, target_char, target_color)

        if frame.target_overlay:
            canvas.set(tx, ty - 1, frame.target_overlay, (255, 0, 0))

        # Draw Actor (always at cx-1)
        ax = cx - 1 + frame.actor_offset[0]
        ay = cy + frame.actor_offset[1]

        canvas.set(ax, ay, "N", (0, 255, 0))

        if frame.actor_overlay:
            canvas.set(ax, ay - 1, frame.actor_overlay, (255, 255, 0))

    write_canvas_png(output_path, canvas)

    return {
        "preview": "animation",
        "output": str(output_path),
        "cue_id": cue_id,
        "frame_count": cue.frame_count,
        "impact_frame": cue.impact_frame,
        "state_change_frame": cue.state_change_frame,
        "asset_keys": {"cue": cue_id},
        "missing_assets": [],
    }

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export simple headless asset previews for sandbox inspection.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview-character", action="store_true", help="Preview a human/NPC readability tile.")
    mode.add_argument("--preview-blueprint", help="Preview a construction blueprint footprint.")
    mode.add_argument("--preview-animal", help="Preview an animal tile.")
    mode.add_argument("--preview-animation", help="Preview an animation cue frame strip.")
    parser.add_argument("--gender", default="male", choices=["male", "female"], help="Character body gender cue.")
    parser.add_argument("--profession", default="Villager", help="Character profession badge/sprite cue.")
    parser.add_argument("--child", action="store_true", help="Use child body cue for character previews.")
    parser.add_argument("--output", help="PNG output path. Defaults to out/asset_previews/...")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.preview_character:
        summary = preview_character(args.gender, args.profession, args.output, child=args.child)
    elif args.preview_blueprint:
        summary = preview_blueprint(args.preview_blueprint, args.output)
    elif args.preview_animation:
        summary = preview_animation(args.preview_animation, args.output)
    else:
        summary = preview_animal(args.preview_animal, args.output)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
