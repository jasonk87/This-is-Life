"""Entity-agnostic social reaction stance evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from entities.social import HistoryFactReactionState

from config import DAY_LENGTH_TICKS
from simulation.social_scene import create_public_event_seed_from_reaction


@dataclass
class SocialReactionAssessment:
    stance: str
    threat_score: float


VIOLENT_CRIME_TERMS = {
    "murder",
    "homicide",
    "manslaughter",
    "assault",
    "attack",
    "violent",
    "battery",
    "robbery",
    "harm",
    "killing",
}
POSITIVE_EMPLOYMENT_ACTIONS = {"hired", "promoted", "appointed", "service"}
SOCIAL_INTEREST_RECORD_TYPES = {
    "npc_birth",
    "npc_marriage",
    "npc_migrated",
    "npc_emigrated",
}
EMPLOYMENT_RECORD_TYPES = {
    "npc_hired",
    "npc_employment_changed",
}


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
    presence_score = _calculate_presence_score(world, target)

    base_threat = max(0.0, distrust - local_opinion + (incident_confidence * 40.0) + visible_threat)
    presence_bonus = min(presence_score, 30.0)
    threat_score = base_threat + presence_bonus

    # Presence alone should not push the stance into hostility.
    if base_threat < 95.0 and threat_score >= 95.0:
        threat_score = 94.9

    if local_opinion >= 35 and distrust < 20:
        return SocialReactionAssessment("respectful", threat_score)
    if threat_score >= 95:
        return SocialReactionAssessment("hostile", threat_score)
    if threat_score >= 70:
        return SocialReactionAssessment("fearful", threat_score)
    if threat_score >= 40:
        return SocialReactionAssessment("wary", threat_score)
    return SocialReactionAssessment("neutral", threat_score)


def apply_known_history_fact_reactions(world, npc) -> int:
    """Apply one narrow reaction pass over an NPC's known structured history facts."""
    if npc is None or getattr(getattr(npc, "physical", None), "is_dead", False):
        return 0
    knowledge = getattr(npc, "knowledge", None)
    known_facts = getattr(knowledge, "known_history_facts", {}) if knowledge else {}
    if not known_facts:
        return 0

    social = _ensure_history_reaction_state(npc)
    applied = 0
    facts = sorted(
        known_facts.values(),
        key=lambda fact: (
            getattr(fact, "known_at_tick", 0),
            getattr(fact, "source_record_id", ""),
        ),
    )
    for fact in facts:
        fact_id = getattr(fact, "source_record_id", "")
        if not fact_id:
            continue
        state = social.reacted_history_fact_state.get(fact_id)
        if state is None and fact_id in social.reacted_history_fact_ids:
            # Backward compatibility: older saves only remembered that a fact
            # had reacted. Keep duplicate protection rather than reapplying.
            social.reacted_history_fact_state[fact_id] = HistoryFactReactionState(
                reacted_confidence=1.0,
                reacted_source_type="legacy_reacted_id",
                last_reaction_tick=int(getattr(world, "game_time", 0)),
                applied_reaction_strength=0.0,
            )
            continue

        confidence = _fact_confidence(fact)
        if state is not None and confidence <= float(getattr(state, "reacted_confidence", 0.0)):
            continue

        record = _get_history_record(world, fact_id)
        reaction = _score_known_history_fact(world, npc, fact, record)
        if reaction is None:
            _remember_history_reaction_state(world, social, fact, confidence, state, 0.0)
            continue

        previous_strength = float(getattr(state, "applied_reaction_strength", 0.0)) if state else 0.0
        signed_score = float(reaction.get("score", 0.0))
        new_strength = abs(signed_score)
        delta_strength = max(0.0, new_strength - previous_strength)
        if delta_strength <= 0.0:
            _remember_history_reaction_state(world, social, fact, confidence, state, new_strength)
            continue

        delta_reaction = dict(reaction)
        delta_reaction["score"] = round((1.0 if signed_score >= 0 else -1.0) * delta_strength, 2)
        _store_history_reaction(world, npc, fact, delta_reaction, is_escalation=state is not None)
        _remember_history_reaction_state(world, social, fact, confidence, state, new_strength)
        applied += 1
    return applied


