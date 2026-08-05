"""Illness/disease system.

Adds a proximity-based contagious sickness meter to NPCs and the player,
modeled the same way as hunger/thirst (see simulation/systems/survival.py):
a 0-100 meter on PhysicalState/MetabolismComponent, a status-effect
threshold, and a level-message for UI display. The key difference from
hunger/thirst is that sickness has no passive per-tick increase - it only
rises via contagion (spread_contagion) or, rarely, a spontaneous onset, so
the system needs an actual "patient zero" before it spreads anywhere.

Treatment is handled by simulation/systems/medical.py, which was extended
to treat the "sick" status effect alongside the pre-existing "broken_leg"
handling, using a new herbal_remedy item (see data/items.py) crafted the
same way as healing_salve. Treatment is an instant, full cure per visit
(this first pass does not model partial/multi-session recovery).
"""

from __future__ import annotations

import random

from config import DAY_LENGTH_TICKS

SICK_STATUS_EFFECT = "sick"

# Meter thresholds (0-100), mirrors hunger's Peckish/Hungry/Very Hungry/
# Starving gradation, just with two tiers instead of four.
SICKNESS_THRESHOLD_SICK = 70        # crosses into the "sick" status effect - debilitating, treatable
SICKNESS_THRESHOLD_FEVERISH = 40    # flavor-only early warning, no mechanical effect yet

# Contagion tuning (judgment calls - flagged in the commit message).
CONTAGION_CHECK_INTERVAL_TICKS = 30   # how often the proximity scan runs, not every tick, to keep it cheap
CONTAGION_RADIUS = 3                  # tiles (Manhattan distance) counted as "proximity"
CONTAGION_CHANCE_PER_CHECK = 0.06     # per sick/healthy pair within radius, per check
AMBIENT_ONSET_CHANCE_PER_CHECK = 0.0008  # rare spontaneous "patient zero" case per healthy entity, per check
SICKNESS_INFECTION_GAIN = 20          # sickness gained per successful exposure roll

# Untreated-illness worsening, mirrors StarvationBehavior's 10%-per-check
# damage-roll idiom and survival.py's starvation-damage cadence.
WORSENING_INTERVAL_TICKS = DAY_LENGTH_TICKS // 20
WORSENING_SICKNESS_GAIN = 5
WORSENING_DAMAGE_CHANCE = 0.10


def _apply_sickness_status(world, entity) -> None:
    """Sync status_effects/level message with the current sickness value,
    mirroring PhysicalState's hunger_level_msg pattern. Applies the same
    halved-speed penalty medical.py already uses for broken_leg."""
    physical = entity.physical
    was_sick = SICK_STATUS_EFFECT in physical.status_effects

    if physical.sickness >= SICKNESS_THRESHOLD_SICK:
        physical.sickness_level_msg = "Very Sick"
        if not was_sick:
            physical.status_effects.append(SICK_STATUS_EFFECT)
            if not hasattr(entity, "original_speed"):
                entity.original_speed = getattr(entity, "speed", 1)
            entity.speed = max(0.5, getattr(entity, "original_speed", 1) / 2.0)
            world.add_message_to_chat_log(f"{world.get_entity_display_name(entity)} has fallen ill.")
    elif physical.sickness >= SICKNESS_THRESHOLD_FEVERISH:
        physical.sickness_level_msg = "Feverish"
    else:
        physical.sickness_level_msg = ""


def recover_from_sickness(entity) -> None:
    """Fully cures an entity's sickness - called by medical.py once
    treatment completes, and by the player's direct herbal_remedy use in
    engine.py's use_item. Mirrors how broken_leg treatment restores speed."""
    physical = entity.physical
    if SICK_STATUS_EFFECT in physical.status_effects:
        physical.status_effects.remove(SICK_STATUS_EFFECT)
    physical.sickness = 0
    physical.sickness_level_msg = ""
    entity.speed = getattr(entity, "original_speed", 1)


def update_entity_illness(world, entity) -> None:
    """Advance one entity's sickness meter/status. Called once per tick for
    the player and every living NPC, mirroring survival.update_npc_survival.
    Sickness itself only rises from contagion (see spread_contagion) - there
    is no passive per-tick increase like hunger/thirst, since illness needs
    an actual cause."""
    physical = getattr(entity, "physical", None)
    if physical is None or not hasattr(physical, "sickness"):
        return

    _apply_sickness_status(world, entity)

    if physical.sickness >= SICKNESS_THRESHOLD_SICK and world.game_time % WORSENING_INTERVAL_TICKS == 0:
        physical.sickness = min(physical.max_sickness, physical.sickness + WORSENING_SICKNESS_GAIN)
        if random.random() < WORSENING_DAMAGE_CHANCE:
            world.add_message_to_chat_log(f"{world.get_entity_display_name(entity)}'s illness is taking a toll...")
            entity.take_damage(1, world=world)


def spread_contagion(world) -> None:
    """Proximity-based contagion pass across the player and all village
    NPCs. Periodic rather than per-tick (see CONTAGION_CHECK_INTERVAL_TICKS)
    to keep the O(sick * nearby) scan cheap. Each sick entity has a per-check
    chance to infect each healthy entity within CONTAGION_RADIUS tiles; a
    much smaller ambient chance lets sickness start spontaneously so the
    system has somewhere to begin without needing a manually-seeded case."""
    if world.game_time % CONTAGION_CHECK_INTERVAL_TICKS != 0:
        return

    contacts = [c for c in [world.player, *world.village_npcs] if c is not None]
    living_contacts = [c for c in contacts if not getattr(getattr(c, "physical", None), "is_dead", False)]
    sick_entities = [c for c in living_contacts if SICK_STATUS_EFFECT in c.physical.status_effects]

    for sick_entity in sick_entities:
        for other in living_contacts:
            if other is sick_entity:
                continue
            if SICK_STATUS_EFFECT in other.physical.status_effects:
                continue
            if abs(sick_entity.x - other.x) + abs(sick_entity.y - other.y) > CONTAGION_RADIUS:
                continue
            if random.random() < CONTAGION_CHANCE_PER_CHECK:
                other.physical.sickness = min(other.physical.max_sickness, other.physical.sickness + SICKNESS_INFECTION_GAIN)

    for healthy in living_contacts:
        if SICK_STATUS_EFFECT in healthy.physical.status_effects:
            continue
        if random.random() < AMBIENT_ONSET_CHANCE_PER_CHECK:
            healthy.physical.sickness = min(healthy.physical.max_sickness, healthy.physical.sickness + SICKNESS_INFECTION_GAIN)
