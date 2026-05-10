"""Lightweight audible ambient speech lines for nearby NPC chatter."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Callable, Literal


AmbientSpeechSource = Literal[
    "small_talk",
    "known_fact",
    "social_reaction",
    "activity",
    "scene",
    "warning",
    "celebration",
]

DEFAULT_SPEECH_TTL_TICKS = 45
DEFAULT_AUDIBLE_RADIUS = 9
MAX_ACTIVE_AMBIENT_SPEECH = 24
MAX_RECENT_SPEECH_IDS = 48
DEFAULT_VISIBLE_SPEECH_LIMIT = 4

SOURCE_PRIORITIES: dict[str, float] = {
    "warning": 95.0,
    "social_reaction": 82.0,
    "known_fact": 72.0,
    "scene": 62.0,
    "celebration": 58.0,
    "activity": 42.0,
    "small_talk": 28.0,
}
SCENE_PRIORITY_BONUS: dict[str, float] = {
    "funeral": 18.0,
    "warning": 18.0,
    "accusation": 16.0,
    "celebration": 12.0,
    "market_concern": 10.0,
    "tavern": 6.0,
    "worksite": 4.0,
}
TONE_PRIORITY_BONUS: dict[str, float] = {
    "tense": 18.0,
    "fearful": 18.0,
    "grieving": 16.0,
    "somber": 12.0,
    "celebratory": 10.0,
    "concerned": 8.0,
}
GENERIC_MURMURS: dict[str, str] = {
    "funeral": "hushed murmurs",
    "warning": "hushed warning",
    "accusation": "tense murmurs",
    "celebration": "excited chatter",
    "market_concern": "concerned chatter",
    "tavern": "tavern chatter",
    "worksite": "work chatter",
}
TONE_PREFIXES: dict[str, str] = {
    "tense": "!",
    "fearful": "!",
    "grieving": "…",
    "somber": "…",
    "celebratory": "♪",
    "concerned": "?",
}


@dataclass(frozen=True)
class AmbientSpeechLine:
    """One short-lived speech line that can be heard near its world position."""

    speech_id: str
    speaker_id: int | str | None
    listener_id: int | str | None = None
    text: str = ""
    source_type: AmbientSpeechSource | str = "small_talk"
    source_record_id: str | None = None
    created_tick: int = 0
    expires_tick: int = 0
    audible_radius: int = DEFAULT_AUDIBLE_RADIUS
    position: tuple[int, int] = (0, 0)
    priority: float = 0.0
    scene_type: str | None = None
    scene_tone: str | None = None


@dataclass
class AmbientSpeechState:
    """Small world-attached state container for active and recent chatter."""

    active_ambient_speech: list[AmbientSpeechLine] = field(default_factory=list)
    recent_speech_ids: list[str] = field(default_factory=list)


def ensure_ambient_speech_state(world) -> AmbientSpeechState:
    """Ensure the world has ambient-speech lists and return a state view."""
    state = getattr(world, "ambient_speech_state", None)
    if state is None:
        state = AmbientSpeechState()
        world.ambient_speech_state = state
    if not hasattr(world, "active_ambient_speech"):
        world.active_ambient_speech = state.active_ambient_speech
    if not hasattr(world, "recent_speech_ids"):
        world.recent_speech_ids = state.recent_speech_ids
    state.active_ambient_speech = world.active_ambient_speech
    state.recent_speech_ids = world.recent_speech_ids
    return state


def add_ambient_speech(
    world,
    *,
    speaker,
    text: str,
    listener=None,
    source_type: AmbientSpeechSource | str = "small_talk",
    source_record_id: str | None = None,
    position: tuple[int, int] | None = None,
    audible_radius: int | None = None,
    priority: float | None = None,
    scene=None,
    ttl_ticks: int = DEFAULT_SPEECH_TTL_TICKS,
) -> AmbientSpeechLine | None:
    """Add a deduped short-lived ambient speech line to world state."""
    text = _clean_text(text)
    if not text:
        return None
    current_tick = _current_tick(world)
    cleanup_ambient_speech(world, current_tick=current_tick)
    scene_type = str(getattr(scene, "scene_type", "") or "") or None
    scene_tone = str(getattr(scene, "tone", "") or "") or None
    position = position or _entity_position(speaker)
    speech_id = _speech_id(
        getattr(speaker, "id", None),
        getattr(listener, "id", None),
        text,
        source_type,
        source_record_id,
        current_tick // max(1, DEFAULT_SPEECH_TTL_TICKS),
    )
    if _is_recent_duplicate(world, speech_id):
        return None
    line = AmbientSpeechLine(
        speech_id=speech_id,
        speaker_id=getattr(speaker, "id", None),
        listener_id=getattr(listener, "id", None),
        text=text,
        source_type=str(source_type or "small_talk"),
        source_record_id=source_record_id,
        created_tick=current_tick,
        expires_tick=current_tick + max(1, int(ttl_ticks)),
        audible_radius=max(1, int(audible_radius if audible_radius is not None else _speech_radius_for(speaker))),
        position=(int(position[0]), int(position[1])),
        priority=float(priority if priority is not None else _priority_for(str(source_type), scene_type, scene_tone)),
        scene_type=scene_type,
        scene_tone=scene_tone,
    )
    active = _active_speech(world)
    active.append(line)
    active.sort(key=lambda item: (item.priority, item.created_tick), reverse=True)
    del active[MAX_ACTIVE_AMBIENT_SPEECH:]
    recent = _recent_speech_ids(world)
    recent.append(speech_id)
    del recent[:-MAX_RECENT_SPEECH_IDS]
    return line


def cleanup_ambient_speech(world, *, current_tick: int | None = None) -> None:
    """Remove expired ambient speech lines from world state."""
    current_tick = _current_tick(world) if current_tick is None else int(current_tick)
    active = _active_speech(world)
    active[:] = [line for line in active if int(line.expires_tick) > current_tick]


def visible_ambient_speech_lines(
    world,
    *,
    player=None,
    current_tick: int | None = None,
    visibility_fn: Callable[[object, int, int], bool] | None = None,
    max_lines: int = DEFAULT_VISIBLE_SPEECH_LIMIT,
) -> list[AmbientSpeechLine]:
    """Return audible, uncluttered speech lines for the player."""
    current_tick = _current_tick(world) if current_tick is None else int(current_tick)
    cleanup_ambient_speech(world, current_tick=current_tick)
    player = player or getattr(world, "player", None)
    visible: list[AmbientSpeechLine] = []
    seen_text: set[str] = set()
    for line in _active_speech(world):
        if not _line_is_audible(world, player, line, current_tick, visibility_fn):
            continue
        text_key = _clean_text(line.text).lower()
        if text_key in seen_text:
            continue
        seen_text.add(text_key)
        visible.append(line)
    visible.sort(
        key=lambda line: (
            float(line.priority),
            -_distance_to_player(player, line.position),
            int(line.created_tick),
        ),
        reverse=True,
    )
    return visible[: max(0, int(max_lines))]


def format_ambient_speech_for_player(line: AmbientSpeechLine, player, *, max_width: int = 64) -> str:
    """Return full, shortened, or muffled text based on distance to player."""
    distance = _distance_to_player(player, line.position)
    close_limit = max(2, line.audible_radius // 3)
    medium_limit = max(close_limit + 1, (line.audible_radius * 2) // 3)
    if distance <= close_limit:
        text = line.text
    elif distance <= medium_limit:
        text = _shorten_text(line.text, min(max_width, 48))
    else:
        text = GENERIC_MURMURS.get(str(line.scene_type or ""), _generic_murmur_for(line))
    prefix = TONE_PREFIXES.get(str(line.scene_tone or ""), "")
    return _shorten_text(f"{prefix} {text}".strip(), max_width)


def ambient_speech_source_for_dialogue(line, *, scene=None) -> AmbientSpeechSource:
    """Classify deterministic dialogue for ambient audibility priority."""
    topic_type = str(getattr(line, "topic_type", "") or "")
    scene_type = str(getattr(scene, "scene_type", "") or "")
    scene_tone = str(getattr(scene, "tone", "") or "")
    if topic_type in {"fear", "crime"} or scene_tone in {"tense", "fearful"} or scene_type in {"warning", "accusation"}:
        return "warning"
    if topic_type in {"grief", "respect", "curiosity"}:
        return "social_reaction"
    if scene_type == "celebration" or scene_tone == "celebratory":
        return "celebration"
    if topic_type == "small_talk":
        return "small_talk"
    if topic_type:
        return "known_fact"
    if scene_type:
        return "scene"
    return "activity"


def add_dialogue_line_as_ambient_speech(world, speaker, listener, dialogue_line, *, scene=None) -> AmbientSpeechLine | None:
    """Publish a deterministic dialogue line to nearby audible chatter."""
    if dialogue_line is None:
        return None
    source_type = ambient_speech_source_for_dialogue(dialogue_line, scene=scene)
    radius = _scene_radius_for(scene, _speech_radius_for(speaker))
    return add_ambient_speech(
        world,
        speaker=speaker,
        listener=listener,
        text=getattr(dialogue_line, "text", ""),
        source_type=source_type,
        source_record_id=str(getattr(dialogue_line, "source_id", "") or "") or None,
        audible_radius=radius,
        scene=scene,
    )


def _active_speech(world) -> list[AmbientSpeechLine]:
    return ensure_ambient_speech_state(world).active_ambient_speech


def _recent_speech_ids(world) -> list[str]:
    return ensure_ambient_speech_state(world).recent_speech_ids


def _is_recent_duplicate(world, speech_id: str) -> bool:
    return speech_id in set(_recent_speech_ids(world))


def _line_is_audible(world, player, line: AmbientSpeechLine, current_tick: int, visibility_fn) -> bool:
    if int(line.expires_tick) <= current_tick:
        return False
    if player is None:
        return True
    distance = _distance_to_player(player, line.position)
    if distance > int(line.audible_radius):
        return False
    hearing_radius = int(getattr(getattr(player, "physical", None), "hearing_radius", line.audible_radius) or line.audible_radius)
    if distance > hearing_radius:
        return False
    if visibility_fn is not None and not visibility_fn(world, line.position[0], line.position[1]):
        return False
    return True


def _priority_for(source_type: str, scene_type: str | None, scene_tone: str | None) -> float:
    priority = SOURCE_PRIORITIES.get(str(source_type or "small_talk"), 35.0)
    priority += SCENE_PRIORITY_BONUS.get(str(scene_type or ""), 0.0)
    priority += TONE_PRIORITY_BONUS.get(str(scene_tone or ""), 0.0)
    return priority


def _scene_radius_for(scene, fallback: int) -> int:
    scene_type = str(getattr(scene, "scene_type", "") or "")
    tone = str(getattr(scene, "tone", "") or "")
    if scene_type == "funeral" or tone in {"grieving", "somber"}:
        return max(4, min(fallback, 6))
    if scene_type == "tavern":
        return max(fallback, 10)
    if scene_type == "celebration" or tone == "celebratory":
        return max(fallback, 12)
    if tone in {"tense", "fearful"} or scene_type in {"warning", "accusation"}:
        return max(6, min(max(fallback, 8), 10))
    return fallback


def _speech_radius_for(speaker) -> int:
    return max(1, int(getattr(speaker, "speech_volume", DEFAULT_AUDIBLE_RADIUS) or DEFAULT_AUDIBLE_RADIUS))


def _speech_id(speaker_id, listener_id, text: str, source_type: str, source_record_id: str | None, bucket: int) -> str:
    seed = "|".join([str(speaker_id), str(listener_id), text.lower(), str(source_type), str(source_record_id or ""), str(bucket)])
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _current_tick(world) -> int:
    return int(getattr(world, "game_time", 0) or 0)


def _entity_position(entity) -> tuple[int, int]:
    return int(getattr(entity, "x", 0)), int(getattr(entity, "y", 0))


def _distance_to_player(player, position: tuple[int, int]) -> int:
    if player is None:
        return 0
    return abs(int(getattr(player, "x", 0)) - int(position[0])) + abs(int(getattr(player, "y", 0)) - int(position[1]))


def _clean_text(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def _shorten_text(text: str, limit: int) -> str:
    text = _clean_text(text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _generic_murmur_for(line: AmbientSpeechLine) -> str:
    if line.source_type == "warning":
        return "hushed warning"
    if line.source_type == "celebration":
        return "excited chatter"
    if line.source_type == "social_reaction":
        return "emotional murmurs"
    return "murmuring"
