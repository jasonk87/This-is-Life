"""Structured harmful incident tracking and attribution helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import uuid

from simulation.ids import new_id

from config import DAY_LENGTH_TICKS

@dataclass
class HarmfulIncident:
    id: str
    attacker_id: int | None
    target_id: int | None
    location: tuple[int, int] | None
    timestamp: int
    day: int
    severity: int
    target_survived: bool
    witness_ids: list[int] = field(default_factory=list)


@dataclass
class HarmfulIncidentAttribution:
    incident_id: str
    attributed_attacker_id: int | None
    confidence: float
    basis: str
    secondhand: bool = False
    told_by_id: int | None = None


def create_harmful_incident(
    world,
    *,
    attacker_id: int | None,
    target_id: int | None,
    location: tuple[int, int] | None,
    severity: int,
    target_survived: bool,
    witness_ids: list[int] | None = None,
) -> HarmfulIncident:
    incident = HarmfulIncident(
        id=f"harm_{new_id()}",
        attacker_id=attacker_id,
        target_id=target_id,
        location=location,
        timestamp=world.game_time,
        day=world.game_time // DAY_LENGTH_TICKS,
        severity=max(1, int(severity)),
        target_survived=bool(target_survived),
        witness_ids=list(witness_ids or []),
    )
    world.harmful_incidents[incident.id] = incident
    return incident


def record_incident_attribution(observer, incident: HarmfulIncident, *, attacker_id: int | None, confidence: float, basis: str) -> None:
    if not hasattr(observer, "knowledge"):
        return
    normalized_confidence = max(0.0, min(1.0, float(confidence)))
    existing = observer.knowledge.known_harmful_incidents.get(incident.id)
    if existing and getattr(existing, "confidence", 0.0) >= normalized_confidence and getattr(existing, "basis", "") in {
        "direct_witness",
        "victim_survived",
        "actor_self",
    }:
        return
    observer.knowledge.known_harmful_incidents[incident.id] = HarmfulIncidentAttribution(
        incident_id=incident.id,
        attributed_attacker_id=attacker_id,
        confidence=normalized_confidence,
        basis=basis,
    )


def tell_harmful_incident_claim(speaker, listener, incident: HarmfulIncident, *, credibility_bonus: float = 0.0) -> bool:
    """Share secondhand incident knowledge from a speaker to a listener with reduced confidence."""
    if not hasattr(speaker, "knowledge") or not hasattr(listener, "knowledge"):
        return False
    speaker_view = speaker.knowledge.known_harmful_incidents.get(incident.id)
    if speaker_view is None:
        return False

    secondhand_confidence = _compute_claim_confidence(
        speaker,
        listener,
        speaker_view,
        transmission_factor=1.0,
        max_cap=0.89,
        credibility_bonus=credibility_bonus,
    )

    current = listener.knowledge.known_harmful_incidents.get(incident.id)
    if current and getattr(current, "confidence", 0.0) >= secondhand_confidence:
        return False

    listener.knowledge.known_harmful_incidents[incident.id] = HarmfulIncidentAttribution(
        incident_id=incident.id,
        attributed_attacker_id=getattr(speaker_view, "attributed_attacker_id", None),
        confidence=secondhand_confidence,
        basis="secondhand_claim",
        secondhand=True,
        told_by_id=getattr(speaker, "id", None),
    )
    return True


def overhear_harmful_incident_claim(speaker, overhearer, incident: HarmfulIncident, *, credibility_bonus: float = 0.0) -> bool:
    """Apply lower-confidence secondhand knowledge for passive overhearing."""
    if not hasattr(speaker, "knowledge") or not hasattr(overhearer, "knowledge"):
        return False
    speaker_view = speaker.knowledge.known_harmful_incidents.get(incident.id)
    if speaker_view is None:
        return False

    overheard_confidence = _compute_claim_confidence(
        speaker,
        overhearer,
        speaker_view,
        transmission_factor=0.7,
        max_cap=0.69,
        credibility_bonus=credibility_bonus,
    )
    current = overhearer.knowledge.known_harmful_incidents.get(incident.id)
    if current and getattr(current, "confidence", 0.0) >= overheard_confidence:
        return False

    overhearer.knowledge.known_harmful_incidents[incident.id] = HarmfulIncidentAttribution(
        incident_id=incident.id,
        attributed_attacker_id=getattr(speaker_view, "attributed_attacker_id", None),
        confidence=overheard_confidence,
        basis="overheard_claim",
        secondhand=True,
        told_by_id=getattr(speaker, "id", None),
    )
    return True


def propagate_harmful_incident_gossip(world, speaker, listener, *, overhear_radius: int = 3) -> bool:
    """Share one known harmful incident with a listener, then spread lower-confidence overheard claims nearby."""
    incident = _select_shareable_incident(world, speaker, listener)
    if incident is None:
        return False
    if not tell_harmful_incident_claim(speaker, listener, incident):
        return False

    current_day = world.game_time // DAY_LENGTH_TICKS
    _apply_claim_social_consequence(listener, incident, current_day=current_day)

    speaker_id = getattr(speaker, "id", None)
    listener_id = getattr(listener, "id", None)
    for npc in world.village_npcs:
        if getattr(getattr(npc, "physical", None), "is_dead", False):
            continue
        npc_id = getattr(npc, "id", None)
        if npc_id in {speaker_id, listener_id}:
            continue
        dist_to_speaker = abs(npc.x - speaker.x) + abs(npc.y - speaker.y)
        dist_to_listener = abs(npc.x - listener.x) + abs(npc.y - listener.y)
        if min(dist_to_speaker, dist_to_listener) > overhear_radius:
            continue
        if overhear_harmful_incident_claim(speaker, npc, incident):
            _apply_claim_social_consequence(npc, incident, current_day=current_day)
    return True


def _select_shareable_incident(world, speaker, listener) -> HarmfulIncident | None:
    speaker_knowledge = getattr(getattr(speaker, "knowledge", None), "known_harmful_incidents", {})
    listener_knowledge = getattr(getattr(listener, "knowledge", None), "known_harmful_incidents", {})
    best_incident = None
    best_rank = None
    for incident_id, attribution in speaker_knowledge.items():
        if incident_id in listener_knowledge:
            continue
        incident = world.harmful_incidents.get(incident_id)
        if incident is None:
            continue
        score = _score_incident_for_role(world, speaker, incident, attribution, for_broadcast=False)
        rank = (score, incident.timestamp)
        if best_rank is None or rank > best_rank:
            best_rank = rank
            best_incident = incident
    return best_incident


def _compute_claim_confidence(
    speaker,
    listener,
    speaker_view,
    *,
    transmission_factor: float,
    max_cap: float,
    credibility_bonus: float = 0.0,
) -> float:
    speaker_confidence = max(0.0, min(1.0, float(getattr(speaker_view, "confidence", 0.0))))
    relationship = listener.social.relationships.get(getattr(speaker, "id", None), 50)
    credibility_factor = 0.5 + (max(0, min(100, relationship)) / 200.0)  # 0.5 -> 1.0
    return max(0.08, min(max_cap, speaker_confidence * 0.7 * (credibility_factor + credibility_bonus) * transmission_factor))


def select_town_crier_incident(world, crier) -> HarmfulIncident | None:
    """Pick the strongest known incident for public rebroadcast."""
    known = getattr(getattr(crier, "knowledge", None), "known_harmful_incidents", {})
    best_incident = None
    best_rank = None
    for incident_id, attribution in known.items():
        incident = world.harmful_incidents.get(incident_id)
        if incident is None:
            continue
        score = _score_incident_for_role(world, crier, incident, attribution, for_broadcast=True)
        rank = (score, incident.timestamp)
        if best_rank is None or rank > best_rank:
            best_rank = rank
            best_incident = incident
    return best_incident


def run_town_crier_broadcast(world, crier, *, radius: int = 8, min_interval: int = 120) -> bool:
    """Publicly rebroadcast one known incident using tell + overhearing logic."""
    if not getattr(getattr(crier, "social", None), "is_town_crier", False):
        return False
    last_tick = getattr(crier, "last_town_cry_tick", -10_000)
    if world.game_time - last_tick < min_interval:
        return False

    incident = select_town_crier_incident(world, crier)
    if incident is None:
        return False

    nearby = [
        npc for npc in world.village_npcs
        if npc.id != crier.id and not npc.physical.is_dead and abs(npc.x - crier.x) + abs(npc.y - crier.y) <= radius
    ]
    if not nearby:
        return False
    nearby.sort(key=lambda npc: abs(npc.x - crier.x) + abs(npc.y - crier.y))
    primary_listener = nearby[0]

    shared = tell_harmful_incident_claim(crier, primary_listener, incident, credibility_bonus=0.15)
    if not shared:
        return False
    current_day = world.game_time // DAY_LENGTH_TICKS
    _apply_claim_social_consequence(primary_listener, incident, current_day=current_day)

    for npc in nearby[1:]:
        if overhear_harmful_incident_claim(crier, npc, incident, credibility_bonus=0.1):
            _apply_claim_social_consequence(npc, incident, current_day=current_day)

    crier.last_town_cry_tick = world.game_time
    return True


def _apply_claim_social_consequence(listener, incident: HarmfulIncident, *, current_day: int) -> None:
    view = listener.knowledge.known_harmful_incidents.get(incident.id)
    attacker_id = getattr(view, "attributed_attacker_id", None) if view else None
    confidence = getattr(view, "confidence", 0.0) if view else 0.0
    if attacker_id is None or attacker_id == getattr(listener, "id", None):
        return
    if confidence < 0.35:
        return
    listener.add_grudge(
        attacker_id,
        "heard_harmful_incident",
        severity=max(5, int(confidence * 30)),
        current_day=current_day,
        decay_days=6,
    )


def update_local_incident_opinion(world, observer, target_id: int | None) -> float:
    """Recompute one observer's local opinion score for a target from believed incidents."""
    if target_id is None or not hasattr(observer, "knowledge"):
        return 0.0
    total = 0.0
    evidence_count = 0
    for incident_id, attribution in observer.knowledge.known_harmful_incidents.items():
        if getattr(attribution, "attributed_attacker_id", None) != target_id:
            continue
        incident = world.harmful_incidents.get(incident_id)
        if incident is None:
            continue

        confidence = max(0.0, min(1.0, float(getattr(attribution, "confidence", 0.0))))
        basis = getattr(attribution, "basis", "")
        basis_weight = {
            "direct_witness": 1.0,
            "victim_survived": 1.0,
            "actor_self": 0.9,
            "secondhand_claim": 0.65,
            "overheard_claim": 0.45,
        }.get(basis, 0.5)
        magnitude = max(1.0, float(incident.severity)) * confidence * basis_weight

        target_entity = world.get_entity_by_id(incident.target_id)
        target_is_threat = bool(
            target_entity
            and (
                getattr(getattr(target_entity, "economic", None), "profession", "") == "Creature"
                or getattr(getattr(target_entity, "combat", None), "is_hostile_to_player", False)
            )
        )
        if target_is_threat:
            total += magnitude * 0.8
        else:
            total -= magnitude
        evidence_count += 1

    current_day = world.game_time // DAY_LENGTH_TICKS
    observer.set_local_opinion(target_id, total, current_day=current_day, evidence_count=evidence_count)
    return observer.get_local_opinion_towards(world.get_entity_by_id(target_id))


