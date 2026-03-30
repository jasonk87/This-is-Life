"""Structured conversation topic/content selection for simulation-driven dialogue."""

from __future__ import annotations

import random
from dataclasses import dataclass

try:
    from config import DAY_LENGTH_TICKS
except ImportError:
    DAY_LENGTH_TICKS = 1000


@dataclass
class ConversationTopicChoice:
    topic_type: str
    payload: dict
    goal: str


def select_conversation_topic(world, speaker, listener, foundation_profile, group_listeners=None) -> ConversationTopicChoice:
    group_listeners = group_listeners or []
    all_listeners = [listener] + [g for g in group_listeners if getattr(g, "id", None) != getattr(listener, "id", None)]

    base_relationship = float(getattr(getattr(speaker, "social", None), "relationships", {}).get(getattr(listener, "id", None), 50))
    relationship = base_relationship
    base_shared_ticks = getattr(getattr(speaker, "social", None), "shared_experience_ticks", {}).get(getattr(listener, "id", None), 0)
    shared_ticks = base_shared_ticks
    is_following = False

    for g in all_listeners:
        g_id = getattr(g, "id", None)
        if g_id is None:
            continue
        rel = float(getattr(getattr(speaker, "social", None), "relationships", {}).get(g_id, 50))
        if rel > relationship:
            relationship = relationship + (rel - relationship) * 0.2

        ticks = getattr(getattr(speaker, "social", None), "shared_experience_ticks", {}).get(g_id, 0)
        if ticks > shared_ticks:
            shared_ticks = int(shared_ticks + (ticks - shared_ticks) * 0.2)

        if getattr(getattr(speaker, "social", None), "follow_target_id", None) == g_id or \
           getattr(getattr(g, "social", None), "follow_target_id", None) == getattr(speaker, "id", None):
            is_following = True

    bias = _get_fresh_knowledge_bias(world, speaker, all_listeners) or {}

    openness = float(getattr(foundation_profile, "openness", 0.5))

    has_incident_gossip = _choose_incident_payload(world, speaker) is not None
    has_incident_report = _choose_incident_payload(world, speaker, min_confidence=0.7) is not None

    candidate_weights = {
        "greeting": 0.5 if relationship < 45 else 0.15,
        "small_talk": 0.9,
        "gossip": 0.4 if has_incident_gossip else 0.0,
        "report_incident": 0.55 if has_incident_report else 0.0,
        "reflection": 0.5 if _choose_reflection_payload(world, speaker, listener) else 0.0,
        "ask_info": 0.25 if _choose_ask_info_payload(speaker, listener) else 0.0,
        "ask_favor": 0.2 if _choose_favor_payload(speaker) else 0.0,
    }

    if openness < 0.4:
        candidate_weights["reflection"] *= 0.25
        candidate_weights["ask_favor"] *= 0.3
    if relationship >= 65 and openness >= 0.55:
        candidate_weights["reflection"] *= 2.0
        candidate_weights["gossip"] *= 1.2
    if relationship < 40:
        candidate_weights["greeting"] *= 1.7
        candidate_weights["small_talk"] *= 1.3
    if _is_low_pressure_gathering_context(speaker):
        candidate_weights["reflection"] *= 1.8
        candidate_weights["gossip"] *= 1.6
        candidate_weights["small_talk"] *= 1.2
    if is_following or shared_ticks > 100:
        candidate_weights["reflection"] *= 1.5
        candidate_weights["gossip"] *= 1.2
        candidate_weights["small_talk"] *= 1.2

    for topic, topic_bias in bias.items():
        if topic in candidate_weights:
            candidate_weights[topic] += topic_bias

    # Apply explicit topic momentum
    context_data = getattr(speaker, "task_context_data", None)
    if isinstance(context_data, dict):
        current_topic = context_data.get("current_topic")
        if current_topic in candidate_weights:
            momentum_bonus = 2.0 if current_topic == "reflection" else 0.5
            if current_topic == "small_talk": momentum_bonus = 0.2
            candidate_weights[current_topic] += momentum_bonus

    topics = [topic for topic, weight in candidate_weights.items() if weight > 0]
    weights = [candidate_weights[topic] for topic in topics]
    if not topics:
        return ConversationTopicChoice("small_talk", {"kind": "weather"}, "continue_conversation")
    topic = random.choices(topics, weights=weights, k=1)[0]
    return ConversationTopicChoice(topic, _build_payload(world, speaker, listener, topic), _goal_for_topic(topic))


