"""Settlement jurisdiction and real player entry points; no LLM services."""
import pickle
from types import SimpleNamespace
import pytest
import main
import engine
from tests.world_cache import fresh_world
from simulation.systems import settlements as civic, bounty_hunting as bounty


@pytest.fixture
def world():
    engine.ENABLE_LLM_CONNECTION = engine.ENABLE_OLLAMA_CONNECTION = False
    return fresh_world(seed=451, pre_simulate=False)


def key(sym):
    return SimpleNamespace(sym=sym)


def choose_notice(world, notice_id):
    world.open_noticeboard_menu()
    world.noticeboard_menu_context["selected_task_index"] = world.noticeboard_menu_context["task_ids"].index(notice_id)
    main.handle_noticeboard_menu_input(key(main.tcod.event.KeySym.RETURN), world)


def test_every_village_has_distinct_named_local_government(world):
    villages = civic.villages(world)
    assert len({v.name for v in villages}) == len(villages) >= 2
    for village in villages:
        with civic.scope(world, village):
            assert world.politics is village.politics
            assert world.get_town_hall_building() in village.buildings
            local_ids = {n.id for n in civic.residents(world)}
            if civic.player_is_citizen(world):
                local_ids.add(world.player.id)
            for name, office in village.politics.offices.items():
                assert office.holder_id in local_ids
                assert village.local_offices[name] == office.holder_id
    for a in villages:
        for b in villages:
            if a is not b:
                assert not set(a.local_offices.values()) & set(b.local_offices.values())


def test_tax_collection_does_not_touch_other_settlement(world):
    local = civic.current(world)
    remote = next(v for v in civic.villages(world) if v is not local)
    people = [n for n in world.village_npcs if world._get_npc_settlement(n) is remote]
    before = [(n.id, n.economic.money) for n in people]
    local.tax_rate = .25
    assert world.politics.tax_rate == .25
    world._collect_daily_city_taxes(world.get_town_hall_building())
    assert before == [(n.id, n.economic.money) for n in people]
    assert remote.tax_rate == .1


def test_player_wins_home_election_but_cannot_govern_visited_town(world):
    home = civic.current(world)
    world.player.social.fame = 10000
    world.game_time = engine.DAY_LENGTH_TICKS * engine.ELECTION_TERM_DAYS + engine.DAILY_GOVERNANCE_TICK_OFFSET
    world._run_daily_governance()
    assert home.local_offices["Mayor"] == world.player.id
    assert world.adjust_city_tax_rate(.02)
    assert home.tax_rate == .12
    other = next(v for v in civic.villages(world) if v is not home)
    world.player.x, world.player.y = world._get_village_anchor_coords(other)
    assert not world.player_has_governance_access()
    assert not world.adjust_city_tax_rate(.02)
    assert other.tax_rate == .1


def test_save_in_countryside_does_not_replace_local_government(world):
    local = civic.current(world)
    local.tax_rate = .27
    saved_holder = local.local_offices["Mayor"]
    world.player.x, world.player.y = 0, 0
    _ = world.politics
    restored = pickle.loads(pickle.dumps(world))
    village = next(v for v in civic.villages(restored) if v.id == local.id)
    assert village.tax_rate == .27
    assert village.local_offices["Mayor"] == saved_holder


def test_player_custody_closes_warrants_in_every_jurisdiction(world):
    from simulation.world_model import PoliticalWarrant
    villages = civic.villages(world)
    for village in villages:
        village.politics.active_warrants.append(PoliticalWarrant("arrest", world.player.id, None, 10, 0))
    world._update_political_warrants()
    assert all(v.politics.active_warrants for v in villages)
    world.player.state.is_jailed = True
    world._update_political_warrants()
    assert all(not v.politics.active_warrants for v in villages)


def test_legacy_records_migrate_once(world):
    village = civic.current(world)
    tracker = village.politics
    tracker.tax_rate = .19
    world.__dict__["politics"] = tracker
    world.__dict__.pop("settlement_governments_migrated", None)
    civic.ensure(world)
    civic.ensure(world)
    assert village.politics is tracker
    legacy = object.__new__(engine.Village)
    legacy.__setstate__({"tax_rate": .22, "local_offices": {"Mayor": 42}})
    assert legacy.politics.tax_rate == .22
    assert legacy.politics.offices["Mayor"].holder_id == 42


def test_noticeboard_directions_and_citizenship_input(world):
    home = civic.current(world)
    other = next(v for v in civic.villages(world) if v is not home)
    choose_notice(world, f"settlement:{other.id}")
    assert world.player.known_settlements[other.id]["name"] == other.name
    assert world.player.travel_destination_id == other.id
    choose_notice(world, f"civic:{home.id}")
    assert any("eligible at the next election" in str(m) for m in world.chat_log)
    world.player.x, world.player.y = world._get_village_anchor_coords(other)
    world.open_noticeboard_menu()
    main.handle_noticeboard_menu_input(key(main.tcod.event.KeySym.R), world)
    assert world.player.civic_settlement_id == other.id


