import tcod.tileset
try:
    tileset = tcod.tileset.load_tilesheet("assets/roguelike_sheet.png", 64, 64, tcod.tileset.CHARMAP_TCOD)
except Exception as e:
    print(f"Failed to load roguelike_sheet: {e}")
