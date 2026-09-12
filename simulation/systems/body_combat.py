"""Local human/wolf combat and the boundary between anatomy and the world.

Body rules live in entities.body_model; this module owns equipment transfers,
simulation consequences, medicine and witnessed events. No model adjudication.
"""
from dataclasses import dataclass
import random

from config import DAY_LENGTH_TICKS, REP_CRIMINAL
from data.items import ITEM_DEFINITIONS
from entities import body_model as body_rules


def supported(actor):
    return (actor is not None and hasattr(actor, "combat")
            and getattr(actor, "animal_type", None) in (None, "wolf", "dire_wolf"))


def ensure_body(actor, now=0):
    if not supported(actor):
        return None
    body = actor.combat.anatomy
    plan = "wolf" if getattr(actor, "animal_type", None) else "human"
    if not body.body_plan:
        if plan == "human" and "broken_leg" in actor.physical.status_effects:
            # Older saves sometimes recorded only the generic status. Preserve
            # it on the weaker recorded leg (left on a tie), never silently cure.
            leg = min(("left_leg", "right_leg"), key=lambda key: body.parts[key].hp / max(1, body.parts[key].max_hp))
            body.parts[leg].ensure_status("broken")
            if hasattr(actor, "original_speed"):
                actor.speed = actor.original_speed  # New movement capability owns the penalty.
        body_rules.upgrade(body, plan, now)
        if actor.physical.is_dead:
            body.death_cause = "legacy death"
            body.death_processed = True
    # Old saves store some real worn gear as string slots. Bind the existing
    # inventory instance when available so its quality/durability is retained.
    from entities.items import ItemReference
    inventory = actor.economic.inventory if hasattr(actor, "state") else actor.economic.npc_inventory
    for slot_name in ("weapon", "body", "head", "hands", "legs", "feet"):
        slot = getattr(actor.equipment, slot_name, None)
        if slot and slot.item_reference is None:
            key = str(slot)
            ref = inventory.get_item_reference(key) if hasattr(inventory, "get_item_reference") else None
            slot.bind(ref if ref is not None else ItemReference(key))
            if ref is not None:
                inventory.extract_item_reference(ref)
    return body


def functions_for(actor):
    body = getattr(getattr(actor, "combat", None), "anatomy", None)
    return body_rules.capabilities(body) if body else dict(movement=1, grip=1, consciousness=1)


def can_act(actor):
    return not getattr(getattr(actor, "physical", None), "is_dead", False) and functions_for(actor)["consciousness"] >= .2


def inventory_for(world, actor):
    return actor.economic.inventory if actor is world.player else actor.economic.npc_inventory


def visible(world, *actors):
    if world.player in actors:
        return True
    fov = getattr(world, "player_fov_map", None)
    if fov is not None:
        for actor in actors:
            try:
                if actor.x >= 0 and actor.y >= 0 and fov[actor.y, actor.x]:
                    return True
            except (IndexError, TypeError):
                pass
    return False


def say(world, message, *actors):
    if visible(world, *actors):
        world.add_message_to_chat_log(message, category="combat")


def held_reference(actor):
    return getattr(getattr(actor.equipment, "weapon", None), "item_reference", None)


def equip_player_weapon(world, key):
    player = world.player
    body = ensure_body(player, world.game_time)
    if not can_act(player) or body_rules.part_function(body, body.weapon_hand) < .2:
        world.add_message_to_chat_log("Your weapon hand cannot hold that right now.")
        return False
    slot = player.equipment.weapon
    if str(slot) == key:
        ref = slot.item_reference
        slot.clear()
        if ref:
            player.add_item_reference(ref)
        world.add_message_to_chat_log("You put your weapon away.")
        return True
    ref = player.pop_item_reference(key)
    if ref is None:
        return False
    previous = slot.item_reference
    slot.bind(ref)
    if previous:
        player.add_item_reference(previous)
    world.add_message_to_chat_log(f"You equip {ref.definition.get('name', key)}.")
    return True