def _ensure_history_reaction_state(npc):
    social = getattr(npc, "social", None)
    if social is None:
        return None
    if not hasattr(social, "recent_social_reactions"):
        social.recent_social_reactions = []
    if not hasattr(social, "opinion_modifiers"):
        social.opinion_modifiers = {}
    if not hasattr(social, "reacted_history_fact_ids"):
        social.reacted_history_fact_ids = set()
    if not hasattr(social, "reacted_history_fact_state"):
        social.reacted_history_fact_state = {}
    return social


def _get_history_record(world, record_id: str):
    history = getattr(world, "history", None)
    get_event = getattr(history, "get_event", None)
    if callable(get_event):
        return get_event(record_id)
    return None


def _score_known_history_fact(world, npc, fact, record) -> dict | None:
    record_type = str(getattr(fact, "record_type", ""))
    record_class_name = str(getattr(fact, "record_class_name", ""))
    if _is_crime_fact(record_type, record_class_name, fact):
        return _score_crime_fact(npc, fact, record)
    if record_type == "entity_death" or record_class_name == "DeathRecord":
        return _score_death_fact(npc, fact, record)
    if record_type in EMPLOYMENT_RECORD_TYPES or record_class_name == "EmploymentRecord":
        return _score_employment_fact(npc, fact, record)
    if record_type in SOCIAL_INTEREST_RECORD_TYPES or record_class_name in {
        "BirthRecord",
        "MarriageRecord",
        "MigrationRecord",
    }:
        return _score_social_interest_fact(npc, fact, record)
    return None


def _is_crime_fact(record_type: str, record_class_name: str, fact) -> bool:
    tags = {str(tag).lower() for tag in getattr(fact, "tags", ()) or ()}
    return record_class_name == "CrimeRecord" or "crime" in record_type or "crime" in tags


def _score_crime_fact(npc, fact, record) -> dict | None:
    suspect_id = getattr(record, "suspect_id", None)
    victim_id = getattr(record, "victim_id", None)
    crime_kind = str(
        getattr(record, "crime_kind", "") or getattr(fact, "record_type", "")
    ).lower()
    if suspect_id is None:
        entity_ids = list(getattr(fact, "subject_entity_ids", ()) or ())
        suspect_id = entity_ids[0] if entity_ids else None
    if suspect_id in {None, getattr(npc, "id", None)}:
        return None
    if not _is_violent_crime(crime_kind):
        return None
    confidence = _fact_confidence(fact)
    return {
        "reaction_type": "fear",
        "target_entity_id": suspect_id,
        "related_entity_id": victim_id,
        "score": -round(35.0 * confidence, 2),
        "reason": "known_violent_crime",
        "grudge_severity": int(45 + (35 * confidence)),
    }


def _is_violent_crime(crime_kind: str) -> bool:
    return any(term in crime_kind for term in VIOLENT_CRIME_TERMS)


def _score_death_fact(npc, fact, record) -> dict | None:
    deceased_id = getattr(record, "deceased_id", None)
    if deceased_id is None:
        entity_ids = list(getattr(fact, "subject_entity_ids", ()) or ())
        deceased_id = entity_ids[0] if entity_ids else None
    if deceased_id in {None, getattr(npc, "id", None)}:
        return None
    if not _is_close_relation(npc, deceased_id):
        return None
    return {
        "reaction_type": "grief",
        "target_entity_id": deceased_id,
        "score": -round(25.0 * _fact_confidence(fact), 2),
        "reason": "known_close_death",
    }


