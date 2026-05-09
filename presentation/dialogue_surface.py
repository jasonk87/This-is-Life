"""Deterministic non-LLM dialogue lines for known history and reactions."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any

from config import DAY_LENGTH_TICKS


@dataclass(frozen=True)
class DialogueContext:
    speaker_id: int | str | None
    listener_id: int | str | None
    current_day: int
    entity_names: dict[int, str] = field(default_factory=dict)
    current_activity_type: str | None = None
    speaker_age_group: str | None = None
    speaker_profession: str | None = None
    speaker_status: str | None = None
    relationship_hint: str | None = None


@dataclass(frozen=True)
class DialogueTopic:
    topic_type: str
    tone: str
    source_id: str
    confidence: float = 1.0
    subject_id: int | None = None
    target_id: int | None = None
    related_id: int | None = None
    record_type: str = ""
    detail: str = ""
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DialogueLine:
    text: str
    topic_type: str
    tone: str
    source_id: str


TOPIC_TYPE_BY_RECORD_TYPE = {
    "crime_recorded": "crime",
    "entity_death": "death",
    "npc_birth": "birth",
    "npc_marriage": "marriage",
    "npc_migrated": "migration",
    "npc_emigrated": "migration",
    "npc_hired": "employment",
    "npc_fired": "employment",
    "npc_quit_job": "employment",
    "npc_employment_changed": "employment",
}
TOPIC_TYPE_BY_CLASS_NAME = {
    "CrimeRecord": "crime",
    "DeathRecord": "death",
    "BirthRecord": "birth",
    "MarriageRecord": "marriage",
    "MigrationRecord": "migration",
    "EmploymentRecord": "employment",
}
REACTION_TONES = {
    "fear": "fearful",
    "grief": "sad",
    "respect": "respectful",
    "curiosity": "curious",
}
FACT_TONES = {
    "crime": "angry",
    "death": "sad",
    "birth": "curious",
    "marriage": "curious",
    "migration": "curious",
    "employment": "respectful",
}

TEMPLATE_POOLS: dict[str, dict[str, tuple[str, ...]]] = {
    "crime": {
        "neutral": (
            "{confidence_phrase} {subject} was named in a crime involving {target}.",
            "{confidence_phrase} there is a crime record naming {subject} and {target}.",
        ),
        "fearful": (
            "{confidence_phrase} {subject} was tied to violence against {target}.",
            "{confidence_phrase} {subject} hurt {target}; I am keeping clear.",
        ),
        "angry": (
            "{confidence_phrase} {subject} was recorded for {detail} involving {target}.",
            "{confidence_phrase} the record names {subject} in {detail} against {target}.",
        ),
        "sad": ("{confidence_phrase} {target} was harmed in a crime involving {subject}.",),
        "curious": ("{confidence_phrase} there is talk of {subject} and a crime involving {target}.",),
        "respectful": ("{confidence_phrase} the record about {subject} and {target} should be taken seriously.",),
        "uncertain": (
            "{confidence_phrase} {subject} may be tied to {detail} involving {target}.",
            "{confidence_phrase} there may be a crime record naming {subject} and {target}.",
        ),
    },
    "death": {
        "neutral": (
            "{confidence_phrase} {subject} died.",
            "{confidence_phrase} the record says {subject} is dead.",
        ),
        "sad": (
            "{confidence_phrase} {subject} died. That is hard news.",
            "{confidence_phrase} {subject} is gone now.",
        ),
        "fearful": ("{confidence_phrase} {subject} died, and I do not like what that means.",),
        "angry": ("{confidence_phrase} {subject} died, and someone should answer for it.",),
        "curious": ("{confidence_phrase} there is a death record for {subject}.",),
        "respectful": ("{confidence_phrase} {subject} should be remembered.",),
        "uncertain": (
            "{confidence_phrase} {subject} may have died.",
            "{confidence_phrase} there may be a death record for {subject}.",
        ),
    },
    "birth": {
        "neutral": ("{confidence_phrase} {subject} was born.",),
        "curious": (
            "{confidence_phrase} {subject} was born; that will change the household.",
            "{confidence_phrase} there is a new child, {subject}.",
        ),
        "fearful": ("{confidence_phrase} {subject} was born in unsettled times.",),
        "angry": ("{confidence_phrase} {subject} was born, though not everyone is kind about it.",),
        "sad": ("{confidence_phrase} {subject} was born. I hope they have an easier life.",),
        "respectful": ("{confidence_phrase} {subject} was born, and the family deserves respect.",),
        "uncertain": ("{confidence_phrase} {subject} may have been born recently.",),
    },
    "marriage": {
        "neutral": ("{confidence_phrase} {subject} and {target} married.",),
        "curious": (
            "{confidence_phrase} {subject} and {target} married; people will talk about that.",
            "{confidence_phrase} there was a marriage between {subject} and {target}.",
        ),
        "fearful": ("{confidence_phrase} {subject} and {target} married during tense times.",),
        "angry": ("{confidence_phrase} {subject} and {target} married, though not everyone approves.",),
        "sad": ("{confidence_phrase} {subject} and {target} married. I hope it brings peace.",),
        "respectful": ("{confidence_phrase} {subject} and {target} made their vows.",),
        "uncertain": ("{confidence_phrase} {subject} and {target} may have married.",),
    },
    "migration": {
        "neutral": ("{confidence_phrase} {subject} moved on.",),
        "curious": (
            "{confidence_phrase} {subject} traveled {detail}.",
            "{confidence_phrase} {subject} has been on the road {detail}.",
        ),
        "fearful": ("{confidence_phrase} {subject} left, and that worries me.",),
        "angry": ("{confidence_phrase} {subject} left {detail}, whether people like it or not.",),
        "sad": ("{confidence_phrase} {subject} left {detail}. It feels quieter now.",),
        "respectful": ("{confidence_phrase} {subject} made the journey {detail}.",),
        "uncertain": ("{confidence_phrase} {subject} may have traveled {detail}.",),
    },
    "employment": {
        "neutral": ("{confidence_phrase} {subject} changed work: {detail}.",),
        "respectful": (
            "{confidence_phrase} {subject} took service as {detail}.",
            "{confidence_phrase} {subject} is working as {detail}; that counts for something.",
        ),
        "fearful": ("{confidence_phrase} {subject} took work as {detail}, so I watch my step.",),
        "angry": ("{confidence_phrase} {subject} got work as {detail}, though I have doubts.",),
        "sad": ("{confidence_phrase} {subject}'s work changed: {detail}.",),
        "curious": ("{confidence_phrase} {subject} has new work as {detail}.",),
        "uncertain": ("{confidence_phrase} {subject} may be working as {detail}.",),
    },
    "fear": {
        "fearful": (
            "I am keeping away from {subject} after what I learned.",
            "I do not feel safe around {subject} now.",
        ),
        "neutral": ("I am wary of {subject}.",),
        "angry": ("{subject} has given people reason to be afraid.",),
        "sad": ("It is sad that {subject} frightens people now.",),
        "curious": ("I wonder what will happen around {subject} now.",),
        "respectful": ("I will be careful speaking of {subject}.",),
        "uncertain": ("People say I should be careful around {subject}.",),
    },
    "grief": {
        "sad": (
            "I am grieving for {subject}.",
            "The news about {subject} still weighs on me.",
        ),
        "neutral": ("I have been thinking about {subject}.",),
        "fearful": ("Losing {subject} makes everything feel less safe.",),
        "angry": ("I am not at peace about what happened to {subject}.",),
        "curious": ("I keep asking what happened to {subject}.",),
        "respectful": ("{subject} deserves to be remembered.",),
        "uncertain": ("People say {subject} is gone, and I do not know what to feel.",),
    },
    "respect": {
        "respectful": (
            "I respect {subject} for that.",
            "{subject} earned some trust from me.",
        ),
        "neutral": ("That reflects well on {subject}.",),
        "fearful": ("I respect {subject}, even if I keep my distance.",),
        "angry": ("Even angry, I can admit {subject} did something useful.",),
        "sad": ("It helps to know {subject} did something worthwhile.",),
        "curious": ("I wonder what {subject} will do next.",),
        "uncertain": ("People say {subject} may deserve respect for that.",),
    },
    "curiosity": {
        "curious": (
            "I keep wondering about {subject}.",
            "There is more to learn about {subject}.",
        ),
        "neutral": ("{subject} has been on my mind.",),
        "fearful": ("I am curious about {subject}, but careful too.",),
        "angry": ("I want to know what {subject} is really doing.",),
        "sad": ("Thinking about {subject} leaves me quiet.",),
        "respectful": ("I would hear more about {subject} respectfully.",),
        "uncertain": ("People say there is more to know about {subject}.",),
    },
}

SMALL_TALK_LINES = (
    "I have not heard anything certain today.",
    "Nothing clear enough to repeat right now.",
    "It has been an ordinary day so far.",
)

TOPIC_PRIORITY = {
    "fear": 120.0,
    "grief": 110.0,
    "crime": 100.0,
    "death": 80.0,
    "respect": 65.0,
    "curiosity": 50.0,
    "employment": 45.0,
    "migration": 40.0,
    "birth": 35.0,
    "marriage": 35.0,
}
TOPIC_COOLDOWN_TICKS = DAY_LENGTH_TICKS
MAX_RECENT_TOPIC_IDS = 8


def build_dialogue_topics_from_npc(npc, world) -> list[DialogueTopic]:
    """Build factual topics from an NPC's known history facts and recent reactions."""
    topics: list[DialogueTopic] = []
    knowledge = getattr(npc, "knowledge", None)
    known_facts = getattr(knowledge, "known_history_facts", {}) if knowledge else {}
    for fact in sorted(known_facts.values(), key=_fact_sort_key, reverse=True):
        topic = _topic_from_fact(fact, world)
        if topic is not None:
            topics.append(topic)

    social = getattr(npc, "social", None)
    reactions = getattr(social, "recent_social_reactions", []) if social else []
    for reaction in reversed(reactions[-8:]):
        topic = _topic_from_reaction(reaction)
        if topic is not None:
            topics.append(topic)

    opinion_modifiers = getattr(social, "opinion_modifiers", {}) if social else {}
    for entity_id, score in sorted(
        opinion_modifiers.items(),
        key=lambda item: abs(item[1]),
        reverse=True,
    )[:3]:
        if score >= 5:
            topics.append(
                DialogueTopic(
                    "respect",
                    "respectful",
                    f"opinion:{entity_id}",
                    subject_id=entity_id,
                    detail="opinion",
                    metadata={"opinion_score": score},
                )
            )
        elif score <= -5:
            topics.append(
                DialogueTopic(
                    "fear",
                    "fearful",
                    f"opinion:{entity_id}",
                    subject_id=entity_id,
                    detail="opinion",
                    metadata={"opinion_score": score},
                )
            )

    return _dedupe_topics(topics)


