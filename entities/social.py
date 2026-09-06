"""Deterministic social memory primitives for gossip and witness recall."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import hashlib
import random
from typing import Any

from config import DAY_LENGTH_TICKS
from entities.pickle_compat import dataclass_setstate


@dataclass(frozen=True)
class MemoryEvent:
    event_type: str
    subject_id: int | str | None
    target_id: int | None
    timestamp: int
    importance_score: int
    headline: str = ""
    location: tuple[int, int] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = ""

    def __post_init__(self):
        if self.id:
            return
        seed = "|".join(
            [
                str(self.event_type),
                str(self.subject_id),
                str(self.target_id),
                str(self.timestamp),
                str(self.importance_score),
                str(self.headline),
                str(self.location),
                str(sorted(self.metadata.items())),
            ]
        )
        object.__setattr__(self, "id", hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16])


@dataclass
class GrudgeRecord:
    """Structured suspicion/grudge state toward another entity."""

    target_id: int
    reason: str
    severity: int = 35
    created_day: int = 0
    last_updated_day: int = 0
    decay_days: int = 5
    persistent: bool = False

    def __setstate__(self, state):
        dataclass_setstate(self, state)


@dataclass
class LocalOpinionRecord:
    """Belief-driven local standing for a target entity from one observer's perspective."""

    target_id: int
    score: float = 0.0
    evidence_count: int = 0
    last_updated_day: int = 0

    def __setstate__(self, state):
        dataclass_setstate(self, state)


@dataclass
class HistoryFactReactionState:
    """Tracks how strongly an NPC has already reacted to a known history fact."""

    reacted_confidence: float = 0.0
    reacted_source_type: str = ""
    last_reaction_tick: int = 0
    applied_reaction_strength: float = 0.0

    def __setstate__(self, state):
        dataclass_setstate(self, state)


@dataclass(frozen=True)
class MemoryProfile:
    """Small profile controlling how a structured fact persists or fades."""

    memory_strength: float
    permanence: float
    emotional_weight: float
    decay_rate: float
    reinforcement_sensitivity: float = 1.0


@dataclass(frozen=True)
class KnownHistoryFact:
    """A holder's structured knowledge of a HistoryLedger record."""

    source_record_id: str
    record_type: str
    subject_entity_ids: tuple[int, ...]
    known_at_tick: int
    source_type: str
    confidence: float
    settlement_id: str | None = None
    region_id: str | None = None
    tags: tuple[str, ...] = ()
    record_class_name: str = ""
    memory_strength: float = 0.55
    permanence: float = 0.05
    emotional_weight: float = 0.0
    decay_rate: float = 0.10
    reinforcement_count: int = 0
    last_recalled_tick: int = 0
    last_reinforced_tick: int = 0
    # Who this was most recently heard from, and everyone it has been heard
    # from. `source_type` says *how* a holder came to know something; neither
    # said *who* told them, which is the question an investigation actually
    # turns on - and which telling a lie apart from repeating one will need.
    #
    # The set exists because repetition and corroboration are not the same
    # thing. Thomas saying it three times is one source; Mara, Owen and Thomas
    # each saying it once is three. Only the second should make a belief
    # sturdier. (Whether those three ultimately trace back to one original
    # rumour is a question for later - this records immediate tellers only.)
    source_entity_id: int | None = None
    heard_from_ids: tuple[int, ...] = ()
    # Which assertion this holder actually believes. Empty on facts written
    # before claims existed, which are read as believing the truth.
    claim_id: str = ""

    def __setstate__(self, state):
        # Pickle replays a saved __dict__ and never calls __init__, so a fact
        # restored from a save written before these fields existed would be
        # missing them entirely. Frozen only blocks __setattr__, not this.
        dataclass_setstate(self, state)


@dataclass(frozen=True)
class Claim:
    """An assertion about what happened. It may or may not be true.

    The three layers this completes:

        record  - what happened.            Owned by the world (HistoryLedger).
        claim   - an assertion about it.    Shared; many people can hold one.
        fact    - somebody believing one.   Personal (KnownHistoryFact).

    Before this, a belief pointed straight at a record, so a villager could be
    uncertain, vague or forgetful but never actually *wrong*. A claim is the
    room for being wrong: it names a record, and then says what the holder
    thinks happened, which need not match.

    The id is a hash of the assertion and nothing else - not who said it, not
    how sure they are, not how well they remember it. That is deliberate. Two
    people who arrive at the same wrong story independently land on the same
    claim id, so a rumour converges instead of fragmenting into one variant per
    teller, and "how many people believe this" is a question with an answer.
    (Same trick MemoryEvent already uses for its own id.)
    """

    source_record_id: str
    believed_record_type: str
    believed_subject_ids: tuple[int, ...] = ()
    believed_target_id: int | None = None
    believed_location_id: str | None = None
    believed_quantity: int | None = None
    id: str = ""

    def __post_init__(self):
        if self.id:
            return
        seed = "|".join(
            [
                str(self.source_record_id),
                str(self.believed_record_type),
                ",".join(str(i) for i in self.believed_subject_ids),
                str(self.believed_target_id),
                str(self.believed_location_id),
                str(self.believed_quantity),
            ]
        )
        object.__setattr__(self, "id", hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16])

    def __setstate__(self, state):
        dataclass_setstate(self, state)