def test_noticeboard_job_claim_and_employer_funded_wage(world):
    village = civic.current(world)
    shop = next(b for b in village.buildings if b.building_type == "general_store")
    shop.max_workers = world._count_active_workers_for_building(shop) + 1
    task = world.town_board.post_employment(shop.id, "Merchant", 23)
    choose_notice(world, f"job:{task.id}")
    assert world.player.economic.job_building_id == shop.id
    assert world.player.economic.daily_wage == 23
    assert world.town_board.get_employment_task(task.id) is None
    world._set_trade_money_balance(shop, 80)
    world.player.x, world.player.y = shop.global_center_x, shop.global_center_y
    world._update_player_career()
    world.game_time += engine.DAY_LENGTH_TICKS
    before = world.player.economic.money
    world._update_player_career()
    assert world.player.economic.money - before == 23
    assert world._get_trade_money_balance(shop) == 57
    world._update_player_career()
    assert world._get_trade_money_balance(shop) == 57


def test_player_job_slot_cannot_be_taken_by_walk_in_hiring(world):
    village = civic.current(world)
    shop = next(b for b in village.buildings if b.building_type == "general_store")
    seeker = next(n for n in civic.residents(world) if n.schedule.work_building_id != shop.id)
    seeker.schedule.work_building_id = None
    world._set_entity_profession(seeker, "Unemployed", reason="fixture")
    shop.max_workers = world._count_active_workers_for_building(shop) + 1
    task = world.town_board.post_employment(shop.id, "Merchant", 23)
    choose_notice(world, f"job:{task.id}")
    assert world._count_active_workers_for_building(shop) == shop.max_workers
    seeker.x, seeker.y = shop.global_center_x, shop.global_center_y
    assert world._try_walk_in_hire(seeker) is None
    assert seeker.schedule.work_building_id is None


def test_visiting_job_seeker_reads_the_board_they_are_standing_at(world):
    village = civic.current(world)
    visitor = next(n for n in world.village_npcs if world._get_village_for_npc(n) is not village)
    board = village.interaction_points["noticeboard"][0]
    world._set_entity_profession(visitor, "Unemployed", reason="fixture")
    visitor.schedule.work_building_id = None
    visitor.is_sleeping = False
    world._update_entity_position(visitor, board[0]+1, board[1]+1)
    visitor.schedule.current_task = "reviewing_noticeboard_jobs"
    visitor.schedule.current_destination_coords = board
    visitor.schedule.current_path = []
    assert world._get_village_for_npc(visitor) is not village
    world.handle_npc_job_seeking(visitor)
    assert visitor.schedule.current_task != "reviewing_noticeboard_jobs"


def test_noticeboard_errand_clears_when_the_last_opening_disappears(world):
    village = civic.current(world)
    seeker = next(n for n in civic.residents(world))
    world._set_entity_profession(seeker, "Unemployed", reason="fixture")
    seeker.schedule.work_building_id = None
    for building in village.buildings:
        building.max_workers = world._count_active_workers_for_building(building)
    world.town_board.economic_needs.clear()
    world.town_board.employment_tasks.clear()
    board = village.interaction_points["noticeboard"][0]
    seeker.is_sleeping = False
    world._update_entity_position(seeker, *board)
    seeker.schedule.current_task = "reviewing_noticeboard_jobs"
    seeker.schedule.current_destination_coords = board
    seeker.schedule.current_path = []
    assert not world.handle_npc_job_seeking(seeker)
    assert seeker.schedule.current_task == "idle"
    assert seeker.schedule.current_destination_coords is None


def wanted(world):
    village = civic.current(world)
    suspect = next(n for n in civic.residents(world) if n.id not in village.local_offices.values())
    world._accrue_crime_bounty(suspect, "murder")
    world.record_crime_event(crime_kind="murder", suspect_id=suspect.id, description="A witnessed crime.",
                             witness_ids=(world.player.id,), location=(world.player.x, world.player.y), settlement_id=village.id)
    contract = next(c for c in bounty.notices(world) if c.target_id == suspect.id)
    return suspect, contract