def _score_incident_for_role(world, speaker, incident: HarmfulIncident, attribution, *, for_broadcast: bool) -> float:
    """Role-aware incident salience score for selecting what gets repeated."""
    confidence = max(0.0, min(1.0, float(getattr(attribution, "confidence", 0.0))))
    base = max(1.0, float(incident.severity)) * confidence
    speaker_role = _classify_speaker_role(speaker)

    target_entity = world.get_entity_by_id(incident.target_id)
    attacker_entity = world.get_entity_by_id(incident.attacker_id)
    target_is_threat = bool(
        target_entity
        and (
            getattr(getattr(target_entity, "economic", None), "profession", "") == "Creature"
            or getattr(getattr(target_entity, "combat", None), "is_hostile_to_player", False)
        )
    )
    attacker_is_threat = bool(
        attacker_entity
        and (
            getattr(getattr(attacker_entity, "economic", None), "profession", "") == "Creature"
            or getattr(getattr(attacker_entity, "combat", None), "is_hostile_to_player", False)
        )
    )
    is_road_danger = target_is_threat or attacker_is_threat
    is_crime_harm = not target_is_threat

    if speaker_role == "merchant":
        score = base * (1.4 if is_road_danger else 0.75)
    elif speaker_role == "guard":
        score = base * (1.45 if is_crime_harm else 0.6)
    elif speaker_role == "town_crier":
        public_interest = 1.0 + min(1.5, float(incident.severity) / 20.0) + (confidence * 0.5)
        score = base * public_interest
    else:
        score = base

    if for_broadcast and speaker_role == "town_crier":
        score *= 1.2
    return score


def _classify_speaker_role(speaker) -> str:
    social = getattr(speaker, "social", None)
    if getattr(social, "is_town_crier", False):
        return "town_crier"
    profession = str(getattr(getattr(speaker, "economic", None), "profession", "")).lower()
    if profession in {"traveling merchant", "merchant", "miller"}:
        return "merchant"
    if profession in {"guard", "sheriff"}:
        return "guard"
    return "generic"


def run_traveler_arrival_incident_sharing(world, traveler, destination_village, *, max_shares: int = 2) -> int:
    """Let a traveling carrier rebroadcast known incidents to a destination settlement."""
    if destination_village is None:
        return 0
    if not getattr(getattr(traveler, "knowledge", None), "known_harmful_incidents", {}):
        return 0

    recipients = [
        npc for npc in world.village_npcs
        if npc.id != traveler.id
        and not npc.physical.is_dead
        and world._get_village_for_npc(npc) == destination_village
    ]
    if not recipients:
        return 0

    random_order = list(recipients)
    import random

    random.shuffle(random_order)
    shared_count = 0
    for recipient in random_order:
        if propagate_harmful_incident_gossip(world, traveler, recipient, overhear_radius=5):
            shared_count += 1
            if shared_count >= max_shares:
                break
    return shared_count