def apply_conversation_topic(world, speaker, listener, choice: ConversationTopicChoice, group_listeners=None) -> tuple[str, str]:
    group_listeners = group_listeners or []
    all_listeners = [listener] + [g for g in group_listeners if getattr(g, "id", None) != getattr(listener, "id", None)]

    topic = choice.topic_type
    payload = choice.payload or {}

    # Mark discussed
    event_id = payload.get("incident_id") or payload.get("memory_id")
    if event_id:
        for participant in [speaker] + all_listeners:
            knowledge = getattr(participant, "knowledge", None)
            if knowledge:
                if not hasattr(knowledge, "discussed_event_ids"):
                    knowledge.discussed_event_ids = set()
                knowledge.discussed_event_ids.add(event_id)

    # Save current topic to speaker context for momentum
    if hasattr(speaker, "task_context_data"):
        context = getattr(speaker, "task_context_data", None)
        if not isinstance(context, dict):
            speaker.task_context_data = {}
        speaker.task_context_data["current_topic"] = topic

    if topic == "greeting":
        return (f"Good to see you, {listener.name}.", "continue_conversation")
    if topic == "small_talk":
        subject = payload.get("kind", "the day")
        return (f"Strange {subject}, isn't it?", "continue_conversation")
    if topic in {"gossip", "report_incident"} and payload.get("incident_id"):
        for g in all_listeners:
            world.propagate_npc_harmful_incident_gossip(speaker, g)
        return ("Have you heard what happened recently?", "continue_conversation")
    if topic == "reflection":
        memory = payload.get("memory_text", "I've been thinking about old times.")
        relationships = getattr(getattr(speaker, "social", None), "relationships", {})
        for g in all_listeners:
            listener_memory = getattr(getattr(g, "knowledge", None), "long_term_memory", None)
            if isinstance(listener_memory, list):
                listener_memory.append(f"Heard from {speaker.name}: {memory}")
                if len(listener_memory) > 50:
                    del listener_memory[:-50]
            if getattr(g, "id", None) is not None:
                relationships[g.id] = min(100, relationships.get(g.id, 50) + 2)
        return (memory, "continue_conversation")
    if topic == "ask_info":
        location_name = payload.get("location_name")
        location_coords = payload.get("location_coords")
        if location_name and location_coords and hasattr(speaker, "knowledge"):
            speaker.knowledge.known_locations[location_name] = location_coords
            return (f"Thanks for the tip about the {location_name}.", "continue_conversation")
        return ("Do you know your way around here?", "continue_conversation")
    if topic == "ask_favor":
        need = payload.get("need", "a hand")
        return (f"I could use {need}, if you're willing.", "continue_conversation")
    return ("Let's keep talking.", "continue_conversation")


def _goal_for_topic(topic: str) -> str:
    if topic in {"report_incident", "ask_favor"}:
        return "socialize"
    return "continue_conversation"


def _build_payload(world, speaker, listener, topic: str) -> dict:
    if topic in {"gossip", "report_incident"}:
        return _choose_incident_payload(world, speaker) or {}
    if topic == "reflection":
        return _choose_reflection_payload(world, speaker, listener) or {}
    if topic == "ask_info":
        return _choose_ask_info_payload(speaker, listener) or {}
    if topic == "ask_favor":
        return _choose_favor_payload(speaker) or {}
    if topic == "small_talk":
        tod = "day"
        if hasattr(world, "_get_time_of_day_str"):
            tod = world._get_time_of_day_str(world.game_time, 1)
        return {"kind": tod.lower()}
    return {}


