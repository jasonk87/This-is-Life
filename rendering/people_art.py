"""Readable people and evidence-backed activity cues, entirely presentation-only."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from runtime_compat import np
from rendering import pixel_scene as pixels
from rendering import actor_motion, atlas_regions, character_layers
from rendering.village_art import rect
from data.dawnlike import ITEM_SPRITES

_people = ()
_views = {}
_postures = {}
PROFESSIONS = {
    "Baker": 4,
    "Blacksmith": 5,
    "Farmer": 6,
    "Carpenter": 7,
    "Woodcutter": 7,
    "Lumber Mill Foreman": 7,
    "Tavern Keeper": 8,
    "Merchant": 9,
    "Traveling Merchant": 9,
    "Healer": 11,
    "Fisherman": 12,
    "Scribe": 13,
    "Miller": 13,
    "Hunter": 14,
}


def install():
    global _people
    character_layers.install()
    root = Path(__file__).resolve().parents[1] / "assets/world32"
    path = root / "people-atlas-v1.png"
    _people = ()
    if path.exists():
        _people = pixels.source_sheet(path, 4, 4, 32, 48)
        female = root / "people-female-atlas-v1.png"
        if female.exists():
            _people += pixels.source_sheet(female, 4, 4, 32, 48)
    character_pixels.cache_clear()
    _views.clear()
    for direction in ("north", "east"):
        poses = []
        for sex in ("male", "female"):
            path = root / f"people-{sex}-{direction}-v1.png"
            if path.exists():
                poses.extend(
                    atlas_regions.normalize(pose, 32, 48)
                    for pose in atlas_regions.read_silhouettes(path)
                )
        if len(poses) == len(_people):
            _views[direction] = tuple(poses)
    _postures.clear()
    for posture, height in (("seated", 40), ("reclining", 48)):
        poses = []
        for sex in ("male", "female"):
            path = root / f"people-{sex}-{posture}-v1.png"
            if path.exists():
                poses.extend(
                    atlas_regions.normalize(pose, 32, height)
                    for pose in atlas_regions.read_silhouettes(path)
                )
        if len(poses) == len(_people):
            _postures[posture] = tuple(poses)
    actor_motion.reset()


@dataclass(frozen=True)
class Activity:
    kind: str = "idle"
    item: str | None = None
    target: tuple | None = None


def activity_for(world, actor):
    """Use active interactions/inventory, never infer work from profession."""
    if getattr(getattr(actor, "physical", None), "is_dead", False):
        return Activity("dead")
    if getattr(actor, "render_disabled", False):
        return Activity()  # Macro suspension is not physical sleep.
    body = getattr(getattr(actor, "combat", None), "anatomy", None)
    if body and body.body_plan:
        if "unconscious" in actor.physical.status_effects:
            return Activity("unconscious")
        if body.last_attack_target and world.game_time < body.attack_ready_tick:
            return Activity(body.last_attack_kind, target=body.last_attack_target)
    state = getattr(actor, "state", None)
    if getattr(actor, "is_sleeping", False) or getattr(state, "is_sleeping", False):
        return Activity("sleep")
    schedule = getattr(actor, "schedule", None)
    if getattr(schedule, "current_task", None) == "sleeping":
        return Activity("sleep")
    iid = getattr(schedule, "active_interaction_id", None)
    resolver = getattr(world, "interaction_resolver", None)
    active = getattr(resolver, "active_interactions", {}).get(iid)
    if (
        active
        and getattr(active, "actor_id", None) == getattr(actor, "id", None)
        and getattr(active, "remaining_work", 0) > 0
    ):
        cue = getattr(active, "animation_cue", None)
        kind = {
            "chop_tree": "chop",
            "build": "hammer",
            "forge_hammer": "hammer",
            "attack_lunge": "fight",
            "drink_or_eat": "eat",
        }.get(cue)
        if kind:
            return Activity(kind, target=getattr(active, "target_pos", None))
    task = str(getattr(schedule, "current_task", "")).lower()
    data = getattr(actor, "task_context_data", None) or {}
    item = data.get("item_key") if isinstance(data, dict) else None
    economic = getattr(actor, "economic", None)
    inventory = getattr(economic, "npc_inventory", None)
    if inventory is None:
        inventory = getattr(economic, "inventory", {})
    if (
        item
        and inventory.get(item, 0) > 0
        and task
        in {"hauling_to_blueprint", "hauling_to_stockpile", "hauling_to_delivery_destination"}
    ):
        return Activity("carry", item=item)
    moving = bool(
        getattr(schedule, "current_path", None)
        or getattr(getattr(actor, "state", None), "current_path", None)
    )
    if not moving and getattr(actor, "task_timer", 0) > 0:
        subtask = str(getattr(actor, "current_sub_task", "")).lower()
        if task in {"eating", "drinking"}:
            return Activity("eat")
        if any(word in subtask for word in ("forge", "smith", "hammer")):
            return Activity("hammer")
        if any(word in subtask for word in ("bake", "knead", "cook")):
            return Activity("prepare")
        if subtask == "chop_trees":
            return Activity("chop")
    _, actual_movement = actor_motion.observe(world, actor)
    from rendering.furniture_occupancy import attachment_for
    if actual_movement and attachment_for(world, actor) is None:
        return Activity("walk")
    tick = getattr(world, "game_time", 0)
    for speech in getattr(world, "active_ambient_speech", []):
        if (
            speech.speaker_id == getattr(actor, "id", None)
            and speech.created_tick <= tick < speech.expires_tick
        ):
            return Activity("talk")
    if getattr(actor, "is_sitting", False) or getattr(state, "is_sitting", False):
        return Activity("sit")
    return Activity()


def outfit_index(actor):
    gender = getattr(actor, "gender", "male")
    age = getattr(actor, "age", 25)
    profession = getattr(getattr(actor, "economic", None), "profession", "")
    appearance = getattr(actor, "appearance", None)
    offset = 16 if gender == "female" and len(_people) >= 32 else 0
    if age < 18:
        return offset + 15
    # Do not depict an armored guard just because somebody has that job.
    equipment = getattr(actor, "equipment", None)
    helmet = (getattr(equipment, "equipped_armor", None) or {}).get("head")
    helmet = getattr(getattr(equipment, "head", None), "item_key", None) or helmet
    if profession in {"Guard", "Sheriff", "Deputy"} and helmet == "iron_helmet":
        return offset + 10
    if age >= 60 and profession in {"", "Unemployed", "Villager"}:
        return offset + 2
    if profession in PROFESSIONS:
        return offset + PROFESSIONS[profession]
    if gender == "female":
        return offset + (3 if getattr(appearance, "skin_tone", None) == "dark" else 1)
    return 0


def shifted(source, dx=0, dy=0):
    """Translate a limb inside its mask without wrapping pixels at the edge."""
    result = np.zeros_like(source)
    h, w = source.shape[:2]
    if abs(dx) < w and abs(dy) < h:
        result[max(0, dy) : min(h, h + dy), max(0, dx) : min(w, w + dx)] = source[
            max(0, -dy) : min(h, h - dy), max(0, -dx) : min(w, w - dx)
        ]
    return result


@lru_cache(maxsize=1536)
def character_pixels(index, zoom, kind, phase, direction, child, moving=False, posture=None):
    if posture in _postures:
        source = _postures[posture][index].copy()
        if posture == "seated" and kind in {"eat", "talk"}:
            source[20:29, 22:29] = shifted(source[20:29, 22:29], dy=-(phase % 2))
        size = 0.75 if child else 1.0
        width, height = (16, 20) if posture == "seated" else (12, 18)
        return pixels.resize(
            source, max(1, round(zoom * width * size)), max(1, round(zoom * height * size))
        )
    if isinstance(direction, bool):
        direction = "west" if direction else "south"
    source_direction = "east" if direction == "west" else direction
    source = _views.get(source_direction, _people)[index].copy()
    if direction == "west":
        source = source[:, ::-1].copy()
    if kind == "walk" or moving:
        stride = (0, 2, 0, -2)[phase]
        if direction in {"east", "west"}:
            source[34:46, 7:17] = shifted(source[34:46, 7:17], dx=stride)
            source[34:46, 17:27] = shifted(source[34:46, 17:27], dx=-stride)
        else:
            source[34:46, 7:16] = shifted(source[34:46, 7:16], dy=stride)
            source[34:46, 16:26] = shifted(source[34:46, 16:26], dy=-stride)
        source[:32] = shifted(source[:32], dy=1 if phase in (1, 3) else 0)
    elif kind == "idle":
        source[:32] = shifted(source[:32], dy=1 if phase == 2 else 0)
    if kind == "sit":
        source = np.concatenate((source[:32], pixels.resize(source[32:], 32, 8)), axis=0)
    if kind in {"hammer", "chop", "prepare", "eat", "talk"}:
        # Small hand/forearm gestures accompany the tool/food cue. Moving an
        # arm never changes collision bounds, position or simulation timing.
        source[22:34, 23:29] = shifted(source[22:34, 23:29], dy=-(phase % 2) * 2)
    if kind == "carry":
        source[22:34, 3:10] = shifted(source[22:34, 3:10], dx=2, dy=-2)
        source[22:34, 22:29] = shifted(source[22:34, 22:29], dx=-2, dy=-2)
    if kind in {"sleep", "dead"}:
        source = np.rot90(source).copy()
        return pixels.resize(source, zoom * 24, zoom * 16)
    size = 0.75 if child else 1.0
    height = 20 if kind == "sit" else 24
    return pixels.resize(
        source, max(1, round(zoom * 16 * size)), max(1, round(zoom * height * size))
    )


@lru_cache(maxsize=32)
def tool_pixels(kind, phase):
    image = np.zeros((32, 24, 4), dtype=np.uint8)
    if kind in {"hammer", "chop"}:
        # Four tool poses. Only emitted for an actual timed action.
        x, y = [(6, 14), (14, 2), (12, 12), (6, 16)][phase]
        rect(image, x, y, 3, 14, (137, 93, 50))
        rect(image, x - 5, y, 12, 5, (175, 188, 180))
        if kind == "chop":
            rect(image, x - 7, y + 2, 5, 7, (187, 201, 192))
            rect(image, x - 8, y + 3, 1, 5, (229, 231, 206))
        if phase == 2:
            rect(image, 18, 22, 3, 2, (250, 204, 102))
            rect(image, 20, 26, 2, 3, (238, 156, 68))
    elif kind == "fight":
        # A lunge gesture, not an invented weapon. Equipped weapons are drawn
        # separately from the actor's actual slots.
        rect(image, 5 + phase * 3, 12, 5, 4, (192, 141, 100))
    elif kind == "eat":
        rect(image, 5, 8 if phase % 2 else 18, 8, 7, (223, 181, 99))
    elif kind == "prepare":
        rect(image, 2, 22, 18, 4, (137, 94, 56))
        rect(image, 6 + phase, 18, 8, 4, (234, 214, 160))
    elif kind == "sleep":
        y = 5 - phase
        rect(image, 5, y, 7, 2, (175, 193, 211))
        rect(image, 9, y + 2, 3, 2, (175, 193, 211))
        rect(image, 5, y + 4, 7, 2, (175, 193, 211))
    elif kind == "talk":
        rect(image, 2, 2, 20, 10, (223, 216, 184))
        rect(image, 5, 12, 4, 3, (223, 216, 184))
        for x in range(5, 7 + (phase % 3) * 5, 5):
            rect(image, x, 6, 2, 2, (62, 65, 54))
    return image


def is_person(world, actor):
    # Animals inherit NPC, including gender/age; they must keep animal art.
    return (
        actor is not None
        and not getattr(actor, "animal_type", None)
        and (hasattr(actor, "gender") or actor is getattr(world, "player", None))
    )


def body_frame(world, actor, zoom):
    from rendering.furniture_occupancy import attachment_for

    activity = activity_for(world, actor)
    direction, moving = actor_motion.observe(world, actor)
    attachment = attachment_for(world, actor)
    posture = attachment.kind if attachment else None
    if attachment:
        # Sitting starts while logical position can still be beside the chair;
        # stale interpolation must not animate a seated person walking in place.
        direction, moving = "south", False
        if activity.kind == "walk":
            activity = Activity("sit" if posture == "seated" else "sleep")
    if activity.target and not attachment:
        direction = actor_motion.direction_from(
            activity.target[0] - actor.x, activity.target[1] - actor.y, direction
        )
    tick = int(getattr(world, "game_time", 0))
    # A stable per-person offset keeps an idle room from breathing in unison.
    offset = sum(ord(c) for c in str(getattr(actor, "id", ""))) % 4
    phase = ((tick // 10 if activity.kind == "idle" else tick // 2) + offset) % 4
    if activity.kind in {"dead", "sit"} or (activity.kind == "carry" and not moving):
        phase = 0
    index = outfit_index(actor)
    child = getattr(actor, "age", 25) < 18
    if not getattr(world, "directional_art_enabled", True):
        direction = "south"
    if character_layers.enabled(world):
        return character_layers.frame(world, actor, zoom, activity, direction, phase, moving, posture)
    image = character_pixels(index, zoom, activity.kind, phase, direction, child, moving, posture)
    return (
        image,
        activity,
        ("person32", index, zoom, activity.kind, phase, direction, child, moving, posture),
    )


def placement(world, actor, zoom, camera_x, camera_y, draw_at=None):
    from rendering import furniture_occupancy as occupancy, interior_art

    attachment = occupancy.attachment_for(world, actor)
    x, y = occupancy.render_anchor(world, actor) if attachment or draw_at is None else draw_at
    image, activity, token = body_frame(world, actor, zoom)
    unit = zoom * 16
    px = int((x - camera_x) * unit + (unit - image.shape[1]) // 2)
    py = int((y - camera_y + 1) * unit - image.shape[0])
    if attachment and character_layers.enabled(world):
        furniture, fx, fy = interior_art.placement(attachment.key, zoom, x, y, camera_x, camera_y)
        contact_x, contact_y = interior_art.support_socket(attachment.key, furniture)
        body_x, body_y = character_layers.support_socket(image, token)
        px, py = fx + contact_x - body_x, fy + contact_y - body_y
    elif attachment and attachment.kind == "reclining" and "reclining" in _postures:
        bed, _, bed_y = interior_art.placement(attachment.key, zoom, x, y, camera_x, camera_y)
        pillow_offset = 0.04 if attachment.key == "bed_simple" else 0.17
        py = bed_y + round(bed.shape[0] * pillow_offset)
    return image, activity, token, px, py


def hit_test(world, camera_x, camera_y, screen_x, screen_y):
    """Pick the visible body under a console cell, including its taller head.

    This only retargets inspection/hover to the actor's real tile. Walking,
    collision and construction continue to use the unchanged ground grid.
    """
    from config import MAP_HEIGHT, MAP_WIDTH

    if (
        not _people
        or not pixels.enabled(world)
        or getattr(world, "player", None) is None
        or not (0 <= screen_x < MAP_WIDTH and 3 <= screen_y < MAP_HEIGHT)
    ):
        return None
    from rendering.room_scene import pick_person

    return pick_person(world, camera_x, camera_y, screen_x, screen_y)


def draw_person(console, world, actor, camera_x, camera_y, draw_x, draw_y):
    if not _people or not pixels.enabled(world) or not is_person(world, actor):
        return False
    from rendering.console_renderer import (
        _get_zoom_factor,
        _get_equipment_overlays,
        _get_appearance_overlays,
        is_visible,
    )
    from rendering import furniture_occupancy as occupancy, interior_art

    if not occupancy.present(world, actor):
        return True  # Handled intentionally; do not fall through to a legacy sprite.

    zoom = int(_get_zoom_factor(world))
    unit = zoom * 16
    attachment = occupancy.attachment_for(world, actor)
    image, activity, token, px, py = placement(
        world, actor, zoom, camera_x, camera_y, (draw_x, draw_y)
    )
    if attachment:
        draw_x, draw_y = attachment.x, attachment.y
    phase = token[4]
    clip = lambda cx, cy: is_visible(world, camera_x + cx // zoom, camera_y + cy // zoom)
    # Contact shadow anchors a taller silhouette to its actual occupied tile.
    shadow = np.zeros((max(2, unit // 8), unit * 3 // 4, 4), dtype=np.uint8)
    shadow[:] = (10, 16, 17, 145)
    is_player = actor is getattr(world, "player", None)
    if is_player:
        # Small broken ground marker keeps the player identifiable in a crowd.
        shadow[-2:, : max(2, unit // 8)] = (223, 188, 110, 230)
        shadow[-2:, -max(2, unit // 8) :] = (223, 188, 110, 230)
    if not attachment:
        pixels.stamp(
            console,
            shadow,
            (draw_x - camera_x) * unit + unit // 8,
            (draw_y - camera_y + 1) * unit - unit // 8,
            token=("actor-shadow", zoom, is_player),
            clip=clip,
        )
    tint = pixels.world_tint(world, (draw_x - camera_x) * zoom, (draw_y - camera_y) * zoom)
    if activity.kind == "dead":
        tint = tuple(channel * 3 // 5 for channel in tint)
    direction = token[5]
    layered = character_layers.enabled(world)

    def draw_carried_item():
        cp = ITEM_SPRITES[activity.item]
        item = pixels.scaled(
            pixels.tile_pixels(cp), unit // 2, unit // 2, token=("carry32-small", cp, zoom)
        )
        offset = {"north": unit // 4, "south": unit // 4, "east": unit // 2, "west": 0}[direction]
        pixels.stamp(
            console,
            item,
            px + offset,
            py + image.shape[0] // 2,
            token=("carry32-small", cp, zoom),
            tint=tint,
            clip=clip,
        )

    carrying = not layered and activity.item and activity.item in ITEM_SPRITES
    if carrying and direction == "north":
        # Facing away, the body occludes what is held in front of the chest.
        draw_carried_item()
    pixels.stamp(
        console,
        image,
        px,
        py,
        token=token,
        tint=tint,
        clip=clip,
    )
    # Existing equipment remains connected to actual equipment slots. Alpha
    # compositing preserves the body instead of replacing an entire quadrant.
    # The joint rig already includes actual gear and held items at its sockets.
    overlays = [] if layered else _get_appearance_overlays(actor) + _get_equipment_overlays(actor)
    for cp, ax, ay, z in sorted(overlays, key=lambda entry: entry[3]):
        item_size = max(8, unit // 2)
        if attachment:
            item_size = max(4, min(item_size, image.shape[1] // 2))
        equipment_token = ("equipment32", cp, zoom, item_size)
        item = pixels.scaled(
            pixels.tile_pixels(cp),
            item_size,
            item_size,
            token=equipment_token,
        )
        overlay_x = px + int(ax * unit)
        overlay_y = py + int((0.2 + ay) * image.shape[0])
        if attachment:
            overlay_x = px + round(ax * (image.shape[1] - item_size))
            overlay_y = py + round(ay * (image.shape[0] - item_size))
        pixels.stamp(
            console,
            item,
            overlay_x,
            overlay_y,
            token=equipment_token,
            tint=tint,
            clip=clip,
        )
    if attachment:
        _, fx, fy = interior_art.placement(
            attachment.key, zoom, attachment.x, attachment.y, camera_x, camera_y
        )
        pixels.stamp(
            console,
            interior_art.foreground_pixels(attachment.key, zoom),
            fx,
            fy,
            token=("furniture-front", attachment.key, zoom),
            tint=tint,
            clip=clip,
        )
        if is_player:
            marker = np.zeros((max(2, zoom), unit, 4), dtype=np.uint8)
            marker[:, :zoom] = marker[:, -zoom:] = (223, 188, 110, 230)
            pixels.stamp(
                console,
                marker,
                (draw_x - camera_x) * unit,
                (draw_y - camera_y + 1) * unit - zoom,
                token=("seated-player-marker", zoom),
                clip=clip,
            )
    if carrying:
        if direction != "north":
            draw_carried_item()
    elif activity.kind in ({"sleep", "talk"} if layered else {"chop", "hammer", "fight", "eat", "prepare", "sleep", "talk"}):
        direction = token[5]
        source = tool_pixels(activity.kind, phase)
        if direction == "west":
            source = source[:, ::-1]
        tool = pixels.scaled(
            source,
            unit * 3 // 4,
            unit,
            token=("activity32", activity.kind, phase, zoom, direction),
        )
        tx, ty = {
            "north": (unit // 4, -unit // 8),
            "south": (unit // 3, unit // 3),
            "east": (unit // 2, unit // 3),
            "west": (-unit // 3, unit // 3),
        }[direction]
        if activity.kind in {"talk", "sleep"}:
            tx, ty = unit // 8, -unit // 3
        elif direction == "north":
            tx, ty = unit // 2, -unit // 8
        pixels.stamp(
            console,
            tool,
            px + tx,
            py + ty,
            token=("activity32", activity.kind, phase, zoom, direction),
            tint=tint,
            clip=clip,
        )
    return True
