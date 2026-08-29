"""Aging, coming-of-age, and elder lifecycle systems."""

from __future__ import annotations
import random
from typing import Any
from config import DAY_LENGTH_TICKS

ADULTHOOD_AGE_THRESHOLD = 18
ELDER_DECLINE_START_AGE = 55
ELDER_MIN_WORK_CAPACITY = 0.65


def get_aging_work_capacity(age: int) -> float:
    """Return a graceful work capacity multiplier based on entity age.
    
    Design principles:
    - Normal peak performance through age 55 (1.0x).
    - Gradual, subtle decline between 55 and 80 (down to 0.65x minimum).
    - Hard floor at 0.65x prevents elders from becoming incompetent or useless.
    - Elders keep their jobs, livelihoods, and societal dignity.
    """
    if age <= ELDER_DECLINE_START_AGE:
        return 1.0
    decline = (age - ELDER_DECLINE_START_AGE) * 0.014
    return max(ELDER_MIN_WORK_CAPACITY, 1.0 - decline)


def update_npc_ages(world: Any) -> None:
    """Increments age, triggers coming-of-age transitions, and updates vitality curves once per game day."""
    if world.game_time <= 0 or world.game_time % DAY_LENGTH_TICKS != 0:
        return

    for npc in getattr(world, "all_npcs", []):
        if getattr(getattr(npc, "physical", None), "is_dead", False):
            continue

        npc.age += 1

        # Child -> Adult transition at age 18
        current_prof = getattr(getattr(npc, "economic", None), "profession", None)
        if current_prof == "Child" and npc.age >= ADULTHOOD_AGE_THRESHOLD:
            if hasattr(world, "_set_entity_profession"):
                world._set_entity_profession(npc, "Unemployed", reason="came_of_age")

        # Update aging work capacity factor
        capacity = get_aging_work_capacity(npc.age)
        if hasattr(npc, "work_efficiency_modifiers"):
            npc.work_efficiency_modifiers["aging_factor"] = round(capacity, 2)

        # Gentle elder natural passing at high ages
        if npc.age >= 75:
            daily_death_chance = (npc.age - 75) * 0.003
            if random.random() < daily_death_chance:
                if hasattr(npc, "physical"):
                    npc.physical.is_dead = True
                if hasattr(world, "log_event"):
                    anchor = (npc.x, npc.y)
                    world.log_event(
                        event_type="entity_death",
                        description=f"{getattr(npc, 'name', 'An elder')} passed away peacefully of old age at the age of {npc.age}.",
                        subject_id=npc.id,
                        location=anchor,
                    )
                if hasattr(world, "add_message_to_chat_log"):
                    # Only notify player if in proximity or familiar
                    dist = abs(npc.x - world.player.x) + abs(npc.y - world.player.y) if hasattr(world, "player") else 999
                    if dist <= 20:
                        world.add_message_to_chat_log(f"{getattr(npc, 'name', 'An elder')} has passed away peacefully of old age.")
