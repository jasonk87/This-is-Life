"""Structured entries for the player's message log.

The renderer used to decide a log line's color by substring-matching the
message text on every frame - so any message containing the word "attack"
turned red, including "You stop attacking the training dummy", and the same
scan re-ran for every visible line at every redraw.

Categorising happens once here, when the message is recorded, and the entry
carries the answer with it. `classify_message` is still keyword-based, but
it is only the *fallback* for callers that don't name a category, and it
runs once per message rather than once per frame.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Order matters: the first matching group wins, so a message mentioning both
# a quest and a reward is filed under "quest".
_CATEGORY_KEYWORDS = (
    ("quest", ("quest", "objective", "bounty", "contract")),
    ("combat", ("attack", "damage", "hostile", "threat", "wound", "kill", "slain", "broke")),
    ("warning", ("freezing", "burning", "starving", "warning", "cannot", "can't", "no longer", "too far")),
    ("gain", ("gain", "equip", "craft", "harvest", "picked up", "learn", "rises", "reward", "built")),
    ("social", ("hello", "says", "trade", "talk", "greet", "gossip", "gift", "married")),
)

DEFAULT_CATEGORY = "default"

# Developer diagnostics. They stay in the history - and in world.chat_log, which
# tests read - but the log panel hides them, because a handful of them per tick
# is enough to push everything the player actually did off a four-line panel.
DEBUG_CATEGORY = "debug"
MAX_LOG_ENTRIES = 100


def visible_entries(entries, *, include_debug=False):
    """The entries a player should see, newest last."""
    if include_debug:
        return list(entries)
    return [entry for entry in entries if entry.category != DEBUG_CATEGORY]


def classify_message(text) -> str:
    """Best-effort category for a message with no explicit one."""
    lowered = str(text).lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return category
    return DEFAULT_CATEGORY


@dataclass
class LogEntry:
    """One line in the message log.

    `count` collapses immediate repeats - walking over five items produces
    one "You pick up 1x Wheat (x5)" row instead of flooding the four-line
    panel with identical text and pushing everything else off screen.
    """

    text: str
    category: str = DEFAULT_CATEGORY
    tick: int = 0
    count: int = 1
    # Where this came from, when the line records something the player learned
    # rather than something that simply happened to them. Empty on ordinary
    # messages and on entries restored from saves written before this existed.
    #
    # `confidence_at_entry` is frozen on purpose. The line's wording was chosen
    # from it at the moment of writing, and a journal that re-renders old
    # entries against present-day confidence would reach back and change what
    # the player is recorded as having believed last week. What they believe
    # *now* is a different question, answered from their knowledge rather than
    # from here.
    claim_id: str = ""
    knowledge_source: str = ""
    source_entity_id: int | None = None
    confidence_at_entry: float | None = None

    def display_text(self) -> str:
        return self.text if self.count <= 1 else f"{self.text} (x{self.count})"

    def __setstate__(self, state):
        # Pickle replays the saved __dict__ without calling __init__, so entries
        # written before these fields existed come back without them.
        self.__dict__.update(state)
        for field_name, default in (
            ("claim_id", ""), ("knowledge_source", ""),
            ("source_entity_id", None), ("confidence_at_entry", None),
        ):
            self.__dict__.setdefault(field_name, default)


def append_message(entries, text, *, category=None, tick=0, max_entries=MAX_LOG_ENTRIES):
    """Record `text` in `entries`, collapsing an immediate repeat.

    Returns the entry that was created or updated. A repeat refreshes the
    entry's tick so the fade timer restarts - a thing that keeps happening
    should keep reading as current.
    """
    text = str(text)
    resolved = str(category) if category else classify_message(text)

    if entries and entries[-1].text == text and entries[-1].category == resolved:
        entries[-1].count += 1
        entries[-1].tick = int(tick)
        return entries[-1]

    entry = LogEntry(text=text, category=resolved, tick=int(tick))
    entries.append(entry)
    while len(entries) > max_entries:
        entries.pop(0)
    return entry


def append_knowledge_message(
    entries,
    text,
    *,
    claim_id="",
    knowledge_source="",
    source_entity_id=None,
    confidence_at_entry=None,
    category="social",
    tick=0,
    max_entries=MAX_LOG_ENTRIES,
):
    """Record something the player *learned*, with how they learned it.

    The text is composed by the caller (presentation.player_journal) and stored
    as written. Two tellings of the same event are separate entries even when
    the wording matches, because "Mara told you" on Monday and "Owen told you"
    on Friday are two different things happening - so this deliberately does not
    collapse repeats the way append_message does.
    """
    entry = LogEntry(
        text=str(text),
        category=str(category) if category else DEFAULT_CATEGORY,
        tick=int(tick),
        claim_id=str(claim_id or ""),
        knowledge_source=str(knowledge_source or ""),
        source_entity_id=source_entity_id,
        confidence_at_entry=None if confidence_at_entry is None else float(confidence_at_entry),
    )
    entries.append(entry)
    while len(entries) > max_entries:
        entries.pop(0)
    return entry


def entries_from_plain_log(messages, *, tick=0):
    """Rebuild entries from a bare list of strings.

    Saves written before the log carried categories only have the plain
    `chat_log` list, so this reconstructs a usable display model on load
    rather than showing the player an empty log.
    """
    entries = []
    for message in messages:
        append_message(entries, message, tick=tick)
    return entries


# Age in ticks over which a message fades from full brightness to its floor.
FADE_WINDOW_TICKS = 600
FADE_FLOOR = 0.45


def fade_ratio(entry, current_tick, *, window=FADE_WINDOW_TICKS, floor=FADE_FLOOR):
    """Brightness multiplier for an entry given how long ago it happened.

    Never returns 0 - an old message should read as settled, not invisible.
    """
    age = max(0, int(current_tick) - int(getattr(entry, "tick", 0)))
    if age >= window:
        return floor
    return floor + (1.0 - floor) * (1.0 - (age / max(1, window)))
