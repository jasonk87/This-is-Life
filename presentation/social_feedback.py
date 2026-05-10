"""Lightweight visible summaries for social scenes and NPC social state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


SCENE_MARKER_STYLES = {
    "funeral": ("†", "funeral", (150, 150, 190)),
    "warning": ("!", "warning", (255, 150, 90)),
    "accusation": ("!", "accusation", (255, 120, 120)),
    "celebration": ("*", "celebration", (255, 220, 120)),
    "market_concern": ("?", "public concern", (210, 190, 120)),
    "tavern": ("~", "tavern chatter", (190, 170, 230)),
    "worksite": ("=", "work chatter", (180, 190, 170)),
    "home": ("h", "household talk", (190, 180, 150)),
    "market": ("?", "market talk", (220, 200, 140)),
    "street": ("'", "street talk", (170, 190, 210)),
}
TONE_LABELS = {
    "grieving": "grieving",
    "somber": "somber",
    "sad": "grieving",
    "tense": "tense",
    "fearful": "fearful",
    "suspicious": "suspicious",
    "celebratory": "celebrating",
    "concerned": "concerned",
    "curious": "curious",
}
REACTION_TAGS = {
    "fear": ("fearful", "!", (255, 130, 100)),
    "grief": ("grieving", "†", (150, 150, 190)),
    "curiosity": ("curious", "?", (180, 200, 255)),
    "respect": ("respectful", "+", (170, 220, 170)),
}
TAG_PRIORITY = (
    "fearful",
    "suspicious",
    "grieving",
    "tense",
    "gossiping",
    "celebrating",
    "concerned",
    "curious",
)


@dataclass(frozen=True)
class SocialIndicator:
    """A compact renderable marker for visible social simulation state."""

    indicator_id: str
    kind: str
    label: str
    tone: str
    location: tuple[int, int]
    glyph: str
    color: tuple[int, int, int]
    participant_count: int = 0
    density: str = "small"
    source: str = "scene"


def describe_social_scene(scene) -> SocialIndicator | None:
    """Return a compact marker/label for a social scene."""
    location = _location_tuple(getattr(scene, "location", None))
    if location is None:
        return None
    scene_type = str(getattr(scene, "scene_type", "generic") or "generic")
    tone = str(getattr(scene, "tone", "neutral") or "neutral")
    participant_count = _participant_count(scene)
    glyph, base_label, color = SCENE_MARKER_STYLES.get(scene_type, ("•", "gathering", (180, 180, 180)))
    tone_label = TONE_LABELS.get(tone, tone if tone != "neutral" else "")
    if scene_type == "generic" and tone_label:
        base_label = tone_label
    label_parts = [part for part in (tone_label, base_label) if part]
    label = " ".join(dict.fromkeys(label_parts)) or "social scene"
    if participant_count >= 4:
        label = f"clustered {label}"
    return SocialIndicator(
        indicator_id=str(getattr(scene, "scene_id", f"scene:{location[0]}:{location[1]}")),
        kind=scene_type,
        label=label,
        tone=tone,
        location=location,
        glyph=glyph,
        color=color,
        participant_count=participant_count,
        density=_density_for_count(participant_count),
        source="public_event" if getattr(scene, "public_event_seed_ids", None) else "scene",
    )


def collect_visible_social_indicators(
    world,
    *,
    visibility_fn: Callable[[object, int, int], bool] | None = None,
    max_distance: int = 18,
) -> list[SocialIndicator]:
    """Return compact social scene indicators the player can plausibly see."""
    indicators = []
    player = getattr(world, "player", None)
    for scene in _iter_social_scenes(world):
        indicator = describe_social_scene(scene)
        if indicator is None:
            continue
        if not _indicator_is_visible(world, player, indicator, visibility_fn, max_distance):
            continue
        indicators.append(indicator)
    indicators.sort(key=lambda item: (_distance_to_player(player, item.location), item.indicator_id))
    return indicators


def social_tags_for_entity(entity, world=None, *, scene=None, limit: int = 2) -> list[str]:
    """Return compact readable NPC social-state tags such as tense or gossiping."""
    tags: list[str] = []
    if getattr(getattr(entity, "combat", None), "is_hostile_to_player", False):
        tags.append("suspicious")
    if getattr(entity, "conversation_partner_id", None) is not None:
        tags.append("gossiping")

    social = getattr(entity, "social", None)
    for reaction in reversed(list(getattr(social, "recent_social_reactions", []) or [])[-4:]):
        reaction_type = str(reaction.get("reaction_type", "") or "")
        tag = REACTION_TAGS.get(reaction_type, (None, None, None))[0]
        if tag:
            tags.append(tag)

    scene = scene or _find_entity_scene(entity, world)
    if scene is not None:
        scene_type = str(getattr(scene, "scene_type", "") or "")
        tone = str(getattr(scene, "tone", "") or "")
        if scene_type in {"funeral"} or tone in {"grieving", "somber", "sad"}:
            tags.append("grieving")
        if scene_type in {"warning", "accusation"} or tone in {"tense", "fearful"}:
            tags.append("tense")
        if scene_type == "celebration" or tone == "celebratory":
            tags.append("celebrating")
        if scene_type == "market_concern" or tone == "concerned":
            tags.append("concerned")
        if tone == "curious":
            tags.append("curious")

    return _prioritize_tags(tags)[: max(0, limit)]


def social_marker_for_entity(entity, world=None, *, scene=None) -> tuple[str, tuple[int, int, int]] | None:
    """Return a tiny icon/color for an NPC's most important social state."""
    tags = social_tags_for_entity(entity, world, scene=scene, limit=1)
    if not tags:
        return None
    tag = tags[0]
    if tag == "fearful":
        return "!", (255, 130, 100)
    if tag == "suspicious":
        return "!", (255, 170, 90)
    if tag == "grieving":
        return "†", (150, 150, 190)
    if tag == "tense":
        return "!", (230, 150, 120)
    if tag == "gossiping":
        return "~", (185, 180, 230)
    if tag == "celebrating":
        return "*", (255, 220, 120)
    if tag == "concerned":
        return "?", (210, 190, 120)
    if tag == "curious":
        return "?", (180, 200, 255)
    return None


