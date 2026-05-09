from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from simulation.history import (
    BirthRecord,
    Book,
    CrimeRecord,
    DeathRecord,
    EmploymentRecord,
    Event,
    HistoryLedger,
    MarriageRecord,
    MigrationRecord,
)


TypedHistoryRecord = (
    BirthRecord
    | DeathRecord
    | MarriageRecord
    | CrimeRecord
    | MigrationRecord
    | EmploymentRecord
)
TYPED_HISTORY_RECORD_TYPES = (
    BirthRecord,
    DeathRecord,
    MarriageRecord,
    CrimeRecord,
    MigrationRecord,
    EmploymentRecord,
)


@dataclass(slots=True)
class CensusSnapshot:
    village_name: str
    year: int
    population: int
    total_wealth: int
    average_wealth: int
    richest_name: str
    richest_wealth: int
    poorest_name: str
    poorest_wealth: int
    profession_counts: dict[str, int]


class CensusLedger:
    """Structured census snapshots that can also be rendered into books."""

    def __init__(self):
        self.snapshots: list[CensusSnapshot] = []

    def record_snapshot(self, snapshot: CensusSnapshot) -> CensusSnapshot:
        self.snapshots.append(snapshot)
        return snapshot


def _entity_label(entity_id: int | None, fallback: str = "Unknown") -> str:
    if entity_id is None:
        return fallback
    return f"Entity {entity_id}"


def _record_year(record: Event) -> int:
    return getattr(record, "game_time", getattr(record, "timestamp", 0))


