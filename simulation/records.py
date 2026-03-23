from __future__ import annotations

from dataclasses import dataclass

from simulation.history import Book, Event, HistoryLedger


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


class BookCompiler:
    """Compiles structured history and social data into written records."""

    def compile_chronicle(
        self,
        *,
        title: str,
        author_id: int,
        author_name: str,
        year_written: int,
        events: list[Event],
    ) -> Book:
        deaths = [event.description for event in events if event.type == "entity_death"]
        births = [event.description for event in events if event.type == "npc_birth"]
        crimes = [event.description for event in events if "crime" in event.type]

        book_content = f"The Chronicle of Year {year_written}\nRequired Reading for Citizens.\n\n"
        if births:
            book_content += "Births:\n" + "\n".join(f"- {description}" for description in births) + "\n\n"
        if deaths:
            book_content += "Deaths:\n" + "\n".join(f"- {description}" for description in deaths) + "\n\n"
        if crimes:
            book_content += "Criminal Activity:\n" + "\n".join(f"- {description}" for description in crimes) + "\n\n"
        if not any((births, deaths, crimes)):
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
            book_content = f"The Life of {subject_name}\n"
            book_content += f"Title: {subject_title or 'Unknown'}\n\n"
            book_content += "Known Deeds:\n"
            for event in subject_events:
                book_content += f"- {event.description}\n"
            referenced_event_ids = [event.id for event in subject_events]
        else:
            reputation_summary = []
            if fame > 0:
                reputation_summary.append(f"They are remembered for notable deeds (fame {fame}).")
            if infamy > 0:
                reputation_summary.append(f"They are also shadowed by infamy ({infamy}).")
            if not reputation_summary:
                reputation_summary.append(f"Little is recorded about {subject_name}, but their story is still worth preserving.")

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
        report_content += f"- Richest Citizen: {snapshot.richest_name} ({snapshot.richest_wealth} coins)\n"
        report_content += f"- Poorest Citizen: {snapshot.poorest_name} ({snapshot.poorest_wealth} coins)\n\n"
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

    def transfer_book_knowledge(self, book: Book, known_events: dict[str, Event]) -> int:
        learned_count = 0
        for event_id in getattr(book, "referenced_event_ids", []) or []:
            if event_id in known_events:
                continue
            event = self.history.get_event(event_id)
            if event is not None:
                known_events[event_id] = event
                learned_count += 1
        return learned_count