def test_bounty_keyboard_acceptance_capture_intake_payment_once(world):
    suspect, contract = wanted(world)
    hall = world.get_town_hall_building()
    money = world._get_trade_money_balance(hall)
    choose_notice(world, f"bounty:{contract.id}")
    assert contract.status == "accepted" and contract.escrow == contract.reward
    assert world._get_trade_money_balance(hall) == money-contract.reward
    suspect.x, suspect.y = world.player.x+1, world.player.y
    assert "Request Surrender" in world._get_actions_for_entity({"type": "npc", "data": suspect})
    assert bounty.request_surrender(world, suspect)
    assert not bounty.turn_in(world, contract)
    jail = next(b for b in civic.current(world).buildings if b.building_type == "sheriff_office")
    world.player.x, world.player.y = jail.global_origin_x, jail.global_origin_y
    suspect.x, suspect.y = world.player.x+1, world.player.y
    before = world.player.economic.money
    assert bounty.turn_in(world, contract)
    assert suspect.schedule.is_jailed and suspect.economic.bounty == 0
    assert contract.status == "completed" and contract.escrow == 0
    assert world.player.economic.money == before+contract.reward
    assert not bounty.turn_in(world, contract)
    assert world.player.economic.money == before+contract.reward


@pytest.mark.parametrize("reason", ["dead", "guard_arrest", "lost"])
def test_unfulfilled_bounty_refunds_escrow(world, reason):
    suspect, contract = wanted(world)
    hall = world.get_town_hall_building()
    before = world._get_trade_money_balance(hall)
    assert bounty.accept_or_turn_in(world, contract.id)
    suspect.x, suspect.y = world.player.x+1, world.player.y
    assert bounty.request_surrender(world, suspect)
    if reason == "dead":
        suspect.physical.is_dead = True
        bounty.refresh(world)
    elif reason == "guard_arrest":
        world._serve_npc_jail_time(suspect)
        bounty.refresh(world)
    else:
        suspect.x += 30
        bounty.maintain_escort(world, suspect)
    assert contract.escrow == 0 and contract.status in {"closed", "abandoned"}
    assert world._get_trade_money_balance(hall) == before
    bounty.refresh(world)
    assert world._get_trade_money_balance(hall) == before


def test_contracts_persist_across_save_load(world):
    suspect, contract = wanted(world)
    bounty.accept_or_turn_in(world, contract.id)
    restored = pickle.loads(pickle.dumps(world))
    loaded = bounty.get_contract(restored, contract.id)
    assert loaded.escrow == contract.escrow and loaded.status == "accepted"
    assert restored.get_entity_by_id(suspect.id).economic.bounty >= 100


def test_unwitnessed_crime_and_unfunded_reward_cannot_pay(world):
    suspect, contract = wanted(world)
    hall = world.get_town_hall_building()
    world._set_trade_money_balance(hall, 0)
    assert not bounty.accept_or_turn_in(world, contract.id)
    assert contract.escrow == 0
    world.bounty_contracts.clear()
    world.bounty_reports.clear()
    world.history.events.clear()
    world.record_crime_event(crime_kind="murder", suspect_id=suspect.id, description="Unseen crime.", location=(world.player.x, world.player.y))
    assert bounty.notices(world) == []


def test_trade_relation_bonus_is_once_per_pair_per_day(world):
    a, b = civic.villages(world)[:2]
    a.village_relationships[b.id] = b.village_relationships[a.id] = 0
    for _ in range(12):
        civic.record_trade_relations(world, a, b)
        civic.record_trade_relations(world, b, a)
    assert a.village_relationships[b.id] == b.village_relationships[a.id] == 2
    world.game_time += engine.DAY_LENGTH_TICKS
    civic.record_trade_relations(world, b, a)
    assert a.village_relationships[b.id] == b.village_relationships[a.id] == 4


def test_remote_pressure_builds_registered_house_with_real_materials(world):
    village = next(v for v in civic.villages(world) if v.chunk_coords == (13, 5))
    supplier = next(b for b in village.buildings if b.building_type == "lumber_mill")
    hall = next(b for b in village.buildings if b.building_type == "capital_hall")
    for building in village.buildings:
        building.building_inventory.pop("raw_log", None)
    supplier.building_inventory["raw_log"] = 50
    world._set_trade_money_balance(hall, 1000)
    treasury_before = world._get_trade_money_balance(hall)
    supplier_before = world._get_trade_money_balance(supplier)
    before = {b.id for b in village.buildings}
    # Genuine generated housing pressure, unmocked land selection.
    world._plan_village_expansion(village)
    blueprint = world._get_village_blueprints(village)[0]
    assert not world._is_blueprint_active(blueprint)
    refs = {id(item) for item in supplier.building_inventory.iter_item_references("raw_log")}
    for _ in range(12):
        world._advance_village_construction(village)
    assert not world._get_village_blueprints(village)
    new = next(b for b in village.buildings if b.id not in before)
    assert new.building_type == "house" and new.settlement_id == village.id
    assert world.get_building_at(new.global_center_x, new.global_center_y) is new
    assert world.atlas.get_village(new.settlement_id) is village
    assert supplier.building_inventory.get("raw_log", 0) == 0
    assert world._get_trade_money_balance(hall) < treasury_before
    assert world._get_trade_money_balance(hall) + world._get_trade_money_balance(supplier) == treasury_before+supplier_before
    deposited = {id(item) for component in blueprint.components for item in component.deposited_inventory.iter_item_references("raw_log")}
    assert deposited == refs