class BookCompiler:
    """Compiles structured history and social data into written records."""

    @staticmethod
    def _format_birth(record: BirthRecord) -> str:
        child_name = record.child_name or _entity_label(record.child_id)
        if record.parent_ids:
            parents = ", ".join(
                _entity_label(parent_id) for parent_id in record.parent_ids
            )
            return f"{child_name} was born to {parents}."
        return f"{child_name} was born."

    @staticmethod
    def _format_death(record: DeathRecord) -> str:
        line = f"{_entity_label(record.deceased_id)} died"
        if record.cause_of_death:
            line += f" from {record.cause_of_death}"
        if record.killer_id is not None:
            line += f"; killer: {_entity_label(record.killer_id)}"
        return line + "."

    @staticmethod
    def _format_marriage(record: MarriageRecord) -> str:
        spouse_a, spouse_b = record.spouse_ids
        return f"{_entity_label(spouse_a)} and {_entity_label(spouse_b)} married."

    @staticmethod
    def _format_crime(record: CrimeRecord) -> str:
        crime_kind = record.crime_kind or "crime"
        line = (
            f"{crime_kind.capitalize()} recorded; "
            f"suspect: {_entity_label(record.suspect_id)}"
        )
        if record.victim_id is not None:
            line += f"; victim: {_entity_label(record.victim_id)}"
        if record.witness_ids:
            witnesses = ", ".join(
                _entity_label(witness_id) for witness_id in record.witness_ids
            )
            line += f"; witnesses: {witnesses}"
        return line + "."

    @staticmethod
    def _format_migration(record: MigrationRecord) -> str:
        traveler = _entity_label(record.traveler_id)
        action = "emigrated" if record.migration_kind == "emigrated" else "migrated"
        if record.origin_label and record.destination_label:
            return (
                f"{traveler} {action} from "
                f"{record.origin_label} to {record.destination_label}."
            )
        if record.destination_label:
            return f"{traveler} {action} to {record.destination_label}."
        if record.origin_label:
            return f"{traveler} {action} from {record.origin_label}."
        return f"{traveler} {action}."

    @staticmethod
    def _format_employment(record: EmploymentRecord) -> str:
        worker = _entity_label(record.worker_id)
        action = record.employment_action or "changed employment"
        profession = record.profession or "an unspecified profession"
        if action == "hired":
            return f"{worker} was hired as {profession}."
        if action == "fired":
            return f"{worker} was fired from {profession}."
        if action == "quit":
            return f"{worker} quit work as {profession}."
        return f"{worker} had an employment change: {profession}."

    @classmethod
    def format_history_record(cls, record: Event) -> str:
        """Render typed history records first, with generic event descriptions as fallback."""

        if isinstance(record, BirthRecord):
            return cls._format_birth(record)
        if isinstance(record, DeathRecord):
            return cls._format_death(record)
        if isinstance(record, MarriageRecord):
            return cls._format_marriage(record)
        if isinstance(record, CrimeRecord):
            return cls._format_crime(record)
        if isinstance(record, MigrationRecord):
            return cls._format_migration(record)
        if isinstance(record, EmploymentRecord):
            return cls._format_employment(record)
        return record.description

    @staticmethod
    def _chronicle_bucket(record: Event) -> str | None:
        if isinstance(record, BirthRecord) or record.type == "npc_birth":
            return "Births"
        if isinstance(record, DeathRecord) or record.type == "entity_death":
            return "Deaths"
        if isinstance(record, MarriageRecord) or record.type == "npc_marriage":
            return "Marriages"
        if isinstance(record, MigrationRecord) or record.type in {
            "npc_migrated",
            "npc_emigrated",
        }:
            return "Migration"
        if isinstance(record, CrimeRecord) or "crime" in record.type:
            return "Criminal Activity"
        if isinstance(record, EmploymentRecord) or record.type in {
            "npc_hired",
            "npc_fired",
            "npc_quit_job",
            "npc_employment_changed",
        }:
            return "Employment"
        return None

    def compile_chronicle(
        self,
        *,
        title: str,
        author_id: int,
        author_name: str,
        year_written: int,
        events: list[Event],
    ) -> Book:
        sections: dict[str, list[str]] = {
            "Births": [],
            "Deaths": [],
            "Marriages": [],
            "Migration": [],
            "Criminal Activity": [],
            "Employment": [],
        }
        for event in events:
            bucket = self._chronicle_bucket(event)
            if bucket is not None:
                sections[bucket].append(self.format_history_record(event))

        book_content = (
            f"The Chronicle of Year {year_written}\n"
            "Required Reading for Citizens.\n\n"
        )
        for heading, lines in sections.items():
            if lines:
                book_content += (
                    f"{heading}:\n"
                    + "\n".join(f"- {line}" for line in lines)
                    + "\n\n"
                )
        if not any(sections.values()):
            book_content += "A year of tranquility and little note."

        return Book(
            title=title,
            author_id=author_id,
            author_name=author_name,
            year_written=year_written,
            content=book_content,
            book_type="chronicle",
            referenced_event_ids=[event.id for event in events],
        )

    def compile_biography(
        self,
        *,
        title: str,
        author_id: int,
        author_name: str,
        year_written: int,
        subject_name: str,
        subject_title: str,
        fame: int,
        infamy: int,
        subject_events: list[Event],
    ) -> Book:
        if subject_events:
            sorted_events = sorted(subject_events, key=_record_year)
            book_content = f"The Life of {subject_name}\n"
            book_content += f"Title: {subject_title or 'Unknown'}\n\n"
            book_content += "Known Deeds:\n"
            for event in sorted_events:
                book_content += f"- {self.format_history_record(event)}\n"
            referenced_event_ids = [event.id for event in sorted_events]
        else:
            reputation_summary = []
            if fame > 0:
                reputation_summary.append(
                    f"They are remembered for notable deeds (fame {fame})."
                )
            if infamy > 0:
                reputation_summary.append(f"They are also shadowed by infamy ({infamy}).")
            if not reputation_summary:
                reputation_summary.append(
                    f"Little is recorded about {subject_name}, "
                    "but their story is still worth preserving."
                )

            book_content = f"The Life of {subject_name}\n"
            book_content += f"Title: {subject_title or 'Unknown'}\n\n"
            book_content += "Known Deeds:\n"
            for summary_line in reputation_summary:
                book_content += f"- {summary_line}\n"
            referenced_event_ids = []

        return Book(
            title=title,
            author_id=author_id,
            author_name=author_name,
            year_written=year_written,
            content=book_content,
            book_type="biography",
            referenced_event_ids=referenced_event_ids,
        )

    def compile_census_report(
        self,
        *,
        title: str,
        author_id: int,
        author_name: str,
        snapshot: CensusSnapshot,
    ) -> Book:
        report_content = f"Official Census Report - Year {snapshot.year}\n\n"
        report_content += f"Jurisdiction: {snapshot.village_name}\n"
        report_content += f"Total Population: {snapshot.population}\n"
        report_content += f"Total Village Wealth: {snapshot.total_wealth} coins\n"
        report_content += f"Average Income: {snapshot.average_wealth} coins\n\n"
        report_content += "Economic Status:\n"
        report_content += (
            f"- Richest Citizen: {snapshot.richest_name} "
            f"({snapshot.richest_wealth} coins)\n"
        )
        report_content += (
            f"- Poorest Citizen: {snapshot.poorest_name} "
            f"({snapshot.poorest_wealth} coins)\n\n"
        )
        report_content += "Employment Statistics:\n"
        for profession, count in snapshot.profession_counts.items():
            report_content += f"- {profession}: {count}\n"

        return Book(
            title=title,
            author_id=author_id,
            author_name=author_name,
            year_written=snapshot.year,
            content=report_content,
            book_type="census",
        )


