"""Small procedural pixel surfaces in the DawnLike palette.

These replace console punctuation with actual 16px materials at every zoom.
All texture noise uses a private seeded RNG; drawing cannot consume simulation
randomness or affect outcomes. Objects and actors keep the original artwork.
"""
import random

from runtime_compat import np
from rendering import sprite_atlas

BASE = 0x100000
VARIANTS = 4
MATERIALS = {
    "plains": (40, 65, 39),
    "road": (99, 84, 62),
    "wood_floor": (103, 73, 48),
    "stone_floor": (74, 80, 78),
    "brick_floor": (101, 70, 52),
    "dirt_floor": (73, 58, 41),
    "water": (31, 74, 94),
    "deep_water": (21, 47, 69),
    "snow": (166, 180, 177),
    "tilled_soil": (77, 53, 37),
    "mountain": (90, 97, 92),
    "mossy_cobblestone": (67, 79, 60),
    "wood_wall": (110, 77, 48),
    "log_wall": (96, 67, 42),
    "plaster_wall": (165, 155, 123),
    "wheat_plant_growing": (77, 53, 37),
    "wheat_plant": (77, 53, 37),
}
GROUND_UNDER_OBJECT = {"forest": "plains", "tall_grass": "plains", "flower": "plains"}
_registered = False


def terrain_codepoint(key, x, y):
    if not _registered:
        return None
    material = GROUND_UNDER_OBJECT.get(key, key)
    if material not in MATERIALS:
        return None
    variant = ((int(x) * 73856093) ^ (int(y) * 19349663)) % VARIANTS
    return BASE + list(MATERIALS).index(material) * VARIANTS + variant


def _surface(material, variant):
    base = np.array(MATERIALS[material], dtype=np.int16)
    pixels = np.empty((16, 16, 4), dtype=np.uint8)
    pixels[:, :, :3] = base
    pixels[:, :, 3] = 255
    rng = random.Random(f"this-is-life:{material}:{variant}")

    def ink(x, y, delta, width=1, height=1):
        pixels[y:min(16,y+height), x:min(16,x+width), :3] = np.clip(base + delta, 0, 255)

    # Fine variation, not a new random texture each frame.
    for _ in range(24):
        ink(rng.randrange(16), rng.randrange(16), rng.choice((-5, -3, 3, 5)))
    if material in ("wood_wall", "log_wall", "plaster_wall"):
        for y in (0, 7, 14):
            ink(0,y,-24,16,2)
            if y < 14:
                ink(1,y+2,14,14)
        if material != "log_wall":
            ink(0,0,-32,2,16)
            ink(14,0,-32,2,16)
            ink(2,2,8,1,12)
    elif material in ("wheat_plant", "wheat_plant_growing"):
        stalk = (196,162,72) if material == "wheat_plant" else (107,143,69)
        for x,y in ((3,3),(8,1),(13,4)):
            pixels[y+2:14,x,:3] = stalk
            for yy in (y,y+2,y+4):
                pixels[yy:yy+2,x-1:x+2,:3] = stalk
            pixels[14,x-1:x+2,:3] = np.clip(base-16,0,255)
    elif material == "wood_floor":
        for y in (0, 5, 10, 15):
            ink(0, y, -22, 16)
            if y < 15:
                ink(0, y+1, 8, 16)
                joint = (variant * 5 + y * 3) % 16
                ink(joint, y+1, -18, 1, 4)
                ink((joint+3)%16, y+3, -6, 5)
    elif material in ("stone_floor", "brick_floor", "mossy_cobblestone"):
        stride = 4 if material == "brick_floor" else 8
        for y in range(0, 16, stride):
            ink(0, y, -21, 16)
            for x in range((y//stride % 2)*4, 16, 8):
                ink(x, y, -21, 1, stride)
                ink(x+1, y+1, 8, min(6,15-x))
    elif material in ("water", "deep_water"):
        for y in (3, 10):
            x = (variant * 3 + y) % 10
            ink(x, y, 16, 4)
            ink(x+3, y-1, 9, 2)
    elif material == "plains":
        for _ in range(7):
            x, y = rng.randrange(14), rng.randrange(2, 15)
            ink(x, y, 9, 2)
            ink(x+1, y-1, 14)
    elif material == "tilled_soil":
        for y in range(1, 16, 4):
            ink(0, y, -15, 16)
            ink(0, y+1, 10, 16)
    elif material == "mountain":
        for y in (3, 9, 14):
            x = rng.randrange(8)
            ink(x, y, -19, 7)
            ink(x+1, y-1, 13, 5)
    else:
        for _ in range(5):
            ink(rng.randrange(15), rng.randrange(15), 13, 2)
    return pixels


def register_terrain_tiles(tileset):
    global _registered
    split_cp = BASE + 0x1000
    for index, material in enumerate(MATERIALS):
        for variant in range(VARIANTS):
            cp = BASE + index * VARIANTS + variant
            pixels = _surface(material, variant)
            split_cp = sprite_atlas.register_pixel_sprite(tileset, cp, pixels, split_cp)
    _registered = True
