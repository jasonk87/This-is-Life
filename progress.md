Original prompt: how can we make this game visually better? Right now it is just hard to tell even what is going on

- Read the renderer and layout constants to identify why the screen felt flat and hard to parse.
- Added a readability-first visual pass in `rendering/console_renderer.py`.
- Terrain now gets background tinting so biomes, interiors, roads, and water separate immediately.
- The right panel now acts like a field guide with scene context, vitals, nearby entities, reputation, and a small legend.
- Player and entities now have stronger contrast, and the nearest visible entities get short name labels.
- Added a top-left HUD line and made the log frame visually distinct from the playfield.
- Follow-up pass expanded this into a fuller readability overhaul:
- Added a minimap panel, focus-target detection, pulsing focus badges, and animated terrain color shifts.
- Simplified the panel language so it shows scene/focus/objective/nearby state with less clutter.
- Color-coded log messages by event type to make important moments easier to scan.
- Latest pass added faux tileset glyph overrides, distance-based lighting/depth shading, and on-map NPC/world markers.
- NPCs now advertise hostility, quests, traders, and civic roles directly over the map.
- Nearby loot, doors, wells, and farmland now get lightweight world markers.

TODO:
- Run the game and tune colors against the real tileset if any combinations feel too loud.
- Replace the old non-ASCII path marker with an ASCII-safe marker if that glyph still renders badly in-game.