def claim_from_record(record: Any) -> Claim:
    """The true claim: what a perfect witness would assert about this record."""
    return Claim(
        source_record_id=_record_id(record),
        believed_record_type=_record_type(record),
        believed_subject_ids=_record_subject_entity_ids(record),
        believed_target_id=getattr(record, "target_id", None),
        believed_location_id=_record_scope_value(record, "settlement_id"),
    )


def _record_id(record: Any) -> str:
    return str(
        getattr(record, "id", None)
        or getattr(record, "record_id", None)
        or ""
    )


def _record_type(record: Any) -> str:
    return str(
        getattr(record, "type", None)
        or getattr(record, "event_type", None)
        or type(record).__name__
    )


def _record_subject_entity_ids(record: Any) -> tuple[int, ...]:
    entity_ids: list[int] = []
    participant_ids = getattr(record, "participant_ids", None)
    if participant_ids is not None:
        entity_ids.extend(
            participant_id
            for participant_id in participant_ids
            if isinstance(participant_id, int)
        )
    for attr_name in (
        "subject_id",
        "target_id",
        "child_id",
        "deceased_id",
        "killer_id",
        "suspect_id",
        "victim_id",
        "traveler_id",
        "worker_id",
    ):
        attr_value = getattr(record, attr_name, None)
        if isinstance(attr_value, int):
            entity_ids.append(attr_value)
    for attr_name in ("parent_ids", "spouse_ids", "witness_ids"):
        attr_value = getattr(record, attr_name, ()) or ()
        entity_ids.extend(
            entity_id for entity_id in attr_value if isinstance(entity_id, int)
        )
    return tuple(dict.fromkeys(entity_ids))


def _record_scope_value(record: Any, key: str) -> str | None:
    value = getattr(record, key, None)
    if value is None:
        metadata = getattr(record, "metadata", {}) or {}
        value = metadata.get(key)
    if value is None:
        return None
    return str(value)


MEMORY_FORGET_THRESHOLD = 0.08
MEMORY_DECAY_INTERVAL_TICKS = DAY_LENGTH_TICKS // 4

_BASE_MEMORY_PROFILES: dict[str, MemoryProfile] = {
    "overheard": MemoryProfile(0.38, 0.02, 0.0, 0.18, 0.85),
    "rumor": MemoryProfile(0.42, 0.03, 0.0, 0.16, 0.90),
    "told": MemoryProfile(0.58, 0.06, 0.0, 0.10, 1.0),
    "direct_conversation": MemoryProfile(0.62, 0.08, 0.0, 0.09, 1.05),
    "witnessed": MemoryProfile(0.82, 0.20, 0.10, 0.045, 1.15),
    "direct_witness": MemoryProfile(0.86, 0.24, 0.12, 0.040, 1.18),
    "traumatic": MemoryProfile(0.94, 0.42, 0.85, 0.022, 1.30),
    "family": MemoryProfile(0.90, 0.48, 0.65, 0.026, 1.25),
    "personal": MemoryProfile(0.84, 0.36, 0.45, 0.036, 1.18),
    "public": MemoryProfile(0.72, 0.30, 0.08, 0.040, 1.05),
    "public_record": MemoryProfile(0.78, 0.38, 0.06, 0.030, 1.05),
    "official_record": MemoryProfile(0.88, 0.58, 0.04, 0.014, 1.0),
    "book": MemoryProfile(0.86, 0.62, 0.02, 0.012, 0.95),
    "chronicle": MemoryProfile(0.90, 0.70, 0.04, 0.010, 0.90),
    "read": MemoryProfile(0.78, 0.46, 0.02, 0.020, 0.95),
}