def _choose_incident_payload(world, speaker, *, min_confidence: float = 0.35) -> dict | None:
    known = getattr(getattr(speaker, "knowledge", None), "known_harmful_incidents", {})
    if not known:
        return None
    candidates = []
    discussed = getattr(getattr(speaker, "knowledge", None), "discussed_event_ids", set())
    current_time = getattr(world, "game_time", 0)


    for incident_id, attribution in known.items():
        confidence = float(getattr(attribution, "confidence", 0.0))
        if confidence < min_confidence:
            continue
        incident = world.harmful_incidents.get(incident_id)
        if incident is None:
            continue
        severity = float(getattr(incident, "severity", 0.0))

        is_undiscussed = incident_id not in discussed
        age = current_time - getattr(incident, "timestamp", 0)
        is_fresh = age < DAY_LENGTH_TICKS * 2

        score = confidence * severity
        if is_undiscussed:
            score += 1000  # Strong bias toward new info
        if is_fresh:
            score += 500

        candidates.append((score, confidence, severity, incident_id, incident, attribution))
    if not candidates:
        return None
    _score, _confidence, _severity, incident_id, incident, attribution = max(candidates, key=lambda item: item[0])
    return {
        "incident_id": incident_id,
        "attacker_id": getattr(attribution, "attributed_attacker_id", None),
        "target_id": getattr(incident, "target_id", None),
        "severity": getattr(incident, "severity", 0),
    }


def _choose_reflection_payload(world, speaker, listener) -> dict | None:
    known_memories = list(getattr(getattr(speaker, "knowledge", None), "known_memories", {}).values())
    if known_memories:
        shared_memories = []
        if listener:
            listener_id = getattr(listener, "id", None)
            shared_memories = [m for m in known_memories if getattr(m, "subject_id", None) == listener_id or getattr(m, "target_id", None) == listener_id]

        pool = shared_memories if shared_memories else known_memories
        discussed = getattr(getattr(speaker, "knowledge", None), "discussed_event_ids", set())
        current_time = getattr(world, "game_time", 0)


        def memory_score(memory):
            score = getattr(memory, "importance_score", 0)
            if getattr(memory, "id", None) not in discussed:
                score += 1000
            age = current_time - getattr(memory, "timestamp", 0)
            if age < DAY_LENGTH_TICKS * 2:
                score += 500
            return (score, getattr(memory, "timestamp", 0))

        pool.sort(key=memory_score, reverse=True)
        memory = pool[0]
        text = getattr(memory, "headline", None) or getattr(memory, "description", None) or getattr(memory, "event_type", "A difficult day.")
        return {"memory_id": getattr(memory, "id", None), "memory_text": str(text)}
    long_term = getattr(getattr(speaker, "knowledge", None), "long_term_memory", [])
    if long_term:
        return {"memory_id": None, "memory_text": str(long_term[-1])}
    return None


def _choose_ask_info_payload(speaker, listener) -> dict | None:
    speaker_locations = getattr(getattr(speaker, "knowledge", None), "known_locations", {})
    listener_locations = getattr(getattr(listener, "knowledge", None), "known_locations", {})
    unknown_to_speaker = [name for name in listener_locations.keys() if name not in speaker_locations]
    if not unknown_to_speaker:
        return None
    location_name = unknown_to_speaker[0]
    return {"location_name": location_name, "location_coords": listener_locations[location_name]}


def _choose_favor_payload(speaker) -> dict | None:
    hunger = float(getattr(getattr(speaker, "physical", None), "hunger", 0))
    thirst = float(getattr(getattr(speaker, "physical", None), "thirst", 0))
    if hunger >= 80:
        return {"need": "a bite to eat"}
    if thirst >= 80:
        return {"need": "a drink"}
    return None