def sync_body(world, actor):
    body = actor.combat.anatomy
    if not body.body_plan:
        return
    caps = body_rules.capabilities(body)
    effects = actor.physical.status_effects
    states = {
        "bleeding": body_rules.bleeding_rate(body, world.game_time) > .00003,
        "unconscious": caps["consciousness"] < .2 and not body.death_cause,
        "broken_leg": any(w.fracture and w.healing < .9 and
                          body.parts[w.part].function == "movement" for w in body.wounds),
        "impaired_grip": body.body_plan == "human" and caps["grip"] < .6,
    }
    for label, active in states.items():
        if active and label not in effects:
            effects.append(label)
        elif not active and label in effects:
            effects.remove(label)
    weapon = held_reference(actor)
    if weapon and (caps["consciousness"] < .2 or
                   body_rules.part_function(body, body.weapon_hand) < .2):
        actor.equipment.weapon.clear()
        # Some legacy equipment aliases still point into the bag.
        inventory = inventory_for(world, actor)
        if hasattr(inventory, "has_item_reference") and inventory.has_item_reference(weapon):
            inventory.extract_item_reference(weapon)
        world.drop_item_reference_on_map(weapon, actor.x, actor.y)
        say(world, f"{actor.name} loses their grip and drops {weapon.definition['name']}.", actor)
    if caps["consciousness"] < .2:
        actor.schedule.current_path = []
        if actor is world.player:
            actor.state.current_path = []
        interaction_id = getattr(actor.schedule, "active_interaction_id", None)
        resolver = getattr(world, "interaction_resolver", None)
        if interaction_id and resolver:
            resolver.cancel_active_interaction(interaction_id, world, "incapacitated")
            actor.schedule.active_interaction_id = None
    if body_rules.assess_death(body) and not body.death_processed:
        body.death_processed = True
        actor.physical.is_dead = True
        killer = next((w.attacker_id for w in reversed(body.wounds) if w.attacker_id is not None), None)
        if actor is world.player:
            world.game_state = "PLAYER_DEAD"
            world.log_event(event_type="entity_death", description="{subject} died from " + body.death_cause + ".",
                            subject_id=actor.id, target_id=killer, location=(actor.x, actor.y))
        else:
            world.handle_npc_death(actor, killer_id=killer, cause_of_death=body.death_cause)
        say(world, f"{actor.name} dies from {body.death_cause}.", actor)


def advance_bodies(world):
    for actor in [world.player, *list(world.all_npcs)]:
        body = ensure_body(actor, world.game_time)
        if body is None or body.death_processed:
            continue
        if not body.wounds and body.blood == 1 and body.systemic_loss == 0:
            body.last_body_tick = max(body.last_body_tick or world.game_time, world.game_time)
            continue
        resting = (getattr(getattr(actor, "state", None), "is_sleeping", False)
                   or actor.schedule.current_task in ("sleeping", "resting_in_bed", "resting")
                   or (actor.schedule.current_task == "recovering_from_injury" and not actor.schedule.current_path))
        nourishment = .3 if (actor.physical.hunger >= actor.physical.max_hunger*.9
                            or actor.physical.thirst >= actor.physical.max_thirst*.9) else 1.0
        body_rules.advance(body, world.game_time, resting, nourishment)
        sync_body(world, actor)


def environmental_damage(actor, amount, world=None):
    """Compatibility reserve for disease/weather; not a fabricated melee wound."""
    body = actor.combat.anatomy
    before = actor.combat.hp
    body.systemic_loss = min(1, body.systemic_loss + max(0, amount) / max(1, body.display_max_hp))
    body_rules.assess_death(body)
    if world is not None:
        sync_body(world, actor)
    elif body.death_cause:
        actor.physical.is_dead = True
    return max(0, before - actor.combat.hp)


def movement_budget(actor, now, speed):
    body = getattr(getattr(actor, "combat", None), "anatomy", None)
    if body is None or not body.body_plan:
        return speed
    if body.movement_tick == now:
        return 0
    body.movement_tick = now
    body.movement_credit += max(0, speed) * functions_for(actor)["movement"]
    moves = int(body.movement_credit)
    body.movement_credit -= moves
    return moves


def retreat_if_injured(world, actor):
    body = actor.combat.anatomy
    if body.body_plan != "wolf" or not body.wounds or not can_act(actor):
        return False
    # Hunger/aggression changes tolerance, but does not give a disabled animal
    # a fresh set of legs. The remembered attacker is the actual threat.
    hunger = actor.physical.hunger / max(1, actor.physical.max_hunger)
    threshold = .35 + hunger * .2 + (.05 if actor.combat.combat_behavior == "aggressive" else 0)
    if body_rules.pain(body) < threshold and functions_for(actor)["movement"] > .65:
        return False
    threat_id = body.last_attacker_id or next((w.attacker_id for w in reversed(body.wounds) if w.attacker_id is not None), None)
    threat = world.get_entity_by_id(threat_id)
    if threat is None or threat.physical.is_dead:
        return False
    distance = max(abs(actor.x - threat.x), abs(actor.y - threat.y))
    if distance > 12:
        actor.combat.is_hostile_to_player = False
        actor.schedule.current_task = "resting"
        actor.schedule.current_path = []
        return True
    from simulation.systems.combat_response import step_away
    actor.schedule.current_task = "fleeing_injury"
    return step_away(world, actor, threat)  # Cornered wolves may defend themselves.