def compute_memory_profile(
    record: Any = None,
    *,
    source_type: str = "told",
    confidence: float = 1.0,
    tags: tuple[str, ...] = (),
    record_type: str = "",
    record_class_name: str = "",
) -> MemoryProfile:
    """Compute the lightweight persistence profile for a structured known fact."""
    source_key = str(source_type or "told").lower()
    profile = _BASE_MEMORY_PROFILES.get(source_key, _BASE_MEMORY_PROFILES["told"])
    confidence = max(0.0, min(1.0, float(confidence)))
    record_type = str(record_type or getattr(record, "event_type", getattr(record, "type", "")) or "")
    if not record_class_name and record is not None:
        record_class_name = type(record).__name__
    record_class_name = str(record_class_name or "")
    tag_set = {str(tag) for tag in (tags or tuple(getattr(record, "tags", ()) or ()))}
    metadata = getattr(record, "metadata", {}) or {}
    crime_kind = str(getattr(record, "crime_kind", metadata.get("crime_kind", "")) or "").lower()
    cause_of_death = str(getattr(record, "cause_of_death", metadata.get("cause_of_death", "")) or "").lower()

    strength = profile.memory_strength * (0.65 + (confidence * 0.35))
    permanence = profile.permanence
    emotional_weight = profile.emotional_weight
    decay_rate = profile.decay_rate
    reinforcement_sensitivity = profile.reinforcement_sensitivity

    is_crime = record_class_name == "CrimeRecord" or "crime" in record_type or "crime" in tag_set or "law" in tag_set
    is_violent_crime = is_crime and any(term in crime_kind for term in ("murder", "kill", "assault", "attack", "violent", "robbery", "harm"))
    is_death = record_class_name == "DeathRecord" or record_type == "entity_death" or "death" in tag_set
    is_life_event = record_class_name in {"BirthRecord", "MarriageRecord"} or bool({"birth", "marriage"} & tag_set)
    is_public_history = source_key in {"official_record", "book", "chronicle", "public", "public_record", "read"}

    if is_violent_crime:
        strength += 0.12
        permanence += 0.12
        emotional_weight += 0.45
        decay_rate *= 0.55
    elif is_crime:
        strength += 0.06
        permanence += 0.06
        emotional_weight += 0.20
        decay_rate *= 0.75

    if is_death:
        strength += 0.10
        permanence += 0.10
        emotional_weight += 0.35
        decay_rate *= 0.65
        if source_key in {"family", "personal"} or any(term in cause_of_death for term in ("murder", "violence", "injury")):
            permanence += 0.18
            emotional_weight += 0.35
            decay_rate *= 0.65

    if is_life_event and source_key in {"family", "personal", "public", "public_record"}:
        strength += 0.06
        permanence += 0.08
        decay_rate *= 0.80

    if is_public_history:
        permanence += 0.08
        decay_rate *= 0.75

    return MemoryProfile(
        memory_strength=max(0.0, min(1.0, strength)),
        permanence=max(0.0, min(0.95, permanence)),
        emotional_weight=max(0.0, min(1.0, emotional_weight)),
        decay_rate=max(0.001, min(1.0, decay_rate)),
        reinforcement_sensitivity=max(0.1, min(2.0, reinforcement_sensitivity)),
    )


def fact_with_memory_profile(fact: KnownHistoryFact, profile: MemoryProfile, *, tick: int | None = None) -> KnownHistoryFact:
    """Return a fact with memory fields initialized from a profile."""
    _ensure_fact_memory_fields(fact)
    tick_value = int(getattr(fact, "known_at_tick", 0) if tick is None else tick)
    return replace(
        fact,
        memory_strength=profile.memory_strength,
        permanence=profile.permanence,
        emotional_weight=profile.emotional_weight,
        decay_rate=profile.decay_rate,
        last_recalled_tick=int(getattr(fact, "last_recalled_tick", 0) or tick_value),
        last_reinforced_tick=int(getattr(fact, "last_reinforced_tick", 0) or tick_value),
    )


def reinforce_known_fact(
    target,
    fact_id: str | None = None,
    *,
    tick: int = 0,
    source_type: str = "told",
    amount: float | None = None,
    emotional_weight: float = 0.0,
):
    """Reinforce a known fact in-place on a knowledge holder, or return a reinforced fact."""
    if isinstance(target, KnownHistoryFact):
        profile = _BASE_MEMORY_PROFILES.get(str(source_type or "told").lower(), _BASE_MEMORY_PROFILES["told"])
        return _reinforced_fact(target, int(tick), profile, amount, emotional_weight)

    facts = getattr(target, "known_history_facts", None)
    if not isinstance(facts, dict):
        return False
    key = str(fact_id or "")
    fact = facts.get(key)
    if fact is None:
        return False
    profile = _BASE_MEMORY_PROFILES.get(str(source_type or getattr(fact, "source_type", "told")).lower(), _BASE_MEMORY_PROFILES["told"])
    facts[key] = _reinforced_fact(fact, int(tick), profile, amount, emotional_weight)
    return True


