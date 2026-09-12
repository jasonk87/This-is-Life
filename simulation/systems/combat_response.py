"""Local, witnessed wildlife emergencies and active wolf combat.

Observers remember an actual attacker/victim and last-seen location. No global
hostility switch, supernatural target tracking, or generated decision text.
"""
from simulation.systems import body_combat as combat


DEFENDERS = {"Guard", "Sheriff", "Militia"}
EMERGENCY_MEMORY_TICKS = 240


def distance(a, b):
    return max(abs(a.x-b.x), abs(a.y-b.y))


def sees(world, observer, target):
    if distance(observer, target) > 20:
        return False
    # Renderer FOV caches are culled away from the player. World witnessing
    # already provides the same terrain/radius rules on and off camera.
    return world._can_witness(observer, target.x, target.y)


def remember_threat(world, observer, attacker, victim=None):
    previous = getattr(observer, "wildlife_emergency", None)
    observer.wildlife_emergency = dict(
        threat_id=attacker.id, victim_id=getattr(victim, "id", None),
        last_seen=(attacker.x, attacker.y), expires=world.game_time+EMERGENCY_MEMORY_TICKS,
    )
    if not previous or previous["threat_id"] != attacker.id:
        if victim is not None:
            observer.knowledge.long_term_memory.append(
                f"Saw {attacker.name} attack {victim.name} near ({victim.x}, {victim.y})."
            )
        if observer.economic.profession in DEFENDERS:
            combat.say(world, f"{observer.name} moves to protect {victim.name if victim else 'the village'} from {attacker.name}!", observer, attacker)
        else:
            combat.say(world, f"{observer.name} retreats from {attacker.name} and calls for help!", observer, attacker)


def raise_wildlife_alarm(world, speaker, threat, victim=None):
    """Share an observed animal threat with nearby guards who can hear/see us."""
    remember_threat(world, speaker, threat, victim)
    for listener in world.village_npcs:
        if (listener is not speaker and listener.economic.profession in DEFENDERS
                and combat.can_act(listener) and distance(speaker, listener) <= 12
                and sees(world, listener, speaker)):
            remember_threat(world, listener, threat, victim)


def witness_attack(world, attacker, victim):
    if (getattr(attacker, "animal_type", None) not in ("wolf", "dire_wolf")
            or getattr(victim, "animal_type", None)):
        return
    for observer in list(world.village_npcs):
        if not combat.can_act(observer) or getattr(observer, "animal_type", None):
            continue
        if observer is victim or (distance(observer, victim) <= 12
                                  and sees(world, observer, attacker) and sees(world, observer, victim)):
            remember_threat(world, observer, attacker, victim)


def step_away(world, actor, threat):
    occupied = {(other.x, other.y) for other in [world.player, *world.all_npcs]
                if other is not actor and not other.physical.is_dead}
    options = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            x, y = actor.x+dx, actor.y+dy
            if (x, y) in occupied or (dx == 0 and dy == 0):
                continue
            tile = world.get_tile_at(x, y)
            if not tile or not tile.passable:
                continue
            if dx and dy:
                sides = (world.get_tile_at(actor.x+dx, actor.y), world.get_tile_at(actor.x, actor.y+dy))
                if any(not side or not side.passable for side in sides):
                    continue
            separation = max(abs(x-threat.x), abs(y-threat.y))
            if separation > distance(actor, threat):
                options.append((separation, x, y))
    if not options:
        actor.schedule.current_path = []
        actor.schedule.current_destination_coords = None
        return False
    _, x, y = max(options)
    actor.schedule.current_path = [(actor.x, actor.y), (x, y)]
    actor.schedule.current_destination_coords = (x, y)
    return True


def approach(world, actor, target_x, target_y):
    # Path to an unoccupied attack position, never the victim's occupied tile.
    destination = world._find_best_adjacent_tile_for_attack(target_x, target_y, actor)
    if destination[0] is None:
        actor.schedule.current_path = []
        return False
    if actor.schedule.current_destination_coords != destination or not actor.schedule.current_path:
        path = world.calculate_path(actor.x, actor.y, *destination)
        actor.schedule.current_path = path or []
        actor.schedule.current_destination_coords = destination if path else None
    return bool(actor.schedule.current_path)


