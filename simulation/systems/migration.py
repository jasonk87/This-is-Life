"""Persistent households moving between real homes, jobs and map positions."""
import math

from config import DAY_LENGTH_TICKS
from entities.social import AspirationType, TravelComponent
from simulation.systems.body_combat import can_act, functions_for

MEMORY_LIFETIME = 7 * DAY_LENGTH_TICKS


def capacity(home):
    return getattr(home, "housing_capacity", max(2, (home.width-2)*(home.height-2)//8))


def home_space(world, home, exclude_leader=None):
    occupants = {p.id for p in home.residents if not p.physical.is_dead}
    reserved = {p.id for p in world.village_npcs if p.travel.is_traveling
                and p.travel.group_leader_id != exclude_leader
                and p.travel.reserved_home_id == home.id and not p.physical.is_dead}
    return max(0, capacity(home)-len(occupants | reserved))


def available_home(world, village, count, exclude_leader=None):
    return next((b for b in village.buildings if b.category == "residential"
                 and home_space(world, b, exclude_leader) >= count), None)


def reserved_workers(world, building):
    return sum(p.travel.is_traveling and p.travel.group_leader_id == p.id
               and p.travel.reserved_work_id == building.id and not p.physical.is_dead
               for p in world.village_npcs)


def valid_job(world, task, village, actor=None):
    if task is None or task.daily_wage <= 0:
        return False
    if task.status != "open" and not (actor and task.status == "claimed" and task.assigned_entity_id == actor.id):
        return False
    building = world.buildings_by_id.get(task.target_building_id)
    if not building or building.settlement_id != village.id:
        return False
    own_reservation = int(bool(actor and actor.travel.is_traveling and actor.travel.reserved_work_id == building.id))
    return (world._count_active_workers_for_building(building)-own_reservation < building.max_workers
            and world._get_trade_money_balance(building) >= task.daily_wage)


def find_destination(world, npc, current):
    if npc.travel.is_traveling or npc.age < 18 or world.game_time < getattr(npc, "migration_retry_tick", 0):
        return None, None
    group = world._get_family_migration_unit(npc)
    candidates = []
    for memory in npc.knowledge.known_memories.values():
        if not 0 <= world.game_time-memory.timestamp <= MEMORY_LIFETIME:
            continue
        village = world.get_settlement_by_id(memory.metadata.get("settlement_id"))
        if village is None or village is current or (current and village.id in current.at_war_with):
            continue
        if available_home(world, village, len(group)) is None:
            continue
        score = None
        if npc.aspiration.aspiration_type == AspirationType.WEALTH and memory.event_type == "job_opportunity":
            task = world.town_board.get_employment_task(memory.metadata.get("employment_task_id"))
            if valid_job(world, task, village) and task.daily_wage > npc.economic.daily_wage:
                score = task.daily_wage-npc.economic.daily_wage
        elif npc.aspiration.aspiration_type == AspirationType.POWER and memory.event_type == "office_opening":
            if village.local_offices.get(memory.metadata.get("office_name"), "unknown") is None:
                score = memory.importance_score
        elif npc.aspiration.aspiration_type == AspirationType.PEACE and memory.event_type == "tax_climate":
            if current and village.tax_rate < current.tax_rate:
                score = current.tax_rate-village.tax_rate
        if score is not None:
            candidates.append((score, memory.timestamp, village, memory.metadata))
    if not candidates:
        return None, None
    _, _, village, metadata = max(candidates, key=lambda c: (c[0], c[1]))
    return village, metadata


def learn_local_opportunities(world, traveler, village):
    """Read the current local board on arrival; retain news brought from elsewhere."""
    world._sync_village_employment_tasks(village)
    world._seed_settlement_macro_knowledge(village)
    seen = set()
    for memory in sorted(village.noticeboard_rumors.values(), key=lambda m: m.timestamp, reverse=True):
        if not 0 <= world.game_time-memory.timestamp <= MEMORY_LIFETIME:
            continue
        if memory.metadata.get("settlement_id") != village.id:
            continue
        key = (memory.event_type, memory.metadata.get("employment_task_id"), memory.metadata.get("office_name"))
        if key in seen:
            continue
        if memory.event_type == "job_opportunity" and not valid_job(world, world.town_board.get_employment_task(key[1]), village):
            continue
        world.record_memory_event(traveler, memory)
        seen.add(key)
        if len(seen) >= 6:
            break


def _targets(world, home, group):
    taken, result = set(), []
    for member in group:
        candidates = [(x,y) for y in range(home.global_origin_y+1, home.global_origin_y+home.height-1)
                      for x in range(home.global_origin_x+1, home.global_origin_x+home.width-1)
                      if (x,y) not in taken and (tile := world.get_tile_at(x,y)) and tile.passable]
        candidates.sort(key=lambda xy: abs(xy[0]-home.global_center_x)+abs(xy[1]-home.global_center_y))
        found = None
        for target in candidates:
            path = world.calculate_path(member.x, member.y, *target)
            if path:
                found = (target, path)
                break
        if found is None:
            return None
        taken.add(found[0])
        result.append(found)
    return result


def start(world, leader, destination, metadata=None):
    if leader is None or destination is None or leader.travel.is_traveling:
        return False
    origin = world._get_village_for_npc(leader)
    group = world._get_family_migration_unit(leader)
    if origin is destination or not group or any(p.travel.is_traveling or not can_act(p)
            or p.schedule.is_jailed or p.schedule.current_task not in world.ROUTINE_SETTLE_TASKS
            or world._get_village_for_npc(p) is not origin for p in group):
        return False
    home = available_home(world, destination, len(group))
    task_id = (metadata or {}).get("employment_task_id")
    task = world.town_board.get_employment_task(task_id)
    if home is None or (task_id and not valid_job(world, task, destination)):
        leader.migration_retry_tick = world.game_time + DAY_LENGTH_TICKS
        return False
    targets = _targets(world, home, group)
    if not targets:
        leader.migration_retry_tick = world.game_time + DAY_LENGTH_TICKS
        return False
    if task and not world.town_board.claim_employment_task(task, leader.id):
        return False
    group_ids = [p.id for p in group]
    for member, (target, route) in zip(group, targets):
        old_home = member.schedule.home_building_id
        old_work = member.schedule.work_building_id
        world._remove_npc_from_settlement_membership(member, world._get_village_for_npc(member))
        member.economic.daily_wage = 0
        # A move ends adult employment; it does not turn a child into a job
        # seeker or discard their age-specific family/school routines.
        if member.age >= 18:
            world._set_entity_profession(member, "Unemployed", reason="family_migration")
        member.travel = TravelComponent(is_traveling=True, origin_settlement_id=origin.id if origin else None,
            destination_settlement_id=destination.id, destination_coords=target,
            eta_days=max(1, math.ceil(len(route)/DAY_LENGTH_TICKS)), group_leader_id=leader.id,
            group_member_ids=group_ids, target_employment_task_id=task_id if member is leader else None,
            reserved_home_id=home.id, reserved_work_id=task.target_building_id if task and member is leader else None,
            original_home_id=old_home, original_work_id=old_work, route=list(route),
            last_progress_tick=world.game_time, departed_tick=world.game_time, status="traveling")
        member.schedule.current_task = "traveling_between_settlements"
        member.schedule.current_path = list(route)
        member.schedule.current_destination_coords = target
        member.aspiration.target_settlement_id = destination.id
    world.record_migration_event(npc=leader, migration_kind="migration_departed", description="{subject}'s household set out for another settlement.", location=(leader.x,leader.y))
    return True


def cancel(world, leader, reason):
    """Release reservations without deleting people, belongings or their history."""
    group_id = leader.travel.group_leader_id or leader.id
    group = [p for p in world.village_npcs if p.travel.group_leader_id == group_id and p.travel.is_traveling]
    for member in group:
        task_id = member.travel.target_employment_task_id
        task = world.town_board.get_employment_task(task_id)
        if task and task.assigned_entity_id == member.id:
            world.town_board.release_employment_task(task_id)
        old_home = world.buildings_by_id.get(member.travel.original_home_id)
        if old_home and home_space(world, old_home, leader.id) > 0 and not member.physical.is_dead:
            old_home.residents.append(member)
            member.schedule.home_building_id = old_home.id
        member.travel.is_traveling = False
        member.travel.status = "interrupted"
        member.travel.failure_reason = reason
        member.schedule.current_task = "idle"
        member.schedule.current_path = []
        member.schedule.current_destination_coords = None
        member.migration_retry_tick = world.game_time + DAY_LENGTH_TICKS
    if group:
        world.record_migration_event(npc=leader, migration_kind="migration_interrupted", description="{subject}'s household could not complete its move: " + reason + ".", location=(leader.x,leader.y))


def arrive(world, leader):
    if not leader.travel.is_traveling:
        return False
    group = [p for p in world.village_npcs if p.travel.group_leader_id == leader.id and p.travel.is_traveling]
    home = world.buildings_by_id.get(leader.travel.reserved_home_id)
    destination = world.get_settlement_by_id(leader.travel.destination_settlement_id)
    if not home or destination is None or home_space(world, home, leader.id) < len(group):
        cancel(world, leader, "destination housing no longer available")
        return False
    if any(not home.contains_global_coords(p.x,p.y) for p in group):
        return False  # Arrival is a physical transition, never a teleport.
    task = world.town_board.get_employment_task(leader.travel.target_employment_task_id)
    for member in group:
        if member not in home.residents:
            home.residents.append(member)
        member.schedule.home_building_id = home.id
        member.travel.is_traveling = False
        member.travel.eta_days = 0
        member.travel.status = "arrived"
        member.schedule.current_task = "idle"
        member.schedule.current_path = []
        member.schedule.current_destination_coords = None
        member.migration_retry_tick = world.game_time + 3*DAY_LENGTH_TICKS
    hired = bool(task and valid_job(world, task, destination, leader) and world._hire_npc_from_employment_task(leader, task))
    if task and not hired and task.assigned_entity_id == leader.id:
        world.town_board.release_employment_task(task.id)
    for member in group:
        member.travel.status = "established" if hired else "arrived_seeking_work"
    world.record_migration_event(npc=leader, migration_kind="migration_arrived", description="{subject}'s household arrived and settled into a shared home.", location=(leader.x,leader.y))
    if hired:
        world.record_migration_event(npc=leader, migration_kind="migration_established", description="{subject} started work after the household's move.", location=(leader.x,leader.y))
    world.share_abstract_rumors_with_settlement(leader, destination)
    learn_local_opportunities(world, leader, destination)
    return True


def prepare_active(world, npc):
    """Use the ordinary collision/door/body-aware movement for visible journeys."""
    travel = npc.travel
    if not travel.is_traveling or travel.group_leader_id is None:
        return False
    if not world._is_entity_active(npc):
        world.sleep_entity(npc)
        return True
    travel.last_progress_tick = world.game_time
    npc.schedule.current_task = "traveling_between_settlements"
    if not npc.schedule.current_path or npc.schedule.current_path[-1] != travel.destination_coords:
        npc.schedule.current_path = world.calculate_path(npc.x, npc.y, *travel.destination_coords)
    npc.schedule.current_destination_coords = travel.destination_coords
    return True


def advance(world):
    travelers = [p for p in world.village_npcs if p.travel.is_traveling]
    for npc in travelers:
        if not npc.travel.is_traveling:
            continue  # An earlier household member may have canceled this trip.
        leader = world.get_entity_by_id(npc.travel.group_leader_id)
        if leader is None or leader.physical.is_dead:
            cancel(world, leader or npc, "household leader unavailable")
            continue
        if npc.physical.is_dead:
            cancel(world, leader, "a household member died during the journey")
            continue
        travel = npc.travel
        if not npc.is_sleeping:
            continue
        elapsed = max(0, world.game_time-travel.last_progress_tick)
        travel.last_progress_tick = world.game_time
        if not can_act(npc):
            continue
        path = npc.schedule.current_path
        if not path or path[0] != (npc.x,npc.y) or path[-1] != travel.destination_coords:
            path = world.calculate_path(npc.x,npc.y,*travel.destination_coords)
        speed = max(0, getattr(npc,"speed",1))*functions_for(npc)["movement"]
        credit = travel.movement_credit + elapsed*speed
        budget = min(512, int(credit))
        travel.movement_credit = credit-int(credit)
        for _ in range(budget):
            if len(path) < 2:
                break
            x,y = path[1]
            tile = world.get_tile_at(x,y)
            if tile and not tile.passable and tile.properties.get("is_door"):
                world.npc_toggle_door(npc,x,y)
                continue
            if not tile or not tile.passable:
                path = []
                break
            world._update_entity_position(npc,x,y)
            path.pop(0)
            if world._is_entity_active(npc):
                world.wake_entity(npc)
                break  # No abstract skipping across the player's visible area.
        npc.schedule.current_path = path
        npc.schedule.current_destination_coords = travel.destination_coords
        travel.route = list(path)
        travel.eta_days = max(1, math.ceil(len(path)/max(.01,speed)/DAY_LENGTH_TICKS))
    for leader in travelers:
        if leader.travel.is_traveling and leader.travel.group_leader_id == leader.id:
            world._complete_travel_arrival(leader)