def render_dialogue_line(topic: DialogueTopic, context: DialogueContext) -> DialogueLine:
    """Render one deterministic factual line for a topic and context."""
    topic_type = topic.topic_type if topic.topic_type in TEMPLATE_POOLS else "curiosity"
    tone = _effective_tone(topic)
    pool = TEMPLATE_POOLS[topic_type].get(tone) or TEMPLATE_POOLS[topic_type]["neutral"]
    template = _choose_template(pool, topic, context)
    text = template.format(
        confidence_phrase=_confidence_phrase(topic.confidence),
        subject=_name_for(topic.subject_id, context),
        target=_name_for(topic.target_id, context, fallback="someone"),
        related=_name_for(topic.related_id, context, fallback="someone"),
        detail=topic.detail or "the matter",
    )
    return DialogueLine(_clean_line(text), topic_type, tone, topic.source_id)


def get_contextual_dialogue_lines(npc, listener, world, limit: int = 3) -> list[DialogueLine]:
    """Return deterministic non-LLM lines about what an NPC knows or feels."""
    topics = build_dialogue_topics_from_npc(npc, world)
    context = _build_context(npc, listener, world, topics)
    selected_topics = _select_dialogue_topics(npc, world, topics, max(1, limit))
    if not selected_topics:
        line = _choose_small_talk(context)
        return [DialogueLine(line, "small_talk", "neutral", "small_talk")]
    lines = [render_dialogue_line(topic, context) for topic in selected_topics]
    _remember_spoken_topics(npc, selected_topics, _current_tick(world))
    return lines