def test_cache_restores_both_id_allocators():
    from entities.base import next_entity_id
    from simulation.ids import new_id
    fresh_world(seed=8451, pre_simulate=False)
    expected = (next_entity_id(), new_id())
    for _ in range(10):
        next_entity_id()
        new_id()
    fresh_world(seed=8451, pre_simulate=False)
    assert (next_entity_id(), new_id()) == expected


@pytest.mark.parametrize("private_owner", [False, True])
def test_remote_service_building_is_staffed_and_produces(world, private_owner):
    from simulation.world_model import TownEconomicNeed
    village = next(v for v in civic.villages(world) if v.chunk_coords == (13, 5))
    # Controlled initial shortage/resources; no forced site, hire, or output.
    for building in village.buildings:
        building.residents.clear()
        building.max_workers = world._count_active_workers_for_building(building)
    village.supply.clear()
    world.town_board.economic_needs.append(TownEconomicNeed(type="service", target_key="Carpenter", settlement_id=village.id))
    supplier = next(b for b in village.buildings if b.building_type == "general_store")
    for item, quantity in {"raw_log":25,"stone_chunk":6,"wooden_plank":8}.items():
        supplier.building_inventory[item] = quantity
    hall = next(b for b in village.buildings if b.building_type == "capital_hall")
    world._set_trade_money_balance(hall, 2000)
    seeker = next(n for n in world.village_npcs if world._get_npc_settlement(n) is village)
    seeker.schedule.work_building_id = None
    world._set_entity_profession(seeker, "Unemployed", reason="fixture")
    for building in village.buildings:
        building.max_workers = world._count_active_workers_for_building(building)
    if private_owner:
        owner = next(n for n in world.village_npcs if world._get_npc_settlement(n) is village and n is not seeker)
        owner.economic.money = 2000
        assert world._npc_maybe_start_construction_project(owner, village) is not None
    else:
        world._plan_village_expansion(village)
    blueprint = world._get_village_blueprints(village)[0]
    assert blueprint.operational_building_type == "carpenter_shop"
    for _ in range(12):
        world._advance_village_construction(village)
    shop = next(b for b in village.buildings if b.building_type == "carpenter_shop")
    assert world.get_building_at(shop.global_center_x, shop.global_center_y) is shop
    if private_owner:
        # Owners start their own business; public openings are posted later
        # by owner management, not the public construction synchronizer.
        worker = owner
        assert worker.schedule.work_building_id == shop.id
        assert not world.town_board.get_open_employment_tasks(shop.id)
    else:
        worker = seeker
        assert world.town_board.get_open_employment_tasks(shop.id)
    shop.building_inventory["lumber_processed"] = 3
    for day in range(1, 31):
        world.game_time = day*engine.DAY_LENGTH_TICKS + engine.DAY_LENGTH_TICKS//2
        world.process_abstract_simulation()
        if shop.building_inventory.get("wooden_table", 0):
            break
    assert worker.schedule.work_building_id == shop.id
    assert worker.economic.profession == "Carpenter"
    assert shop.building_inventory.get("wooden_table", 0) > 0
    assert shop.building_inventory.get("lumber_processed", 0) < 3


def test_surrendered_suspect_really_walks_and_keeps_escort_task(world):
    suspect, contract = wanted(world)
    assert bounty.accept_or_turn_in(world, contract.id)
    px, py = world.player.x, world.player.y
    suspect.x, suspect.y = px-1, py
    world._mark_entity_positions_dirty()
    assert bounty.request_surrender(world, suspect)
    # A short actual route in the existing room/street, not a coordinate jump.
    from tools.probe_settlement_loops import cardinal_path
    village = civic.current(world)
    route = cardinal_path(world, (px, py), world._get_village_anchor_coords(village))
    before = (suspect.x, suspect.y)
    world.is_paused = True
    keys = {(1,0):main.tcod.event.KeySym.RIGHT,(-1,0):main.tcod.event.KeySym.LEFT,
            (0,1):main.tcod.event.KeySym.DOWN,(0,-1):main.tcod.event.KeySym.UP}
    for x,y in route[:12]:
        tile = world.get_tile_at(x,y)
        if not tile.passable and tile.properties.get("is_door"):
            world.player_attempt_toggle_door(x,y)
        assert main.handle_playing_input(key(keys[(x-world.player.x,y-world.player.y)]),world,None)
        for _ in range(3):
            world.update()
    assert (suspect.x,suspect.y) != before
    assert contract.status == "escorting"
    assert suspect.schedule.current_task == "bounty_escort"
    assert not suspect.schedule.is_jailed
