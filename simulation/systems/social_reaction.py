"""Entity-agnostic social reaction stance evaluation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SocialReactionAssessment:
    stance: str
    threat_score: float


def evaluate_social_reaction_stance(world, observer, target) -> SocialReactionAssessment:
    """Derive a lightweight social reaction stance from belief + visible threat cues."""
    if observer is None or target is None:
        return SocialReactionAssessment("neutral", 0.0)
    if getattr(observer, "id", None) == getattr(target, "id", None):
        return SocialReactionAssessment("neutral", 0.0)

    local_opinion = world.refresh_local_incident_opinion(observer, getattr(target, "id", None))
    distrust = float(getattr(observer, "get_distrust_towards", lambda _t: 0)(target))
    incident_confidence = _mean_incident_confidence(observer, getattr(target, "id", None))
    visible_threat = _visible_threat_score(target)

    threat_score = max(0.0, distrust - local_opinion + (incident_confidence * 40.0) + visible_threat)
    if local_opinion >= 35 and distrust < 20:
        return SocialReactionAssessment("respectful", threat_score)
    if threat_score >= 95:
        return SocialReactionAssessment("hostile", threat_score)
    if threat_score >= 70:
        return SocialReactionAssessment("fearful", threat_score)
    if threat_score >= 40:
        return SocialReactionAssessment("wary", threat_score)
    return SocialReactionAssessment("neutral", threat_score)


def _mean_incident_confidence(observer, target_id: int | None) -> float:
    if target_id is None:
        return 0.0
    known = getattr(getattr(observer, "knowledge", None), "known_harmful_incidents", {})
    confidences = [
        float(getattr(view, "confidence", 0.0))
        for view in known.values()
        if getattr(view, "attributed_attacker_id", None) == target_id
    ]
    if not confidences:
        return 0.0
    return max(0.0, min(1.0, sum(confidences) / len(confidences)))


def _visible_threat_score(target) -> float:
    get_equipped = getattr(target, "get_equipped_item_reference", None)
    if not callable(get_equipped):
        return 0.0
    weapon = get_equipped("weapon")
    if weapon is None:
        return 0.0
    return 20.0