def _select_dialogue_topics(npc, world, topics: list[DialogueTopic], limit: int) -> list[DialogueTopic]:
    if not topics:
        return []
    memory = _dialogue_memory(npc)
    current_tick = _current_tick(world)
    scored_topics = [
        (_topic_score(topic, memory, current_tick), topic)
        for topic in topics
        if not _topic_is_on_cooldown(topic, memory, current_tick)
    ]
    if not scored_topics:
        return []
    scored_topics = [item for item in scored_topics if item[0] > 0.0]
    if not scored_topics:
        return []
    scored_topics.sort(key=lambda item: (item[0], item[1].source_id), reverse=True)

    selected: list[DialogueTopic] = []
    selected_ids: set[str] = set()
    for _score, topic in scored_topics:
        topic_id = _topic_memory_id(topic)
        if topic_id in selected_ids:
            continue
        selected.append(topic)
        selected_ids.add(topic_id)
        if len(selected) >= limit:
            break
    return selected


def _topic_score(topic: DialogueTopic, memory, current_tick: int) -> float:
    topic_id = _topic_memory_id(topic)
    score = TOPIC_PRIORITY.get(topic.topic_type, 25.0)
    score += max(0.0, min(1.0, float(topic.confidence))) * 10.0
    score += _freshness_bonus(topic, current_tick)
    score -= float(memory["counts"].get(topic_id, 0)) * 25.0
    if memory["recent"] and memory["recent"][0] == topic_id:
        score -= 45.0
    return score


