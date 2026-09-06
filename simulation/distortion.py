"""How a story changes in the retelling.

One thing only, for now: who did it. A listener half-hearing a rumour in a noisy
tavern substitutes a name they already have in mind, and from then on believes
that instead. Everything else about the claim - what happened, to whom, where -
comes through intact.

Identity alone on purpose. It is the distortion a player can immediately
understand ("they think it was the miller, it was the baker"), and if the first
version mutated the actor, the event type, the victim, the place and the number
all at once, the results would be nonsense with no way to tell which knob made
them nonsense.

Two rules this must not break:

**Deterministic.** The tick loop is reproducible from a seed, and three separate
bugs have been fixed in this project from real time and uuid4 leaking into it.
Distortion never rolls dice: it hashes the claim, the two people and the day, so
the same telling in the same run always garbles the same way, and a replay of the
seed produces the same village gossip.

**Weak evidence only.** Somebody who watched it happen does not get talked out of
it by hearsay. Distortion applies to what is being *told*, and a listener's
stronger belief is not displaced by it - see the confidence ordering in
KnowledgeComponent.learn_history_record.

The substitution is deliberately *plausible* rather than random. A name is only
borrowed if the listener has some reason to reach for it - somebody they bear a
grudge against, or think poorly of. A villager from the other side of the map
being blamed at random reads as a bug; the neighbour you already dislike being
blamed reads as a rumour.
"""

from __future__ import annotations

import hashlib
from typing import Any

from entities.social import Claim

# How often a told story loses its subject, in hundredths. Low on purpose: this
# should be a thing that happens sometimes and is startling, not the normal way
# information moves.
MISHEARING_CHANCE = 12

# Above this, the teller is sure enough - and telling it plainly enough - that it
# does not get garbled. Hearsay arrives at 0.8, so this only spares first-hand
# and official tellings.
DISTORTION_CONFIDENCE_CEILING = 0.85


def _stable_int(value: Any) -> int:
    """Same trick as dialogue_surface: a hash, not a die roll."""
    return int(hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:8], 16)


def _bias_against(listener, candidate_id: int) -> int:
    """How ready this listener is to believe the worst of somebody."""
    grudge = 0
    getter = getattr(listener, "get_grudge_severity_towards", None)
    if callable(getter):
        try:
            grudge = int(getter(candidate_id) or 0)
        except Exception:
            grudge = 0
    opinion = 0.0
    opinion_getter = getattr(listener, "get_local_opinion_towards", None)
    if callable(opinion_getter):
        try:
            opinion = float(opinion_getter(candidate_id) or 0.0)
        except Exception:
            opinion = 0.0
    # A low opinion counts towards suspicion; a good one counts against it.
    return grudge + int(max(0.0, -opinion))


def _plausible_scapegoats(listener, claim, villagers) -> list:
    """Who this listener might wrongly reach for, most suspected first.

    Only people they already hold something against. Without that filter a
    stranger from the far side of the map gets blamed and it reads as a bug
    rather than as a rumour.
    """
    off_limits = set(claim.believed_subject_ids)
    off_limits.add(getattr(listener, "id", None))
    if claim.believed_target_id is not None:
        off_limits.add(claim.believed_target_id)

    scored = []
    for villager in villagers:
        villager_id = getattr(villager, "id", None)
        if villager_id is None or villager_id in off_limits:
            continue
        if getattr(getattr(villager, "physical", None), "is_dead", False):
            continue
        bias = _bias_against(listener, villager_id)
        if bias > 0:
            scored.append((bias, villager_id))
    # Sorted by id as well, so equal suspicion resolves the same way every run.
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [villager_id for _, villager_id in scored]


def distort_on_telling(claim, *, speaker, listener, villagers, confidence, day) -> Claim:
    """The claim as the listener takes it away. Usually unchanged.

    Returns `claim` itself when nothing is misheard, so callers can compare
    identity to find out whether anything happened.
    """
    if claim is None or not claim.believed_subject_ids:
        return claim
    if float(confidence) > DISTORTION_CONFIDENCE_CEILING:
        return claim

    speaker_id = getattr(speaker, "id", None)
    listener_id = getattr(listener, "id", None)
    roll = _stable_int(f"mishear|{claim.id}|{speaker_id}|{listener_id}|{int(day)}")
    if roll % 100 >= MISHEARING_CHANCE:
        return claim

    candidates = _plausible_scapegoats(listener, claim, villagers)
    if not candidates:
        return claim
    blamed = candidates[_stable_int(f"who|{claim.id}|{listener_id}|{int(day)}") % len(candidates)]

    # Only the actor moves. The first believed subject is the one a record names
    # as responsible (_record_subject_entity_ids puts subject_id first).
    replaced = (blamed,) + tuple(claim.believed_subject_ids[1:])
    return Claim(
        source_record_id=claim.source_record_id,
        believed_record_type=claim.believed_record_type,
        believed_subject_ids=replaced,
        believed_target_id=claim.believed_target_id,
        believed_location_id=claim.believed_location_id,
        believed_quantity=claim.believed_quantity,
    )
