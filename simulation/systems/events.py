"""Scheduled event (festivals, fairs, market days) system for autonomous living."""

from __future__ import annotations
from typing import Any
from config import DAY_LENGTH_TICKS, DAYS_PER_SEASON

# Generic event definitions:
#   key                 - unique identifier string
#   name                - human-readable display name
#   season              - "Spring" | "Summer" | "Autumn" | "Winter" (or None for recurring each season)
#   start_day_of_season - integer 0 .. DAYS_PER_SEASON - 1
#   duration_days       - duration in full game days
#   demand_boost_items  - list of item_key strings whose village demand increases
#   demand_boost_amount - integer added to demand for each listed item
#   status_effect       - optional status effect applied to living villagers & player
#   draws_crowd         - bool; if True, NPCs prioritize town square / market gathering
#   start_message       - broadcast to message log on start
#   end_message         - broadcast to message log on end

SCHEDULED_EVENT_DEFINITIONS: list[dict[str, Any]] = [
    {
        "key": "harvest_festival",
        "name": "Harvest Festival",
        "season": "Autumn",
        "start_day_of_season": 0,
        "duration_days": 4,
        "demand_boost_items": ["bread", "wheat", "apple", "cooked_meat"],
        "demand_boost_amount": 8,
        "status_effect": "Festive",
        "draws_crowd": True,
        "start_message": "The Harvest Festival has begun! Villages are alive with music, feasting, and full market stalls.",
        "end_message": "The Harvest Festival has come to an end for another year.",
    },
    {
        "key": "spring_fair",
        "name": "Spring Planting Fair",
        "season": "Spring",
        "start_day_of_season": 1,
        "duration_days": 3,
        "demand_boost_items": ["wheat_seeds", "timber", "stone_knife", "iron_axe"],
        "demand_boost_amount": 6,
        "status_effect": "Festive",
        "draws_crowd": True,
        "start_message": "The Spring Planting Fair is underway! Farmers and artisans gather in the square with seedlings and new tools.",
        "end_message": "The Spring Planting Fair has drawn to a close.",
    },
    {
        "key": "winter_solstice",
        "name": "Winter Hearth Celebration",
        "season": "Winter",
        "start_day_of_season": 6,
        "duration_days": 3,
        "demand_boost_items": ["wood", "timber", "bread", "ale", "cooked_meat"],
        "demand_boost_amount": 8,
        "status_effect": "Festive",
        "draws_crowd": True,
        "start_message": "The Winter Hearth Celebration has begun! Townspeople gather around roaring hearths for warm food and songs.",
        "end_message": "The Winter Hearth Celebration has ended.",
    },
    {
        "key": "market_day_mid",
        "name": "Weekly Town Market",
        "season": None,  # Occurs every season
        "start_day_of_season": 4,
        "duration_days": 1,
        "demand_boost_items": ["bread", "flour", "iron_ingot", "leather", "apple"],
        "demand_boost_amount": 5,
        "status_effect": "Lively",
        "draws_crowd": True,
        "start_message": "Market Day has arrived! Traders and villagers set up stalls across the town square.",
        "end_message": "The weekly market winds down as merchants pack up their stalls.",
    },
]


def run_scheduled_events(world: Any) -> None:
    """Reusable scheduled-event dispatcher checked once per game day."""
    if not hasattr(world, "active_scheduled_events"):
        world.active_scheduled_events = {}
    if not hasattr(world, "scheduled_events_last_checked_day"):
        world.scheduled_events_last_checked_day = -1

    current_day = world.game_time // max(1, DAY_LENGTH_TICKS)
    if world.scheduled_events_last_checked_day >= current_day:
        return
    world.scheduled_events_last_checked_day = current_day

    # End events whose window has closed
    for key in list(world.active_scheduled_events.keys()):
        if current_day >= world.active_scheduled_events[key]["end_day"]:
            end_scheduled_event(world, key)

    days_into_season = current_day % max(1, DAYS_PER_SEASON)
    current_season_name = world.seasons[world.current_season_index] if hasattr(world, "seasons") else "Spring"

    for definition in SCHEDULED_EVENT_DEFINITIONS:
        key = definition["key"]
        if key in world.active_scheduled_events:
            continue
        req_season = definition.get("season")
        if req_season is not None and current_season_name != req_season:
            continue
        if days_into_season != definition.get("start_day_of_season", 0):
            continue
        start_scheduled_event(world, definition, current_day)


def start_scheduled_event(world: Any, definition: dict[str, Any], current_day: int) -> None:
    """Applies a scheduled event's start effects: village demand boost, status effects, and announcement."""
    key = definition["key"]
    world.active_scheduled_events[key] = {
        "end_day": current_day + definition["duration_days"],
        "name": definition["name"],
        "draws_crowd": definition.get("draws_crowd", False),
    }

    boost_amount = definition.get("demand_boost_amount", 0)
    for item_key in definition.get("demand_boost_items", []):
        for village in getattr(world, "villages", []):
            village.demand[item_key] = village.demand.get(item_key, 0) + boost_amount

    status_effect = definition.get("status_effect")
    if status_effect:
        all_entities = [getattr(world, "player", None), *getattr(world, "all_npcs", [])]
        for entity in all_entities:
            if entity is None:
                continue
            physical = getattr(entity, "physical", None)
            if physical is not None and not getattr(physical, "is_dead", False):
                if status_effect not in physical.status_effects:
                    physical.status_effects.append(status_effect)

    start_message = definition.get("start_message")
    if start_message and hasattr(world, "add_message_to_chat_log"):
        world.add_message_to_chat_log(start_message)


def end_scheduled_event(world: Any, key: str) -> None:
    """Reverses scheduled event effects cleanly."""
    state = world.active_scheduled_events.pop(key, None)
    if state is None:
        return
    definition = next((d for d in SCHEDULED_EVENT_DEFINITIONS if d["key"] == key), None)
    if definition is None:
        return

    boost_amount = definition.get("demand_boost_amount", 0)
    for item_key in definition.get("demand_boost_items", []):
        for village in getattr(world, "villages", []):
            if item_key in village.demand:
                village.demand[item_key] = max(0, village.demand[item_key] - boost_amount)
                if village.demand[item_key] <= 0:
                    del village.demand[item_key]

    status_effect = definition.get("status_effect")
    if status_effect:
        all_entities = [getattr(world, "player", None), *getattr(world, "all_npcs", [])]
        for entity in all_entities:
            if entity is None:
                continue
            physical = getattr(entity, "physical", None)
            if physical is not None and status_effect in physical.status_effects:
                physical.status_effects.remove(status_effect)

    end_message = definition.get("end_message")
    if end_message and hasattr(world, "add_message_to_chat_log"):
        world.add_message_to_chat_log(end_message)


def is_scheduled_event_active(world: Any, key: str) -> bool:
    """Return True if the specified event key is currently running."""
    return key in getattr(world, "active_scheduled_events", {})


def is_crowd_event_active(world: Any) -> bool:
    """Return True if any active scheduled event draws crowds to the town square."""
    for event_data in getattr(world, "active_scheduled_events", {}).values():
        if event_data.get("draws_crowd", False):
            return True
    return False
