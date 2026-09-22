"""Dispatcher wiring, physical conservation and persistent household journeys."""
import pickle
from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import engine
from config import DAY_LENGTH_TICKS
from entities.social import AspirationType
from simulation.systems import economy, migration, survival
from simulation.systems.tick import run_world_tick
from tests.world_cache import fresh_world


@pytest.fixture
def world():
    engine.ENABLE_LLM_CONNECTION = engine.ENABLE_OLLAMA_CONNECTION = False
    return fresh_world(seed=451, pre_simulate=False)


def totals(world):
    stock = Counter()
    money = 0
    for entity in [*world.buildings_by_id.values(), *world.village_npcs, *world.npcs]:
        inv = world._get_trade_inventory(entity)
        if inv is not None:
            stock.update({k:v for k,v in inv.items() if k != "money"})
        money += world._get_trade_money_balance(entity)
    return stock, money


def test_actual_tick_calls_shortage_detector(world):
    village = world.villages[0]
    for b in village.buildings:
        b.building_inventory.pop("bread", None)
    village.demand["bread"] = 1000
    world.game_time += 100
    with patch.object(economy, "_update_village_economic_needs", wraps=economy._update_village_economic_needs) as detector:
        run_world_tick(world)
    assert detector.call_count >= len(world.villages)
    assert village.population_cache == len(economy.residents(world, village)) > 0
    assert any(n.target_key == "bread" and n.settlement_id == village.id for n in world.town_board.economic_needs)


def test_summary_does_not_consume_or_produce_any_inventory(world):
    before = totals(world)
    for village in world.villages:
        economy.simulate_village_economy(world, village)
    assert totals(world) == before


def test_daily_ledger_matches_physical_stocks_and_survives_refresh(world):
    world.game_time += DAY_LENGTH_TICKS
    world._update_abstract_simulation()
    # Construction/trade/hunting can legitimately change stock; no ledger-only
    # result may disappear when the next economy refresh runs.
    before = {v.id: dict(v.supply) for v in world.villages}
    world._update_economy()
    assert before == {v.id: dict(v.supply) for v in world.villages}


def test_empty_inventory_means_no_phantom_meal(world):
    npc = world.village_npcs[0]
    npc.economic.npc_inventory.clear()
    village = world._get_village_for_npc(npc)
    for building in village.buildings:
        building.building_inventory.clear()
    npc.physical.hunger, npc.physical.thirst = 90, 0
    npc.metabolism_last_tick = world.game_time
    before = totals(world)
    economy.provide_sleeping_sustenance(world, npc)
    assert npc.physical.hunger == 90
    assert totals(world) == before


def test_sleeping_meal_consumes_real_food_and_pays_the_seller(world):
    npc = world.village_npcs[0]
    npc.economic.npc_inventory.clear()
    npc.economic.money = 100
    npc.physical.hunger, npc.physical.thirst = 90, 0
    npc.metabolism_last_tick = world.game_time
    village = world._get_village_for_npc(npc)
    for building in village.buildings:
        for key in economy.FOODS:
            building.building_inventory.pop(key, None)
    seller = next(b for b in village.buildings if b.building_type == "bakery")
    seller.building_inventory["bread"] = 1
    money = world._get_trade_money_balance(seller)
    before = totals(world)
    economy.provide_sleeping_sustenance(world, npc)
    after = totals(world)
    assert npc.physical.hunger == 55
    assert seller.building_inventory.get("bread", 0) == 0
    assert world._get_trade_money_balance(seller) > money
    assert after[1] == before[1]
    assert after[0]["bread"] == before[0]["bread"]-1


def test_shared_metabolic_clock_does_not_double_count(world):
    npc = world.village_npcs[0]
    npc.metabolism_last_tick = 0
    npc.physical.hunger = npc.physical.thirst = 0
    world.game_time = DAY_LENGTH_TICKS // 2
    survival.advance_npc_metabolism(world, npc)
    expected = (npc.physical.hunger, npc.physical.thirst)
    survival.advance_npc_metabolism(world, npc)
    assert expected == (25, 49)
    assert expected == (npc.physical.hunger, npc.physical.thirst)


