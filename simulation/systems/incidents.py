"""Structured harmful incident tracking and attribution helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import uuid

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
        id=f"harm_{uuid.uuid4().hex[:12]}",
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


def tell_harmful_incident_claim(speaker, listener, incident: HarmfulIncident) -> bool:
    """Share secondhand incident knowledge from a speaker to a listener with reduced confidence."""
    if not hasattr(speaker, "knowledge") or not hasattr(listener, "knowledge"):
        return False
    speaker_view = speaker.knowledge.known_harmful_incidents.get(incident.id)
    if speaker_view is None:
        return False

    speaker_confidence = max(0.0, min(1.0, float(getattr(speaker_view, "confidence", 0.0))))
    relationship = listener.social.relationships.get(getattr(speaker, "id", None), 50)
    credibility_factor = 0.5 + (max(0, min(100, relationship)) / 200.0)  # 0.5 -> 1.0
    secondhand_confidence = max(0.1, min(0.89, speaker_confidence * 0.7 * credibility_factor))

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