class ChronicleArchive:
    """Owns authored books and knowledge transfer built on top of the history ledger."""

    def __init__(self, history: HistoryLedger):
        self.history = history
        self.compiler = BookCompiler()
        self.census = CensusLedger()

    @property
    def books(self) -> list[Book]:
        return self.history.books

    def add_book(self, book: Book) -> Book:
        return self.history.add_book(book)

    def get_book(self, book_id: str) -> Book | None:
        return self.history.get_book(book_id)

    def add_record(self, record: Event) -> Event:
        return self.history.add_record(record)

    def get_record(self, record_id: str) -> Event | None:
        return self.history.get_event(record_id)

    def get_records_for_entity(self, entity_id: int) -> list[Event]:
        return self.history.get_records_by_entity(entity_id)

    def get_records_by_type(self, record_type: str | type[Event]) -> list[Event]:
        return self.history.get_records_by_type(record_type)

    def get_records_by_settlement(self, settlement_id: str) -> list[Event]:
        return self.history.get_records_by_settlement(settlement_id)

    def get_records_by_region(self, region_id: str) -> list[Event]:
        return self.history.get_records_by_region(region_id)

    def get_typed_records(self) -> list[TypedHistoryRecord]:
        return [
            record
            for record in self.history.events
            if isinstance(record, TYPED_HISTORY_RECORD_TYPES)
        ]

    def record_birth(self, **kwargs) -> BirthRecord:
        return self.history.record_birth(**kwargs)

    def record_death(self, **kwargs) -> DeathRecord:
        return self.history.record_death(**kwargs)

    def record_marriage(self, **kwargs) -> MarriageRecord:
        return self.history.record_marriage(**kwargs)

    def record_crime(self, **kwargs) -> CrimeRecord:
        return self.history.record_crime(**kwargs)

    def record_migration(self, **kwargs) -> MigrationRecord:
        return self.history.record_migration(**kwargs)

    def record_employment_change(self, **kwargs) -> EmploymentRecord:
        return self.history.record_employment_change(**kwargs)

    def register_book_item(self, book: Book, inventory: dict[str, int]) -> Book:
        self.add_book(book)
        inventory[f"book_{book.id}"] = inventory.get(f"book_{book.id}", 0) + 1
        return book

    def compile_chronicle(self, **kwargs) -> Book:
        return self.compiler.compile_chronicle(**kwargs)

    def compile_biography(self, **kwargs) -> Book:
        return self.compiler.compile_biography(**kwargs)

    def record_census_snapshot(self, snapshot: CensusSnapshot) -> CensusSnapshot:
        return self.census.record_snapshot(snapshot)

    def compile_census_report(self, **kwargs) -> Book:
        return self.compiler.compile_census_report(**kwargs)

    def transfer_book_knowledge(
        self,
        book: Book,
        knowledge_target: dict[str, Event] | Any,
        *,
        source_type: str = "read",
        confidence: float = 1.0,
        tick: int = 0,
    ) -> int:
        learned_count = 0
        known_events = (
            knowledge_target
            if isinstance(knowledge_target, dict)
            else getattr(knowledge_target, "known_events", None)
        )
        learn_history_record = (
            None
            if isinstance(knowledge_target, dict)
            else getattr(knowledge_target, "learn_history_record", None)
        )

        for event_id in getattr(book, "referenced_event_ids", []) or []:
            event = self.history.get_event(event_id)
            if event is None:
                continue

            learned_fact = False
            if callable(learn_history_record):
                learned_fact = learn_history_record(
                    event,
                    source_type,
                    confidence,
                    tick,
                )

            learned_event = False
            if isinstance(known_events, dict) and event_id not in known_events:
                known_events[event_id] = event
                learned_event = True

            if learned_fact or learned_event:
                learned_count += 1
        return learned_count