def respond_to_wildlife(world, actor):
    emergency = getattr(actor, "wildlife_emergency", None)
    if not emergency or actor.combat.is_hostile_to_player:
        return False
    threat = world.get_entity_by_id(emergency["threat_id"])
    if (threat is None or threat.physical.is_dead or world.game_time > emergency["expires"]
            or getattr(threat, "animal_type", None) not in ("wolf", "dire_wolf")):
        actor.wildlife_emergency = None
        if actor.schedule.current_task in ("protecting_from_wildlife", "escaping_wildlife"):
            actor.schedule.current_task = "idle"
            actor.schedule.current_path = []
            actor.schedule.current_destination_coords = None
        return False
    if not combat.can_act(actor):
        return True
    visible = sees(world, actor, threat)
    if visible:
        emergency["last_seen"] = (threat.x, threat.y)
        # Only a current attack renews urgency; merely seeing a resting wolf
        # must not cause villagers to abandon their lives indefinitely.
    defender = actor.economic.profession in DEFENDERS and combat.functions_for(actor)["movement"] >= .3
    if defender:
        actor.is_frightened = False
        actor.schedule.current_task = "protecting_from_wildlife"
        if visible and distance(actor, threat) <= 1:
            world.npc_attempt_attack_npc(actor, threat)
            actor.schedule.current_path = []
            actor.schedule.current_destination_coords = None
        elif visible or (actor.x, actor.y) != tuple(emergency["last_seen"]):
            approach(world, actor, *emergency["last_seen"])
        else:
            actor.schedule.current_path = []
        return True
    if visible and distance(actor, threat) < 8:
        actor.schedule.current_task = "escaping_wildlife"
        if not step_away(world, actor, threat) and distance(actor, threat) <= 1:
            # A cornered person can defend themselves; not a guaranteed rescue.
            world.npc_attempt_attack_npc(actor, threat)
        return True
    if actor.schedule.current_task == "escaping_wildlife":
        actor.schedule.current_task = "idle"
        actor.schedule.current_path = []
        actor.schedule.current_destination_coords = None
    return False


def update_wolf_combat(world, wolf):
    body = getattr(wolf.combat, "anatomy", None)
    if body is None or body.body_plan != "wolf" or not combat.can_act(wolf):
        return False
    if combat.retreat_if_injured(world, wolf):
        return True
    target = None
    if wolf.combat.is_hostile_to_player:
        target = world.player
    elif wolf.schedule.current_task in ("hunting", "wolf_combat"):
        candidate = world.get_entity_by_id(wolf.task_target_entity_id)
        if candidate is not None and not getattr(candidate, "animal_type", None):
            target = candidate
    if target is None and world.game_time-body.last_attacked_tick <= EMERGENCY_MEMORY_TICKS:
        target = world.get_entity_by_id(body.last_attacker_id)
    if target is None or target.physical.is_dead:
        return False
    recent_attacker = world.get_entity_by_id(body.last_attacker_id)
    if (recent_attacker is not None and not recent_attacker.physical.is_dead
            and world.game_time-body.last_attacked_tick <= EMERGENCY_MEMORY_TICKS
            and distance(wolf, recent_attacker) <= distance(wolf, target)
            and sees(world, wolf, recent_attacker)):
        target = recent_attacker
    if not sees(world, wolf, target):
        memory = getattr(wolf, "body_combat_pursuit", None)
        if not memory or memory["target_id"] != target.id:
            return False  # Existing predator pursuit owns earlier searches.
        if world.game_time > memory["until"]:
            wolf.body_combat_pursuit = None
            wolf.schedule.current_task = "idle"
            wolf.schedule.current_path = []
            wolf.schedule.current_destination_coords = None
            wolf.task_target_entity_id = None
            if target is world.player:
                wolf.combat.is_hostile_to_player = False
            return True
        destination = tuple(memory["last_seen"])
        wolf.schedule.current_task = "wolf_combat"
        if (wolf.x, wolf.y) == destination:
            wolf.schedule.current_path = []
        elif wolf.schedule.current_destination_coords != destination or not wolf.schedule.current_path:
            wolf.schedule.current_path = world.calculate_path(wolf.x, wolf.y, *destination) or []
            wolf.schedule.current_destination_coords = destination
        return True
    wolf.body_combat_pursuit = dict(target_id=target.id, last_seen=(target.x, target.y), until=world.game_time+60)
    wolf.combat.target_entity_id = target.id
    wolf.task_target_entity_id = target.id
    wolf.schedule.current_task = "wolf_combat"
    if distance(wolf, target) <= 1:
        combat.attack(world, wolf, target)
        wolf.schedule.current_path = []
        wolf.schedule.current_destination_coords = None
    else:
        approach(world, wolf, target.x, target.y)
    return True
