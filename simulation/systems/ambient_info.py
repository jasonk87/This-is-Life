"""Lightweight structured history-fact sharing during ambient conversation."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from typing import Any

from config import DAY_LENGTH_TICKS
from entities.social import KnownHistoryFact, compute_memory_profile, fact_with_memory_profile, reinforce_known_fact
from presentation.dialogue_surface import (
    build_dialogue_topic_from_fact,
    is_dialogue_topic_on_cooldown,
)
from simulation.activity import is_actor_available_for_conversation

SHARE_COOLDOWN_TICKS = 80
PAIR_SHARE_COOLDOWN_TICKS = 160
MIN_SHARE_SCORE = 18.0

HIGH_PRIORITY_TOPIC_TYPES = {"crime", "fear", "grief", "death"}
MEDIUM_PRIORITY_TOPIC_TYPES = {"birth", "marriage", "migration"}
LOW_PRIORITY_TOPIC_TYPES = {"employment"}


def can_share_known_fact(speaker, listener, fact, world) -> bool:
    """Return whether a speaker may share one structured history fact now."""
    if speaker is None or listener is None or fact is None:
        return False
    speaker_knowledge = getattr(speaker, "knowledge", None)
    listener_knowledge = getattr(listener, "knowledge", None)
    if speaker_knowledge is None or listener_knowledge is None:
        return False

    fact_id = str(getattr(fact, "source_record_id", "") or "")
    if not fact_id:
        return False
    if fact_id not in getattr(speaker_knowledge, "known_history_facts", {}):
        return False
    if fact_id in getattr(listener_knowledge, "known_history_facts", {}):
        return False
    if _speaker_already_told_listener(speaker, listener, fact_id):
        return False
    if not _actor_can_share_now(speaker) or not is_actor_available_for_conversation(listener):
        return False
    if _on_share_cooldown(speaker, listener, world):
        return False

    topic = build_dialogue_topic_from_fact(fact, world)
    if topic is None:
        return False
    if is_dialogue_topic_on_cooldown(speaker, topic, world):
        return False
    if _fact_relevance_score(speaker, listener, fact, topic, world) < MIN_SHARE_SCORE:
        return False
    return _passes_relationship_persona_activity_gate(speaker, listener, fact, topic, world)


def choose_shareable_fact(speaker, listener, world):
    """Choose the best known structured fact worth sharing, or ``None``."""
    knowledge = getattr(speaker, "knowledge", None)
    known_facts = getattr(knowledge, "known_history_facts", {}) if knowledge else {}
    candidates = []
    for fact in known_facts.values():
        if not can_share_known_fact(speaker, listener, fact, world):
            continue
        topic = build_dialogue_topic_from_fact(fact, world)
        if topic is None:
            continue
        score = _fact_relevance_score(speaker, listener, fact, topic, world)
        score += _stable_fraction(f"share-order:{getattr(speaker, 'id', '')}:{getattr(listener, 'id', '')}:{topic.source_id}")
        candidates.append((score, str(getattr(fact, "source_record_id", "")), fact))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


def share_known_fact(speaker, listener, fact, source_type: str = "told", current_tick: int | None = None) -> bool:
    """Transfer a structured fact to the listener with slight confidence decay."""
    listener_knowledge = getattr(listener, "knowledge", None)
    if listener_knowledge is None or fact is None:
        return False
    fact_id = str(getattr(fact, "source_record_id", "") or "")
    if not fact_id:
        return False
    current_tick = int(getattr(fact, "known_at_tick", 0) if current_tick is None else current_tick)
    speaker_id = getattr(speaker, "id", None)
    existing = getattr(listener_knowledge, "known_history_facts", {}).get(fact_id)
    if existing is not None:
        # Repetition from somebody already counted is not corroboration, and
        # must not make the memory sturdier - the same rule
        # KnowledgeComponent.learn_history_record applies. This path builds its
        # facts by hand rather than going through that, so it has to say so
        # itself.
        heard_from = tuple(getattr(existing, "heard_from_ids", ()) or ())
        teller_is_new = speaker_id is not None and int(speaker_id) not in heard_from
        if speaker_id is not None and not teller_is_new:
            return False
        reinforced = reinforce_known_fact(
            listener_knowledge,
            fact_id,
            tick=current_tick,
            source_type=source_type,
            emotional_weight=float(getattr(fact, "emotional_weight", 0.0) or 0.0),
        )
        if reinforced and speaker_id is not None:
            updated = listener_knowledge.known_history_facts[fact_id]
            listener_knowledge.known_history_facts[fact_id] = replace(
                updated,
                source_entity_id=int(speaker_id),
                heard_from_ids=heard_from + (int(speaker_id),),
            )
        return bool(reinforced)

    confidence = _decayed_confidence(float(getattr(fact, "confidence", 0.0)), source_type=source_type)
    new_fact = KnownHistoryFact(
        source_record_id=fact_id,
        record_type=str(getattr(fact, "record_type", "") or ""),
        subject_entity_ids=tuple(getattr(fact, "subject_entity_ids", ()) or ()),
        known_at_tick=current_tick,
        source_type=str(source_type),
        confidence=confidence,
        settlement_id=getattr(fact, "settlement_id", None),
        region_id=getattr(fact, "region_id", None),
        tags=tuple(getattr(fact, "tags", ()) or ()),
        record_class_name=str(getattr(fact, "record_class_name", "") or ""),
        # Who said it, so "who did you hear that from?" has an answer on this
        # route too. Conversation and overheard scenes come through here rather
        # than through KnowledgeSystem.share_event, and used to drop the speaker
        # entirely - the listener ended up knowing something with no idea where
        # it came from.
        source_entity_id=None if speaker_id is None else int(speaker_id),
        heard_from_ids=() if speaker_id is None else (int(speaker_id),),
        # And the speaker's claim, not a fresh one. subject_entity_ids is copied
        # above so the belief's content already carries across, but without the
        # claim id the listener's belief was not recognisably the same assertion
        # as the speaker's - believers_of would not have counted them together.
        claim_id=str(getattr(fact, "claim_id", "") or ""),
    )
    profile = compute_memory_profile(
        source_type=str(source_type),
        confidence=confidence,
        tags=new_fact.tags,
        record_type=new_fact.record_type,
        record_class_name=new_fact.record_class_name,
    )
    listener_knowledge.known_history_facts[fact_id] = fact_with_memory_profile(new_fact, profile, tick=current_tick)
    _remember_pair_fact_shared(speaker, listener, fact_id)
    return True


def mark_share_cooldowns(speaker, listener, world) -> None:
    """Apply per-speaker and per-pair cooldowns after a fact-sharing attempt succeeds."""
    current_tick = _current_tick(world)
    setattr(speaker, "known_fact_share_cooldown_until", current_tick + SHARE_COOLDOWN_TICKS)
    key = _pair_key(speaker, listener)
    pair_cooldowns = _ensure_pair_cooldowns(speaker)
    pair_cooldowns[key] = current_tick + PAIR_SHARE_COOLDOWN_TICKS


def _actor_can_share_now(actor) -> bool:
    if not is_actor_available_for_conversation(actor):
        return False
    activity = getattr(actor, "current_activity", None)
    if activity is not None and not getattr(activity, "allows_social_sharing", False):
        return False
    if getattr(getattr(actor, "physical", None), "is_dead", False):
        return False
    if getattr(getattr(actor, "combat", None), "is_hostile_to_player", False):
        return False
    return True


def _on_share_cooldown(speaker, listener, world) -> bool:
    current_tick = _current_tick(world)
    if current_tick < int(getattr(speaker, "known_fact_share_cooldown_until", 0) or 0):
        return True
    return current_tick < int(_ensure_pair_cooldowns(speaker).get(_pair_key(speaker, listener), 0) or 0)


def _fact_relevance_score(speaker, listener, fact, topic, world) -> float:
    topic_type = str(getattr(topic, "topic_type", "") or "")
    if topic_type in HIGH_PRIORITY_TOPIC_TYPES:
        score = 58.0
    elif topic_type in MEDIUM_PRIORITY_TOPIC_TYPES:
        score = 36.0
    elif topic_type in LOW_PRIORITY_TOPIC_TYPES:
        score = 18.0
    else:
        score = 24.0

    confidence = max(0.0, min(1.0, float(getattr(fact, "confidence", 0.0))))
    score += confidence * 12.0
    score += _relationship_bonus(speaker, listener)
    score += _activity_bonus(speaker)
    score += _listener_relevance_bonus(listener, fact, topic, world)
    age = max(0, _current_tick(world) - int(getattr(fact, "known_at_tick", 0) or 0))
    if age <= DAY_LENGTH_TICKS:
        score += 8.0
    return score


def _passes_relationship_persona_activity_gate(speaker, listener, fact, topic, world) -> bool:
    chance = 0.12
    topic_type = str(getattr(topic, "topic_type", "") or "")
    if topic_type in HIGH_PRIORITY_TOPIC_TYPES:
        chance += 0.50
    elif topic_type in MEDIUM_PRIORITY_TOPIC_TYPES:
        chance += 0.28
    elif topic_type in LOW_PRIORITY_TOPIC_TYPES:
        chance += 0.10
    chance += min(0.20, _relationship_bonus(speaker, listener) / 100.0)
    chance += min(0.12, _activity_bonus(speaker) / 100.0)

    personality = str(getattr(getattr(speaker, "social", None), "personality", "") or "").lower()
    if personality in {"friendly", "generous", "gregarious", "curious"}:
        chance += 0.12
    # "withdrawn" is a drift-only trait (see NPC.record_trait_pressure /
    # World._apply_bereavement_trait_drift) - it never appears in the base
    # LLM-generated personality string, only in activated_traits, so it's
    # checked separately rather than folded into the exact-match check
    # above (which is intentionally left as-is to avoid changing existing
    # base-personality behavior here).
    speaker_activated_traits = set(getattr(getattr(speaker, "social", None), "activated_traits", None) or ())
    if personality in {"reserved", "shy", "secretive"} or "withdrawn" in speaker_activated_traits:
        chance -= 0.12

    confidence = max(0.0, min(1.0, float(getattr(fact, "confidence", 0.0))))
    if confidence < 0.45:
        chance -= 0.10
    if _listener_relevance_bonus(listener, fact, topic, world) >= 15.0:
        chance += 0.10
    if _fact_relevance_score(speaker, listener, fact, topic, world) >= 90.0:
        return True

    chance = max(0.05, min(0.95, chance))
    gate = _stable_fraction(
        f"share-gate:{getattr(speaker, 'id', '')}:{getattr(listener, 'id', '')}:{getattr(fact, 'source_record_id', '')}:{_current_tick(world) // 20}"
    )
    return gate <= chance


def _listener_relevance_bonus(listener, fact, topic, world) -> float:
    listener_id = getattr(listener, "id", None)
    subject_ids = set(getattr(fact, "subject_entity_ids", ()) or ())
    if listener_id in subject_ids:
        return 25.0

    listener_knowledge = getattr(listener, "knowledge", None)
    if listener_knowledge is not None:
        for listener_fact in getattr(listener_knowledge, "known_history_facts", {}).values():
            if subject_ids.intersection(getattr(listener_fact, "subject_entity_ids", ()) or ()):
                return 18.0

    listener_profession = _profession(listener)
    record = _history_record(world, getattr(fact, "source_record_id", ""))
    record_profession = _profession(record)
    if listener_profession and record_profession and listener_profession == record_profession:
        return 16.0

    listener_village = _settlement_id_for(listener, world)
    fact_settlement = getattr(fact, "settlement_id", None)
    if listener_village and fact_settlement and str(listener_village) == str(fact_settlement):
        return 10.0
    return 0.0


def _relationship_bonus(speaker, listener) -> float:
    relationships = getattr(getattr(speaker, "social", None), "relationships", {}) or {}
    score = relationships.get(getattr(listener, "id", None), 50)
    try:
        score = float(score)
    except (TypeError, ValueError):
        score = 50.0
    if score >= 80:
        return 22.0
    if score >= 65:
        return 14.0
    if score <= 25:
        return -12.0
    return 0.0


def _activity_bonus(actor) -> float:
    activity = getattr(actor, "current_activity", None)
    if activity is None:
        return 4.0
    activity_type = str(getattr(activity, "activity_type", "") or "")
    if activity_type in {"sitting", "idle_social", "resting"}:
        return 12.0
    if activity_type.startswith("work:") or activity_type == "forging":
        return 6.0
    return 0.0


def _decayed_confidence(confidence: float, *, source_type: str = "told") -> float:
    multiplier = 0.55 if str(source_type) == "overheard" else 0.85
    return max(0.05, min(0.95, confidence * multiplier))


def _speaker_already_told_listener(speaker, listener, fact_id: str) -> bool:
    shared = _ensure_shared_fact_listener_ids(speaker)
    return int(getattr(listener, "id", 0) or 0) in shared.get(str(fact_id), set())


def _remember_pair_fact_shared(speaker, listener, fact_id: str) -> None:
    shared = _ensure_shared_fact_listener_ids(speaker)
    shared.setdefault(str(fact_id), set()).add(int(getattr(listener, "id", 0) or 0))


def _ensure_pair_cooldowns(speaker) -> dict[str, int]:
    knowledge = getattr(speaker, "knowledge", None)
    if knowledge is not None:
        if not hasattr(knowledge, "fact_share_pair_cooldowns"):
            knowledge.fact_share_pair_cooldowns = {}
        return knowledge.fact_share_pair_cooldowns
    if not hasattr(speaker, "fact_share_pair_cooldowns"):
        speaker.fact_share_pair_cooldowns = {}
    return speaker.fact_share_pair_cooldowns


def _ensure_shared_fact_listener_ids(speaker) -> dict[str, set[int]]:
    knowledge = getattr(speaker, "knowledge", None)
    if knowledge is not None:
        if not hasattr(knowledge, "shared_fact_listener_ids"):
            knowledge.shared_fact_listener_ids = {}
        return knowledge.shared_fact_listener_ids
    if not hasattr(speaker, "shared_fact_listener_ids"):
        speaker.shared_fact_listener_ids = {}
    return speaker.shared_fact_listener_ids


def _pair_key(speaker, listener) -> str:
    return f"{getattr(speaker, 'id', '')}:{getattr(listener, 'id', '')}"


def _current_tick(world) -> int:
    return int(getattr(world, "game_time", 0) or 0)


def _stable_fraction(value: Any) -> float:
    digest = hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:8]
    return int(digest, 16) / 0xFFFFFFFF


def _profession(entity) -> str:
    if entity is None:
        return ""
    profession = getattr(entity, "profession", None)
    if profession is None:
        profession = getattr(getattr(entity, "economic", None), "profession", None)
    return str(profession or "").strip().lower()


def _history_record(world, record_id: str):
    history = getattr(world, "history", None)
    get_event = getattr(history, "get_event", None)
    if callable(get_event):
        return get_event(record_id)
    return None


def _settlement_id_for(entity, world) -> str | None:
    village_getter = getattr(world, "_get_village_for_npc", None)
    if callable(village_getter):
        village = village_getter(entity)
        village_id = getattr(village, "id", None)
        if village_id is not None:
            return str(village_id)
    return None

INITIATION_SPEAKER_COOLDOWN_TICKS = 70
INITIATION_PAIR_COOLDOWN_TICKS = 140
INITIATION_LOCATION_COOLDOWN_TICKS = 45
MIN_INITIATION_SCORE = 34.0
MAX_INITIATION_DISTANCE = 4

REFLECTIVE_TOPIC_TYPES = {"death", "grief", "crime", "fear"}
YOUTH_TOPIC_TYPES = {"birth", "marriage", "migration", "curiosity"}
WORK_TOPIC_TYPES = {"employment"}
PUBLIC_TOPIC_TYPES = {"crime", "fear", "death", "employment", "migration"}
HIGH_STATUS_TITLES = {"mayor", "sheriff", "captain", "elder", "guild", "chief", "council"}


def score_ambient_conversation_pair(speaker, listener, world) -> float:
    """Score whether this pair should start a lightweight ambient conversation."""
    if not _can_initiate_base(speaker, listener, world):
        return 0.0

    distance = _distance(speaker, listener)
    score = max(0.0, 24.0 - (distance * 4.0))
    score += _relationship_bonus(speaker, listener)
    score += _shared_context_bonus(speaker, listener, world)
    score += _knowledge_and_reaction_bonus(speaker, listener, world)
    score += _persona_age_role_bonus(speaker, listener, world)
    score -= _danger_avoidance_penalty(speaker, listener)

    if _on_initiation_cooldown(speaker, listener, world):
        return 0.0
    return max(0.0, score)


def choose_ambient_conversation_pair(world):
    """Choose the highest-scoring ambient speaker/listener pair, if any."""
    candidates = []
    npcs = list(getattr(world, "village_npcs", []) or [])
    for speaker in npcs:
        for listener in npcs:
            if getattr(speaker, "id", None) == getattr(listener, "id", None):
                continue
            score = score_ambient_conversation_pair(speaker, listener, world)
            if score < MIN_INITIATION_SCORE:
                continue
            score += _stable_fraction(f"ambient-init:{_current_tick(world)}:{getattr(speaker, 'id', '')}:{getattr(listener, 'id', '')}")
            candidates.append((score, getattr(speaker, "id", 0), getattr(listener, "id", 0), speaker, listener))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], -int(item[1] or 0), -int(item[2] or 0)), reverse=True)
    return candidates[0][3], candidates[0][4]


def mark_ambient_conversation_started(speaker, listener, world) -> None:
    """Apply speaker, pair, and coarse location cooldowns after ambient talk starts."""
    current_tick = _current_tick(world)
    setattr(speaker, "ambient_initiation_cooldown_until", current_tick + INITIATION_SPEAKER_COOLDOWN_TICKS)
    _ensure_initiation_pair_cooldowns(speaker)[_pair_key(speaker, listener)] = current_tick + INITIATION_PAIR_COOLDOWN_TICKS
    _ensure_location_cooldowns(world)[_location_key(speaker)] = current_tick + INITIATION_LOCATION_COOLDOWN_TICKS


def _can_initiate_base(speaker, listener, world) -> bool:
    if speaker is None or listener is None:
        return False
    if getattr(getattr(speaker, "physical", None), "is_dead", False):
        return False
    if getattr(getattr(listener, "physical", None), "is_dead", False):
        return False
    if getattr(getattr(speaker, "combat", None), "is_hostile_to_player", False):
        return False
    if getattr(getattr(listener, "combat", None), "is_hostile_to_player", False):
        return False
    if getattr(speaker, "conversation_partner_id", None) is not None:
        return False
    if getattr(listener, "conversation_partner_id", None) is not None:
        return False
    if getattr(speaker, "conversation_cooldown", 0) > 0 or getattr(listener, "conversation_cooldown", 0) > 0:
        return False
    if not is_actor_available_for_conversation(speaker) or not is_actor_available_for_conversation(listener):
        return False
    speaker_activity = getattr(speaker, "current_activity", None)
    if speaker_activity is not None and not getattr(speaker_activity, "allows_social_sharing", False):
        return False
    if _distance(speaker, listener) > MAX_INITIATION_DISTANCE:
        return False
    return True


def _on_initiation_cooldown(speaker, listener, world) -> bool:
    current_tick = _current_tick(world)
    if current_tick < int(getattr(speaker, "ambient_initiation_cooldown_until", 0) or 0):
        return True
    if current_tick < int(_ensure_initiation_pair_cooldowns(speaker).get(_pair_key(speaker, listener), 0) or 0):
        return True
    if current_tick < int(_ensure_location_cooldowns(world).get(_location_key(speaker), 0) or 0):
        return True
    return False


def _shared_context_bonus(speaker, listener, world) -> float:
    bonus = 0.0
    if _activity_type(speaker) and _activity_type(speaker) == _activity_type(listener):
        bonus += 10.0
    if _profession(speaker) and _profession(speaker) == _profession(listener):
        bonus += 8.0
    if getattr(getattr(speaker, "schedule", None), "work_building_id", None) and getattr(getattr(speaker, "schedule", None), "work_building_id", None) == getattr(getattr(listener, "schedule", None), "work_building_id", None):
        bonus += 8.0
    if getattr(getattr(speaker, "schedule", None), "home_building_id", None) and getattr(getattr(speaker, "schedule", None), "home_building_id", None) == getattr(getattr(listener, "schedule", None), "home_building_id", None):
        bonus += 6.0
    if _settlement_id_for(speaker, world) and _settlement_id_for(speaker, world) == _settlement_id_for(listener, world):
        bonus += 5.0
    return bonus


def _knowledge_and_reaction_bonus(speaker, listener, world) -> float:
    best_topic_score = 0.0
    for topic_type, confidence in _known_fact_topic_confidences(speaker, world):
        topic_score = _base_topic_initiation_score(topic_type) + (confidence * 8.0)
        topic_score += _topic_preference_bonus(speaker, topic_type)
        if _is_high_status(speaker) and topic_type in PUBLIC_TOPIC_TYPES:
            topic_score += 7.0
        best_topic_score = max(best_topic_score, topic_score)

    reaction_bonus = 0.0
    social = getattr(speaker, "social", None)
    for reaction in list(getattr(social, "recent_social_reactions", []) if social else [])[-5:]:
        reaction_type = str(reaction.get("reaction_type", ""))
        magnitude = min(12.0, abs(float(reaction.get("score", 0.0))) / 3.0)
        reaction_bonus = max(reaction_bonus, 8.0 + magnitude + _topic_preference_bonus(speaker, reaction_type))
    return max(best_topic_score, reaction_bonus)


def _persona_age_role_bonus(speaker, listener, world) -> float:
    bonus = 0.0
    personality = str(getattr(getattr(speaker, "social", None), "personality", "") or "").lower()
    if personality in {"friendly", "generous", "gregarious", "curious"}:
        bonus += 8.0
    if personality in {"reserved", "shy", "secretive"}:
        bonus -= 8.0
    if _age_group(speaker) == "elder":
        bonus += 3.0
    if _age_group(speaker) in {"child", "youth"}:
        bonus += 5.0
    if _profession(speaker) and _activity_type(speaker) and (_activity_type(speaker).startswith("work:") or _activity_type(speaker) == "forging"):
        bonus += 6.0
    if _is_high_status(speaker):
        bonus -= 8.0
    return bonus


def _danger_avoidance_penalty(speaker, listener) -> float:
    listener_id = getattr(listener, "id", None)
    if listener_id is None:
        return 0.0
    if getattr(getattr(listener, "combat", None), "is_hostile_to_player", False):
        return 100.0
    social = getattr(speaker, "social", None)
    if not social:
        return 0.0
    penalty = 0.0
    if getattr(social, "opinion_modifiers", {}).get(listener_id, 0.0) <= -10:
        penalty += 18.0
    if getattr(social, "grudges", {}).get(listener_id) is not None:
        penalty += 30.0
    for reaction in list(getattr(social, "recent_social_reactions", []) or [])[-8:]:
        if reaction.get("reaction_type") == "fear" and reaction.get("target_entity_id") == listener_id:
            penalty += 40.0
            break
    return penalty


def _known_fact_topic_confidences(speaker, world) -> list[tuple[str, float]]:
    facts = getattr(getattr(speaker, "knowledge", None), "known_history_facts", {}) or {}
    results = []
    for fact in facts.values():
        topic = build_dialogue_topic_from_fact(fact, world)
        if topic is None:
            continue
        results.append((str(getattr(topic, "topic_type", "") or ""), max(0.0, min(1.0, float(getattr(fact, "confidence", 0.0))))))
    return results


def _base_topic_initiation_score(topic_type: str) -> float:
    if topic_type in HIGH_PRIORITY_TOPIC_TYPES:
        return 18.0
    if topic_type in MEDIUM_PRIORITY_TOPIC_TYPES:
        return 12.0
    if topic_type in LOW_PRIORITY_TOPIC_TYPES:
        return 8.0
    return 6.0


def _topic_preference_bonus(speaker, topic_type: str) -> float:
    topic_type = str(topic_type or "")
    age_group = _age_group(speaker)
    profession = _profession(speaker)
    bonus = 0.0
    if age_group == "elder" and topic_type in REFLECTIVE_TOPIC_TYPES:
        bonus += 12.0
    if age_group in {"child", "youth"} and topic_type in YOUTH_TOPIC_TYPES:
        bonus += 10.0
    if profession and topic_type in WORK_TOPIC_TYPES:
        bonus += 12.0
    return bonus


def _age_group(entity) -> str | None:
    age = getattr(entity, "age", None)
    if age is None:
        return None
    try:
        age = int(age)
    except (TypeError, ValueError):
        return None
    if age < 13:
        return "child"
    if age < 20:
        return "youth"
    if age >= 65:
        return "elder"
    return "adult"


def _activity_type(entity) -> str:
    activity = getattr(entity, "current_activity", None)
    return str(getattr(activity, "activity_type", "") or "") if activity is not None else ""


def _is_high_status(entity) -> bool:
    title = str(getattr(getattr(entity, "social", None), "title", "") or "").lower()
    profession = _profession(entity)
    return any(term in title or term in profession for term in HIGH_STATUS_TITLES)


def _distance(left, right) -> int:
    return abs(int(getattr(left, "x", 0)) - int(getattr(right, "x", 0))) + abs(int(getattr(left, "y", 0)) - int(getattr(right, "y", 0)))


def _ensure_initiation_pair_cooldowns(speaker) -> dict[str, int]:
    knowledge = getattr(speaker, "knowledge", None)
    if knowledge is not None:
        if not hasattr(knowledge, "ambient_initiation_pair_cooldowns"):
            knowledge.ambient_initiation_pair_cooldowns = {}
        return knowledge.ambient_initiation_pair_cooldowns
    if not hasattr(speaker, "ambient_initiation_pair_cooldowns"):
        speaker.ambient_initiation_pair_cooldowns = {}
    return speaker.ambient_initiation_pair_cooldowns


def _ensure_location_cooldowns(world) -> dict[str, int]:
    if not hasattr(world, "ambient_conversation_location_cooldowns"):
        world.ambient_conversation_location_cooldowns = {}
    return world.ambient_conversation_location_cooldowns


def _location_key(actor) -> str:
    activity = getattr(actor, "current_activity", None)
    coords = getattr(activity, "anchor_coords", None) or getattr(activity, "location", None)
    if coords is None:
        coords = (getattr(actor, "x", 0), getattr(actor, "y", 0))
    return f"{int(coords[0]) // 4}:{int(coords[1]) // 4}"
