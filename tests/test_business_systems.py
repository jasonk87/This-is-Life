import unittest
from types import SimpleNamespace

import engine
from entities.base import NPC
from simulation.systems.business import (
    actor_business_role,
    create_business_for_building,
    evaluate_worker_for_job,
    operate_business_tick,
    post_business_openings,
    should_owner_delegate_low_labor,
    sync_business_from_world,
    update_business_economic_needs,
)
from simulation.world_model import Building, TownBoard, TownEconomicNeed, Village


class BusinessWorldStub:
    def __init__(self):
        self.game_time = 0
        self.town_board = TownBoard()
        self.village = Village()
        self.buildings_by_id = {}
        self.village_npcs = []
        self.businesses_by_id = {}
        self.messages = []

    def _get_employment_daily_wage(self, role, **_kwargs):
        return 20 if role == "Blacksmith" else 10

    def _get_village_for_npc(self, _npc, **_kwargs):
        return self.village

    def add_message_to_chat_log(self, message):
        self.messages.append(message)


def make_worker(name="Worker", profession="Unemployed", x=0, y=0):
    npc = NPC(x, y, name=name)
    npc.economic.profession = profession
    return npc


class TestBusinessSystems(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = BusinessWorldStub()

    def add_building(self, building_type="blacksmith_shop", category="industrial_workplace"):
        building = Building(0, 0, 5, 5, building_type=building_type, category=category)
        self.world.village.add_building(building)
        self.world.buildings_by_id[building.id] = building
        return building

    def test_business_creation_tracks_owner_inventory_workplace_and_role(self):
        owner = make_worker("Owner", "Blacksmith")
        building = self.add_building("blacksmith_shop")
        business = create_business_for_building(self.world, building, owner)

        self.assertEqual(business.owner_id, owner.id)
        self.assertEqual(business.profession_type, "Blacksmith")
        self.assertEqual(business.production_role, "producer")
        self.assertEqual(business.workplace_building_id, building.id)
        self.assertEqual(business.inventory_storage_id, building.id)
        self.assertEqual(building.business_id, business.id)
        self.assertIn(business.id, self.world.businesses_by_id)

    def test_hiring_logic_scores_wage_distance_fit_desperation_and_posts_opening(self):
        owner = make_worker("Owner", "Blacksmith")
        building = self.add_building("blacksmith_shop")
        building.max_workers = 1
        business = create_business_for_building(self.world, building, owner)
        desperate_smith = make_worker("Smith", "Blacksmith", x=1, y=1)
        desperate_smith.economic.money = 0
        distant_worker = make_worker("Distant", "Unemployed", x=100, y=100)

        fit_score = evaluate_worker_for_job(self.world, desperate_smith, business, "Blacksmith", 20)
        distant_score = evaluate_worker_for_job(self.world, distant_worker, business, "Blacksmith", 20)
        posted = post_business_openings(self.world, business, force_wage=20)

        self.assertGreater(fit_score, distant_score)
        self.assertEqual(len(posted), 1)
        self.assertEqual(posted[0].profession_role, "Blacksmith")
        self.assertGreaterEqual(posted[0].daily_wage, 20)

    def test_delegated_labor_assignment_separates_owner_and_worker_roles(self):
        owner = make_worker("Owner", "Lumber Mill Foreman")
        worker = make_worker("Worker", "Woodcutter")
        building = self.add_building("lumber_mill")
        business = create_business_for_building(self.world, building, owner)
        owner.schedule.work_building_id = building.id
        worker.schedule.work_building_id = building.id
        self.world.village_npcs.extend([owner, worker])
        sync_business_from_world(self.world, business)

        self.assertEqual(actor_business_role(self.world, owner, business), "owner")
        self.assertEqual(actor_business_role(self.world, worker, business), "laborer")
        self.assertTrue(should_owner_delegate_low_labor(self.world, owner, business))

    def test_wage_pressure_rises_when_business_is_understaffed_or_desperate(self):
        building = self.add_building("blacksmith_shop")
        business = create_business_for_building(self.world, building, None)
        base = self.world._get_employment_daily_wage("Blacksmith")
        business.demand_pressure = 80
        posted = post_business_openings(self.world, business, force_wage=base)

        self.assertGreater(posted[0].daily_wage, base)
        self.assertEqual(business.wages["Blacksmith"], posted[0].daily_wage)

    def test_production_requires_inputs_time_and_workplace_presence(self):
        building = self.add_building("blacksmith_shop")
        business = create_business_for_building(self.world, building, None)
        worker = make_worker("Smith", "Blacksmith")
        worker.schedule.work_building_id = building.id
        self.world.village_npcs.append(worker)
        building.building_inventory.add_item("iron_ore", 2)
        building.building_inventory.add_item("coal", 1)
        sync_business_from_world(self.world, business)

        for _ in range(11):
            operate_business_tick(self.world, business, worker=worker)
        self.assertEqual(building.building_inventory.get("iron_ingot", 0), 0)
        operate_business_tick(self.world, business, worker=worker)

        self.assertEqual(building.building_inventory.get("iron_ingot", 0), 1)
        self.assertEqual(building.building_inventory.get("iron_ore", 0), 0)
        self.assertEqual(business.completed_batches, 1)

    def test_shortages_stall_production_and_create_economic_need_pressure(self):
        building = self.add_building("blacksmith_shop")
        business = create_business_for_building(self.world, building, None)
        worker = make_worker("Smith", "Blacksmith")
        worker.schedule.work_building_id = building.id
        self.world.village_npcs.append(worker)
        sync_business_from_world(self.world, business)

        self.assertFalse(operate_business_tick(self.world, business, worker=worker))
        update_business_economic_needs(self.world, self.world.village)

        self.assertEqual(business.operating_status, "stalled")
        self.assertIn("iron_ore", business.current_shortages)
        self.assertTrue(any(n.type == "shortage" and n.target_key == "iron_ore" for n in self.world.town_board.economic_needs))

    def test_logistics_delivery_pulls_inputs_between_business_storage(self):
        tavern = self.add_building("tavern", "commercial_workplace")
        farm = self.add_building("farm", "agricultural_workplace")
        farm.building_inventory.add_item("wheat", 1)
        farm.building_inventory.add_item("raw_log", 1)
        business = create_business_for_building(self.world, tavern, None)
        worker = make_worker("Keeper", "Tavern Keeper")
        worker.schedule.work_building_id = tavern.id
        self.world.village_npcs.append(worker)
        sync_business_from_world(self.world, business)

        operate_business_tick(self.world, business, worker=worker)

        self.assertEqual(tavern.building_inventory.get("wheat", 0), 1)
        self.assertEqual(tavern.building_inventory.get("raw_log", 0), 1)
        self.assertEqual(business.visible_status, "Delivering supplies.")

    def test_npc_autonomous_opportunity_pursuit_starts_business_for_need(self):
        world = engine.World(seed=12)
        village = Village()
        smithy = Building(0, 0, 5, 5, building_type="blacksmith_shop", category="industrial_workplace")
        village.add_building(smithy)
        village.interaction_points["noticeboard"] = [(0, 0)]
        world.villages.append(village)
        world.buildings_by_id[smithy.id] = smithy
        npc = NPC(0, 0, name="Founder")
        npc.economic.money = 50
        world.village_npcs = [npc]
        world.town_board.economic_needs = [TownEconomicNeed(type="service", target_key="Blacksmith", settlement_id=village.id)]

        business = world.npc_pursue_business_opportunity(npc, village)

        self.assertIsNotNone(business)
        self.assertEqual(smithy.owner_id, npc.id)
        self.assertEqual(npc.economic.profession, "Blacksmith")
        self.assertTrue(world.town_board.get_open_employment_tasks(smithy.id))

    def test_contract_fulfillment_updates_supply_and_can_resolve_shortage_regression(self):
        building = self.add_building("farm", "agricultural_workplace")
        business = create_business_for_building(self.world, building, None)
        worker = make_worker("Farmer", "Farmer")
        worker.schedule.work_building_id = building.id
        self.world.village_npcs.append(worker)
        self.world.village.demand["wheat"] = 2
        self.world.town_board.economic_needs.append(TownEconomicNeed(type="shortage", target_key="wheat", settlement_id=self.world.village.id))
        sync_business_from_world(self.world, business)

        for _ in range(10):
            operate_business_tick(self.world, business, worker=worker)

        self.assertEqual(building.building_inventory.get("wheat", 0), 2)
        self.assertGreaterEqual(self.world.village.supply.get("wheat", 0), 2)
        self.assertEqual(business.completed_batches, 1)


if __name__ == "__main__":
    unittest.main()
