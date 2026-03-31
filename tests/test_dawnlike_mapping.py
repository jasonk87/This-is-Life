from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from data.animals import ANIMAL_DEFINITIONS
from data.dawnlike import all_catalog_codepoints, get_entity_sprite
from data.decorations import DECORATION_ITEM_DEFINITIONS
from data.environment import WEATHER_DEFINITIONS
from data.items import ITEM_DEFINITIONS
from data.tiles import TILE_DEFINITIONS


ASSET_PATH = Path(__file__).resolve().parents[1] / "assets" / "dawnlike_combined.png"
TILE_SIZE = 16
TILES_PER_ROW = 16


def _is_non_empty_sprite(codepoint: int, sheet: Image.Image) -> bool:
    offset = codepoint - 0xE000
    col = offset % TILES_PER_ROW
    row = offset // TILES_PER_ROW
    tile = sheet.crop(
        (
            col * TILE_SIZE,
            row * TILE_SIZE,
            (col + 1) * TILE_SIZE,
            (row + 1) * TILE_SIZE,
        )
    )
    return tile.getbbox() is not None


def test_world_tiles_use_non_empty_dawnlike_sprites():
    with Image.open(ASSET_PATH).convert("RGBA") as sheet:
        keys = [
            "plains",
            "forest",
            "road",
            "wood_wall",
            "stone_wall",
            "door",
            "window",
            "water",
            "deep_water",
            "mountain",
            "snow",
            "tall_grass",
            "flower",
            "well",
            "tilled_soil",
            "fire_trap_hidden",
        ]
        for key in keys:
            assert _is_non_empty_sprite(TILE_DEFINITIONS[key]["char"], sheet), key


def test_world_decorations_use_non_empty_dawnlike_sprites():
    with Image.open(ASSET_PATH).convert("RGBA") as sheet:
        keys = [
            "wooden_door_closed",
            "wooden_door_open",
            "chest_wooden",
            "bed_simple",
            "wooden_chair",
            "smoking_rack",
            "wooden_table",
            "wall_shelf",
            "fire_pit_simple",
            "rubble",
            "bones",
            "bookshelf",
            "corpse_humanoid",
            "corpse_animal",
            "thicket",
        ]
        for key in keys:
            assert _is_non_empty_sprite(DECORATION_ITEM_DEFINITIONS[key]["char"], sheet), key


def test_distinct_furniture_role_sprites():
    """Verify that different furniture roles map to distinct sprites, preventing visual collisions."""
    from data.items import ITEM_DEFINITIONS

    # Furniture roles that should be visually distinct
    distinct_roles = ["bed_simple", "wooden_table", "desk", "counter", "workbench", "chest_wooden"]

    seen_sprites = set()
    for role in distinct_roles:
        # Check that the role exists and has a char
        assert role in ITEM_DEFINITIONS, f"Role {role} missing from ITEM_DEFINITIONS"
        sprite_char = ITEM_DEFINITIONS[role]["char"]
        assert sprite_char not in seen_sprites, f"Role '{role}' shares a sprite ({sprite_char}) with another distinct role"
        seen_sprites.add(sprite_char)


def test_animals_and_items_use_non_empty_dawnlike_sprites():
    with Image.open(ASSET_PATH).convert("RGBA") as sheet:
        animal_keys = [
            "deer",
            "bear",
            "fish",
            "wolf",
            "dire_wolf",
            "sheep",
            "fox",
            "boar",
            "salmon",
            "trout",
            "rabbit",
            "bison",
            "badger",
        ]
        for key in animal_keys:
            assert _is_non_empty_sprite(ANIMAL_DEFINITIONS[key]["char"], sheet), key

        item_keys = [
            "raw_log",
            "stone_chunk",
            "medicinal_herb",
            "wheat",
            "bread",
            "wooden_plank",
            "axe_stone",
            "healing_salve",
            "torch_lit",
            "apple",
            "pear",
            "raw_meat",
            "rotten_food",
            "rusty_sword",
            "short_bow",
            "stone_pickaxe",
            "cloth",
            "fishing_rod",
            "raw_fish",
            "book_census",
        ]
        for key in item_keys:
            assert _is_non_empty_sprite(ITEM_DEFINITIONS[key]["char"], sheet), key

        weather_keys = ["clear", "rain", "snow"]
        for key in weather_keys:
            assert _is_non_empty_sprite(WEATHER_DEFINITIONS[key]["char"], sheet), key


def test_named_catalog_entries_are_non_empty():
    with Image.open(ASSET_PATH).convert("RGBA") as sheet:
        for key, codepoint in all_catalog_codepoints().items():
            assert _is_non_empty_sprite(codepoint, sheet), key


def test_entity_sprite_selector_covers_humans_animals_and_player():
    with Image.open(ASSET_PATH).convert("RGBA") as sheet:
        entities = [
            SimpleNamespace(name="Player"),
            SimpleNamespace(
                name="Guard",
                age=32,
                gender="male",
                economic=SimpleNamespace(profession="Guard"),
                schedule=SimpleNamespace(current_task="idle"),
            ),
            SimpleNamespace(
                name="Sister",
                age=14,
                gender="female",
                economic=SimpleNamespace(profession="Unemployed"),
                schedule=SimpleNamespace(current_task="sleeping"),
            ),
            SimpleNamespace(
                name="Wolf",
                animal_type="wolf",
                economic=SimpleNamespace(profession="Creature"),
            ),
            SimpleNamespace(
                name="Player",
                state=SimpleNamespace(is_sitting=True),
            ),
        ]
        for entity in entities:
            assert _is_non_empty_sprite(get_entity_sprite(entity), sheet), entity.name
