from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import uuid

from simulation.ids import new_id


def _new_history_id() -> str:
    return new_id()


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
    id: str = field(default_factory=_new_history_id)


@dataclass(slots=True)
class Event:
    """A significant world event stored in the history ledger."""

    event_type: str
    description: str
    subject_id: int
    game_time: int
    target_id: int | None = None
    location: tuple[int, int] | None = None
    id: str = field(default_factory=_new_history_id)
    public_knowledge: bool = False
    tags: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

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

    @property
    def record_id(self) -> str:
        return self.id

    @record_id.setter
    def record_id(self, value: str):
        self.id = value

    @property
    def tick(self) -> int:
        return self.game_time

    @tick.setter
    def tick(self, value: int):
        self.game_time = value

    @property
    def participant_ids(self) -> tuple[int, ...]:
        participants = [self.subject_id]
        if self.target_id is not None:
            participants.append(self.target_id)
        for participant_id in self.metadata.get("participant_ids", ()):
            if participant_id is not None:
                participants.append(participant_id)
        return tuple(dict.fromkeys(participants))


@dataclass(slots=True, kw_only=True)
class BirthRecord(Event):
    child_id: int
    parent_ids: tuple[int, ...]
    child_name: str = ""
    settlement_id: str | None = None
    region_id: str | None = None

    def __post_init__(self):
        self.event_type = "npc_birth"
        self.metadata.setdefault("child_id", self.child_id)
        self.metadata.setdefault("parent_ids", list(self.parent_ids))
        self.metadata.setdefault("child_name", self.child_name)
        if self.settlement_id is not None:
            self.metadata.setdefault("settlement_id", self.settlement_id)
        if self.region_id is not None:
            self.metadata.setdefault("region_id", self.region_id)
        self.metadata.setdefault(
            "participant_ids",
            [self.child_id, *self.parent_ids],
        )


@dataclass(slots=True, kw_only=True)
class DeathRecord(Event):
    deceased_id: int
    killer_id: int | None = None
    cause_of_death: str = ""
    settlement_id: str | None = None
    region_id: str | None = None

    def __post_init__(self):
        self.event_type = "entity_death"
        self.metadata.setdefault("deceased_id", self.deceased_id)
        self.metadata.setdefault("killer_id", self.killer_id)
        self.metadata.setdefault("cause_of_death", self.cause_of_death)
        if self.settlement_id is not None:
            self.metadata.setdefault("settlement_id", self.settlement_id)
        if self.region_id is not None:
            self.metadata.setdefault("region_id", self.region_id)
        participant_ids = [self.deceased_id]
        if self.killer_id is not None:
            participant_ids.append(self.killer_id)
        self.metadata.setdefault("participant_ids", participant_ids)


@dataclass(slots=True, kw_only=True)
class MarriageRecord(Event):
    spouse_ids: tuple[int, int]
    settlement_id: str | None = None
    region_id: str | None = None

    def __post_init__(self):
        self.event_type = "npc_marriage"
        self.metadata.setdefault("spouse_ids", list(self.spouse_ids))
        if self.settlement_id is not None:
            self.metadata.setdefault("settlement_id", self.settlement_id)
        if self.region_id is not None:
            self.metadata.setdefault("region_id", self.region_id)
        self.metadata.setdefault("participant_ids", list(self.spouse_ids))


@dataclass(slots=True, kw_only=True)
class MigrationRecord(Event):
    traveler_id: int
    migration_kind: str
    origin_label: str | None = None
    destination_label: str | None = None
    settlement_id: str | None = None
    region_id: str | None = None

    def __post_init__(self):
        self.event_type = "npc_emigrated" if self.migration_kind == "emigrated" else "npc_migrated"
        self.metadata.setdefault("traveler_id", self.traveler_id)
        self.metadata.setdefault("migration_kind", self.migration_kind)
        self.metadata.setdefault("origin_label", self.origin_label)
        self.metadata.setdefault("destination_label", self.destination_label)
        if self.settlement_id is not None:
            self.metadata.setdefault("settlement_id", self.settlement_id)
        if self.region_id is not None:
            self.metadata.setdefault("region_id", self.region_id)
        self.metadata.setdefault("participant_ids", [self.traveler_id])


