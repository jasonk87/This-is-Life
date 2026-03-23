from __future__ import annotations

from simulation.records import ChronicleArchive


class KnowledgeSystem:
    """Owns structured learning and sharing of event/book knowledge."""

    def __init__(self, records: ChronicleArchive):
        self.records = records

    def learn_event(self, holder, event) -> bool:
        if event.id in holder.knowledge.known_events:
            return False
        holder.knowledge.known_events[event.id] = event
        return True

    def learn_events(self, holder, events) -> int:
        learned = 0
        for event in events:
            if self.learn_event(holder, event):
                learned += 1
        return learned

    def share_event(self, source, recipient, event) -> bool:
        if event.id not in source.knowledge.known_events:
            return False
        return self.learn_event(recipient, event)

    def share_remote_events(self, source, recipient, *, current_coords: tuple[int, int], chunk_size: int) -> int:
        current_chunk_x = current_coords[0] // chunk_size
        current_chunk_y = current_coords[1] // chunk_size
        shared = 0
        for event in source.knowledge.known_events.values():
            is_local = False
            if event.location:
                chunk_x = event.location[0] // chunk_size
                chunk_y = event.location[1] // chunk_size
                is_local = chunk_x == current_chunk_x and chunk_y == current_chunk_y
            if not is_local and self.learn_event(recipient, event):
                shared += 1
        return shared

    def reset_known_events(self, holder):
        holder.knowledge.known_events.clear()

    def learn_local_events(self, holder, events, *, center: tuple[int, int], radius_sq: float) -> int:
        local_events = []
        for event in events:
            if not event.location:
                continue
            dist_sq = (event.location[0] - center[0]) ** 2 + (event.location[1] - center[1]) ** 2
            if dist_sq < radius_sq:
                local_events.append(event)
        return self.learn_events(holder, local_events)

    def learn_from_book(self, holder, book, *, book_item_key: str | None = None) -> int:
        learned = self.records.transfer_book_knowledge(book, holder.knowledge.known_events)
        if book_item_key and hasattr(holder.knowledge, "known_books"):
            holder.knowledge.known_books.add(book_item_key)
        return learned