def test_caravan_conserves_items_and_currency(world):
    source, dest = world.villages[:2]
    seller = next(b for b in source.buildings if b.building_type == "general_store")
    buyer = next(b for b in dest.buildings if b.building_type == "general_store")
    seller.building_inventory["arrow_shaft"] = 40
    for b in dest.buildings:
        b.building_inventory.pop("arrow_shaft", None)
    buyer.building_inventory["money"] = 500
    identities = {id(r) for r in seller.building_inventory.iter_item_references("arrow_shaft")}
    before = totals(world)
    assert economy.trade_settlement_surplus(world, source, dest) > 0
    assert totals(world) == before
    assert buyer.building_inventory.get("arrow_shaft", 0) > 0
    assert {id(r) for r in buyer.building_inventory.iter_item_references("arrow_shaft")} <= identities


def test_no_detached_salary_or_double_daily_payment(world):
    npc = next(n for n in world.village_npcs if n.schedule.work_building_id)
    employer = world.buildings_by_id[npc.schedule.work_building_id]
    npc.is_sleeping = True
    npc.economic.daily_wage = 24
    npc.schedule.last_paid_day = -1
    npc.physical.hunger = npc.physical.thirst = 0
    npc.metabolism_last_tick = DAY_LENGTH_TICKS//2
    world.game_time = DAY_LENGTH_TICKS//2
    world.last_abstract_simulation_hour = -1
    employer.building_inventory["money"] = 1000
    with patch.object(world, "_is_building_active", return_value=False):
        before = npc.economic.money
        world.process_abstract_simulation()
    hourly = npc.economic.money-before
    assert hourly > 0
    with patch.object(world, "village_npcs", [npc]):
        world._pay_daily_company_wages()
        assert npc.economic.money-before == 24
        world._pay_daily_company_wages()
        assert npc.economic.money-before == 24
    npc.schedule.work_building_id = None
    npc.physical.hunger = npc.physical.thirst = 0
    world.game_time += DAY_LENGTH_TICKS//24
    before = npc.economic.money
    with patch.object(world, "_run_abstract_labour_market", return_value=0):
        world.process_abstract_simulation()
    assert npc.economic.money == before


@pytest.mark.parametrize("funded,active", [(True, False), (False, False), (True, True)])
def test_remote_inputs_require_real_stock_payment_and_dormant_supplier(world, funded, active):
    npc = world.village_npcs[0]
    village = world._get_npc_settlement(npc)
    workplace = next(b for b in village.buildings if b.building_type == "bakery")
    supplier = next(b for b in village.buildings if b.building_type == "general_store")
    npc.economic.profession = "Baker"
    for b in village.buildings:
        b.building_inventory.pop("flour", None)
    supplier.building_inventory["flour"] = 1
    ref = supplier.building_inventory.get_item_reference("flour")
    workplace.owner_id = None  # Public workplaces are not exempt from payment.
    workplace.building_inventory["money"] = 100 if funded else 0
    before = totals(world)
    seller_money = world._get_trade_money_balance(supplier)
    with patch.object(world, "_is_building_active", side_effect=lambda b: active and b is supplier):
        moved = economy.procure_worker_inputs(world, npc, workplace)
    assert totals(world) == before
    if funded and not active:
        assert moved == 1
        assert workplace.building_inventory.get_item_reference("flour") is ref
        assert world._get_trade_money_balance(supplier) > seller_money
    else:
        assert moved == 0
        assert supplier.building_inventory.get_item_reference("flour") is ref


def test_hourly_input_payment_is_not_overwritten_by_payroll(world):
    npc = world.village_npcs[0]
    village = world._get_npc_settlement(npc)
    workplace = next(b for b in village.buildings if b.building_type == "bakery")
    supplier = next(b for b in village.buildings if b.building_type == "general_store")
    npc.schedule.work_building_id = workplace.id
    npc.economic.profession = "Baker"
    npc.economic.daily_wage = 24
    npc.schedule.last_paid_day = -1
    npc.is_sleeping = True
    npc.physical.hunger = npc.physical.thirst = 0
    world.game_time = DAY_LENGTH_TICKS // 2
    npc.metabolism_last_tick = world.game_time
    world.last_abstract_simulation_hour = -1
    for b in village.buildings:
        b.building_inventory.pop("flour", None)
    supplier.building_inventory["flour"] = 1
    workplace.building_inventory["money"] = 100
    money = sum(world._get_trade_money_balance(e) for e in [npc, workplace, supplier])
    bread = workplace.building_inventory.get("bread", 0)
    with patch.object(world, "village_npcs", [npc]), patch.object(world, "npcs", []), \
            patch.object(world, "_is_building_active", return_value=False):
        world.process_abstract_simulation()
    assert workplace.building_inventory.get("bread", 0) == bread+1
    assert supplier.building_inventory.get("flour", 0) == 0
    assert sum(world._get_trade_money_balance(e) for e in [npc, workplace, supplier]) == money


