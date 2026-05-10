"""Lightweight social scenes for ambient conversations and overhearing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from presentation.dialogue_surface import DialogueTopic
from simulation.activity import can_actor_observe_nearby_events, is_actor_available_for_conversation
from simulation.systems.ambient_info import score_ambient_conversation_pair, share_known_fact

SCENE_UPDATE_INTERVAL_TICKS = 20
SCENE_INACTIVE_TICKS = 180
MAX_SCENE_PARTICIPANTS = 6
SCENE_PROXIMITY_RADIUS = 4
PUBLIC_EVENT_SEED_TTL_TICKS = 600
PUBLIC_EVENT_SEED_RADIUS = 8


@dataclass
class PublicEventSeed:
    """Temporary public social pressure created by an important record or reaction."""

    seed_id: str
    seed_type: str
    source_record_id: str
    created_tick: int
    expires_tick: int
    location: tuple[int, int] | None = None
    building_id: str | None = None
    settlement_id: str | None = None
    region_id: str | None = None
    participant_ids: list[int] = field(default_factory=list)
    tone: str = "neutral"
    topic_hints: list[str] = field(default_factory=list)


@dataclass
class SocialScene:
    """A small local cluster of NPCs sharing social context."""

    scene_id: str
    scene_type: str = "generic"
    location: tuple[int, int] | None = None
    building_id: str | None = None
    region_id: str | None = None
    participant_ids: list[int] = field(default_factory=list)
    started_tick: int = 0
    last_active_tick: int = 0
    tone: str = "neutral"
    active_topic_ids: list[str] = field(default_factory=list)
    overheard_record_ids: set[str] = field(default_factory=set)
    public_event_seed_ids: list[str] = field(default_factory=list)


def create_public_event_seed_from_record(world, record, *, current_tick: int | None = None) -> PublicEventSeed | None:
    """Create or refresh a narrow public scene seed for an important typed record."""
    seed_kind = _seed_kind_for_record(record)
    if seed_kind is None:
        return None
    seed_type, tone, topic_hints = seed_kind
    created_tick = _current_tick(world) if current_tick is None else int(current_tick)
    source_record_id = str(getattr(record, "record_id", getattr(record, "id", "")) or "")
    if not source_record_id:
        return None
    seed = PublicEventSeed(
        seed_id=f"public_event:{seed_type}:{source_record_id}",
        seed_type=seed_type,
        source_record_id=source_record_id,
        created_tick=created_tick,
        expires_tick=created_tick + PUBLIC_EVENT_SEED_TTL_TICKS,
        location=_record_location(record),
        building_id=_record_building_id(record),
        settlement_id=_record_settlement_id(record),
        region_id=_record_region_id(record),
        participant_ids=list(_record_participant_ids(record)),
        tone=tone,
        topic_hints=list(topic_hints),
    )
    _public_event_seed_store(world)[seed.seed_id] = seed
    return seed


def create_public_event_seed_from_reaction(world, reaction: dict, *, current_tick: int | None = None) -> PublicEventSeed | None:
    """Create or refresh a public scene seed from a strong lightweight social reaction."""
    seed_kind = _seed_kind_for_reaction(reaction)
    if seed_kind is None:
        return None
    seed_type, tone, topic_hints = seed_kind
    created_tick = _current_tick(world) if current_tick is None else int(current_tick)
    source_record_id = str(reaction.get("source_record_id") or "")
    if not source_record_id:
        return None
    participant_ids = [
        value
        for value in (reaction.get("target_entity_id"), reaction.get("related_entity_id"))
        if isinstance(value, int)
    ]
    seed = PublicEventSeed(
        seed_id=f"public_reaction:{seed_type}:{source_record_id}",
        seed_type=seed_type,
        source_record_id=source_record_id,
        created_tick=created_tick,
        expires_tick=created_tick + PUBLIC_EVENT_SEED_TTL_TICKS,
        participant_ids=list(dict.fromkeys(participant_ids)),
        tone=tone,
        topic_hints=list(topic_hints),
    )
    _public_event_seed_store(world)[seed.seed_id] = seed
    return seed


def get_active_public_event_seeds(world) -> list[PublicEventSeed]:
    """Return non-expired public event seeds for the current world tick."""
    current_tick = _current_tick(world)
    _expire_public_event_seeds(world, current_tick)
    return [seed for seed in _public_event_seed_store(world).values() if seed.expires_tick > current_tick]


def update_social_scenes(world, *, force: bool = False) -> list[SocialScene]:
    """Create, refresh, and expire small local social scenes."""
    current_tick = _current_tick(world)
    if not hasattr(world, "social_scenes"):
        world.social_scenes = {}
    active_seeds = get_active_public_event_seeds(world)
    if not force and current_tick < int(getattr(world, "next_social_scene_update_tick", 0) or 0):
        return list(world.social_scenes.values())

    world.next_social_scene_update_tick = current_tick + SCENE_UPDATE_INTERVAL_TICKS
    _expire_social_scenes(world, current_tick)

    grouped: dict[tuple[Any, ...], list] = {}
    for npc in list(getattr(world, "village_npcs", []) or []):
        if not _eligible_scene_participant(npc):
            continue
        key = _scene_group_key(world, npc)
        grouped.setdefault(key, []).append(npc)
        for seed in active_seeds:
            if _npc_is_near_public_seed(npc, seed):
                grouped.setdefault(("public_seed", seed.seed_id), []).append(npc)

    for key, participants in grouped.items():
        if len(participants) < 2:
            continue
        participants = _limit_nearby_participants(participants)
        if len(participants) < 2:
            continue
        scene_type, building_id, region_id, location = _scene_details_from_key(world, key, participants)
        scene_id = _scene_id(scene_type, building_id, region_id, location)
        scene = world.social_scenes.get(scene_id)
        if scene is None:
            scene = SocialScene(
                scene_id=scene_id,
                scene_type=scene_type,
                location=location,
                building_id=building_id,
                region_id=region_id,
                started_tick=current_tick,
            )
            world.social_scenes[scene_id] = scene
        scene.scene_type = scene_type
        scene.location = location
        scene.building_id = building_id
        scene.region_id = region_id
        scene.participant_ids = [int(getattr(npc, "id")) for npc in participants if getattr(npc, "id", None) is not None]
        scene.last_active_tick = current_tick
        if key[0] == "public_seed":
            seed = _public_event_seed_store(world).get(str(key[1]))
            _apply_public_seed_to_scene(scene, seed)
        else:
            _apply_nearby_public_seed_to_scene(scene, active_seeds)

    _expire_social_scenes(world, current_tick)
    return list(world.social_scenes.values())


def choose_strongest_social_scene(world) -> SocialScene | None:
    """Return the strongest currently active scene that can support a pair interaction."""
    scenes = update_social_scenes(world)
    candidates = []
    for scene in scenes:
        pair = choose_scene_interaction_pair(scene, world)
        if pair is None:
            continue
        score = _scene_strength(scene, world, pair)
        candidates.append((score, scene.scene_id, scene))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


def choose_scene_interaction_pair(scene: SocialScene, world):
    """Choose one speaker/listener pair within a scene using ambient pair scoring."""
    participants = _scene_participants(scene, world)
    candidates = []
    for speaker in participants:
        for listener in participants:
            if getattr(speaker, "id", None) == getattr(listener, "id", None):
                continue
            score = score_ambient_conversation_pair(speaker, listener, world)
            if score <= 0.0:
                continue
            candidates.append((score, getattr(speaker, "id", 0), getattr(listener, "id", 0), speaker, listener))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], -int(item[1] or 0), -int(item[2] or 0)), reverse=True)
    return candidates[0][3], candidates[0][4]


def find_scene_for_pair(world, speaker, listener) -> SocialScene | None:
    """Find an active scene containing both actors, if one exists."""
    speaker_id = getattr(speaker, "id", None)
    listener_id = getattr(listener, "id", None)
    if speaker_id is None or listener_id is None:
        return None
    for scene in update_social_scenes(world):
        ids = set(scene.participant_ids)
        if speaker_id in ids and listener_id in ids:
            return scene
    return None


def record_scene_topic(scene: SocialScene | None, topic: DialogueTopic | None, world) -> None:
    """Update scene topic memory and tone from a spoken topic."""
    if scene is None or topic is None:
        return
    topic_id = f"{topic.topic_type}:{topic.source_id}"
    if topic_id in scene.active_topic_ids:
        scene.active_topic_ids.remove(topic_id)
    scene.active_topic_ids.insert(0, topic_id)
    del scene.active_topic_ids[8:]
    scene.tone = _tone_for_topic(topic, scene.tone)
    scene.last_active_tick = _current_tick(world)


def share_fact_with_scene_overhearers(world, scene: SocialScene | None, speaker, listener, fact) -> int:
    """Teach a shared fact to eligible bystanders in the same scene as overheard."""
    if scene is None or fact is None:
        return 0
    speaker_id = getattr(speaker, "id", None)
    listener_id = getattr(listener, "id", None)
    shared = 0
    for participant in _scene_participants(scene, world):
        participant_id = getattr(participant, "id", None)
        if participant_id in {speaker_id, listener_id}:
            continue
        if not _eligible_overhearer(participant):
            continue
        if share_known_fact(speaker, participant, fact, source_type="overheard", current_tick=_current_tick(world)):
            shared += 1
    if shared:
        record_id = str(getattr(fact, "source_record_id", "") or "")
        if record_id:
            scene.overheard_record_ids.add(record_id)
        scene.last_active_tick = _current_tick(world)
    return shared


def _eligible_scene_participant(npc) -> bool:
    if getattr(getattr(npc, "physical", None), "is_dead", False):
        return False
    if getattr(getattr(npc, "combat", None), "is_hostile_to_player", False):
        return False
    return is_actor_available_for_conversation(npc) and can_actor_observe_nearby_events(npc)


def _eligible_overhearer(npc) -> bool:
    return _eligible_scene_participant(npc)


def _scene_group_key(world, npc) -> tuple[Any, ...]:
    building_id = _building_id_for(npc)
    region_id = _region_id_for(npc)
    if building_id:
        return ("building", str(building_id), region_id)
    activity = getattr(npc, "current_activity", None)
    coords = getattr(activity, "anchor_coords", None) or getattr(activity, "location", None)
    activity_type = str(getattr(activity, "activity_type", "") or "")
    if coords is not None:
        return ("activity", activity_type, int(coords[0]) // 4, int(coords[1]) // 4, region_id)
    return ("street", int(getattr(npc, "x", 0)) // 4, int(getattr(npc, "y", 0)) // 4, region_id)


def _scene_details_from_key(world, key: tuple[Any, ...], participants: list) -> tuple[str, str | None, str | None, tuple[int, int]]:
    key_type = key[0]
    if key_type == "public_seed":
        seed = _public_event_seed_store(world).get(str(key[1]))
        if seed is not None:
            return seed.seed_type, seed.building_id, seed.region_id, seed.location or _average_location(participants)
    if key_type == "building":
        building_id = str(key[1])
        region_id = key[2]
        return _scene_type_for_building(world, building_id), building_id, region_id, _average_location(participants)
    if key_type == "activity":
        activity_type = str(key[1] or "")
        scene_type = "worksite" if activity_type.startswith("work:") or activity_type == "forging" else "generic"
        return scene_type, None, key[4], _average_location(participants)
    return "street", None, key[3], _average_location(participants)


def _scene_type_for_building(world, building_id: str) -> str:
    building = getattr(world, "buildings_by_id", {}).get(building_id) if hasattr(world, "buildings_by_id") else None
    building_type = str(getattr(building, "building_type", "") or building_id).lower()
    category = str(getattr(building, "category", "") or "").lower()
    if "tavern" in building_type:
        return "tavern"
    if "work" in category or "workplace" in category or "smith" in building_type or "forge" in building_type:
        return "worksite"
    if "market" in building_type or "store" in building_type or "shop" in building_type:
        return "market"
    if "home" in building_type or "house" in building_type or "residential" in category:
        return "home"
    return "generic"


def _building_id_for(npc) -> str | None:
    for attr_name in ("current_building_id", "location_building_id", "building_id"):
        value = getattr(npc, attr_name, None)
        if value:
            return str(value)
    schedule = getattr(npc, "schedule", None)
    current_task = str(getattr(schedule, "current_task", "") or "").lower()
    work_building_id = getattr(schedule, "work_building_id", None)
    home_building_id = getattr(schedule, "home_building_id", None)
    if work_building_id and ("work" in current_task or current_task in {"forging", "at work"}):
        return str(work_building_id)
    if home_building_id and ("home" in current_task or current_task in {"sitting"}):
        return str(home_building_id)
    return str(work_building_id or home_building_id) if (work_building_id or home_building_id) else None


def _region_id_for(npc) -> str | None:
    for attr_name in ("region_id", "current_region_id"):
        value = getattr(npc, attr_name, None)
        if value is not None:
            return str(value)
    return None


def _limit_nearby_participants(participants: list) -> list:
    participants = sorted(participants, key=lambda npc: int(getattr(npc, "id", 0) or 0))
    best_group: list = []
    for anchor in participants:
        group = [npc for npc in participants if _distance(anchor, npc) <= SCENE_PROXIMITY_RADIUS]
        if len(group) > len(best_group):
            best_group = group
    return best_group[:MAX_SCENE_PARTICIPANTS]


def _scene_participants(scene: SocialScene, world) -> list:
    get_entity = getattr(world, "get_entity_by_id", None)
    participants = []
    for entity_id in scene.participant_ids:
        entity = get_entity(entity_id) if callable(get_entity) else None
        if entity is None:
            entity = next((npc for npc in getattr(world, "village_npcs", []) if getattr(npc, "id", None) == entity_id), None)
        if entity is not None and _eligible_scene_participant(entity):
            participants.append(entity)
    return participants


def _scene_strength(scene: SocialScene, world, pair) -> float:
    speaker, listener = pair
    public_seed_bonus = 18.0 if getattr(scene, "public_event_seed_ids", None) else 0.0
    return (len(scene.participant_ids) * 10.0) + public_seed_bonus + score_ambient_conversation_pair(speaker, listener, world)


def _expire_social_scenes(world, current_tick: int) -> None:
    scenes = getattr(world, "social_scenes", {}) or {}
    active_seed_ids = {seed.seed_id for seed in get_active_public_event_seeds(world)}
    expired = []
    for scene_id, scene in scenes.items():
        if current_tick - int(scene.last_active_tick) > SCENE_INACTIVE_TICKS:
            expired.append(scene_id)
            continue
        seed_ids = set(getattr(scene, "public_event_seed_ids", []) or [])
        if seed_ids and seed_ids.isdisjoint(active_seed_ids):
            expired.append(scene_id)
    for scene_id in expired:
        scenes.pop(scene_id, None)



def _public_event_seed_store(world) -> dict[str, PublicEventSeed]:
    seeds = getattr(world, "public_event_seeds", None)
    if seeds is None:
        seeds = {}
        world.public_event_seeds = seeds
    if isinstance(seeds, list):
        seeds = {seed.seed_id: seed for seed in seeds}
        world.public_event_seeds = seeds
    return seeds


def _expire_public_event_seeds(world, current_tick: int) -> None:
    seeds = _public_event_seed_store(world)
    for seed_id, seed in list(seeds.items()):
        if int(getattr(seed, "expires_tick", 0) or 0) <= current_tick:
            seeds.pop(seed_id, None)


def _seed_kind_for_record(record) -> tuple[str, str, tuple[str, ...]] | None:
    class_name = type(record).__name__
    event_type = str(getattr(record, "event_type", getattr(record, "type", "")) or "")
    tags = {str(tag) for tag in getattr(record, "tags", ()) or ()}
    if class_name == "DeathRecord" or event_type == "entity_death" or "death" in tags:
        return "funeral", "grieving", ("death", "grief")
    if class_name == "CrimeRecord" or "crime" in event_type or "crime" in tags:
        return "accusation", "tense", ("crime", "fear")
    if class_name in {"BirthRecord", "MarriageRecord"} or event_type in {"npc_birth", "npc_marriage"} or {"birth", "marriage"} & tags:
        hints = ("birth",) if class_name == "BirthRecord" or event_type == "npc_birth" or "birth" in tags else ("marriage",)
        return "celebration", "celebratory", hints
    if class_name == "MigrationRecord" or event_type in {"npc_migrated", "npc_emigrated"} or "migration" in tags:
        return "celebration", "curious", ("migration", "curiosity")
    if class_name == "EmploymentRecord" or "employment" in event_type or {"economy", "employment"} & tags:
        return "market_concern", "concerned", ("employment", "migration")
    return None


def _seed_kind_for_reaction(reaction: dict) -> tuple[str, str, tuple[str, ...]] | None:
    reaction_type = str(reaction.get("reaction_type", "") or "")
    score = abs(float(reaction.get("score", 0.0) or 0.0))
    if reaction_type == "fear" and score >= 6.0:
        return "warning", "tense", ("fear", "crime")
    if reaction_type == "grief" and score >= 6.0:
        return "funeral", "grieving", ("grief", "death")
    if reaction_type == "respect" and score >= 6.0:
        return "celebration", "celebratory", ("respect",)
    if reaction_type == "curiosity" and score >= 4.0:
        return "market_concern", "curious", ("curiosity",)
    return None


def _record_location(record) -> tuple[int, int] | None:
    location = getattr(record, "location", None)
    if isinstance(location, tuple) and len(location) == 2:
        return int(location[0]), int(location[1])
    if isinstance(location, list) and len(location) == 2:
        return int(location[0]), int(location[1])
    return None


def _record_building_id(record) -> str | None:
    value = getattr(record, "building_id", None) or getattr(record, "metadata", {}).get("building_id")
    return str(value) if value else None


def _record_settlement_id(record) -> str | None:
    value = getattr(record, "settlement_id", None) or getattr(record, "metadata", {}).get("settlement_id")
    return str(value) if value else None


def _record_region_id(record) -> str | None:
    value = getattr(record, "region_id", None) or getattr(record, "metadata", {}).get("region_id")
    return str(value) if value else None


def _record_participant_ids(record) -> tuple[int, ...]:
    participants = []
    for value in getattr(record, "participant_ids", ()) or ():
        if isinstance(value, int):
            participants.append(value)
    return tuple(dict.fromkeys(participants))


def _npc_is_near_public_seed(npc, seed: PublicEventSeed) -> bool:
    npc_id = getattr(npc, "id", None)
    if npc_id in set(seed.participant_ids):
        return True
    if seed.region_id is not None:
        npc_region = _region_id_for(npc)
        if npc_region is not None and str(npc_region) != str(seed.region_id):
            return False
    if seed.location is None:
        return False
    return _distance_to_location(npc, seed.location) <= PUBLIC_EVENT_SEED_RADIUS


def _apply_nearby_public_seed_to_scene(scene: SocialScene, active_seeds: list[PublicEventSeed]) -> None:
    if scene.location is None:
        return
    candidates = [
        seed for seed in active_seeds
        if seed.location is not None and _location_distance(scene.location, seed.location) <= PUBLIC_EVENT_SEED_RADIUS
    ]
    if not candidates:
        return
    candidates.sort(key=lambda seed: (seed.created_tick, seed.seed_id), reverse=True)
    _apply_public_seed_to_scene(scene, candidates[0])


def _apply_public_seed_to_scene(scene: SocialScene, seed: PublicEventSeed | None) -> None:
    if seed is None:
        return
    scene.scene_type = seed.seed_type
    scene.tone = seed.tone or scene.tone
    if seed.building_id is not None:
        scene.building_id = seed.building_id
    if seed.region_id is not None:
        scene.region_id = seed.region_id
    if seed.location is not None:
        scene.location = seed.location
    if seed.seed_id not in scene.public_event_seed_ids:
        scene.public_event_seed_ids.insert(0, seed.seed_id)
        del scene.public_event_seed_ids[4:]
    for topic_hint in reversed(seed.topic_hints):
        topic_id = f"{topic_hint}:{seed.source_record_id}"
        if topic_id in scene.active_topic_ids:
            scene.active_topic_ids.remove(topic_id)
        scene.active_topic_ids.insert(0, topic_id)
    del scene.active_topic_ids[8:]


def _tone_for_topic(topic: DialogueTopic, current_tone: str) -> str:
    topic_type = str(getattr(topic, "topic_type", "") or "")
    if topic_type in {"death", "grief"}:
        return "grieving"
    if topic_type in {"fear"}:
        return "fearful"
    if topic_type in {"crime"}:
        return "tense"
    if topic_type in {"birth", "marriage"}:
        return "celebratory"
    if topic_type in {"migration", "curiosity"} and current_tone == "neutral":
        return "neutral"
    return current_tone or "neutral"


def _average_location(participants: list) -> tuple[int, int]:
    if not participants:
        return (0, 0)
    return (
        round(sum(int(getattr(npc, "x", 0)) for npc in participants) / len(participants)),
        round(sum(int(getattr(npc, "y", 0)) for npc in participants) / len(participants)),
    )


def _scene_id(scene_type: str, building_id: str | None, region_id: str | None, location: tuple[int, int]) -> str:
    if building_id:
        return f"scene:{scene_type}:building:{building_id}:{region_id or ''}"
    return f"scene:{scene_type}:tile:{int(location[0]) // 4}:{int(location[1]) // 4}:{region_id or ''}"


def _current_tick(world) -> int:
    return int(getattr(world, "game_time", 0) or 0)


def _distance(left, right) -> int:
    return abs(int(getattr(left, "x", 0)) - int(getattr(right, "x", 0))) + abs(int(getattr(left, "y", 0)) - int(getattr(right, "y", 0)))


def _distance_to_location(entity, location: tuple[int, int]) -> int:
    return abs(int(getattr(entity, "x", 0)) - int(location[0])) + abs(int(getattr(entity, "y", 0)) - int(location[1]))


def _location_distance(left: tuple[int, int], right: tuple[int, int]) -> int:
    return abs(int(left[0]) - int(right[0])) + abs(int(left[1]) - int(right[1]))
