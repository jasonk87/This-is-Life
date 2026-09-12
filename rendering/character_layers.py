"""Modular people: identity + actual equipment, never a profession costume.

Parts follow a shared joint rig at runtime. Original PNGs are untouched.
The state signature includes every visible choice so live changes invalidate
the cached composite immediately, without changing the face or reloading art.
"""

from functools import lru_cache
from pathlib import Path

from rendering import atlas_regions, pixel_scene as pixels
from rendering.village_art import rect
from runtime_compat import np
from simulation.systems.appearance import identity_for

_parts = {}
REQUIRED_PARTS = {"heads-male", "heads-female", "hair", "beards", "tops", "lower", "hats"}
DIRECTIONS = {"south": 0, "east": 1, "north": 2, "west": 3}
SKIN = {
    "pale": (239, 200, 167),
    "light": (219, 168, 126),
    "medium": (186, 131, 91),
    "tan": (151, 100, 66),
    "dark": (99, 63, 45),
}
HAIR = {
    "black": (45, 38, 35),
    "brown": (104, 66, 40),
    "blonde": (204, 174, 99),
    "red": (163, 73, 39),
    "gray": (146, 145, 135),
    "white": (215, 209, 190),
}
EYES = {
    "brown": (72, 44, 27),
    "hazel": (124, 103, 44),
    "green": (67, 107, 70),
    "blue": (75, 130, 160),
    "gray": (119, 137, 143),
}
HAIRSTYLES = {"short": 0, "long": 1, "braided": 2, "curly": 3}
BEARDS = {"stubble": 0, "mustache": 1, "short_beard": 2, "full_beard": 3}
TOPS = {
    "cloth_tunic": 0,
    "wool_shirt": 1,
    "leather_jerkin": 2,
    "iron_breastplate": 3,
    "fur_cloak": 1,
}
HATS = {"hooded_cowl": 0, "straw_hat": 1, "iron_helmet": 2, "wool_cap": 3}
LOWER = {"linen_trousers": 0, "wool_trousers": 1}
FOOTWEAR = {"leather_boots": 2, "leather_shoes": 3}


def install():
    root = Path(__file__).resolve().parents[1] / "assets/world32"
    _parts.clear()
    for name in ("heads-male", "heads-female", "hair", "beards", "tops", "lower", "hats"):
        path = root / f"dynamic-{name}-v1.png"
        if path.exists():
            _parts[name] = atlas_regions.read_parts(path)
    cloak = root / "dynamic-cloak-v1.png"
    if cloak.exists():
        _parts["cloak"] = atlas_regions.read_parts(cloak, rows=1)
    rig.cache_clear()
    part.cache_clear()
    identity_head.cache_clear()
    from rendering import character_pose
    character_pose.clear()


def enabled(world):
    return (
        REQUIRED_PARTS.issubset(_parts)
        and pixels.enabled(world)
        and getattr(world, "dynamic_characters_enabled", True)
    )


def equipped(actor, slot):
    gear = getattr(actor, "equipment", None)
    # NPC EquipmentSlot and the player's legacy armor dictionary both remain
    # supported. A bound item takes precedence over an absent dictionary value.
    bound = getattr(getattr(gear, slot, None), "item_key", None)
    return bound or (getattr(gear, "equipped_armor", None) or {}).get(slot)


def item_icon(key):
    """Menu thumbnails for new garments from the same canonical wearable art."""
    if not REQUIRED_PARTS.issubset(_parts):
        return None
    sources = {
        "wool_shirt": ("tops", 4),
        "wool_cap": ("hats", 12),
        "linen_trousers": ("lower", 0),
        "wool_trousers": ("lower", 4),
        "leather_boots": ("lower", 8),
        "leather_shoes": ("lower", 12),
    }
    if key not in sources:
        return None
    name, index = sources[key]
    return atlas_regions.normalize(_parts[name][index], 16, 16)


def signature(actor):
    appearance = getattr(actor, "appearance", None)
    face, eyes, build = identity_for(actor)
    hair = getattr(appearance, "hairstyle", "none")
    # Legacy "none" meant no extra hair OVERLAY on an already-haired base
    # sprite. Keep a natural short cut; only explicit "bald" removes hair.
    if hair == "none":
        hair = "short"
    return (
        "female" if getattr(actor, "gender", None) == "female" else "male",
        face,
        eyes,
        build,
        getattr(appearance, "skin_tone", "medium"),
        hair,
        getattr(appearance, "hair_color", "brown"),
        getattr(appearance, "facial_hair", "none") if getattr(actor, "age", 25) >= 18 else "none",
        equipped(actor, "head"),
        equipped(actor, "body"),
        equipped(actor, "legs"),
        equipped(actor, "feet"),
        equipped(actor, "hands"),
    )


