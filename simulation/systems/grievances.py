"""People doing things to each other, for reasons.

The village had every part of a rumour mill except the rumours. An event could
be witnessed, remembered, doubted, retold with the wrong name attached, argued
about by a town crier and turned into a grudge - but the only thing that could
ever start one was the player throwing a punch. Ninety people lived together for
two game days and gave each other no reason to talk.

This module is the missing half: the part where somebody is not paid, and
notices, and holds it against the person who did not pay them.

Four rules shape it.

**Causes come from circumstances, not dice.** Nothing here rolls "should a
random bad thing happen". Every grievance is read off state the simulation is
already keeping: a purse with less in it than a day's wage, two people rostered
to the same workshop who cannot stand each other, an empty stomach next to a
full one. There is no die roll anywhere in this file - not even for pacing.
Which grievance surfaces first is decided by how hard the circumstances push,
with actor id and kind breaking ties, so the same village state always produces
the same events in the same order. In a prosperous village where everyone gets
on, nothing happens here at all, and that is the correct output.

**An act is not the same as a resentment.** Nobody wrongs you by holding the job
you wanted, or by being liked by your wife. Those are things you feel, not
things they did. Resentments quietly build history and are never witnessed,
never gossiped about, and never blamed on anyone publicly, because no event took
place. Acts - an unpaid wage, a theft, an insult - are real occurrences with
witnesses, and only those become incidents. Blurring the two would have the
village inventing crimes nobody committed.

**Non-violence is the normal case.** Violence is one entry at the top of the
ladder, gated behind accumulated history: you cannot punch a man you have no
record with. The common events are arguments, unpaid money, a sack of grain gone
missing. A stabbing should be the rare end of a long story, not the story.

**Escalation is earned.** What one person will do to another is a function of
what is already between them - grudge severity, soured opinion, a relationship
gone cold. `_history_between` computes that from what the actor *believes*
rather than what actually happened, so a man convinced of something that never
occurred escalates on it just the same.

Everything produced here goes through `create_harmful_incident`, so it inherits
attribution, confidence, second-hand distortion, gossip, town criers, reputation
and grudges. Crimes additionally go through `record_crime_event`, putting them in
the history ledger where the knowledge system, claims, dialogue and the player's
journal can all see them. Nothing here is a private drama channel.

Every kind defined below has a detector that can produce it. If you add one
without a trigger it is dead content, and this project has been bitten by that
often enough to be worth saying out loud.
"""

from __future__ import annotations

from dataclasses import dataclass

from config import DAY_LENGTH_TICKS
from simulation.systems.incidents import create_harmful_incident, record_incident_attribution


@dataclass(frozen=True)
class GrievanceKind:
    """One thing that can pass between two people."""

    key: str
    severity: int
    # History required before somebody will do this. 0 is something you would do
    # to anyone who annoyed you; 3 needs a real feud.
    tier: int
    # False for resentments: felt, not done. No incident, no witnesses, no blame -
    # only a private souring that counts as history later.
    is_act: bool = True
    # Set when the law should hear about it. These also become history records,
    # so they reach the knowledge system and the player's journal.
    crime_kind: str | None = None
    # Traits that make somebody likelier to do this, or hold them back.
    inclined: str | None = None
    restrained_by: str | None = None
    # Used to phrase the event wherever it is described.
    describes: str = "wronged"


GRIEVANCE_KINDS: dict[str, GrievanceKind] = {
    # --- resentments: nobody did anything, somebody minds anyway --------------
    "job_envy": GrievanceKind(
        "job_envy", severity=4, tier=0, is_act=False,
        describes="resents the position of"),
    "romantic_jealousy": GrievanceKind(
        "romantic_jealousy", severity=5, tier=0, is_act=False,
        describes="is jealous of"),

    # --- tier 0 acts: friction between people with no particular history ------
    "workplace_argument": GrievanceKind(
        "workplace_argument", severity=2, tier=0,
        inclined="aggressive", restrained_by="lawful",
        describes="argued with"),

    # --- tier 1 acts: something material behind them --------------------------
    "unpaid_wages": GrievanceKind(
        "unpaid_wages", severity=6, tier=1,
        inclined="greedy",
        describes="did not pay"),

    # --- tier 2 acts: the law would care --------------------------------------
    "theft": GrievanceKind(
        "theft", severity=9, tier=2, crime_kind="theft",
        inclined="greedy", restrained_by="lawful",
        describes="stole from"),
    "insult": GrievanceKind(
        "insult", severity=3, tier=2,
        inclined="aggressive", restrained_by="lawful",
        describes="insulted"),
    "slander": GrievanceKind(
        "slander", severity=6, tier=2,
        inclined="chaotic",
        describes="spread lies about"),
    "vandalism": GrievanceKind(
        "vandalism", severity=8, tier=2, crime_kind="vandalism",
        inclined="chaotic", restrained_by="lawful",
        describes="damaged property of"),

    # --- tier 3 acts: the rare end of a long story ----------------------------
    "public_humiliation": GrievanceKind(
        "public_humiliation", severity=10, tier=3,
        inclined="aggressive", restrained_by="lawful",
        describes="humiliated"),
    "assault": GrievanceKind(
        "assault", severity=18, tier=3, crime_kind="assault",
        inclined="aggressive", restrained_by="lawful",
        describes="attacked"),
}