def _score_employment_fact(npc, fact, record) -> dict | None:
    worker_id = getattr(record, "worker_id", None)
    action = str(getattr(record, "employment_action", "") or "").lower()
    profession = str(getattr(record, "profession", "") or "").lower()
    if worker_id is None:
        entity_ids = list(getattr(fact, "subject_entity_ids", ()) or ())
        worker_id = entity_ids[0] if entity_ids else None
    if worker_id in {None, getattr(npc, "id", None)}:
        return None
    if action not in POSITIVE_EMPLOYMENT_ACTIONS and "guard" not in profession:
        return None
    confidence = _fact_confidence(fact)
    return {
        "reaction_type": "respect",
        "target_entity_id": worker_id,
        "score": round(8.0 * confidence, 2),
        "reason": "known_service_work",
    }


def _score_social_interest_fact(npc, fact, record) -> dict | None:
    target_id = _first_other_entity_id(npc, getattr(fact, "subject_entity_ids", ()) or ())
    if target_id is None:
        return None
    return {
        "reaction_type": "curiosity",
        "target_entity_id": target_id,
        "score": round(3.0 * _fact_confidence(fact), 2),
        "reason": "known_life_event",
    }


def _store_history_reaction(world, npc, fact, reaction: dict, *, is_escalation: bool = False) -> None:
    social = _ensure_history_reaction_state(npc)
    if social is None:
        return
    target_id = reaction.get("target_entity_id")
    score = float(reaction.get("score", 0.0))
    if target_id is not None:
        social.opinion_modifiers[target_id] = (
            social.opinion_modifiers.get(target_id, 0.0) + score
        )
        if reaction["reaction_type"] == "fear":
            current_day = int(getattr(world, "game_time", 0)) // DAY_LENGTH_TICKS
            if is_escalation:
                existing_grudge = getattr(social, "grudges", {}).get(target_id)
                if existing_grudge is not None:
                    existing_grudge.severity = max(existing_grudge.severity, int(reaction.get("grudge_severity", 60)))
                    existing_grudge.last_updated_day = current_day
            else:
                add_grudge = getattr(npc, "add_grudge", None)
                if callable(add_grudge):
                    add_grudge(
                        target_id,
                        reaction.get("reason", "known_history_fact"),
                        severity=reaction.get("grudge_severity", 60),
                        current_day=current_day,
                        decay_days=8,
                    )
        elif reaction["reaction_type"] == "grief":
            # Personality drift (item 3): scoped specifically to losing a
            # genuine family member (spouse/partner/parent/child/sibling -
            # see _family_ties_include), not the broader "close relation"
            # eligibility _is_close_relation also allows for a very close
            # friend (relationship >= 70). A cherished friendship dying is
            # already handled above via the opinion_modifiers/relationship
            # hit; this additional character-shaping effect is reserved for
            # actual family loss, matching Jason's brief.
            family_ties = getattr(getattr(npc, "social", None), "family_ties", None) or {}
            if _family_ties_include(family_ties, target_id):
                _apply_bereavement_trait_drift(npc)
        elif reaction["reaction_type"] == "respect":
            social.relationships[target_id] = min(
                100,
                social.relationships.get(target_id, 50) + int(max(1, score)),
            )
        elif reaction["reaction_type"] == "curiosity":
            social.relationships[target_id] = min(
                100, social.relationships.get(target_id, 50) + 1
            )

    stored_reaction = {
        "source_record_id": getattr(fact, "source_record_id", ""),
        "reaction_type": reaction["reaction_type"],
        "target_entity_id": target_id,
        "related_entity_id": reaction.get("related_entity_id"),
        "score": score,
        "reason": reaction.get("reason", "known_history_fact"),
        "tick": int(getattr(world, "game_time", 0)),
    }
    social.recent_social_reactions.append(stored_reaction)
    create_public_event_seed_from_reaction(world, stored_reaction)
    if len(social.recent_social_reactions) > 12:
        del social.recent_social_reactions[:-12]