def over(canvas, source, x, y):
    x, y = int(x), int(y)
    x0, y0, x1, y1 = (
        max(0, x),
        max(0, y),
        min(canvas.shape[1], x + source.shape[1]),
        min(canvas.shape[0], y + source.shape[0]),
    )
    if x0 >= x1 or y0 >= y1:
        return
    src = source[y0 - y : y1 - y, x0 - x : x1 - x].astype(np.uint32)
    dst = canvas[y0:y1, x0:x1].astype(np.uint32)
    a, b = src[:, :, 3:4], dst[:, :, 3:4]
    alpha = a + (b * (255 - a) + 127) // 255
    rgb = (src[:, :, :3] * a + (dst[:, :, :3] * b * (255 - a) + 127) // 255) // np.maximum(1, alpha)
    canvas[y0:y1, x0:x1, :3] = rgb.astype(np.uint8)
    canvas[y0:y1, x0:x1, 3:4] = alpha.astype(np.uint8)


@lru_cache(maxsize=1024)
def part(name, index, width, height, palette=None):
    source = _parts[name][index]
    # Independent source parts are fitted to explicit mount bounds, not sliced
    # out of an entire profession sprite. Cell gutters never become hitboxes.
    image = pixels.resize(source, width, height).copy()
    if palette:
        rgb = image[:, :, :3].astype(np.float32)
        lum = rgb.mean(axis=2)
        if name.startswith("heads"):
            # Keep dark eyes, mouth and contours; recolor only skin pixels.
            mask = (rgb[:, :, 0] > rgb[:, :, 2] * 1.15) & (lum > 55)
            shade = np.clip(lum / 155, 0.38, 1.35)
        else:
            mask = image[:, :, 3] > 0
            shade = np.clip(lum / 85, 0.30, 1.55)
        recolored = np.clip(shade[:, :, None] * np.array(palette), 0, 255).astype(np.uint8)
        image[:, :, :3][mask] = recolored[mask]
    return image


@lru_cache(maxsize=512)
def identity_head(state, direction, rest=False):
    """One identity in every pose: face, eyes, hair, beard and actual headwear."""
    sex, face, eyes, build, skin, hair, hair_color, beard, hat, top, legs, feet, hands = state
    d = DIRECTIONS.get(direction, 0)
    profile = direction in {"east", "west"}
    image = np.zeros((34, 36, 4), dtype=np.uint8)
    skin_color, hair_palette = SKIN.get(skin, SKIN["medium"]), HAIR.get(hair_color, HAIR["brown"])
    head_w = 18 if profile else 22
    head_x, head_y = (36 - head_w) // 2, 2
    head = part("heads-" + sex, face * 4 + d, head_w, 23, skin_color)
    over(image, head, head_x, head_y)
    # Tiny iris accents are anchored within each visible eye, not to profession.
    if direction == "south":
        for ex in (head_x + 7, head_x + head_w - 8):
            if rest:
                rect(image, ex-2, head_y+11, 5, 4, skin_color)
                rect(image, ex-1, head_y+13, 3, 1, tuple(c//2 for c in skin_color))
            else:
                rect(image, ex, head_y + 12, 1, 1, EYES.get(eyes, EYES["brown"]))
    if beard in BEARDS and direction != "north":
        beard_w = 13 if profile else 18
        beard_h = {"stubble": 4, "mustache": 3, "short_beard": 8, "full_beard": 13}[beard]
        b = part("beards", BEARDS[beard] * 4 + d, beard_w, beard_h, hair_palette)
        over(
            image,
            b,
            (36 - beard_w) // 2 + (3 if direction == "east" else -3 if direction == "west" else 0),
            head_y + 15,
        )
    if hair in HAIRSTYLES and hat not in {"hooded_cowl", "iron_helmet"}:
        hair_height = {"short": 20, "long": 29, "braided": 32, "curly": 22}[hair]
        h = part("hair", HAIRSTYLES[hair] * 4 + d, head_w + 4, hair_height, hair_palette)
        over(image, h, (36 - h.shape[1]) // 2, head_y - 2)
    if hat in HATS:
        width = head_w + 12 if hat == "straw_hat" else head_w + 5
        height = 28 if hat == "hooded_cowl" else 22 if hat == "iron_helmet" else 15
        h = part("hats", HATS[hat] * 4 + d, width, height)
        over(image, h, (36 - width) // 2, head_y - 2)
    if rest:
        image = pixels.resize(image, 36, 29)
    return image


@lru_cache(maxsize=1536)
def rig(state, direction, kind="idle", phase=0, posture=None, moving=False, item=None, held=None):
    from rendering.character_pose import render
    return render(state, direction, kind, phase, posture, moving or kind == "walk", item, held)


def frame(world, actor, zoom, activity, direction, phase, moving, posture):
    state = signature(actor)
    held = equipped(actor, "weapon")
    source = rig(state, direction, activity.kind, phase, posture, moving, activity.item, held)
    scale = 0.75 if getattr(actor, "age", 25) < 18 else 1.0
    # Seat and standing heads use the SAME scale. Supine bodies are foreshortened.
    density = 0.30 if posture == "reclining" else 0.375
    if activity.kind in {"sleep", "dead", "unconscious"} and not posture:
        source = np.rot90(source)
    image = pixels.resize(
        source, max(1, round(source.shape[1] * zoom * density * scale)),
        max(1, round(source.shape[0] * zoom * density * scale))
    )
    token = (
        "person32",
        ("layered-pose-v2", state, activity.item, held),
        zoom,
        activity.kind,
        phase,
        direction,
        scale,
        moving,
        posture,
    )
    return image, activity, token


def support_socket(image, token):
    """Pixel contact point shared by furniture placement, drawing and picking."""
    from rendering.character_pose import layout, project
    pose = layout(token[5], token[3], token[4], token[-1], token[7])
    point = (pose.head[0], pose.head[1]+12) if pose.reclined else pose.waist
    return project(point, (pose.size[1], pose.size[0]), image.shape)