@dataclass(frozen=True)
class AttackResult:
    attempted: bool = False
    hit: bool = False
    part: str | None = None
    force: float = 0
    absorbed: float = 0
    wound_id: int | None = None
    reason: str = ""


def armor_at(actor, part):
    body = actor.combat.anatomy
    slot = body.parts[part].coverage
    if part == "neck":
        slot = "head"
    if slot is None:
        return None, None
    ref = getattr(getattr(actor.equipment, slot, None), "item_reference", None)
    key = ref.key if ref else (getattr(actor.equipment, "equipped_armor", {}) or {}).get(slot)
    if not key:
        return None, None
    definition = ITEM_DEFINITIONS.get(key, {})
    # Coverage describes an item, never the owner's profession or total AC.
    coverage = definition.get("properties", {}).get("body_coverage")
    if coverage is None:
        coverage = {name for name, node in body.parts.items() if node.coverage == slot}
        if key == "iron_breastplate":
            coverage = {"torso"}
        elif key == "leather_jerkin":
            coverage = {"torso", "left_arm", "right_arm"}
        elif key == "hooded_cowl":
            coverage = {"head", "neck"}
    return (slot, definition) if part in coverage else (None, None)


def _profile(actor, action):
    body = actor.combat.anatomy
    if body.body_plan == "wolf":
        return "bite", "puncture", "jaws", "1d6", 4, 5
    if action == "kick":
        limb = max(("left_foot", "right_foot"), key=lambda n: body_rules.part_function(body, n))
        return "kick", "crush", limb, "1d4", 3, 3
    weapon = held_reference(actor) if action == "attack" else None
    if weapon:
        props = weapon.definition.get("properties", {})
        kind = props.get("attack_type")
        if kind not in ("cut", "puncture", "crush"):
            kind = "cut" if any(word in weapon.key for word in ("axe", "sword", "knife")) else "puncture" if any(word in weapon.key for word in ("spear", "bow", "pickaxe")) else "crush"
        return weapon.definition["name"], kind, body.weapon_hand, props.get("damage_dice", "1d4"), props.get("damage_bonus", 0)+3, 4
    limb = max(("left_hand", "right_hand"), key=lambda n: body_rules.part_function(body, n))
    return "punch", "crush", limb, "1d3", 2, 2