def _topic_is_on_cooldown(topic: DialogueTopic, memory, current_tick: int) -> bool:
    topic_id = _topic_memory_id(topic)
    last_tick = memory["last_ticks"].get(topic_id)
    if last_tick is None:
        return False
    return current_tick - int(last_tick) < TOPIC_COOLDOWN_TICKS


def _freshness_bonus(topic: DialogueTopic, current_tick: int) -> float:
    source_tick = (
        topic.metadata.get("reaction_tick")
        or topic.metadata.get("known_at_tick")
        or 0
    )
    try:
        age = max(0, current_tick - int(source_tick))
    except (TypeError, ValueError):
        return 0.0
    if source_tick <= 0:
        return 0.0
    if age <= DAY_LENGTH_TICKS:
        return 30.0
    if age <= DAY_LENGTH_TICKS * 3:
        return 15.0
    return 0.0


def _dialogue_memory(npc) -> dict[str, Any]:
    knowledge = getattr(npc, "knowledge", None)
    if knowledge is None:
        return {"recent": [], "last_ticks": {}, "counts": {}}
    if not hasattr(knowledge, "recently_spoken_topic_ids"):
        knowledge.recently_spoken_topic_ids = []
    if not hasattr(knowledge, "last_spoken_topic_tick"):
        knowledge.last_spoken_topic_tick = {}
    if not hasattr(knowledge, "spoken_topic_counts"):
        knowledge.spoken_topic_counts = {}
    return {
        "recent": knowledge.recently_spoken_topic_ids,
        "last_ticks": knowledge.last_spoken_topic_tick,
        "counts": knowledge.spoken_topic_counts,
    }


def _remember_spoken_topics(npc, topics: list[DialogueTopic], current_tick: int) -> None:
    memory = _dialogue_memory(npc)
    for topic in topics:
        topic_id = _topic_memory_id(topic)
        recent = memory["recent"]
        if topic_id in recent:
            recent.remove(topic_id)
        recent.insert(0, topic_id)
        del recent[MAX_RECENT_TOPIC_IDS:]
        memory["last_ticks"][topic_id] = int(current_tick)
        memory["counts"][topic_id] = int(memory["counts"].get(topic_id, 0)) + 1


def _topic_memory_id(topic: DialogueTopic) -> str:
    return f"{topic.topic_type}:{topic.source_id}"


def _topic_from_fact(fact, world) -> DialogueTopic | None:
    record_type = str(getattr(fact, "record_type", ""))
    class_name = str(getattr(fact, "record_class_name", ""))
    topic_type = TOPIC_TYPE_BY_RECORD_TYPE.get(record_type) or TOPIC_TYPE_BY_CLASS_NAME.get(class_name)
    if topic_type is None:
        return None

    record = _get_history_record(world, getattr(fact, "source_record_id", ""))
    subject_id, target_id, related_id = _ids_for_topic(topic_type, fact, record)
    tone = "uncertain" if _fact_confidence(fact) < 0.45 else FACT_TONES.get(topic_type, "neutral")
    return DialogueTopic(
        topic_type=topic_type,
        tone=tone,
        source_id=str(getattr(fact, "source_record_id", "")),
        confidence=_fact_confidence(fact),
        subject_id=subject_id,
        target_id=target_id,
        related_id=related_id,
        record_type=record_type,
        detail=_detail_for_topic(topic_type, record, fact),
        tags=tuple(getattr(fact, "tags", ()) or ()),
        metadata={"known_at_tick": int(getattr(fact, "known_at_tick", 0))},
    )