def decay_known_facts(knowledge, current_tick: int) -> int:
    """Apply lightweight memory decay and remove forgotten low-permanence facts."""
    facts = getattr(knowledge, "known_history_facts", None)
    if not isinstance(facts, dict):
        return 0
    removed = 0
    for fact_id, fact in list(facts.items()):
        decayed = _decayed_fact(fact, int(current_tick))
        if should_forget_fact(decayed):
            facts.pop(fact_id, None)
            removed += 1
        else:
            facts[fact_id] = decayed
    return removed


def should_forget_fact(fact: KnownHistoryFact) -> bool:
    """Return whether a low-strength, low-permanence fact should be forgotten."""
    return _memory_strength(fact) <= MEMORY_FORGET_THRESHOLD and _permanence(fact) < 0.20


DURABLE_SOURCE_TYPES = {
    "family",
    "personal",
    "traumatic",
    "public",
    "public_record",
    "official_record",
    "book",
    "chronicle",
    "read",
}
TRANSIENT_SOURCE_TYPES = {
    "overheard",
    "rumor",
    "told",
    "direct_conversation",
}


def is_transient_known_fact(fact: KnownHistoryFact) -> bool:
    """Return whether a typed fact is transient gossip/news rather than durable memory."""
    _ensure_fact_memory_fields(fact)
    source_type = str(getattr(fact, "source_type", "") or "").lower()
    permanence = _permanence(fact)
    strength = _memory_strength(fact)
    if source_type in DURABLE_SOURCE_TYPES:
        return False
    if permanence >= 0.35:
        return False
    if source_type in {"witnessed", "direct_witness"} and strength >= 0.65 and permanence >= 0.20:
        return False
    if _emotional_weight(fact) >= 0.55 and permanence >= 0.25:
        return False
    if source_type in TRANSIENT_SOURCE_TYPES:
        return True
    return strength < 0.45 and permanence < 0.20


def should_clear_fact_for_reset(fact: KnownHistoryFact, reset_scope: str = "transient") -> bool:
    """Return whether a fact should be removed for a legacy-style knowledge reset."""
    scope = str(reset_scope or "transient").lower()
    if scope in {"none", "legacy_only"}:
        return False
    if scope in {"all_typed", "typed_all"}:
        return True
    if scope in {"local", "travel", "transient"}:
        return is_transient_known_fact(fact)
    return is_transient_known_fact(fact)


def reset_transient_knowledge(holder_or_knowledge, *, reset_scope: str = "transient", clear_legacy_events: bool = True) -> set[str]:
    """Clear legacy events plus transient typed facts while preserving durable memory tiers."""
    knowledge = getattr(holder_or_knowledge, "knowledge", holder_or_knowledge)
    if knowledge is None:
        return set()
    if clear_legacy_events and hasattr(knowledge, "known_events"):
        knowledge.known_events.clear()

    facts = getattr(knowledge, "known_history_facts", None)
    if not isinstance(facts, dict):
        return set()
    cleared_fact_ids: set[str] = set()
    for fact_id, fact in list(facts.items()):
        if should_clear_fact_for_reset(fact, reset_scope):
            facts.pop(fact_id, None)
            cleared_fact_ids.add(str(fact_id))

    social = getattr(holder_or_knowledge, "social", None)
    for fact_id in cleared_fact_ids:
        clear_fact_dependent_memory(knowledge, fact_id, social=social)
    return cleared_fact_ids


def clear_fact_dependent_memory(holder_or_knowledge, fact_id: str, *, social=None) -> None:
    """Remove cooldown/share/reaction state tied specifically to one cleared fact id."""
    knowledge = getattr(holder_or_knowledge, "knowledge", holder_or_knowledge)
    fact_id = str(fact_id)
    if knowledge is not None:
        recent = getattr(knowledge, "recently_spoken_topic_ids", None)
        if isinstance(recent, list):
            recent[:] = [topic_id for topic_id in recent if not _topic_memory_matches_fact(topic_id, fact_id)]
        for attr_name in ("last_spoken_topic_tick", "spoken_topic_counts"):
            values = getattr(knowledge, attr_name, None)
            if isinstance(values, dict):
                for key in list(values.keys()):
                    if _topic_memory_matches_fact(str(key), fact_id):
                        values.pop(key, None)
        shared = getattr(knowledge, "shared_fact_listener_ids", None)
        if isinstance(shared, dict):
            shared.pop(fact_id, None)
        pair_cooldowns = getattr(knowledge, "fact_share_pair_cooldowns", None)
        if isinstance(pair_cooldowns, dict):
            for key in list(pair_cooldowns.keys()):
                if fact_id in str(key):
                    pair_cooldowns.pop(key, None)

    if social is not None:
        reacted_ids = getattr(social, "reacted_history_fact_ids", None)
        if isinstance(reacted_ids, set):
            reacted_ids.discard(fact_id)
        reacted_state = getattr(social, "reacted_history_fact_state", None)
        if isinstance(reacted_state, dict):
            reacted_state.pop(fact_id, None)
        reactions = getattr(social, "recent_social_reactions", None)
        if isinstance(reactions, list):
            reactions[:] = [reaction for reaction in reactions if str(reaction.get("source_record_id", "")) != fact_id]


