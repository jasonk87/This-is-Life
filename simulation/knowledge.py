from __future__ import annotations

from entities.social import reset_transient_knowledge
from simulation.records import ChronicleArchive


class KnowledgeSystem:
    """Owns structured learning and sharing of event/book knowledge."""

    def __init__(self, records: ChronicleArchive):
        self.records = records

    @staticmethod
    def _event_tick(event) -> int:
        return int(getattr(event, "timestamp", getattr(event, "game_time", 0)))

    def learn_history_record(
        self,
        holder,
        record,
        *,
        source_type: str = "witnessed",
        confidence: float = 1.0,
        tick: int | None = None,
        source_entity_id: int | None = None,
    ) -> bool:
        knowledge = getattr(holder, "knowledge", None)
        if knowledge is None or record is None:
            return False
        if tick is None:
            tick = self._event_tick(record)

        learned_fact = False
        learn_history_record = getattr(knowledge, "learn_history_record", None)
        if callable(learn_history_record):
            learned_fact = learn_history_record(
                record, source_type, confidence, tick, source_entity_id=source_entity_id
            )

        known_events = getattr(knowledge, "known_events", None)
        learned_event = False
        record_id = getattr(record, "id", getattr(record, "record_id", None))
        if record_id and isinstance(known_events, dict) and record_id not in known_events:
            known_events[record_id] = record
            learned_event = True
        return learned_fact or learned_event

    def learn_event(
        self,
        holder,
        event,
        *,
        source_type: str = "witnessed",
        confidence: float = 1.0,
        tick: int | None = None,
        source_entity_id: int | None = None,
    ) -> bool:
        return self.learn_history_record(
            holder,
            event,
            source_type=source_type,
            confidence=confidence,
            tick=tick,
            source_entity_id=source_entity_id,
        )

    def learn_events(self, holder, events) -> int:
        learned = 0
        for event in events:
            if self.learn_event(holder, event):
                learned += 1
        return learned

    def share_event(self, source, recipient, event) -> bool:
        source_knowledge = getattr(source, "knowledge", None)
        if source_knowledge is None:
            return False
        event_id = getattr(event, "id", getattr(event, "record_id", None))
        if not event_id:
            return False
        source_knows_event = event_id in getattr(source_knowledge, "known_events", {})
        knows_record = getattr(source_knowledge, "knows_record", None)
        source_knows_fact = callable(knows_record) and knows_record(event_id)
        if not source_knows_event and not source_knows_fact:
            return False
        return self.learn_history_record(
            recipient,
            event,
            source_type="told",
            confidence=0.8,
            tick=self._event_tick(event),
            # The one place a belief passes between two people, and the only
            # place that knows who the teller was.
            source_entity_id=getattr(source, "id", None),
        )

    def share_remote_events(
        self,
        source,
        recipient,
        *,
        current_coords: tuple[int, int],
        chunk_size: int,
    ) -> int:
        current_chunk_x = current_coords[0] // chunk_size
        current_chunk_y = current_coords[1] // chunk_size
        shared = 0
        for event in source.knowledge.known_events.values():
            is_local = False
            if event.location:
                chunk_x = event.location[0] // chunk_size
                chunk_y = event.location[1] // chunk_size
                is_local = chunk_x == current_chunk_x and chunk_y == current_chunk_y
            if not is_local and self.share_event(source, recipient, event):
                shared += 1
        return shared

    def reset_known_events(
        self,
        holder,
        *,
        clear_typed_facts: bool = True,
        reset_scope: str = "transient",
    ):
        knowledge = getattr(holder, "knowledge", None)
        if knowledge is None:
            return set()
        if clear_typed_facts:
            return reset_transient_knowledge(
                holder,
                reset_scope=reset_scope,
                clear_legacy_events=True,
            )
        knowledge.known_events.clear()
        return set()

    def learn_local_events(
        self,
        holder,
        events,
        *,
        center: tuple[int, int],
        radius_sq: float,
    ) -> int:
        local_events = []
        for event in events:
            if not event.location:
                continue
            dist_sq = (event.location[0] - center[0]) ** 2 + (
                event.location[1] - center[1]
            ) ** 2
            if dist_sq < radius_sq:
                local_events.append(event)
        return self.learn_events(holder, local_events)

    def learn_from_book(
        self,
        holder,
        book,
        *,
        book_item_key: str | None = None,
        tick: int = 0,
    ) -> int:
        learned = self.records.transfer_book_knowledge(
            book,
            holder.knowledge,
            source_type="read",
            confidence=1.0,
            tick=tick,
        )
        if book_item_key and hasattr(holder.knowledge, "known_books"):
            holder.knowledge.known_books.add(book_item_key)
        return learned