def prepared_household(world):
    leader = next(n for n in world.village_npcs if n.age >= 18 and len(world._get_family_migration_unit(n)) >= 2)
    origin = world._get_village_for_npc(leader)
    destination = next(v for v in world.villages if v is not origin)
    group = world._get_family_migration_unit(leader)
    home = next(b for b in destination.buildings if b.category == "residential")
    home.housing_capacity = len(home.residents)+len(group)
    job = next(b for b in destination.buildings if b.building_type == "bakery")
    job.max_workers = world._count_active_workers_for_building(job)+1
    job.building_inventory["money"] = 1000
    task = world.town_board.post_employment(job.id, "Baker", leader.economic.daily_wage+50)
    leader.aspiration.aspiration_type = AspirationType.WEALTH
    leader.knowledge.known_memories.clear()
    memory = world._create_job_opportunity_memory(task, destination)
    world.record_memory_event(leader, memory)
    return leader, group, origin, destination, home, job, task, memory


def test_stale_job_and_expired_memory_do_not_start_a_move(world):
    leader, group, origin, dest, home, job, task, memory = prepared_household(world)
    assert migration.find_destination(world, leader, origin)[0] is dest
    world.town_board.remove_employment_task(task.id)
    assert migration.find_destination(world, leader, origin) == (None, None)
    assert not world._start_family_migration(leader, dest, memory.metadata)
    assert all(not n.travel.is_traveling for n in group)
    world.town_board.employment_tasks.append(task)
    world.game_time += migration.MEMORY_LIFETIME+1
    assert migration.find_destination(world, leader, origin) == (None, None)


def test_household_requires_one_home_not_scattered_vacancies(world):
    leader, group, origin, dest, home, job, task, memory = prepared_household(world)
    for home in dest.buildings:
        if home.category == "residential":
            home.housing_capacity = len(home.residents)+1
    assert not world._start_family_migration(leader, dest, memory.metadata)
    assert all(n.schedule.home_building_id for n in group)
    assert task.status == "open"


@pytest.mark.parametrize("task", ["bounty_escort", "following_player", "hauling_to_delivery_destination", "combat_action_attack_player"])
def test_household_move_does_not_cancel_existing_commitments(world, task):
    leader, group, origin, dest, home, job, offer, memory = prepared_household(world)
    group[-1].schedule.current_task = task
    assert not world._start_family_migration(leader, dest, memory.metadata)
    assert group[-1].schedule.current_task == task
    assert offer.status == "open"
    assert all(not n.travel.is_traveling for n in group)


def test_move_reserves_job_and_home_without_paying_travelers(world):
    leader, group, origin, dest, home, job, task, memory = prepared_household(world)
    assert world._start_family_migration(leader, dest, memory.metadata)
    assert task.status == "claimed" and task.assigned_entity_id == leader.id
    assert migration.home_space(world, home) == 0
    assert world._count_active_workers_for_building(job) == job.max_workers
    outsider = next(n for n in world.village_npcs if n not in group)
    assert not world._assign_job(outsider, job)
    assert all(n.economic.daily_wage == 0 and n.schedule.work_building_id is None for n in group)
    assert not world._assign_job(leader, job)
    assert not world._complete_travel_arrival(leader)  # Cannot teleport via the arrival helper.


def test_household_walks_arrives_and_survives_save_load(world):
    leader, group, origin, dest, home, job, task, memory = prepared_household(world)
    ids = [n.id for n in group]
    clothes = {n.id: dict(n.economic.npc_inventory) for n in group}
    assert world._start_family_migration(leader, dest, memory.metadata)
    world = pickle.loads(pickle.dumps(world))
    leader = world.get_entity_by_id(leader.id)
    # Exercise both dormant catch-up and normal active collision/door movement.
    for tick in range(1200):
        world.game_time += 1
        migration.advance(world)
        for nid in ids:
            member = world.get_entity_by_id(nid)
            if member.travel.is_traveling and not member.is_sleeping:
                migration.prepare_active(world, member)
        world._update_npc_movement()
        if not leader.travel.is_traveling:
            break
    assert not leader.travel.is_traveling, [(world.get_entity_by_id(i).x, world.get_entity_by_id(i).y) for i in ids]
    assert leader.schedule.work_building_id == job.id
    assert leader.travel.status == "established"
    for nid in ids:
        member = world.get_entity_by_id(nid)
        assert member.schedule.home_building_id == home.id
        assert all(member.economic.npc_inventory.get(k,0) >= q for k,q in clothes[nid].items())
    restored = pickle.loads(pickle.dumps(world))
    assert restored.get_entity_by_id(leader.id).schedule.work_building_id == job.id