def attack(world, attacker, target, action="attack", target_part=None):
    if not supported(attacker) or not supported(target):
        return AttackResult(reason="unsupported_body")
    if target.physical.is_dead:
        say(world, f"{target.name} is already defeated.", attacker, target)
        return AttackResult(reason="dead_target")
    a = ensure_body(attacker, world.game_time)
    b = ensure_body(target, world.game_time)
    for actor in (attacker, target):
        body_rules.advance(actor.combat.anatomy, world.game_time)
        sync_body(world, actor)
    reason = None
    if not can_act(attacker) or target.physical.is_dead or target is attacker:
        reason = "Unable to attack."
    elif max(abs(attacker.x-target.x), abs(attacker.y-target.y)) > (
            held_reference(attacker).definition.get("properties", {}).get("attack_range", 1)
            if action == "attack" and held_reference(attacker) else 1):
        reason = "Move next to your target to attack."
    elif world.game_time < a.attack_ready_tick:
        reason = "Still recovering from the last attack."
    elif target_part is not None and target_part not in b.parts:
        reason = "That target has no such body part."
    if reason:
        if attacker is world.player:
            say(world, reason, attacker)
        return AttackResult(reason=reason)
    from tcod_compat import tcod
    for x, y in list(tcod.los.bresenham((attacker.x, attacker.y), (target.x, target.y)))[1:-1]:
        tile = world.get_tile_at(int(x), int(y))
        if tile is None or (getattr(tile, "properties", {}) or {}).get("blocks_fov"):
            return AttackResult(reason="The attack is blocked by terrain.")
    name, kind, limb, dice, bonus, recovery = _profile(attacker, action)
    function = body_rules.part_function(a, limb)
    if function < .2:
        return AttackResult(reason="The attacking limb cannot function.")
    a.attack_ready_tick = world.game_time + recovery
    a.last_attack_target = (target.x, target.y)
    b.last_attacker_id = attacker.id
    b.last_attacked_tick = world.game_time
    from simulation.systems.combat_response import witness_attack
    witness_attack(world, attacker, target)
    _npc_assault(world, attacker, target)
    attacker.facing = "east" if target.x > attacker.x else "west" if target.x < attacker.x else "south" if target.y > attacker.y else "north"
    world.emit_sound(attacker.x, attacker.y, "combat_attack", volume=10, source_entity_id=attacker.id)
    roll = random.randint(1, 20)
    skill = attacker.skills.get_level("melee", 5)
    hit = roll == 20 or (roll != 1 and roll + skill * function * functions_for(attacker)["sight"] >= 8 + functions_for(target)["movement"]*3)
    if attacker is world.player and target is not world.player and not target.physical.is_dead:
        target.combat.is_hostile_to_player = True
        if not getattr(target, "animal_type", None):
            target.add_grudge(attacker.id, "attacked_me", severity=85, current_day=world.game_time//DAY_LENGTH_TICKS, decay_days=12)
    if not hit:
        say(world, f"{attacker.name}'s {name} misses {target.name}.", attacker, target)
        _player_assault(world, attacker, target, 0)
        return AttackResult(attempted=True, reason="miss")
    if target_part is None:
        weights = target_weights(a, b)
        target_part = random.choices(list(b.parts), weights=weights, k=1)[0]
    count, faces = map(int, dice.split("d"))
    force = (sum(random.randint(1, faces) for _ in range(count)) + bonus) * function
    force *= max(.25, 1-body_rules.pain(a)*.5)
    if roll == 20:
        force *= 1.5
    slot, armor = armor_at(target, target_part)
    absorbed = 0
    if armor:
        defense = armor.get("properties", {}).get("defense_bonus", 0)
        absorbed = min(force, .75 + defense*1.8)
        if target is world.player:
            target._degrade_equipped_armor_slot(slot, world=world)
        else:
            target.degrade_equipped_item(slot, world=world)
    wound = body_rules.inflict(b, target_part, kind, force-absorbed, world.game_time, attacker.id, name)
    target.combat.last_hit_part = target_part
    if wound:
        attacker.skills.gain_experience("melee", max(1, round(force-absorbed)), default_level=5)
        new_status = {"broken_leg"} if wound.fracture and b.parts[target_part].function == "movement" else set()
        world._broadcast_combat_memory(attacker, target, name, max(1, round(force-absorbed)), new_status)
    region = target_part.replace("_", " ")
    outcome = f"{kind} wound" + (", fracture" if wound and wound.fracture else "") if wound else "no wound"
    armor_text = f"; {armor['name']} absorbs {absorbed:.1f} force" if armor else ""
    say(world, f"{attacker.name} hits {target.name}'s {region} with {name}: {outcome}{armor_text}.", attacker, target)
    # The social record type has meaning: combat_attack carries a negative
    # human-violence reputation score. Wildlife remains witnessed history,
    # but defending against a wolf must not make its rescuer a criminal.
    event_type = "wildlife_combat" if getattr(attacker, "animal_type", None) or getattr(target, "animal_type", None) else "combat_attack"
    world.log_event(event_type=event_type, description="{subject} struck {target}'s " + region + " with " + name + ": " + outcome + ".",
                    subject_id=attacker.id, target_id=target.id, location=(target.x, target.y))
    if held_reference(attacker) and action == "attack":
        if attacker is world.player:
            ref = held_reference(attacker)
            ref.current_durability = max(0, ref.current_durability-1) if ref.current_durability is not None else None
            if ref.current_durability == 0:
                attacker.equipment.weapon.clear()
                broken = "broken_tool_handle" if ref.tool_type else None
                if broken:
                    attacker.add_item(broken, 1)
                say(world, f"{name} breaks.", attacker)
        else:
            attacker.degrade_equipped_item("weapon", world=world)
    sync_body(world, target)
    _player_assault(world, attacker, target, max(1, round(force-absorbed)) if wound else 0)
    return AttackResult(True, True, target_part, force, absorbed, wound.id if wound else None)


def _npc_assault(world, attacker, target):
    if (attacker is world.player or target is world.player
            or getattr(attacker, "animal_type", None) or getattr(target, "animal_type", None)
            or attacker.schedule.current_task == "execute_political_warrant"
            or getattr(attacker, "faction_id", None) is not None
            or getattr(attacker, "enemy_faction_id", None) is not None):
        return
    world.record_crime_event(crime_kind="assault", suspect_id=attacker.id, victim_id=target.id,
        witness_ids=tuple(w.id for w in world._get_witnesses_to_action(attacker.x, attacker.y, "assault")),
        description="{subject} assaulted {target}.", location=(attacker.x, attacker.y))
    world._accrue_crime_bounty(attacker, "assault")


def _player_assault(world, attacker, target, severity):
    if attacker is not world.player or getattr(target, "animal_type", None):
        return
    # Retain the existing incident/grievance/witness pipeline for human harm.
    from simulation.systems.incidents import create_harmful_incident, record_incident_attribution
    witnesses = world._get_witnesses_to_action(target.x, target.y, "assault")
    others = [w for w in witnesses if w.id != target.id]
    if severity:
        incident = create_harmful_incident(world, attacker_id=attacker.id, target_id=target.id,
            location=(target.x, target.y), severity=severity, target_survived=not target.physical.is_dead,
            witness_ids=[w.id for w in others])
        for person, basis, confidence in [(attacker, "actor_self", 1.0), *([] if target.physical.is_dead else [(target, "victim_survived", 1.0)]),
                                          *[(w, "direct_witness", .95) for w in others]]:
            record_incident_attribution(person, incident, attacker_id=attacker.id, confidence=confidence, basis=basis)
    if witnesses:
        attacker.adjust_reputation(REP_CRIMINAL, 10)
        for witness in others:
            world._handle_witness_reaction(witness, "assault", attacker, victim=target)


def needs_wound_treatment(actor):
    body = actor.combat.anatomy
    return bool(body.body_plan and any(w.healing < .9 and
                ((w.bleeding > 0 and not w.dressed) or (w.fracture and not w.splinted)) for w in body.wounds))


def target_weights(attacker_body, target_body):
    """Surface/reach weighting; no preferred side or fixed calf target."""
    return [node.hit_weight * (1.8 if attacker_body.body_plan == "wolf"
                              and node.function in ("grip", "movement") else 1)
            for node in target_body.parts.values()]


def treat(world, healer, patient, item_key=None):
    body = ensure_body(patient, world.game_time)
    if body is None or patient.physical.is_dead or not can_act(healer) or functions_for(healer)["grip"] < .2:
        return False
    if max(abs(healer.x-patient.x), abs(healer.y-patient.y)) > 1:
        return False
    body_rules.advance(body, world.game_time)
    sync_body(world, patient)
    if patient.physical.is_dead:
        return False
    inventory = inventory_for(world, healer)
    skill = healer.skills.get_level("medicine", 8 if healer.economic.profession == "Healer" else 1)
    quality = min(1.0, .2 + skill*.04)
    if healer is patient:
        quality *= .8  # One's own injured limb is harder to reach and stabilize.
    keys = [item_key] if item_key else ["bandage", "healing_salve", "splint"]
    for key in keys:
        if key not in ("bandage", "healing_salve", "splint"):
            continue
        if inventory.get(key, 0) <= 0:
            continue
        injuries = [w for w in body.wounds if w.healing < .9 and
                    (w.fracture and not w.splinted if key == "splint" else w.bleeding > 0 and not w.dressed)]
        if not injuries:
            continue
        wound = max(injuries, key=lambda w: w.bleeding)
        if not healer.remove_item(key, 1):
            continue
        for injury in body.wounds:
            if injury.part == wound.part and key == "splint" and injury.fracture:
                injury.splinted = True
                injury.splint_quality = quality
                injury.treated_by = healer.id
        if key != "splint":
            wound.dressed = True
            wound.dressing_quality = quality
            wound.treated_by = healer.id
        healer.skills.gain_experience("medicine", 3, default_level=8 if healer.economic.profession == "Healer" else 1)
        sync_body(world, patient)
        say(world, f"{healer.name} {'splints' if key == 'splint' else 'dresses'} {patient.name}'s {wound.part.replace('_', ' ')}. Recovery still takes time.", healer, patient)
        return True
    return False


def examine(world, actor):
    body = ensure_body(actor, world.game_time)
    if body is None:
        return
    world.body_menu_target_id = actor.id
    world.body_menu_scroll = 0
    world.game_state = "BODY_MENU"


def work_progress(interaction, multiplier, base=1):
    """Fractional work survives tick boundaries instead of rounding every limp away."""
    credit = getattr(interaction, "body_work_credit", 0.0) + max(0, multiplier)*base
    progress = int(credit)
    interaction.body_work_credit = credit-progress
    return progress