def social_hover_summary(world, coords: tuple[int, int]) -> str | None:
    """Return a short hover/context summary for visible social state at a tile."""
    x, y = coords
    matching = []
    for scene in _iter_social_scenes(world):
        indicator = describe_social_scene(scene)
        if indicator is None:
            continue
        if _location_distance(indicator.location, (x, y)) <= 1:
            matching.append(indicator)
    if not matching:
        return None
    matching.sort(key=lambda item: (item.source == "public_event", item.participant_count), reverse=True)
    indicator = matching[0]
    count = f"{indicator.participant_count} NPCs" if indicator.participant_count else "NPCs"
    return f"{indicator.label} ({count})"



def _iter_social_scenes(world):
    scenes = getattr(world, "social_scenes", {}) or {}
    if hasattr(scenes, "values"):
        return list(scenes.values())
    return list(scenes)

def _find_entity_scene(entity, world):
    if world is None:
        return None
    entity_id = getattr(entity, "id", None)
    if entity_id is None:
        return None
    for scene in _iter_social_scenes(world):
        if entity_id in set(getattr(scene, "participant_ids", []) or []):
            return scene
    return None


def _indicator_is_visible(world, player, indicator, visibility_fn, max_distance: int) -> bool:
    if player is not None and _distance_to_player(player, indicator.location) > max_distance:
        return False
    if visibility_fn is None:
        return True
    return bool(visibility_fn(world, indicator.location[0], indicator.location[1]))


def _participant_count(scene) -> int:
    try:
        return len(getattr(scene, "participant_ids", []) or [])
    except TypeError:
        return 0


def _density_for_count(count: int) -> str:
    if count >= 5:
        return "crowd"
    if count >= 3:
        return "cluster"
    return "small"


def _prioritize_tags(tags: list[str]) -> list[str]:
    unique = list(dict.fromkeys(tag for tag in tags if tag))
    unique.sort(key=lambda tag: TAG_PRIORITY.index(tag) if tag in TAG_PRIORITY else len(TAG_PRIORITY))
    return unique


def _location_tuple(value) -> tuple[int, int] | None:
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return int(value[0]), int(value[1])
    return None


def _distance_to_player(player, location: tuple[int, int]) -> int:
    if player is None:
        return 0
    return abs(int(getattr(player, "x", 0)) - location[0]) + abs(int(getattr(player, "y", 0)) - location[1])


def _location_distance(left: tuple[int, int], right: tuple[int, int]) -> int:
    return abs(int(left[0]) - int(right[0])) + abs(int(left[1]) - int(right[1]))