def _topic_from_reaction(reaction: dict) -> DialogueTopic | None:
    reaction_type = str(reaction.get("reaction_type", ""))
    if reaction_type not in REACTION_TONES:
        return None
    source_id = str(reaction.get("source_record_id") or f"reaction:{id(reaction)}")
    return DialogueTopic(
        topic_type=reaction_type,
        tone=REACTION_TONES[reaction_type],
        source_id=f"{source_id}:{reaction_type}",
        confidence=1.0,
        subject_id=_coerce_int(reaction.get("target_entity_id")),
        target_id=_coerce_int(reaction.get("related_entity_id")),
        detail=str(reaction.get("reason", "the matter")).replace("_", " "),
        metadata={"reaction_tick": int(reaction.get("tick", 0) or 0)},
    )


def _ids_for_topic(topic_type: str, fact, record) -> tuple[int | None, int | None, int | None]:
    entity_ids = list(getattr(fact, "subject_entity_ids", ()) or ())
    if topic_type == "crime":
        return (
            _coerce_int(getattr(record, "suspect_id", None)) or _entity_id_at(entity_ids, 0),
            _coerce_int(getattr(record, "victim_id", None)) or _entity_id_at(entity_ids, 1),
            None,
        )
    if topic_type == "death":
        return (
            _coerce_int(getattr(record, "deceased_id", None))
            or _entity_id_at(entity_ids, 0),
            None,
            None,
        )
    if topic_type == "birth":
        return (
            _coerce_int(getattr(record, "child_id", None))
            or _entity_id_at(entity_ids, 0),
            _entity_id_at(entity_ids, 1),
            None,
        )
    if topic_type == "marriage":
        spouse_ids = tuple(getattr(record, "spouse_ids", ()) or ())
        return _entity_id_at(spouse_ids or entity_ids, 0), _entity_id_at(spouse_ids or entity_ids, 1), None
    if topic_type == "migration":
        return _coerce_int(getattr(record, "traveler_id", None)) or _entity_id_at(entity_ids, 0), None, None
    if topic_type == "employment":
        return _coerce_int(getattr(record, "worker_id", None)) or _entity_id_at(entity_ids, 0), None, None
    return _entity_id_at(entity_ids, 0), _entity_id_at(entity_ids, 1), None


def _detail_for_topic(topic_type: str, record, fact) -> str:
    if topic_type == "crime":
        return str(getattr(record, "crime_kind", "crime") or "crime").replace("_", " ")
    if topic_type == "employment":
        profession = str(getattr(record, "profession", "work") or "work").replace("_", " ")
        action = str(getattr(record, "employment_action", "") or "").replace("_", " ")
        return f"{profession}" if not action else f"{action} {profession}"
    if topic_type == "migration":
        origin = getattr(record, "origin_label", None)
        destination = getattr(record, "destination_label", None)
        if origin and destination:
            return f"from {origin} to {destination}"
        if destination:
            return f"to {destination}"
        if origin:
            return f"from {origin}"
        return "elsewhere"
    return str(getattr(fact, "record_type", "the record") or "the record").replace("_", " ")


def _build_context(npc, listener, world, topics: list[DialogueTopic]) -> DialogueContext:
    entity_ids = set()
    for topic in topics:
        for entity_id in (topic.subject_id, topic.target_id, topic.related_id):
            if isinstance(entity_id, int):
                entity_ids.add(entity_id)
    for entity in (npc, listener):
        entity_id = getattr(entity, "id", None)
        if isinstance(entity_id, int):
            entity_ids.add(entity_id)
    return DialogueContext(
        speaker_id=getattr(npc, "id", None),
        listener_id=getattr(listener, "id", None),
        current_day=_current_day(world),
        entity_names={entity_id: _resolve_entity_name(world, entity_id) for entity_id in entity_ids},
        current_activity_type=_activity_type_for(npc),
        speaker_age_group=_age_group_for(npc),
        speaker_profession=_profession_for(npc),
        speaker_status=_status_for(npc),
        relationship_hint=_relationship_hint_for(npc, listener),
    )



def _activity_type_for(entity) -> str | None:
    activity = getattr(entity, "current_activity", None)
    if activity is None:
        return None
    return str(getattr(activity, "activity_type", "") or "") or None


def _age_group_for(entity) -> str | None:
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


