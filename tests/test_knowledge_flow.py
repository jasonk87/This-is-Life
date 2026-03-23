from types import SimpleNamespace

from simulation.history import Book, Event, HistoryLedger
from simulation.knowledge import KnowledgeSystem
from simulation.records import ChronicleArchive


def _holder():
    return SimpleNamespace(
        knowledge=SimpleNamespace(
            known_events={},
            known_books=set(),
        )
    )


def test_knowledge_system_shares_remote_and_local_events():
    history = HistoryLedger()
    knowledge = KnowledgeSystem(ChronicleArchive(history))
    source = _holder()
    recipient = _holder()

    remote_event = Event("remote", "Remote news", 1, 10, location=(80, 80))
    local_event = Event("local", "Local news", 2, 10, location=(5, 5))
    knowledge.learn_event(source, remote_event)
    knowledge.learn_event(source, local_event)

    shared = knowledge.share_remote_events(
        source,
        recipient,
        current_coords=(4, 4),
        chunk_size=40,
    )

    assert shared == 1
    assert remote_event.id in recipient.knowledge.known_events
    assert local_event.id not in recipient.knowledge.known_events


def test_knowledge_system_learns_from_books_and_local_event_refresh():
    history = HistoryLedger()
    archive = ChronicleArchive(history)
    knowledge = KnowledgeSystem(archive)
    holder = _holder()

    nearby = history.add_event("nearby", "Nearby event", 1, game_time=4, location=(12, 12))
    distant = history.add_event("far", "Far event", 2, game_time=4, location=(200, 200))
    book = Book(
        "Chronicle",
        7,
        "Scribe",
        1,
        "Content",
        "chronicle",
        referenced_event_ids=[nearby.id],
    )
    archive.add_book(book)

    learned = knowledge.learn_from_book(holder, book, book_item_key=f"book_{book.id}")
    knowledge.reset_known_events(holder)
    relearned = knowledge.learn_local_events(
        holder,
        history.events,
        center=(10, 10),
        radius_sq=30 ** 2,
    )

    assert learned == 1
    assert f"book_{book.id}" in holder.knowledge.known_books
    assert relearned == 1
    assert nearby.id in holder.knowledge.known_events
    assert distant.id not in holder.knowledge.known_events