@dataclass(slots=True, kw_only=True)
class CrimeRecord(Event):
    crime_kind: str
    suspect_id: int
    victim_id: int | None = None
    witness_ids: tuple[int, ...] = ()
    settlement_id: str | None = None
    region_id: str | None = None

    def __post_init__(self):
        self.metadata.setdefault("crime_kind", self.crime_kind)
        self.metadata.setdefault("suspect_id", self.suspect_id)
        self.metadata.setdefault("victim_id", self.victim_id)
        self.metadata.setdefault("witness_ids", list(self.witness_ids))
        if self.settlement_id is not None:
            self.metadata.setdefault("settlement_id", self.settlement_id)
        if self.region_id is not None:
            self.metadata.setdefault("region_id", self.region_id)
        participant_ids = [self.suspect_id]
        if self.victim_id is not None:
            participant_ids.append(self.victim_id)
        participant_ids.extend(self.witness_ids)
        self.metadata.setdefault("participant_ids", participant_ids)


@dataclass(slots=True, kw_only=True)
class EmploymentRecord(Event):
    worker_id: int
    profession: str
    employment_action: str
    building_id: str | None = None
    settlement_id: str | None = None
    region_id: str | None = None

    def __post_init__(self):
        action_to_type = {
            "hired": "npc_hired",
            "fired": "npc_fired",
            "quit": "npc_quit_job",
        }
        self.event_type = action_to_type.get(self.employment_action, "npc_employment_changed")
        self.metadata.setdefault("worker_id", self.worker_id)
        self.metadata.setdefault("profession", self.profession)
        self.metadata.setdefault("employment_action", self.employment_action)
        self.metadata.setdefault("building_id", self.building_id)
        if self.settlement_id is not None:
            self.metadata.setdefault("settlement_id", self.settlement_id)
        if self.region_id is not None:
            self.metadata.setdefault("region_id", self.region_id)
        self.metadata.setdefault("participant_ids", [self.worker_id])