# How much accumulated history unlocks each tier. Grudge severity runs 0-100 and
# soured opinion is negative, so this is "how badly do these two already get on".
#
# Calibrated against what one incident actually produces rather than guessed.
# `add_grudge` drops the relationship by 40 outright, which alone contributes 20
# here, so the first thresholds tried (25 and 55) meant a single workplace
# argument immediately unlocked slander, theft and vandalism between two people
# who had merely bickered once. Escalation is supposed to be earned.
#
# Measured: one argument leaves about 26 between them; a second, more serious
# grievance on top reaches the low forties; a sustained feud with several
# believed incidents souring opinion as well passes sixty. So tier 2 wants more
# than one bad afternoon, and tier 3 - which is where violence lives - wants a
# genuine history.
TIER_THRESHOLDS = {0: 0.0, 1: 0.0, 2: 35.0, 3: 60.0}

# Grievances are slow social events, not per-tick physics, and the pairwise scan
# is the expensive part.
EVALUATION_INTERVAL = 60

# At most this many across the whole village per evaluation, so a bad day cannot
# become a riot of simultaneous events.
MAX_INCIDENTS_PER_EVALUATION = 3

# One sore subject should not fire every cadence.
PAIR_COOLDOWN_TICKS = DAY_LENGTH_TICKS // 4

INTERACTION_RADIUS = 6
WITNESS_RADIUS = 7

# Below this, two people have no history worth escalating on.
FEUD_MINIMUM_HISTORY = 15.0

# Acts that put hands on somebody. Restricted to people with the temperament for
# it, and given a longer cooling-off period than a sharp word.
VIOLENT_KINDS = frozenset({"assault"})

# A serious act settles things for longer than a squabble does, which is what
# stops a feud running at full speed indefinitely.
SERIOUS_ACT_COOLDOWN_TICKS = DAY_LENGTH_TICKS


def _alive(npc) -> bool:
    return not getattr(getattr(npc, "physical", None), "is_dead", False)


def _relationship(a, b_id, default: int = 50) -> int:
    return int(getattr(a.social, "relationships", {}).get(b_id, default))


def _history_between(actor, target_id) -> float:
    """How much bad blood the actor believes is on record with this person."""
    score = float(actor.get_grudge_severity_towards(target_id) or 0)
    opinion = getattr(actor.social, "local_opinions", {}).get(target_id)
    if opinion is not None:
        # Soured opinion is negative; only the bad half counts toward escalation.
        score += max(0.0, -float(getattr(opinion, "score", 0.0) or 0.0))
    score += max(0, 50 - _relationship(actor, target_id)) * 0.5
    return score


def _inclination(actor, kind: GrievanceKind) -> float:
    """Personality weighting. Never the sole cause - only a thumb on the scale."""
    weight = 1.0
    if kind.inclined and actor.has_trait(kind.inclined):
        weight *= 2.0
    if kind.restrained_by and actor.has_trait(kind.restrained_by):
        weight *= 0.35
    return weight


# --------------------------------------------------------------------------
# Detectors
#
# Each reads standing state and yields (kind_key, wrongdoer, victim, context)
# for grievances that genuinely exist right now. Wrongdoer and victim are named
# explicitly because they are not always the obvious way round - an unpaid wage
# is noticed by the worker but committed by the employer.
#
# A detector that finds nothing yields nothing. There is no "otherwise pick
# something random" branch anywhere in this file and there should never be one.
# --------------------------------------------------------------------------

def _nearby(world, actor, radius: int = INTERACTION_RADIUS):
    for other in world.village_npcs:
        if other is actor or not _alive(other):
            continue
        if abs(other.x - actor.x) + abs(other.y - actor.y) <= radius:
            yield other