def _profession_for(entity) -> str | None:
    profession = str(getattr(getattr(entity, "economic", None), "profession", "") or "").strip()
    return profession or None


def _status_for(entity) -> str | None:
    social = getattr(entity, "social", None)
    title = str(getattr(social, "title", "") or "").strip()
    if title:
        return title
    if hasattr(entity, "get_title_label"):
        label = str(entity.get_title_label() or "").strip()
        if label:
            return label
    return None


def _relationship_hint_for(speaker, listener) -> str | None:
    if hasattr(speaker, "get_relationship_to"):
        relation = speaker.get_relationship_to(listener)
        if relation:
            return str(relation)
    speaker_social = getattr(speaker, "social", None)
    relationships = getattr(speaker_social, "relationships", {}) if speaker_social else {}
    listener_id = getattr(listener, "id", None)
    if listener_id in relationships:
        score = relationships[listener_id]
        if score >= 70:
            return "friendly"
        if score <= 30:
            return "strained"
        return "neutral"
    return None

def _resolve_entity_name(world, entity_id: int) -> str:
    entity = None
    get_entity = getattr(world, "get_entity_by_id", None)
    if callable(get_entity):
        entity = get_entity(entity_id)
    if entity is None and getattr(getattr(world, "player", None), "id", None) == entity_id:
        entity = world.player
    if entity is None:
        for collection_name in ("village_npcs", "npcs"):
            for candidate in getattr(world, collection_name, []) or []:
                if getattr(candidate, "id", None) == entity_id:
                    entity = candidate
                    break
            if entity is not None:
                break
    name = str(getattr(entity, "name", "") or "").strip() if entity is not None else ""
    return name or f"Entity {entity_id}"


def _name_for(entity_id: int | None, context: DialogueContext, fallback: str = "someone") -> str:
    if entity_id is None:
        return fallback
    return context.entity_names.get(entity_id) or f"Entity {entity_id}"


def _get_history_record(world, record_id: str):
    history = getattr(world, "history", None)
    get_event = getattr(history, "get_event", None)
    if callable(get_event):
        return get_event(record_id)
    return None


def _current_day(world) -> int:
    return _current_tick(world) // DAY_LENGTH_TICKS


def _current_tick(world) -> int:
    return int(getattr(world, "game_time", 0))


def _confidence_phrase(confidence: float) -> str:
    confidence = max(0.0, min(1.0, float(confidence)))
    if confidence >= 0.75:
        return "I know"
    if confidence >= 0.45:
        return "I heard"
    return "People say"


def _effective_tone(topic: DialogueTopic) -> str:
    if topic.confidence < 0.45:
        return "uncertain"
    return topic.tone if topic.tone in TEMPLATE_POOLS.get(topic.topic_type, {}) else "neutral"


def _choose_template(pool: tuple[str, ...], topic: DialogueTopic, context: DialogueContext) -> str:
    if not pool:
        return "{confidence_phrase} something happened."
    base = _stable_int(f"{topic.source_id}|{topic.topic_type}|{topic.tone}|{context.listener_id}")
    index = (base + _stable_int(context.speaker_id) + int(context.current_day)) % len(pool)
    return pool[index]


def _choose_small_talk(context: DialogueContext) -> str:
    index = (
        _stable_int(context.speaker_id)
        + _stable_int(context.listener_id)
        + int(context.current_day)
    ) % len(SMALL_TALK_LINES)
    return SMALL_TALK_LINES[index]


def _stable_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    digest = hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:8]
    return int(digest, 16)


def _fact_sort_key(fact) -> tuple[int, str]:
    return int(getattr(fact, "known_at_tick", 0)), str(
        getattr(fact, "source_record_id", "")
    )


def _dedupe_topics(topics: list[DialogueTopic]) -> list[DialogueTopic]:
    deduped = []
    seen = set()
    for topic in topics:
        key = (topic.topic_type, topic.source_id, topic.subject_id, topic.target_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(topic)
    return deduped


def _fact_confidence(fact) -> float:
    return max(0.0, min(1.0, float(getattr(fact, "confidence", 0.0))))


def _coerce_int(value) -> int | None:
    return value if isinstance(value, int) else None


def _entity_id_at(entity_ids, index: int) -> int | None:
    try:
        value = entity_ids[index]
    except (IndexError, TypeError):
        return None
    return value if isinstance(value, int) else None


def _clean_line(text: str) -> str:
    return " ".join(text.replace("  ", " ").split()).strip()
