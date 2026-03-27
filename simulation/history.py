from __future__ import annotations

from dataclasses import dataclass, field
import uuid


@dataclass(slots=True)
class Book:
    """A written record that can be surfaced as an in-world item."""

    title: str
    author_id: int
    author_name: str
    year_written: int
    content: str
    book_type: str = "chronicle"
    referenced_event_ids: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass(slots=True)
class Event:
    """A significant world event stored in the history ledger."""

    event_type: str
    description: str
    subject_id: int
    game_time: int
    target_id: int | None = None
    location: tuple[int, int] | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    public_knowledge: bool = False

    @property
    def type(self) -> str:
        return self.event_type

    @type.setter
    def type(self, value: str):
        self.event_type = value

    @property
    def timestamp(self) -> int:
        return self.game_time

    @timestamp.setter
    def timestamp(self, value: int):
        self.game_time = value


class HistoryLedger:
    """Owns world-scale history and authored records."""

    def __init__(self, event_limit: int = 200):
        self.event_limit = event_limit
        self.events: list[Event] = []
        self.books: list[Book] = []

    def add_event(
        self,
        event_type: str,
        description: str,
        subject_id: int,
        game_time: int,
        target_id: int | None = None,
        location: tuple[int, int] | None = None,
    ) -> Event:
        event = Event(
            event_type=event_type,
            description=description,
            subject_id=subject_id,
            target_id=target_id,
            location=location,
            game_time=game_time,
        )
        self.events.append(event)
        if len(self.events) > self.event_limit:
            self.events.pop(0)
        return event

    def add_book(self, book: Book) -> Book:
        self.books.append(book)
        return book

    def get_event(self, event_id: str) -> Event | None:
        return next((event for event in self.events if event.id == event_id), None)

    def get_book(self, book_id: str) -> Book | None:
        return next((book for book in self.books if book.id == book_id), None)

    def recent_events_since(self, minimum_game_time: int) -> list[Event]:
        return [event for event in self.events if event.timestamp >= minimum_game_time]