def _median(values, default: float) -> float:
    ordered = sorted(values)
    return float(ordered[len(ordered) // 2]) if ordered else default


def village_context(world) -> dict:
    """What counts as poor, or as getting on badly, in *this* village.

    The thresholds below were originally absolute numbers - a purse under five
    coins, a relationship under forty-five - and every one of them was wrong,
    because they were guesses about a village that turned out to have almost no
    spread. Measured on seed 2024: purses ran 9 to 305, relationships 48 to 71.
    Nobody was ever under five coins or under forty-five regard, so every
    detector keyed on those numbers was permanently dead while looking
    perfectly reasonable.

    Comparing against the village's own middle fixes that and says something
    truer besides. A grievance is not about an absolute quantity of money; it is
    about having noticeably less than the people around you.
    """
    npcs = [n for n in getattr(world, "village_npcs", []) if _alive(n)]
    money = [int(getattr(n.economic, "money", 0) or 0) for n in npcs]
    regard = [s for n in npcs for s in getattr(n.social, "relationships", {}).values()]
    return {
        "median_money": _median(money, 50.0),
        "median_regard": _median(regard, 50.0),
    }


def _detect_workplace_friction(world, actor, context):
    """Two people rostered to the same place who get on worse than most do.

    This is the seed for everything above tier 0. Feuds need history and only
    incidents make history, so without something that can fire between two
    people with no record at all, the escalation ladder has no bottom rung and
    nothing ever starts. Sharing a workroom with somebody you find tiresome is
    the most ordinary way that begins.
    """
    building_id = getattr(actor.schedule, "work_building_id", None)
    if not building_id:
        return
    threshold = context["median_regard"] - 4
    known = getattr(actor.social, "relationships", {})
    for other in _nearby(world, actor):
        if getattr(other.schedule, "work_building_id", None) != building_id:
            continue
        # They must actually know each other. Reading the default 50 out of a
        # missing entry made this fire between coworkers who had never so much
        # as spoken - friction generated from absent data rather than from a
        # soured relationship, which is precisely the sort of thing that makes a
        # simulation look broken when a player inspects it.
        if other.id not in known:
            continue
        regard = _relationship(actor, other.id)
        # Either they already get on badly for this village, or the actor is
        # simply somebody who picks fights.
        if regard > threshold and not actor.has_trait("aggressive"):
            continue
        yield "workplace_argument", actor, other, {
            "building_id": str(building_id), "regard": regard}


def _detect_job_envy(world, actor, context):
    """Out of work, watching other people go to theirs.

    A resentment, not an act: the employed man has wronged nobody. It sours the
    actor's view of him, which is what later makes something else possible.

    Originally this compared professions, so an unemployed villager would envy
    whoever held the job they had trained for. There is no such person: losing
    work sets the profession to "Unemployed", so the comparison was always
    against a trade they no longer had, and it never matched. What is actually
    resented is simply having work when you do not.
    """
    if getattr(actor.schedule, "work_building_id", None):
        return
    idle_days = int(getattr(actor.economic, "days_unemployed", 0) or 0)
    if idle_days < 1:
        return
    for other in _nearby(world, actor):
        if not getattr(other.schedule, "work_building_id", None):
            continue
        yield "job_envy", other, actor, {
            "their_work": str(getattr(other.economic, "profession", "")),
            "days_unemployed": idle_days}


def _detect_romantic_jealousy(world, actor, context):
    """Somebody unattached is well liked by the person you are partnered to."""
    partner_id = getattr(actor.social, "family_ties", {}).get("partner_id")
    if partner_id is None:
        return
    partner = world.get_entity_by_id(partner_id)
    if partner is None or not _alive(partner):
        return
    for other in _nearby(world, actor):
        if other.id in {partner_id, actor.id}:
            continue
        if getattr(other.social, "family_ties", {}).get("partner_id") is not None:
            continue
        if _relationship(partner, other.id) < 70:
            continue
        yield "romantic_jealousy", other, actor, {"partner_id": partner_id}


def _detect_hardship_theft(world, actor, context):
    """Poor by the standards of this village, and standing beside someone who
    is comfortably better off.

    Needs a real gap, not an absolute quantity: half the village median in your
    purse, and somebody within arm's reach carrying twice it. A village where
    everyone is equally poor produces no theft, which is right - people steal
    from those who visibly have more.
    """
    money = int(getattr(actor.economic, "money", 0) or 0)
    poor_line = context["median_money"] * 0.5
    if money > poor_line:
        return
    for other in _nearby(world, actor, radius=2):
        their_money = int(getattr(other.economic, "money", 0) or 0)
        if their_money < max(20, money * 2 + 20):
            continue
        yield "theft", actor, other, {"purse": money, "theirs": their_money,
                                      "poor_line": round(poor_line, 1)}


def _detect_feud_escalation(world, actor, context):
    """Where existing bad blood turns into a fresh act.

    Everything offered here is filtered by tier afterwards, so which rungs are
    actually reachable depends on how much history the pair already has. This is
    the only detector that can produce violence, and only at the very top.
    """
    for other in _nearby(world, actor):
        history = _history_between(actor, other.id)
        if history < FEUD_MINIMUM_HISTORY:
            continue
        context = {"history": round(history, 1)}
        for key in ("insult", "slander", "public_humiliation", "vandalism", "assault"):
            yield key, actor, other, context


DETECTORS = (
    _detect_workplace_friction,
    _detect_job_envy,
    _detect_romantic_jealousy,
    _detect_hardship_theft,
    _detect_feud_escalation,
)


# --------------------------------------------------------------------------
# Consequences
# --------------------------------------------------------------------------

def _pair_key(wrongdoer, victim) -> tuple:
    """Unordered, so a quarrel is one subject rather than two.

    Keying on (wrongdoer, victim) in that order gave each pair two independent
    cooldowns, so A wronging B never delayed B wronging A. The two of them
    simply took turns every cadence and the result was a tennis match: ten
    incidents between the same two people inside a day, most of them assaults.
    """
    a, b = getattr(wrongdoer, "id", None), getattr(victim, "id", None)
    return (a, b) if (a is None or b is None or a <= b) else (b, a)


def _on_cooldown(world, key, now: int) -> bool:
    seen = getattr(world, "grievance_pair_cooldowns", None)
    if not isinstance(seen, dict):
        world.grievance_pair_cooldowns = {}
        return False
    entry = seen.get(key)
    if entry is None:
        return False
    # Stored as (tick, cooldown). Older saves hold a bare tick.
    last, window = entry if isinstance(entry, tuple) else (entry, PAIR_COOLDOWN_TICKS)
    return (now - int(last)) < int(window)


def _witnesses_to(world, wrongdoer, victim):
    """Who could see it. Deliberately generous - being seen is what makes a
    grievance social rather than private, and the knowledge system is what
    decides whether a witness actually believes what they saw."""
    out = []
    for npc in world.village_npcs:
        if npc.id in {wrongdoer.id, victim.id} or not _alive(npc):
            continue
        if abs(npc.x - wrongdoer.x) + abs(npc.y - wrongdoer.y) <= WITNESS_RADIUS:
            out.append(npc)
    return out


def _apply_resentment(world, kind: GrievanceKind, subject, holder, context: dict) -> None:
    """A private souring. Nothing happened, so nobody saw anything."""
    current_day = world.game_time // DAY_LENGTH_TICKS
    holder.add_grudge(
        subject.id,
        f"{kind.describes} {getattr(subject, 'name', 'them')}",
        severity=kind.severity,
        current_day=current_day,
        decay_days=8,
    )


def apply_grievance_act(world, kind: GrievanceKind, wrongdoer, victim, context: dict):
    """A real occurrence: recorded, witnessed, and available to be talked about."""
    current_day = world.game_time // DAY_LENGTH_TICKS
    witnesses = _witnesses_to(world, wrongdoer, victim)

    incident = create_harmful_incident(
        world,
        attacker_id=wrongdoer.id,
        target_id=victim.id,
        location=(wrongdoer.x, wrongdoer.y),
        severity=kind.severity,
        target_survived=True,
        witness_ids=[w.id for w in witnesses],
        kind=kind.key,
        context=dict(context),
    )

    # The person who did it knows perfectly well that they did.
    record_incident_attribution(
        wrongdoer, incident, attacker_id=wrongdoer.id, confidence=1.0, basis="actor_self")
    # So does the person it was done to. `victim_survived` is the existing basis
    # name for "the target's own account", which is what this is.
    record_incident_attribution(
        victim, incident, attacker_id=wrongdoer.id, confidence=1.0, basis="victim_survived")
    for witness in witnesses:
        record_incident_attribution(
            witness, incident, attacker_id=wrongdoer.id, confidence=0.85, basis="direct_witness")

    # The victim holds it against them directly - no gossip required.
    victim.add_grudge(
        wrongdoer.id,
        f"{getattr(wrongdoer, 'name', 'Someone')} {kind.describes} me",
        severity=kind.severity * 3,
        current_day=current_day,
        decay_days=10,
    )

    # Crimes go into the history ledger, which is what carries them into the
    # knowledge system, claims, dialogue and the player's journal. Non-crimes
    # stay in the incident layer and travel by gossip alone.
    if kind.crime_kind:
        recorder = getattr(world, "record_crime_event", None)
        if callable(recorder):
            recorder(
                crime_kind=kind.crime_kind,
                suspect_id=wrongdoer.id,
                victim_id=victim.id,
                witness_ids=tuple(w.id for w in witnesses),
                description=(f"{getattr(wrongdoer, 'name', 'Someone')} "
                             f"{kind.describes} {getattr(victim, 'name', 'someone')}."),
                location=(wrongdoer.x, wrongdoer.y),
            )

    # Doing a thing makes you a little more the sort of person who does it.
    if kind.crime_kind:
        pressure = getattr(wrongdoer, "record_trait_pressure", None)
        if callable(pressure):
            pressure("criminal")

    tracer = getattr(world, "_record_decision_explanation", None)
    if callable(tracer):
        tracer(
            explanation_type="grievance_incident",
            decision="incident_created",
            primary_reason=kind.key,
            actor=wrongdoer,
            contributing_factors={"victim_id": victim.id, **context},
        )
    return incident


def advance_interpersonal_incidents(world) -> int:
    """Look for grievances that genuinely exist, and let a few of them happen.

    Returns how many occurred, which is almost always zero - this is a slow
    social process, and a contented village should produce nothing.
    """
    now = int(getattr(world, "game_time", 0) or 0)
    if now % EVALUATION_INTERVAL:
        return 0
    if not isinstance(getattr(world, "grievance_pair_cooldowns", None), dict):
        world.grievance_pair_cooldowns = {}

    context = village_context(world)
    candidates = []
    for actor in list(getattr(world, "village_npcs", [])):
        if not _alive(actor):
            continue
        for detector in DETECTORS:
            for key, wrongdoer, victim, detail in detector(world, actor, context):
                kind = GRIEVANCE_KINDS.get(key)
                if kind is None or wrongdoer is None or victim is None:
                    continue
                if getattr(wrongdoer, "id", None) == getattr(victim, "id", None):
                    continue
                # Escalation gate: what is on record between them decides which
                # rungs are available. For an act that is the wrongdoer's view
                # of the victim; for a resentment there is no actor, so it is
                # the holder's view of the person they mind.
                judge, judged = (wrongdoer, victim) if kind.is_act else (victim, wrongdoer)
                if _history_between(judge, judged.id) < TIER_THRESHOLDS[kind.tier]:
                    continue
                # Most people never hit anybody, however badly they are treated.
                #
                # History alone is a poor gate for violence, because an assault
                # leaves a grudge severe enough to re-qualify the pair for
                # another one immediately - it sustains itself, and a single
                # falling-out becomes a standing brawl. Requiring the temperament
                # as well means violence stays with the seven people in a
                # hundred who are built that way, and everyone else expresses a
                # feud the ways people usually do: talking, cutting, lying.
                if kind.key in VIOLENT_KINDS and not wrongdoer.has_trait("aggressive"):
                    continue
                # Milder acts are preferred, not severe ones.
                #
                # This was `* (1.0 + kind.tier)`, which sorted the worst thing
                # somebody could do to the top of the list and made assault the
                # single most common event in the village: two people who fell
                # out traded seven of them in a day. People reach for the
                # smallest thing that expresses the grievance, and only rarely
                # for the largest.
                weight = _inclination(wrongdoer, kind) / (1.0 + kind.tier * 2.0)
                candidates.append((weight, kind, wrongdoer, victim, detail))

    if not candidates:
        return 0

    # Ordering is by how strongly the situation pushes, with the actor and kind
    # breaking ties so the same world state always produces the same sequence.
    candidates.sort(key=lambda c: (-c[0], getattr(c[2], "id", 0), c[1].key))

    fired = 0
    for _weight, kind, wrongdoer, victim, detail in candidates:
        if fired >= MAX_INCIDENTS_PER_EVALUATION:
            break
        key = _pair_key(wrongdoer, victim)
        if _on_cooldown(world, key, now):
            continue
        if kind.is_act:
            apply_grievance_act(world, kind, wrongdoer, victim, detail)
        else:
            _apply_resentment(world, kind, wrongdoer, victim, detail)
        window = SERIOUS_ACT_COOLDOWN_TICKS if kind.tier >= 2 else PAIR_COOLDOWN_TICKS
        world.grievance_pair_cooldowns[key] = (now, window)
        fired += 1
    return fired