def test_destroyed_destination_releases_reservations_not_people(world):
    leader, group, origin, dest, home, job, task, memory = prepared_household(world)
    assert world._start_family_migration(leader, dest, memory.metadata)
    del world.buildings_by_id[home.id]
    assert not migration.arrive(world, leader)
    assert task.status == "open"
    assert all(world.get_entity_by_id(n.id) is n and not n.travel.is_traveling for n in group)


def test_child_keeps_family_role_and_identity_when_household_moves(world):
    leader, group, origin, dest, home, job, task, memory = prepared_household(world)
    child = engine.NPC(leader.x, leader.y, name="Household Child")
    child.age = 10
    child.social.family_ties["father_id"] = leader.id
    child.schedule.home_building_id = leader.schedule.home_building_id
    child.schedule.current_task = "idle"
    world._set_entity_profession(child, "Child", reason="test_child")
    world.village_npcs.append(child)
    world.buildings_by_id[child.schedule.home_building_id].residents.append(child)
    world._mark_entity_positions_dirty()
    home.housing_capacity += 1
    assert world._start_family_migration(leader, dest, memory.metadata)
    assert child.travel.group_leader_id == leader.id
    assert child.age == 10 and child.economic.profession == "Child"
    restored = pickle.loads(pickle.dumps(world))
    saved_child = restored.get_entity_by_id(child.id)
    assert saved_child.economic.profession == "Child"
    assert saved_child.social.family_ties["father_id"] == leader.id


def test_lost_job_does_not_release_another_persons_claim(world):
    leader, group, origin, dest, home, job, task, memory = prepared_household(world)
    assert world._start_family_migration(leader, dest, memory.metadata)
    outsider = next(n for n in world.village_npcs if n not in group)
    task.assigned_entity_id = outsider.id
    # Isolate arrival validation; walking and save/load have separate coverage.
    for member in group:
        world._update_entity_position(member, *member.travel.destination_coords)
    assert migration.arrive(world, leader)
    assert task.assigned_entity_id == outsider.id and task.status == "claimed"
    assert leader.travel.status == "arrived_seeking_work"
    assert leader.schedule.work_building_id is None


def test_merchant_travel_is_not_replaced_with_household_movement(world):
    merchant = next(n for n in world.npcs if n.economic.profession == "Traveling Merchant")
    merchant.travel.is_traveling = True
    merchant.schedule.current_task = "traveling_to_village"
    assert not migration.prepare_active(world, merchant)
    assert merchant.schedule.current_task == "traveling_to_village"


def test_merchant_learns_local_opportunities_and_carries_them(world):
    merchant = next(n for n in world.npcs if n.economic.profession == "Traveling Merchant")
    leader, group, origin, dest, home, job, task, memory = prepared_household(world)
    migration.learn_local_opportunities(world, merchant, dest)
    assert any(m.event_type == "job_opportunity" and m.metadata.get("settlement_id") == dest.id
               for m in merchant.knowledge.known_memories.values())
    for _ in range(10):
        world.share_abstract_rumors_with_settlement(merchant, origin)
    assert any(m.event_type == "job_opportunity" and m.metadata.get("settlement_id") == dest.id
               for n in world._get_settlement_residents(origin) for m in n.knowledge.known_memories.values())


def test_missing_industry_is_detected_from_normal_summary(world):
    village = world.villages[0]
    village.buildings = [b for b in village.buildings if b.building_type != "bakery"]
    for npc in world.village_npcs:
        b = world.buildings_by_id.get(npc.schedule.work_building_id)
        if b and b.settlement_id == village.id and b.building_type == "bakery":
            npc.schedule.work_building_id = None
    economy.simulate_village_economy(world, village)
    assert any(n.type == "service" and n.target_key == "Baker" and n.settlement_id == village.id
               for n in world.town_board.economic_needs)


@pytest.mark.parametrize("state", ["available", "employed", "distant", "sleeping", "traveling", "jailed", "dead",
    "bounty_escort", "following_player", "hauling_to_delivery_destination", "combat_action_attack_player",
    "other_haul", "other_construction", "own_haul", "own_construction"])
