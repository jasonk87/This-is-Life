"""Aging, coming-of-age, and elder lifecycle systems."""

from __future__ import annotations
import random
from typing import Any
from config import DAY_LENGTH_TICKS, DAYS_PER_SEASON

ADULTHOOD_AGE_THRESHOLD = 18

# How many game days make a year of an entity's life. The world already keeps a
# calendar - four seasons of DAYS_PER_SEASON days - and this is that year.
#
# Everything else in this file ran once a day and added a year to every entity,
# so a villager aged 112 years for every year the world lived through. Measured
# over sixty simulated days: a village of 76 people fell to 7, with 66 deaths
# against 1 birth, and the median age of the survivors was 80. The population
# was not starving or being killed, it was simply being aged to death - a
# forty-year-old farmer is past the elder death rolls inside about five weeks of
# play. The rest of the function is still daily: work capacity, coming of age
# and the elder passing roll are all meant to be checked every day.
SEASONS_PER_YEAR = 4
DAYS_PER_YEAR = DAYS_PER_SEASON * SEASONS_PER_YEAR
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
    # See World.begin_new_day: game_time jumps when the player sleeps or takes a
    # costly action, so an equality test against midnight silently skips days.
    # Falls back to the old test for the stand-in worlds used in tests.
    begin_new_day = getattr(world, "begin_new_day", None)
    if begin_new_day is not None:
        if not begin_new_day("npc_ages"):
            return
    elif world.game_time <= 0 or world.game_time % DAY_LENGTH_TICKS != 0:
        return

    # A birthday for everyone when the calendar year turns over, rather than
    # every day. The first call on a world only records which year it is, so a
    # freshly generated village does not immediately age a year.
    day = int(getattr(world, "game_time", 0)) // max(1, DAY_LENGTH_TICKS)
    year = day // max(1, DAYS_PER_YEAR)
    had_birthday = hasattr(world, "_last_aging_year") and year != world._last_aging_year
    world._last_aging_year = year

    for npc in getattr(world, "all_npcs", []):
        if getattr(getattr(npc, "physical", None), "is_dead", False):
            continue

        if had_birthday:
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
