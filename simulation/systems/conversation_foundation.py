"""Structured conversation foundation driven by simulation state."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class ConversationFoundationProfile:
    can_start: bool
    reason: str
    stance: str
    tone: str
    openness: float
    outcome_weights: dict[str, float]


def evaluate_conversation_foundation(world, speaker, listener, *, max_distance: int = 2) -> ConversationFoundationProfile:
    """Compute conversation startability + stance/tone/openness + outcome weights."""
    if speaker is None or listener is None:
        return ConversationFoundationProfile(False, "missing_participant", "neutral", "neutral", 0.0, {"end_conversation": 1.0})
    if getattr(getattr(speaker, "physical", None), "is_dead", False) or getattr(getattr(listener, "physical", None), "is_dead", False):
        return ConversationFoundationProfile(False, "participant_unavailable", "neutral", "neutral", 0.0, {"end_conversation": 1.0})
    distance = abs(getattr(speaker, "x", 0) - getattr(listener, "x", 0)) + abs(getattr(speaker, "y", 0) - getattr(listener, "y", 0))
    if distance > max_distance:
        return ConversationFoundationProfile(False, "too_far", "neutral", "neutral", 0.0, {"end_conversation": 1.0})

    assessment = _safe_social_assessment(world, speaker, listener)
    relationship = float(getattr(getattr(speaker, "social", None), "relationships", {}).get(getattr(listener, "id", None), 50))
    openness = _openness_from_stance_and_relationship(assessment.stance, relationship)
    tone = _tone_from_stance(assessment.stance)
    weights = _outcome_weights_for_stance(assessment.stance, openness, relationship)
    can_start = assessment.stance != "hostile" or openness >= 0.55
    reason = "ok" if can_start else "hostile_closed"
    return ConversationFoundationProfile(can_start, reason, assessment.stance, tone, openness, weights)


def choose_structured_conversation_outcome(profile: ConversationFoundationProfile, world) -> str:
    """Pick a structured conversation outcome from weighted options."""
    options = [(goal, weight) for goal, weight in profile.outcome_weights.items() if weight > 0]
    if not options:
        return "end_conversation"
    goals = [goal for goal, _weight in options]
    weights = [weight for _goal, weight in options]
    return random.choices(goals, weights=weights, k=1)[0]


def _tone_from_stance(stance: str) -> str:
    return {
        "respectful": "warm",
        "neutral": "neutral",
        "wary": "guarded",
        "fearful": "nervous",
        "hostile": "tense",
    }.get(stance, "neutral")


def _openness_from_stance_and_relationship(stance: str, relationship: float) -> float:
    base = {
        "respectful": 0.85,
        "neutral": 0.55,
        "wary": 0.35,
        "fearful": 0.2,
        "hostile": 0.1,
    }.get(stance, 0.5)
    rel_shift = (max(0.0, min(100.0, relationship)) - 50.0) / 200.0
    return max(0.0, min(1.0, base + rel_shift))


def _outcome_weights_for_stance(stance: str, openness: float, relationship: float) -> dict[str, float]:
    continue_weight = max(0.0, openness * 1.2)
    end_weight = max(0.1, 1.0 - openness)
    weights = {
        "continue_conversation": continue_weight,
        "end_conversation": end_weight,
        "socialize": 0.2 if openness >= 0.55 else 0.0,
        "go_home": 0.08 if stance in {"wary", "fearful"} else 0.03,
        "go_to_work": 0.05 if stance in {"neutral", "wary"} else 0.02,
    }
    if stance == "respectful" and relationship >= 60:
        weights["socialize"] = max(weights.get("socialize", 0.0), 0.35)
    if stance in {"fearful", "hostile"}:
        weights["end_conversation"] = max(weights["end_conversation"], 0.8)
        weights["continue_conversation"] *= 0.4
    return weights


def _safe_social_assessment(world, speaker, listener):
    try:
        return world.evaluate_social_reaction_stance(speaker, listener)
    except Exception:
        class _FallbackAssessment:
            stance = "neutral"
            threat_score = 0.0

        return _FallbackAssessment()