class HistoryLedger:
    """Owns world-scale history and authored records."""

    def __init__(self, event_limit: int = 200):
        self.event_limit = event_limit
        self.events: list[Event] = []
        self.books: list[Book] = []
        self._events_by_id: dict[str, Event] = {}
        self._books_by_id: dict[str, Book] = {}
        self._entity_event_ids: dict[int, list[str]] = defaultdict(list)
        self._location_event_ids: dict[tuple[int, int], list[str]] = defaultdict(list)
        self._type_event_ids: dict[str, list[str]] = defaultdict(list)
        self._settlement_record_ids: dict[str, list[str]] = defaultdict(list)
        self._region_record_ids: dict[str, list[str]] = defaultdict(list)

    @staticmethod
    def _record_settlement_id(record: Event) -> str | None:
        return getattr(record, "settlement_id", None) or record.metadata.get("settlement_id")

    @staticmethod
    def _record_region_id(record: Event) -> str | None:
        return getattr(record, "region_id", None) or record.metadata.get("region_id")

    def _index_event(self, event: Event):
        self._events_by_id[event.id] = event
        self._type_event_ids[event.type].append(event.id)
        if event.location is not None:
            self._location_event_ids[event.location].append(event.id)
        settlement_id = self._record_settlement_id(event)
        if settlement_id is not None:
            self._settlement_record_ids[str(settlement_id)].append(event.id)
        region_id = self._record_region_id(event)
        if region_id is not None:
            self._region_record_ids[str(region_id)].append(event.id)
        for participant_id in event.participant_ids:
            self._entity_event_ids[participant_id].append(event.id)

    def _remove_event_from_indexes(self, event: Event):
        self._events_by_id.pop(event.id, None)
        event_ids = self._type_event_ids.get(event.type)
        if event_ids and event.id in event_ids:
            event_ids.remove(event.id)
        if event.location is not None:
            location_ids = self._location_event_ids.get(event.location)
            if location_ids and event.id in location_ids:
                location_ids.remove(event.id)
        settlement_id = self._record_settlement_id(event)
        if settlement_id is not None:
            settlement_ids = self._settlement_record_ids.get(str(settlement_id))
            if settlement_ids and event.id in settlement_ids:
                settlement_ids.remove(event.id)
        region_id = self._record_region_id(event)
        if region_id is not None:
            region_ids = self._region_record_ids.get(str(region_id))
            if region_ids and event.id in region_ids:
                region_ids.remove(event.id)
        for participant_id in event.participant_ids:
            participant_event_ids = self._entity_event_ids.get(participant_id)
            if participant_event_ids and event.id in participant_event_ids:
                participant_event_ids.remove(event.id)

    def _trim_if_needed(self):
        while len(self.events) > self.event_limit:
            removed = self.events.pop(0)
            self._remove_event_from_indexes(removed)

    def add_record(self, event: Event) -> Event:
        self.events.append(event)
        self._index_event(event)
        self._trim_if_needed()
        return event

    def add_event(
        self,
        event_type: str,
        description: str,
        subject_id: int,
        game_time: int,
        target_id: int | None = None,
        location: tuple[int, int] | None = None,
        tags: tuple[str, ...] = (),
        metadata: dict[str, object] | None = None,
    ) -> Event:
        return self.add_record(
            Event(
                event_type=event_type,
                description=description,
                subject_id=subject_id,
                target_id=target_id,
                location=location,
                game_time=game_time,
                tags=tags,
                metadata=metadata or {},
            )
        )

    def record_birth(
        self,
        *,
        child_id: int,
        parent_ids: tuple[int, ...],
        child_name: str,
        description: str,
        game_time: int,
        location: tuple[int, int] | None = None,
        settlement_id: str | None = None,
        region_id: str | None = None,
    ) -> BirthRecord:
        return self.add_record(
            BirthRecord(
                event_type="npc_birth",
                description=description,
                subject_id=child_id,
                target_id=parent_ids[0] if parent_ids else None,
                game_time=game_time,
                location=location,
                child_id=child_id,
                parent_ids=parent_ids,
                child_name=child_name,
                settlement_id=settlement_id,
                region_id=region_id,
                tags=("life", "birth"),
            )
        )

    def record_death(
        self,
        *,
        deceased_id: int,
        description: str,
        game_time: int,
        killer_id: int | None = None,
        location: tuple[int, int] | None = None,
        cause_of_death: str = "",
        settlement_id: str | None = None,
        region_id: str | None = None,
    ) -> DeathRecord:
        return self.add_record(
            DeathRecord(
                event_type="entity_death",
                description=description,
                subject_id=deceased_id,
                target_id=killer_id,
                game_time=game_time,
                location=location,
                deceased_id=deceased_id,
                killer_id=killer_id,
                cause_of_death=cause_of_death,
                settlement_id=settlement_id,
                region_id=region_id,
                tags=("life", "death"),
            )
        )

    def record_marriage(
        self,
        *,
        spouse_ids: tuple[int, int],
        description: str,
        game_time: int,
        location: tuple[int, int] | None = None,
        settlement_id: str | None = None,
        region_id: str | None = None,
    ) -> MarriageRecord:
        return self.add_record(
            MarriageRecord(
                event_type="npc_marriage",
                description=description,
                subject_id=spouse_ids[0],
                target_id=spouse_ids[1],
                game_time=game_time,
                location=location,
                spouse_ids=spouse_ids,
                settlement_id=settlement_id,
                region_id=region_id,
                tags=("social", "marriage"),
            )
        )

    def record_migration(
        self,
        *,
        traveler_id: int,
        migration_kind: str,
        description: str,
        game_time: int,
        location: tuple[int, int] | None = None,
        origin_label: str | None = None,
        destination_label: str | None = None,
        settlement_id: str | None = None,
        region_id: str | None = None,
    ) -> MigrationRecord:
        return self.add_record(
            MigrationRecord(
                event_type="npc_migrated",
                description=description,
                subject_id=traveler_id,
                game_time=game_time,
                location=location,
                traveler_id=traveler_id,
                migration_kind=migration_kind,
                origin_label=origin_label,
                destination_label=destination_label,
                settlement_id=settlement_id,
                region_id=region_id,
                tags=("social", "migration"),
            )
        )

    def record_crime(
        self,
        *,
        crime_kind: str,
        suspect_id: int,
        description: str,
        game_time: int,
        victim_id: int | None = None,
        witness_ids: tuple[int, ...] = (),
        location: tuple[int, int] | None = None,
        settlement_id: str | None = None,
        region_id: str | None = None,
        event_type: str = "crime_recorded",
    ) -> CrimeRecord:
        return self.add_record(
            CrimeRecord(
                event_type=event_type,
                description=description,
                subject_id=suspect_id,
                target_id=victim_id,
                game_time=game_time,
                location=location,
                crime_kind=crime_kind,
                suspect_id=suspect_id,
                victim_id=victim_id,
                witness_ids=witness_ids,
                settlement_id=settlement_id,
                region_id=region_id,
                tags=("law", "crime"),
            )
        )

    def record_employment_change(
        self,
        *,
        worker_id: int,
        profession: str,
        employment_action: str,
        description: str,
        game_time: int,
        location: tuple[int, int] | None = None,
        building_id: str | None = None,
        settlement_id: str | None = None,
        region_id: str | None = None,
    ) -> EmploymentRecord:
        return self.add_record(
            EmploymentRecord(
                event_type="npc_employment_changed",
                description=description,
                subject_id=worker_id,
                game_time=game_time,
                location=location,
                worker_id=worker_id,
                profession=profession,
                employment_action=employment_action,
                building_id=building_id,
                settlement_id=settlement_id,
                region_id=region_id,
                tags=("economy", "employment"),
            )
        )

    def add_book(self, book: Book) -> Book:
        self.books.append(book)
        self._books_by_id[book.id] = book
        return book

    def get_event(self, event_id: str) -> Event | None:
        return self._events_by_id.get(event_id)

    def get_book(self, book_id: str) -> Book | None:
        return self._books_by_id.get(book_id)

    def get_events_for_entity(self, entity_id: int) -> list[Event]:
        return [self._events_by_id[event_id] for event_id in self._entity_event_ids.get(entity_id, []) if event_id in self._events_by_id]

    def get_events_by_type(self, event_type: str) -> list[Event]:
        return [self._events_by_id[event_id] for event_id in self._type_event_ids.get(event_type, []) if event_id in self._events_by_id]

    def get_records_by_entity(self, entity_id: int) -> list[Event]:
        return self.get_events_for_entity(entity_id)

    def get_records_by_type(self, record_type: str | type[Event]) -> list[Event]:
        if isinstance(record_type, str):
            return self.get_events_by_type(record_type)
        return [record for record in self.events if isinstance(record, record_type)]

    def get_records_by_settlement(self, settlement_id: str) -> list[Event]:
        return [self._events_by_id[event_id] for event_id in self._settlement_record_ids.get(str(settlement_id), []) if event_id in self._events_by_id]

    def get_records_by_region(self, region_id: str) -> list[Event]:
        return [self._events_by_id[event_id] for event_id in self._region_record_ids.get(str(region_id), []) if event_id in self._events_by_id]

    def get_events_at_location(self, location: tuple[int, int]) -> list[Event]:
        return [self._events_by_id[event_id] for event_id in self._location_event_ids.get(location, []) if event_id in self._events_by_id]

    def recent_events_since(self, minimum_game_time: int) -> list[Event]:
        return [event for event in self.events if event.timestamp >= minimum_game_time]

    def recent_public_events_since(self, minimum_game_time: int) -> list[Event]:
        return [event for event in self.events if event.timestamp >= minimum_game_time and event.public_knowledge]