def _topic_memory_matches_fact(topic_id: str, fact_id: str) -> bool:
    return topic_id == fact_id or topic_id.endswith(f":{fact_id}")


def _reinforced_fact(fact: KnownHistoryFact, tick: int, profile: MemoryProfile, amount: float | None, emotional_weight: float) -> KnownHistoryFact:
    _ensure_fact_memory_fields(fact)
    base_amount = profile.reinforcement_sensitivity * (0.10 if amount is None else float(amount))
    emotion_bonus = max(0.0, float(emotional_weight)) * 0.08
    new_emotion = max(_emotional_weight(fact), min(1.0, float(emotional_weight)))
    return replace(
        fact,
        memory_strength=min(1.0, _memory_strength(fact) + base_amount + emotion_bonus),
        permanence=min(0.95, max(_permanence(fact), _permanence(fact) + (base_amount * 0.10 if _permanence(fact) >= 0.20 else 0.0))),
        emotional_weight=new_emotion,
        reinforcement_count=int(getattr(fact, "reinforcement_count", 0) or 0) + 1,
        last_recalled_tick=tick,
        last_reinforced_tick=tick,
    )


def _decayed_fact(fact: KnownHistoryFact, current_tick: int) -> KnownHistoryFact:
    _ensure_fact_memory_fields(fact)
    last_value = getattr(fact, "last_recalled_tick", None)
    if last_value is None:
        last_value = getattr(fact, "known_at_tick", current_tick)
    last_tick = int(last_value)
    elapsed_ticks = max(0, current_tick - last_tick)
    if elapsed_ticks <= 0:
        return fact
    elapsed_days = elapsed_ticks / max(1, DAY_LENGTH_TICKS)
    emotional_resistance = 1.0 + _emotional_weight(fact)
    decay_amount = elapsed_days * _decay_rate(fact) / emotional_resistance
    new_strength = max(_permanence(fact), _memory_strength(fact) - decay_amount)
    return replace(fact, memory_strength=new_strength, last_recalled_tick=current_tick)



def _ensure_fact_memory_fields(fact) -> None:
    defaults = {
        "memory_strength": 0.55,
        "permanence": 0.05,
        "emotional_weight": 0.0,
        "decay_rate": 0.10,
        "reinforcement_count": 0,
        "last_recalled_tick": int(getattr(fact, "known_at_tick", 0) or 0),
        "last_reinforced_tick": int(getattr(fact, "known_at_tick", 0) or 0),
    }
    for name, value in defaults.items():
        if not hasattr(fact, name):
            object.__setattr__(fact, name, value)


def _memory_strength(fact) -> float:
    return max(0.0, min(1.0, float(getattr(fact, "memory_strength", 0.55))))


def _permanence(fact) -> float:
    return max(0.0, min(1.0, float(getattr(fact, "permanence", 0.05))))


def _emotional_weight(fact) -> float:
    return max(0.0, min(1.0, float(getattr(fact, "emotional_weight", 0.0))))


def _decay_rate(fact) -> float:
    return max(0.001, min(1.0, float(getattr(fact, "decay_rate", 0.10))))