def _remember_history_reaction_state(world, social, fact, confidence: float, previous_state, applied_strength: float) -> None:
    fact_id = str(getattr(fact, "source_record_id", "") or "")
    if not fact_id:
        return
    social.reacted_history_fact_ids.add(fact_id)
    social.reacted_history_fact_state[fact_id] = HistoryFactReactionState(
        reacted_confidence=max(confidence, float(getattr(previous_state, "reacted_confidence", 0.0)) if previous_state else 0.0),
        reacted_source_type=str(getattr(fact, "source_type", "") or ""),
        last_reaction_tick=int(getattr(world, "game_time", 0)),
        applied_reaction_strength=max(applied_strength, float(getattr(previous_state, "applied_reaction_strength", 0.0)) if previous_state else 0.0),
    )

def _fact_confidence(fact) -> float:
    return max(0.0, min(1.0, float(getattr(fact, "confidence", 0.0))))


def _is_close_relation(npc, entity_id: int) -> bool:
    social = getattr(npc, "social", None)
    if social is None:
        return False
    if social.relationships.get(entity_id, 0) >= 70:
        return True
    return _family_ties_include(getattr(social, "family_ties", {}) or {}, entity_id)


def _family_ties_include(value, entity_id: int) -> bool:
    if value == entity_id:
        return True
    if isinstance(value, dict):
        return any(_family_ties_include(child, entity_id) for child in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_family_ties_include(child, entity_id) for child in value)
    return False


def _apply_bereavement_trait_drift(npc) -> None:
    """
    Personality drift (item 3) on losing a spouse/close family member.
    "Character shapes the outcome": an already aggressive/chaotic NPC's
    grief comes out as anger/volatility - aggressive, doubling down on
    their existing emotional-expression style rather than diverging from
    it. An already lawful/studious (orderly, reflective) NPC instead turns
    inward - withdrawn. An already greedy/merchant-leaning NPC's loss
    sharpens a protective instinct over whatever/whoever remains - greedy.
    Anyone without one of those leanings defaults to withdrawn, grief's
    most universally plausible baseline effect (reduced sociability - see
    ambient_info.py's chattiness gate) for someone without a strong prior
    lean either way.
    """
    if not hasattr(npc, "has_trait") or not hasattr(npc, "record_trait_pressure"):
        return  # not an NPC-shaped entity (e.g. the player)
    if npc.has_trait("aggressive") or npc.has_trait("chaotic"):
        npc.record_trait_pressure("aggressive")
    elif npc.has_trait("lawful") or npc.has_trait("studious"):
        npc.record_trait_pressure("withdrawn")
    elif npc.has_trait("greedy") or npc.has_trait("merchant"):
        npc.record_trait_pressure("greedy")
    else:
        npc.record_trait_pressure("withdrawn")


def _first_other_entity_id(npc, entity_ids) -> int | None:
    npc_id = getattr(npc, "id", None)
    for entity_id in entity_ids:
        if isinstance(entity_id, int) and entity_id != npc_id:
            return entity_id
    return None


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


def _calculate_presence_score(world, target) -> float:
    """Calculate a lightweight social presence/importance score."""
    if not target:
        return 0.0

    score = 0.0

    # 1. High-status professions
    profession = str(getattr(getattr(target, "economic", None), "profession", "")).lower()
    if profession in {"mayor", "sheriff", "noble", "guard", "captain", "boss", "deputy", "head_priest"}:
        score += 15.0

    # 2. Guard escorts
    if hasattr(world, "get_entities_in_radius") and hasattr(target, "x") and hasattr(target, "y"):
        nearby = world.get_entities_in_radius(target.x, target.y, 10)
        target_id = getattr(target, "id", None)
        if target_id is not None:
            for entity in nearby:
                social = getattr(entity, "social", None)
                if social and getattr(social, "follow_target_id", None) == target_id and getattr(social, "follow_role", None) == "guard":
                    score += 20.0

    return score


def _visible_threat_score(target) -> float:
    get_equipped = getattr(target, "get_equipped_item_reference", None)
    if not callable(get_equipped):
        return 0.0
    weapon = get_equipped("weapon")
    if weapon is None:
        return 0.0
    return 20.0