def _is_low_pressure_gathering_context(speaker) -> bool:
    context = getattr(speaker, "task_context_data", None)
    return isinstance(context, dict) and context.get("social_context") == "gathering"


def _get_fresh_knowledge_bias(world, speaker, all_listeners) -> dict[str, float]:
    """Calculate weight biases for conversation topics based on fresh, undiscussed knowledge."""
    bias = {"gossip": 0.0, "report_incident": 0.0, "reflection": 0.0}

    participants = [speaker] + all_listeners
    current_time = getattr(world, "game_time", 0)
    day_length = 1000  # Assume something like DAY_LENGTH_TICKS if world doesn't have it

    # 1 tick roughly = 1 minute if day is 1000 ticks, let's say "fresh" is within 2 days
    freshness_threshold = DAY_LENGTH_TICKS * 2

    for participant in participants:
        knowledge = getattr(participant, "knowledge", None)
        if not knowledge:
            continue

        discussed = getattr(knowledge, "discussed_event_ids", set())

        # Check harmful incidents
        known_incidents = getattr(knowledge, "known_harmful_incidents", {})
        for incident_id, attribution in known_incidents.items():
            # The speaker must know about the incident to bring it up
            if incident_id not in getattr(getattr(speaker, "knowledge", None), "known_harmful_incidents", {}):
                continue
            if incident_id in discussed:
                continue
            incident = world.harmful_incidents.get(incident_id)
            if not incident:
                continue

            incident_time = getattr(incident, "timestamp", 0)
            age = current_time - incident_time
            if age < freshness_threshold:
                severity = float(getattr(incident, "severity", 0.0))
                confidence = float(getattr(attribution, "confidence", 0.0))

                # Determine relevance and prestige
                relevance_multiplier = 1.0
                incident_target = getattr(incident, "target_id", None)
                incident_attacker = getattr(incident, "attacker_id", None)

                # Personal relevance
                participant_ids = {getattr(p, "id", None) for p in participants if getattr(p, "id", None) is not None}
                if incident_target in participant_ids or incident_attacker in participant_ids:
                    relevance_multiplier += 1.5

                # Local relevance
                loc = getattr(incident, "location", None)
                speaker_loc = (getattr(speaker, "x", 0), getattr(speaker, "y", 0))
                if loc and hasattr(speaker, "x") and hasattr(speaker, "y"):
                    dist_sq = (loc[0] - speaker_loc[0])**2 + (loc[1] - speaker_loc[1])**2
                    if dist_sq < 400:  # Roughly within 20 tiles
                        relevance_multiplier += 0.5

                # Base score from severity and confidence
                score = (severity / 50.0) * confidence * (1.0 - (age / freshness_threshold)) * relevance_multiplier

                if confidence >= 0.7:
                    bias["report_incident"] = max(bias["report_incident"], score * 2.0)
                else:
                    bias["gossip"] = max(bias["gossip"], score * 1.5)

        # Check known memories
        known_memories = getattr(knowledge, "known_memories", {})
        for memory_id, memory in known_memories.items():
            # The speaker must know about the memory to bring it up
            if memory_id not in getattr(getattr(speaker, "knowledge", None), "known_memories", {}):
                continue
            if memory_id in discussed:
                continue

            memory_time = getattr(memory, "timestamp", 0)
            age = current_time - memory_time
            if age < freshness_threshold:
                importance = float(getattr(memory, "importance_score", 0.0))
                relevance_multiplier = 1.0

                # Personal relevance
                participant_ids = {getattr(p, "id", None) for p in participants if getattr(p, "id", None) is not None}
                mem_subject = getattr(memory, "subject_id", None)
                mem_target = getattr(memory, "target_id", None)
                if mem_subject in participant_ids or mem_target in participant_ids:
                    relevance_multiplier += 1.5

                score = (importance / 50.0) * (1.0 - (age / freshness_threshold)) * relevance_multiplier
                bias["reflection"] = max(bias["reflection"], score * 1.5)

    return bias
