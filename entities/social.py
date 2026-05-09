"""Deterministic social memory primitives for gossip and witness recall."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import random
from typing import Any


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


@dataclass
class LocalOpinionRecord:
    """Belief-driven local standing for a target entity from one observer's perspective."""

    target_id: int
    score: float = 0.0
    evidence_count: int = 0
    last_updated_day: int = 0


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
    claimed_tasks: list[str] = field(default_factory=list)
    known_books: set[str] = field(default_factory=set)
    recently_spoken_topic_ids: list[str] = field(default_factory=list)
    last_spoken_topic_tick: dict[str, int] = field(default_factory=dict)
    spoken_topic_counts: dict[str, int] = field(default_factory=dict)
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
    ) -> bool:
        if record is None:
            return False
        source_record_id = _record_id(record)
        if not source_record_id:
            return False
        confidence = max(0.0, min(1.0, float(confidence)))
        existing = self.known_history_facts.get(source_record_id)
        if existing is not None and existing.confidence >= confidence:
            return False
        tags = tuple(getattr(record, "tags", ()) or ())
        fact = KnownHistoryFact(
            source_record_id=source_record_id,
            record_type=_record_type(record),
            subject_entity_ids=_record_subject_entity_ids(record),
            known_at_tick=int(tick),
            source_type=str(source_type),
            confidence=confidence,
            settlement_id=_record_scope_value(record, "settlement_id"),
            region_id=_record_scope_value(record, "region_id"),
            tags=tags,
            record_class_name=type(record).__name__,
        )
        self.known_history_facts[source_record_id] = fact
        return True

    def knows_record(self, record_id: str) -> bool:
        return str(record_id) in self.known_history_facts

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
        "crafted_masterwork": 10,
        "quest_complete": 15,
        "heroic_rescue": 25,
        "received_gift": 15,
        "marriage": 10,
        "raised_taxes": -25,
        "lowered_taxes": 12,
        "issued_bounty": -15,
        "issued_arrest_warrant": -10,
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

    def get_reputation_towards(self, target_entity) -> int:
        if target_entity is None:
            return 0
        if hasattr(target_entity, "is_identity_concealed") and target_entity.is_identity_concealed():
            return 0

        target_id = getattr(target_entity, "id", None)
        if target_id is None:
            return 0

        total_score = 0
        for memory in self.known_memories.values():
            if memory.subject_id != target_id:
                continue
            total_score += self.REPUTATION_EVENT_SCORES.get(memory.event_type, 0)
        return total_score

    def _trim_memory_events(self) -> None:
        while len(self.known_memories) > self.max_memory_events:
            lowest_priority = min(
                self.known_memories.values(),
                key=lambda memory: (memory.importance_score, memory.timestamp, memory.id),
            )
            self.known_memories.pop(lowest_priority.id, None)


class AspirationType(str, Enum):
    WEALTH = "wealth"
    POWER = "power"
    PEACE = "peace"


@dataclass
class AspirationComponent:
    aspiration_type: AspirationType = AspirationType.WEALTH
    target_settlement_id: str | None = None
    last_evaluated_day: int = -1


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
