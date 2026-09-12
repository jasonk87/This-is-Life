# Visual direction

The simulation remains deep. Presentation should make its existing state and
causality easier to read, without inventing NPC motives or revealing information
the player has not observed.

## Style

- Keep the established dark/gold interface. The subsequent [world-art pass](world-art-pass.md)
  adds 32px-normalized people, larger trees and footprint-aware architecture;
  DawnLike furniture and items remain in use.
- Use crisp integer scaling (1x–4x); never blur sprites or substitute repeated
  punctuation for enlarged grass, floors, walls, crops or water.
- Charcoal-green panels, warm ivory text, muted gold focus, and consistent thin
  borders. Semantic colors and item-quality colors retain their meanings.
- Native procedural material textures use private seeded randomness. Rendering
  must never advance simulation randomness. No new third-party assets or
  purchases are required for this pass.

## Interaction

- Health, hunger and thirst remain pinned while longer field-guide observations,
  quests and reputation scroll beneath them. The atlas has a reserved region.
- Hover observations use the existing sensory descriptions and remain readable
  while moving the pointer into the sidebar to scroll.
- Toolbar clicks call the existing keyboard commands. Wheel input belongs to
  the sidebar, log or active menu before it can change map zoom.
- Inventory selection has its own background; quality colors stay visible.
  Right-click selects without using. Left-click/Enter use through the existing
  inventory handler. Category headers never trigger an item action.
- Crafting reads the real item definitions, including resources and workstations.
  Recipe details and construction details fit beside their lists on the map side.
- Weather is drawn beneath actors and interface layers. Dialogue input stays
  inside its panel and history can scroll.

## Review and testing

Run from the project root:

```powershell
python tools/visual_review.py --output artifacts/visual-review
python tools/visual_review.py --smoke
python tools/visual_review.py --live
python -m pytest tests/test_visual_refresh.py tests/test_ui.py tests/test_ui_polish.py tests/test_player_ui.py tests/test_inventory_use.py tests/test_look_mode.py tests/test_camera.py tests/test_seasonal_colour.py tests/test_appearance_overlays.py tests/test_render_stress.py -q
```

The preview creates a disposable seeded world, disables remote dialogue, and
never loads or writes saves. `--smoke` opens the real tcod renderer briefly;
`--live` stays playable until closed. PNG captures use the actual console and
tileset, not mockups. Fixtures populate an inventory and a conversation solely
to exercise those screens. Generated captures are ignored by Git.

This document describes the UI foundation. The next world-art pass is documented
in [world-art-pass.md](world-art-pass.md), including its limits and verification.
Additional packs should match the pixel scale, palette and perspective and have
their licenses checked before inclusion.
