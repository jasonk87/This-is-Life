"""What the player knows, written the way they came to know it.

The log used to state the world's facts:

    The baker killed Clara.

That is the database talking. The player is an entity with the same
KnowledgeComponent as everybody else, so their log should be their knowledge of
the world rather than the world itself:

    You saw the baker strike Clara.
    Mara told you the baker killed Clara.
    You heard the miller may have killed Clara.

Three different epistemic states, and the third can be wrong.

**A journal line is written once and never rewritten.** The phrasing is composed
here, at the moment the player learns something, from the confidence they had
*then*. If it were re-rendered later against current confidence, then learning
the truth on Friday would reach back and silently change what Monday's entry
says you believed - and a journal that edits its own past is worse than no
journal. The provenance is stored on the entry too, so a separate
"what do I believe now" view can render the live picture without touching this.
"""

from __future__ import annotations

from typing import Any

# record type -> (reported, witnessed). Two forms because "You saw the baker
# attacked Clara" is not a sentence: seeing something takes the bare verb,
# being told about it takes the past tense.
_ACTION_PHRASES = {
    "crime_recorded": ("attacked", "attack"),
    "entity_death": ("killed", "kill"),
    "npc_death": ("killed", "kill"),
    "murder": ("killed", "kill"),
    "assault": ("attacked", "attack"),
    "theft": ("stole from", "steal from"),
    "npc_birth": ("had a child with", "have a child with"),
    "npc_marriage": ("married", "marry"),
    "npc_hired": ("took on", "take on"),
}
_DEFAULT_ACTION = ("was involved with", "get involved with")

# How sure the player is, in their own words. Mirrors the confidence bands
# dialogue_surface uses for NPC speech, in second person.
CERTAIN = 0.75
PROBABLE = 0.45


def _name(names: dict, entity_id: Any) -> str:
    if entity_id is None:
        return ""
    return str(names.get(entity_id) or f"someone")


def describe_claim(claim, names: dict, *, witnessed: bool = False) -> str:
    """The assertion in plain words: "the baker attacked Clara"."""
    if claim is None:
        return "something happened"
    subject = _name(names, claim.believed_subject_ids[0]) if claim.believed_subject_ids else "someone"
    reported, bare = _ACTION_PHRASES.get(str(claim.believed_record_type), _DEFAULT_ACTION)
    action = bare if witnessed else reported
    target = _name(names, claim.believed_target_id)
    return f"{subject} {action} {target}".strip() if target else f"{subject} {action}".strip()


def journal_line(claim, *, source_type: str, teller_name: str = "",
                 confidence: float = 1.0, names: dict | None = None) -> str:
    """One journal line, in the player's voice, fixed at the moment of writing."""
    source = str(source_type or "").lower()
    what = describe_claim(claim, names or {}, witnessed=(source == "witnessed"))

    if source == "witnessed":
        return f"You saw {what}."
    if source == "overheard":
        hedge = "" if confidence >= CERTAIN else " - or so it sounded"
        return f"You overheard that {what}{hedge}."
    if source in {"official_record", "public_record"}:
        return f"The record says {what}."
    if source == "told" and teller_name:
        if confidence >= CERTAIN:
            return f"{teller_name} told you {what}."
        if confidence >= PROBABLE:
            return f"{teller_name} says {what}."
        return f"{teller_name} reckons {what}, though they seemed unsure."
    # No named teller: it reached the player as talk rather than testimony.
    if confidence >= CERTAIN:
        return f"You heard that {what}."
    if confidence >= PROBABLE:
        return f"Word going round is that {what}."
    return f"People are saying {what}, but nobody seems certain."