@dataclass
class KnowledgeComponent:
    """Bounded structured knowledge used by both players and NPCs."""

    known_events: dict[str, Any] = field(default_factory=dict)
    known_history_facts: dict[str, KnownHistoryFact] = field(default_factory=dict)
    known_memories: dict[str, MemoryEvent] = field(default_factory=dict)
    known_harmful_incidents: dict[str, Any] = field(default_factory=dict)
    reacted_to_event_ids: set[str] = field(default_factory=set)
    discussed_event_ids: set[str] = field(default_factory=set)
    last_global_event_index_checked: int = -1
    help_needed: str | None = None
    long_term_memory: list[str] = field(default_factory=list)
    known_locations: dict[str, tuple[int, int]] = field(default_factory=dict)
    perceived_item_tiles: list[tuple[int, int]] = field(default_factory=list)
    active_quests: dict = field(default_factory=dict)
    completed_quests: list[str] = field(default_factory=list)
    # Quests that became permanently uncompletable (currently: their giver
    # NPC died - see World._fail_quests_orphaned_by_death) rather than being
    # finished. Kept separate from completed_quests so quest-log UI/logic
    # can distinguish "done" from "failed" if it ever wants to.
    failed_quests: list[str] = field(default_factory=list)
    claimed_tasks: list[str] = field(default_factory=list)
    known_books: set[str] = field(default_factory=set)
    recently_spoken_topic_ids: list[str] = field(default_factory=list)
    last_spoken_topic_tick: dict[str, int] = field(default_factory=dict)
    spoken_topic_counts: dict[str, int] = field(default_factory=dict)
    fact_share_pair_cooldowns: dict[str, int] = field(default_factory=dict)
    shared_fact_listener_ids: dict[str, set[int]] = field(default_factory=dict)
    lockpicking_skill: int = 3
    max_memory_events: int = 50
    chronicle_pending_memory_ids: set[str] = field(default_factory=set)
    chronicle_written_memory_ids: set[str] = field(default_factory=set)

    def learn_history_record(
        self,
        record: Any,
        source_type: str,
        confidence: float,
        tick: int,
        source_entity_id: int | None = None,
        claim: "Claim | None" = None,
    ) -> bool:
        if record is None:
            return False
        source_record_id = _record_id(record)
        if not source_record_id:
            return False
        confidence = max(0.0, min(1.0, float(confidence)))
        believed = claim if claim is not None else claim_from_record(record)
        tags = tuple(getattr(record, "tags", ()) or ())
        profile = compute_memory_profile(
            record,
            source_type=str(source_type),
            confidence=confidence,
            tags=tags,
            record_type=_record_type(record),
            record_class_name=type(record).__name__,
        )
        existing = self.known_history_facts.get(source_record_id)
        if existing is not None:
            heard_from = tuple(getattr(existing, "heard_from_ids", ()) or ())
            teller_is_new = source_entity_id is not None and int(source_entity_id) not in heard_from
            # Hearing it again from someone already counted is repetition, not
            # corroboration, and must not make the memory sturdier. Callers that
            # do not say who told them keep the old unconditional behaviour -
            # most of them are witnessing or reading a record, where there is no
            # teller to be repetitive.
            if source_entity_id is None or teller_is_new:
                reinforced = reinforce_known_fact(
                    existing,
                    tick=int(tick),
                    source_type=str(source_type),
                    emotional_weight=profile.emotional_weight,
                )
            else:
                reinforced = existing
            if confidence > float(getattr(reinforced, "confidence", 0.0)):
                # Better evidence replaces what is believed, not just how
                # strongly. Somebody who heard the miller did it and then sees
                # the baker do it should end up believing the baker - and the
                # reverse must not happen, which is why this is gated on
                # confidence rising rather than on merely being told again.
                # That ordering is the whole evidence hierarchy: witnessed and
                # official beat hearsay, hearsay never overturns them.
                reinforced = replace(
                    reinforced,
                    confidence=confidence,
                    source_type=str(source_type),
                    claim_id=believed.id,
                    subject_entity_ids=believed.believed_subject_ids,
                    record_type=believed.believed_record_type,
                )
            if source_entity_id is not None:
                reinforced = replace(
                    reinforced,
                    source_entity_id=int(source_entity_id),
                    heard_from_ids=heard_from if not teller_is_new else heard_from + (int(source_entity_id),),
                )
            self.known_history_facts[source_record_id] = reinforced
            return confidence > float(getattr(existing, "confidence", 0.0))
        fact = KnownHistoryFact(
            source_record_id=source_record_id,
            record_type=_record_type(record),
            # From the claim, not the record. Every consumer of this field -
            # get_known_records_about_entity, dialogue_surface, ambient_info,
            # social_reaction - already reads it off the fact, so a belief about
            # the wrong person flows through all of them without their knowing
            # anything about claims.
            subject_entity_ids=believed.believed_subject_ids,
            known_at_tick=int(tick),
            source_type=str(source_type),
            confidence=confidence,
            settlement_id=_record_scope_value(record, "settlement_id"),
            region_id=_record_scope_value(record, "region_id"),
            tags=tags,
            record_class_name=type(record).__name__,
            source_entity_id=None if source_entity_id is None else int(source_entity_id),
            heard_from_ids=() if source_entity_id is None else (int(source_entity_id),),
            claim_id=believed.id,
        )
        self.known_history_facts[source_record_id] = fact_with_memory_profile(fact, profile, tick=int(tick))
        return True

    def knows_record(self, record_id: str) -> bool:
        return str(record_id) in self.known_history_facts

    def reset_transient_knowledge(self, *, reset_scope: str = "transient", clear_legacy_events: bool = True) -> set[str]:
        return reset_transient_knowledge(self, reset_scope=reset_scope, clear_legacy_events=clear_legacy_events)

    def get_known_records_by_type(
        self, record_type: str | type
    ) -> list[KnownHistoryFact]:
        if isinstance(record_type, type):
            return [
                fact
                for fact in self.known_history_facts.values()
                if fact.record_class_name == record_type.__name__
            ]
        record_type_name = str(record_type)
        return [
            fact
            for fact in self.known_history_facts.values()
            if fact.record_type == record_type_name
            or fact.record_class_name == record_type_name
        ]

    def get_known_records_about_entity(self, entity_id: int) -> list[KnownHistoryFact]:
        return [
            fact
            for fact in self.known_history_facts.values()
            if entity_id in fact.subject_entity_ids
        ]

    REPUTATION_EVENT_SCORES = {
        "murder": -50,
        "unpaid_wages": -20,
        # Witnessed crime (theft, assault, etc. - see engine.py's
        # record_crime_event / _process_npc_witness_events, which log these
        # with event_type="crime_witnessed") previously wasn't in this table
        # at all, so a witnessed theft or assault never touched reputation -
        # only unpaid wages and murder actually fed pricing/elections.
        # -25 is a judgment call: worse than unpaid_wages (-20), a purely
        # economic/civil wrong, since this covers real criminal acts against
        # people or property including violence, but well short of murder
        # (-50). This is a single flat value for all crime_kind values
        # (theft, assault, etc. alike) - REPUTATION_EVENT_SCORES has no
        # mechanism to differentiate by crime_kind today (murder/unpaid_wages
        # are flat single values too), so a theft and an assault currently
        # cost a witness's opinion the same amount. Splitting that out would
        # be a reasonable follow-up but is a bigger change than this pass.
        "crime_witnessed": -25,
        "crafted_masterwork": 10,
        "quest_complete": 15,
        "heroic_rescue": 25,
        "received_gift": 15,
        "marriage": 10,
        "raised_taxes": -25,
        "lowered_taxes": 12,
        "issued_bounty": -15,
        "issued_arrest_warrant": -10,
        # Grudge escalation (simulation/systems/scheduling.py's
        # run_npc_grudge_escalation_policy): a rare, severe/long-held
        # NPC-on-NPC grudge can now actually escalate into targeted gossip
        # or petty sabotage instead of just sitting there as a passive
        # distrust modifier. Both are deliberately milder than
        # crime_witnessed (-25) - unproven rumor/petty spite, not an actual
        # witnessed crime - with sabotage worse than plain gossip since it's
        # a real material act, not just talk.
        "malicious_gossip": -8,
        "petty_sabotage": -15,
    }

    def record_event(self, event: MemoryEvent) -> bool:
        if event is None:
            return False
        existing = self.known_memories.get(event.id)
        if existing is not None and existing.importance_score >= event.importance_score:
            return False
        self.known_memories[event.id] = event
        self._trim_memory_events()
        return True

    def knows_memory(self, event: MemoryEvent | str | None) -> bool:
        if isinstance(event, MemoryEvent):
            return event.id in self.known_memories
        if not event:
            return False
        return str(event) in self.known_memories

    def get_shareable_memory(self, listener: "KnowledgeComponent" | None = None, *, minimum_importance: int = 1) -> MemoryEvent | None:
        unknown_memories = [
            memory
            for memory in self.known_memories.values()
            if memory.importance_score >= minimum_importance
            and (listener is None or not listener.knows_memory(memory))
        ]
        if not unknown_memories:
            return None
        unknown_memories.sort(key=lambda memory: (-memory.importance_score, -memory.timestamp, memory.id))
        return unknown_memories[0]

    def choose_memories_to_share(
        self,
        listener: "KnowledgeComponent" | None = None,
        *,
        maximum: int = 3,
        minimum_importance: int = 1,
    ) -> list[MemoryEvent]:
        candidates = [
            memory
            for memory in self.known_memories.values()
            if memory.importance_score >= minimum_importance
            and (listener is None or not listener.knows_memory(memory))
        ]
        if not candidates:
            return []
        selection_count = random.randint(1, min(maximum, len(candidates)))
        selected: list[MemoryEvent] = []
        remaining = list(candidates)
        while remaining and len(selected) < selection_count:
            weights = [max(1, memory.importance_score) + random.randint(0, 10) for memory in remaining]
            picked = random.choices(remaining, weights=weights, k=1)[0]
            selected.append(picked)
            remaining = [memory for memory in remaining if memory.id != picked.id]
        selected.sort(key=lambda memory: (-memory.importance_score, -memory.timestamp, memory.id))
        return selected

    # --- Reputation decay (redemption over time) ---
    # Previously get_reputation_towards summed REPUTATION_EVENT_SCORES over
    # every known memory forever, with no way for an NPC who stopped
    # committing crimes to ever rebuild trust - the only pruning was
    # _trim_memory_events' capacity-based eviction, which can just as easily
    # drop a positive memory as a negative one and isn't triggered by time
    # passing at all.
    #
    # Design (judgment call, flagged for review): a fixed "grace period"
    # during which an event counts at full weight (recent behavior should
    # matter fully, not be discounted from day one), followed by exponential
    # half-life decay after that. Half-life decay was chosen over a hard
    # cutoff or linear fade so contribution shrinks quickly at first but
    # never fully vanishes - a notorious past murder should still leave a
    # faint trace generations later, matching "slow redemption, not instant
    # forgiveness" rather than a clean memory wipe. Both constants are in
    # game-days (via DAY_LENGTH_TICKS) and deliberately long relative to
    # GrudgeRecord's 5-12 day decay_days values elsewhere in this file -
    # grudges are personal, situational suspicion; reputation is meant to be
    # a much slower-moving, longer-memory signal.
    #
    # Applied symmetrically to positive AND negative events (a reformed
    # criminal's old good deeds fade at the same rate as their old crimes) -
    # the alternative (decay negative-only) would mean a single ancient
    # crime could keep outweighing a lifetime of subsequent good behavior,
    # which runs against the "gradual rebuilding of trust" goal.
    REPUTATION_DECAY_GRACE_DAYS = 14
    REPUTATION_DECAY_HALFLIFE_DAYS = 45

    def _reputation_decay_multiplier(self, current_tick: int, event_tick: int) -> float:
        age_ticks = current_tick - event_tick
        if age_ticks <= 0:
            return 1.0
        age_days = age_ticks / DAY_LENGTH_TICKS
        if age_days <= self.REPUTATION_DECAY_GRACE_DAYS:
            return 1.0
        decayed_days = age_days - self.REPUTATION_DECAY_GRACE_DAYS
        return 0.5 ** (decayed_days / self.REPUTATION_DECAY_HALFLIFE_DAYS)

    def get_reputation_towards(self, target_entity, *, current_tick: int | None = None) -> int:
        """Sum this entity's reputation-relevant memories about target_entity.

        current_tick: pass the world's current game_time to apply real
        time-based decay (older events count for progressively less, per
        _reputation_decay_multiplier). Left as None (no decay - identical
        to the old always-full-weight behavior) by default so callers that
        only care about an instantaneous, timeless comparison (and existing
        tests written against fixed-timestamp memories) are unaffected;
        production call sites in engine.py pass self.game_time explicitly.
        """
        if target_entity is None:
            return 0
        if hasattr(target_entity, "is_identity_concealed") and target_entity.is_identity_concealed():
            return 0

        target_id = getattr(target_entity, "id", None)
        if target_id is None:
            return 0

        total_score = 0.0
        for memory in self.known_memories.values():
            if memory.subject_id != target_id:
                continue
            base_score = self.REPUTATION_EVENT_SCORES.get(memory.event_type, 0)
            if current_tick is not None:
                base_score *= self._reputation_decay_multiplier(current_tick, memory.timestamp)
            total_score += base_score
        return int(round(total_score))

    def _trim_memory_events(self) -> None:
        while len(self.known_memories) > self.max_memory_events:
            lowest_priority = min(
                self.known_memories.values(),
                key=lambda memory: (memory.importance_score, memory.timestamp, memory.id),
            )
            self.known_memories.pop(lowest_priority.id, None)

    def __setstate__(self, state):
        dataclass_setstate(self, state)


class AspirationType(str, Enum):
    WEALTH = "wealth"
    POWER = "power"
    PEACE = "peace"


@dataclass
class AspirationComponent:
    aspiration_type: AspirationType = AspirationType.WEALTH
    target_settlement_id: str | None = None
    last_evaluated_day: int = -1

    def __setstate__(self, state):
        dataclass_setstate(self, state)


@dataclass
class TravelComponent:
    is_traveling: bool = False
    origin_settlement_id: str | None = None
    destination_settlement_id: str | None = None
    destination_coords: tuple[int, int] | None = None
    eta_days: int = 0
    group_leader_id: int | None = None
    group_member_ids: list[int] = field(default_factory=list)
    target_employment_task_id: str | None = None

    def __setstate__(self, state):
        dataclass_setstate(self, state)