@pytest.mark.parametrize("materials", [False, True])
def test_construction_dispatch_respects_local_availability_and_existing_commitments(world, state, materials):
    actor = world.village_npcs[0]
    settlement = world._get_village_for_npc(actor)
    actor.is_sleeping = False
    actor.economic.profession = "Laborer"
    actor.schedule.work_building_id = None
    actor.schedule.current_task = "idle"
    actor.task_context = None
    if state == "employed":
        actor.economic.profession = "Baker"
        actor.schedule.work_building_id = settlement.buildings[0].id
    elif state == "distant":
        settlement = next(v for v in world.villages if v is not settlement)
    elif state == "sleeping":
        actor.is_sleeping = True
    elif state == "traveling":
        actor.travel.is_traveling = True
    elif state == "jailed":
        actor.schedule.is_jailed = True
    elif state == "dead":
        actor.physical.is_dead = True
    elif state in {"other_haul", "other_construction", "own_haul", "own_construction"}:
        actor.task_context = "hauling" if state.endswith("haul") else "construction"
        actor.task_context_data = {"blueprint_id": "site" if state.startswith("own") else "another_site"}
    elif state != "available":
        actor.schedule.current_task = state
    before = (actor.schedule.current_task, actor.task_context, actor.schedule.work_building_id)
    component = SimpleNamespace(id="wall", status="pending", has_all_materials=lambda: materials)
    blueprint = SimpleNamespace(id="site", settlement_id=settlement.id, components=[component])
    task = engine.ProductionTask(task_type="build_component", metadata={"blueprint_id": "site", "component_id": "wall"})
    with patch.object(world, "village_npcs", [actor]), patch.dict(world.blueprints_by_id, {"site": blueprint}), \
            patch.object(world, "_assign_haul_task_to_npc") as assign_haul, \
            patch.object(world, "_assign_construction_task_to_npc") as assign_build, \
            patch.object(world, "_handle_npc_hauling_task") as handle_haul, \
            patch.object(world, "_handle_npc_construction_task") as handle_build, \
            patch.object(world, "_mark_production_task_progress"), patch.object(world, "_mark_production_task_blocked"):
        world._advance_build_component_task(task)
    assert assign_haul.call_count == int(state == "available" and not materials)
    assert assign_build.call_count == int(state == "available" and materials)
    assert handle_haul.call_count == int(state == "own_haul")
    assert handle_build.call_count == int(state == "own_construction")
    if state == "available":
        (assign_build if materials else assign_haul).assert_called_once_with(actor, blueprint_id="site")
    assert (actor.schedule.current_task, actor.task_context, actor.schedule.work_building_id) == before


@pytest.mark.parametrize("task", ["idle", "bounty_escort", "following_player", "combat_action_attack_player", "traveling_between_settlements"])
def test_free_time_hauling_does_not_steal_arriving_workers_or_busy_unemployed_people(world, task):
    from entities.human_behaviors import HaulingBehavior
    actor = world.village_npcs[0]
    actor.schedule.current_task = task
    actor.schedule.current_path = []
    actor.economic.profession = "Unemployed"
    actor.schedule.work_building_id = None
    if task == "idle":
        actor.economic.profession = "Blacksmith"
        actor.schedule.work_building_id = world.villages[0].buildings[0].id
        actor.current_sub_task = "fetch_ore"
        actor.sub_task_target_coords = (actor.x + 1, actor.y)
        world.game_time = DAY_LENGTH_TICKS // 2
    with patch.object(world, "_assign_haul_task_to_npc") as haul, \
            patch.object(world, "_assign_delivery_task_to_npc") as deliver, \
            patch.object(world, "_assign_construction_task_to_npc") as build:
        assert not HaulingBehavior().take_turn(actor, world)
        haul.assert_not_called()
        deliver.assert_not_called()
        build.assert_not_called()
    assert actor.schedule.current_task == task


def test_truly_free_worker_can_still_volunteer_for_hauling(world):
    from entities.human_behaviors import HaulingBehavior
    actor = world.village_npcs[0]
    actor.schedule.current_task = "idle"
    actor.schedule.current_path = []
    actor.current_sub_task = "fetch_ore"
    actor.sub_task_target_coords = (actor.x + 8, actor.y)
    world.game_time = DAY_LENGTH_TICKS // 2
    with patch.object(world, "_assign_haul_task_to_npc", return_value=True) as haul, \
            patch.object(world, "_assign_delivery_task_to_npc", return_value=False):
        assert HaulingBehavior().take_turn(actor, world)
        haul.assert_called_once_with(actor)
