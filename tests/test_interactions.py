import unittest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace
import json
import math
import time
import uuid

import engine
from engine import World
import main
import rendering.console_renderer as console_renderer
from save_manager import save_game, load_game
from data.items import ITEM_DEFINITIONS
from data.decorations import DECORATION_ITEM_DEFINITIONS
import config
from services.llm_gossip import AsyncLLMGossipService
from simulation.systems import survival
from simulation.systems.work import update_npc_work_sub_tasks
from tcod_compat import tcod
import tile_types
from entities.items import Inventory, ItemReference

class TestWorldInteractionActions(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()
        self.mock_call_llm.return_value = json.dumps({
            "name": "Test NPC",
            "personality": "test",
            "family_ties": "none",
            "attitude_to_player": "neutral",
            "dialogue": ["Hello."],
            "wealth_level": "average",
            "combat_behavior": "defensive",
            "base_attack_name": "fists"
        })
        self.world = World()

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def test_trade_action_uses_npc_economic_profession(self):
        merchant = engine.NPC(0, 0, name="Merchant")
        merchant.economic.profession = "Merchant"

        actions = self.world._get_actions_for_entity({"type": "npc", "data": merchant, "name": merchant.name})

        self.assertIn("Talk", actions)
        self.assertIn("Attack", actions)
        self.assertIn("Trade", actions)

    def test_initialize_trade_session_uses_schedule_work_building_id(self):
        merchant = engine.NPC(0, 0, name="Merchant")
        merchant.economic.profession = "Merchant"
        merchant.schedule.work_building_id = "shop_1"

        shop = SimpleNamespace(building_type="general_store", building_inventory={"raw_log": 3, "money": 25})
        self.world.trade_ui_active = True
        self.world.trade_ui_npc_target = merchant
        self.world.buildings_by_id = {"shop_1": shop}

        with patch.object(self.world, "_get_village_for_npc", return_value=None), \
             patch.object(self.world, "get_dynamic_price", return_value=7):
            self.world.initialize_trade_session()

        self.assertIn(("raw_log", 3, 7), self.world.trade_ui_merchant_inventory_snapshot)

    def test_handle_trade_action_uses_schedule_work_building_id(self):
        merchant = engine.NPC(0, 0, name="Merchant")
        merchant.economic.profession = "Merchant"
        merchant.schedule.work_building_id = "shop_1"

        shop = SimpleNamespace(building_type="general_store", building_inventory={"raw_log": 1, "money": 0})
        self.world.trade_ui_active = True
        self.world.trade_ui_npc_target = merchant
        self.world.trade_ui_player_selling = False
        self.world.trade_ui_merchant_inventory_snapshot = [("raw_log", 1, 5)]
        self.world.trade_ui_merchant_item_index = 0
        self.world.buildings_by_id = {"shop_1": shop}

        self.world.player.economic.money = 10 # Provide enough money for purchase
        with patch.object(self.world, "_get_village_for_npc", return_value=None):
            self.world.handle_trade_action()

        self.assertTrue(self.world.player.has_item("raw_log", 1))
        self.assertEqual(shop.building_inventory["money"], 5)
        self.assertNotIn("raw_log", shop.building_inventory)

    def test_handle_npc_goal_start_trade_activates_trade_ui(self):
        merchant = engine.NPC(0, 0, name="Merchant")
        merchant.economic.profession = "Merchant"
        self.world.chat_ui_active = True
        self.world.needs_text_input = True

        with patch.object(self.world, "initialize_trade_session") as mock_init:
            self.world._handle_npc_goal(merchant, "start_trade", "")
            main.apply_ui_requests(self.world)

        self.assertEqual(self.world.game_state, "TRADE_MENU")
        self.assertTrue(self.world.trade_ui_active)
        self.assertIs(self.world.trade_ui_npc_target, merchant)
        self.assertFalse(self.world.chat_ui_active)
        self.assertFalse(self.world.needs_text_input)
        mock_init.assert_called_once_with()

    def test_execute_trade_preserves_item_reference_and_moves_money(self):
        buyer = engine.NPC(0, 0, name="Buyer")
        buyer.economic.money = 100
        seller_building = engine.Building(0, 0, 4, 4, building_type="general_store", category="commercial_workplace")
        seller_building.building_inventory.add_item("axe_stone", 1, quality="Masterwork", crafter_name="Smith")
        item_reference = seller_building.building_inventory.get_item_reference("axe_stone")
        item_reference.current_durability = 7
        price = item_reference.value

        traded = self.world.execute_trade(buyer=buyer, seller=seller_building, item_reference=item_reference, price=price)

        self.assertTrue(traded)
        self.assertEqual(buyer.economic.money, 100 - price)
        self.assertEqual(seller_building.building_inventory.get("money", 0), price)
        self.assertEqual(buyer.economic.npc_inventory.get("axe_stone", 0), 0)
        self.assertIs(buyer.get_equipped_item_reference("weapon"), item_reference)
        self.assertEqual(buyer.get_equipped_item_reference("weapon").current_durability, 7)
        self.assertEqual(buyer.get_equipped_item_reference("weapon").crafter_name, "Smith")

    def test_item_reference_utility_prefers_quality_and_penalizes_damage(self):
        worn_sword = ItemReference("rusty_sword", quality="Masterwork")
        worn_sword.current_durability = 2
        fresh_sword = ItemReference("rusty_sword", quality="Fine")

        self.assertGreater(fresh_sword.evaluate_utility(), worn_sword.evaluate_utility())

    def test_npc_equip_and_unequip_preserves_item_reference_object(self):
        npc = engine.NPC(0, 0, name="Guard")
        npc.economic.npc_inventory.add_item("iron_sword", 1, quality="Masterwork", crafter_name="Smith")
        sword = npc.economic.npc_inventory.get_item_reference("iron_sword")
        sword.current_durability = 9

        equipped = npc.equip_item_reference("weapon", sword)
        returned_item = npc.unequip_item("weapon")

        self.assertTrue(equipped)
        self.assertIs(returned_item, sword)
        self.assertEqual(npc.economic.npc_inventory.get("iron_sword", 0), 1)
        self.assertIs(npc.economic.npc_inventory.get_item_reference("iron_sword"), sword)
        self.assertEqual(sword.current_durability, 9)

    def test_execute_trade_auto_equips_better_weapon_and_returns_old_weapon_to_inventory(self):
        buyer = engine.NPC(0, 0, name="Buyer")
        buyer.economic.money = 200
        buyer.add_item("rusty_sword", 1)
        old_weapon = buyer.economic.npc_inventory.get_item_reference("rusty_sword")
        buyer.equip_item_reference("weapon", old_weapon)
        seller_building = engine.Building(0, 0, 4, 4, building_type="general_store", category="commercial_workplace")
        seller_building.building_inventory.add_item("iron_sword", 1, quality="Masterwork", crafter_name="Smith")
        new_weapon = seller_building.building_inventory.get_item_reference("iron_sword")

        traded = self.world.execute_trade(buyer=buyer, seller=seller_building, item_reference=new_weapon, price=new_weapon.value)

        self.assertTrue(traded)
        self.assertIs(buyer.get_equipped_item_reference("weapon"), new_weapon)
        self.assertEqual(buyer.economic.npc_inventory.get("iron_sword", 0), 0)
        self.assertEqual(buyer.economic.npc_inventory.get("rusty_sword", 0), 1)
        self.assertIs(buyer.economic.npc_inventory.get_item_reference("rusty_sword"), old_weapon)

    def test_npc_craft_item_auto_equips_better_weapon(self):
        npc = engine.NPC(0, 0, name="Smith")
        npc.economic.profession = "Blacksmith"
        npc.add_item("rusty_sword", 1)
        old_weapon = npc.economic.npc_inventory.get_item_reference("rusty_sword")
        npc.equip_item_reference("weapon", old_weapon)

        with patch("entities.base.roll_crafted_item_quality", return_value="Masterwork"):
            npc.craft_item("iron_sword", 1)

        equipped_weapon = npc.get_equipped_item_reference("weapon")
        self.assertIsNotNone(equipped_weapon)
        self.assertEqual(equipped_weapon.key, "iron_sword")
        self.assertEqual(equipped_weapon.quality, "Masterwork")
        self.assertEqual(npc.economic.npc_inventory.get("rusty_sword", 0), 1)

    def test_npc_brain_evaluates_owned_gear_once_per_day(self):
        npc = engine.NPC(0, 0, name="Guard")
        world = SimpleNamespace(game_time=0, _run_humanoid_schedule_logic=lambda entity: False)

        with patch.object(npc, "evaluate_and_upgrade_equipment", return_value=True) as evaluator:
            npc.ai_brain.take_turn(npc, world)
            npc.ai_brain.take_turn(npc, world)
            world.game_time = config.DAY_LENGTH_TICKS
            npc.ai_brain.take_turn(npc, world)

        self.assertEqual(evaluator.call_count, 2)

    def test_npc_buy_food_uses_quality_scaled_trade_value(self):
        tavern = engine.Building(0, 0, 4, 4, building_type="tavern", category="commercial_workplace")
        tavern.building_inventory.add_item("apple", 1, quality="Fine", crafter_name="Orchard")
        item_reference = tavern.building_inventory.get_item_reference("apple")
        buyer = engine.NPC(0, 0, name="Hungry Buyer")
        buyer.economic.money = item_reference.value

        with patch.object(self.world, "_get_village_for_npc", return_value=None):
            bought = self.world._npc_buy_or_collect_food(buyer, tavern)

        bought_item = buyer.economic.npc_inventory.get_item_reference("apple")
        self.assertTrue(bought)
        self.assertIs(bought_item, item_reference)
        self.assertEqual(buyer.economic.money, 0)
        self.assertEqual(tavern.building_inventory.get("money", 0), item_reference.value)

    def test_place_construction_blueprint_posts_haul_tasks_and_uses_material_sprite(self):
        blueprint = self.world.place_construction_blueprint("wooden_chair", 8, 8)

        self.assertIsNotNone(blueprint)
        self.assertEqual(blueprint.char, ITEM_DEFINITIONS["wooden_plank"]["char"])
        self.assertEqual(len(self.world.town_board.get_open_tasks(blueprint.id)), 2)
        self.assertIs(self.world.get_blueprint_at(8, 8), blueprint)

    def test_noticeboard_tile_exposes_read_notices_action(self):
        tile_def = DECORATION_ITEM_DEFINITIONS["noticeboard"]
        tile = tile_types.Tile(
            char=tile_def["char"],
            color=tile_def["color"],
            passable=tile_def["passable"],
            name=tile_def["name"],
            properties=tile_def["properties"],
        )

        actions = self.world._get_actions_for_entity({"type": "tile", "data": tile, "name": tile.name})

        self.assertIn("Read Notices", actions)

    def test_unowned_workplace_exposes_buy_property_action(self):
        building = engine.Building(2, 2, 5, 5, building_type="general_store", category="commercial_workplace")

        actions = self.world._get_actions_for_entity({"type": "building", "data": building, "name": building.building_type})

        self.assertIn("Buy Property", actions)
        self.assertNotIn("Company Ledger", actions)

    def test_buy_property_sets_owner_and_deducts_player_money(self):
        building = engine.Building(2, 2, 5, 5, building_type="general_store", category="commercial_workplace")
        self.world.player.economic.money = 500
        price = self.world.get_property_purchase_price(building)

        bought = self.world.buy_property(building)

        self.assertTrue(bought)
        self.assertEqual(building.owner_id, self.world.player.id)
        self.assertTrue(building.player_owned)
        self.assertEqual(self.world.player.economic.money, 500 - price)

    def test_owned_building_exposes_company_ledger_and_transfers_cash_without_creating_money(self):
        building = engine.Building(2, 2, 5, 5, building_type="general_store", category="commercial_workplace")
        building.building_inventory["money"] = 125
        building.building_inventory["wooden_plank"] = 7
        self.world.buildings_by_id[building.id] = building
        self.world.player.economic.money = 80
        self.world._set_building_owner(building, self.world.player)

        actions = self.world._get_actions_for_entity({"type": "building", "data": building, "name": building.building_type})
        opened = self.world.open_company_ledger_menu(building)
        deposited = self.world.transfer_company_funds(building, 50, withdraw=False)
        withdrew = self.world.transfer_company_funds(building, 100, withdraw=True)
        stock_snapshot = self.world.get_company_ledger_stock_snapshot(building)

        self.assertIn("Company Ledger", actions)
        self.assertTrue(opened)
        self.assertTrue(deposited)
        self.assertTrue(withdrew)
        self.assertEqual(self.world.player.economic.money, 130)
        self.assertEqual(building.building_inventory.get("money", 0), 75)
        self.assertEqual(sum(quantity for _, quantity in stock_snapshot), 7)

    def test_post_employment_listing_creates_notice_for_owned_building(self):
        building = engine.Building(2, 2, 5, 5, building_type="general_store", category="commercial_workplace")
        self.world.buildings_by_id[building.id] = building
        self.world._set_building_owner(building, self.world.player)
        self.world.player.economic.money = 50

        task = self.world.post_employment_listing(building, "Merchant", 25)

        self.assertIsNotNone(task)
        self.assertEqual(task.target_building_id, building.id)
        self.assertEqual(task.profession_role, "Merchant")
        self.assertEqual(task.daily_wage, 25)
        self.assertEqual(self.world.player.economic.money, 45)

    def test_unemployed_npc_accepts_player_posted_job_from_noticeboard(self):
        building = engine.Building(2, 2, 5, 5, building_type="general_store", category="commercial_workplace")
        self.world.buildings_by_id[building.id] = building
        self.world._set_building_owner(building, self.world.player)
        task = self.world.town_board.post_employment(building.id, "Merchant", 22, poster_entity_id=self.world.player.id)
        npc = engine.NPC(5, 5, name="Job Seeker")
        npc.economic.profession = "Unemployed"
        npc.ai_brain.assign_profession("Unemployed")
        self.world.village_npcs = [npc]
        village = SimpleNamespace(interaction_points={"noticeboard": [(5, 5)]})

        with patch.object(self.world, "_get_village_for_npc", return_value=village):
            accepted = self.world.handle_npc_job_seeking(npc)

        self.assertTrue(accepted)
        self.assertEqual(npc.economic.profession, "Merchant")
        self.assertEqual(npc.schedule.work_building_id, building.id)
        self.assertEqual(npc.economic.daily_wage, 22)
        self.assertIsNone(self.world.town_board.get_employment_task(task.id))

    def test_unemployed_npc_accepts_settlement_noticeboard_job_for_non_player_building(self):
        building = engine.Building(2, 2, 5, 5, building_type="farm", category="agricultural_workplace")
        building.max_workers = 1
        village = engine.Village()
        village.interaction_points = {"noticeboard": [(5, 5)]}
        village.add_building(building)
        self.world.buildings_by_id[building.id] = building
        task = self.world.town_board.post_employment(building.id, "Farmer", 14)
        npc = engine.NPC(5, 5, name="Field Hand")
        npc.economic.profession = "Unemployed"
        npc.ai_brain.assign_profession("Unemployed")
        self.world.village_npcs = [npc]

        with patch.object(self.world, "_get_village_for_npc", return_value=village):
            accepted = self.world.handle_npc_job_seeking(npc)

        self.assertTrue(accepted)
        self.assertEqual(npc.economic.profession, "Farmer")
        self.assertEqual(npc.schedule.work_building_id, building.id)
        self.assertEqual(npc.economic.daily_wage, 14)
        self.assertIsNone(self.world.town_board.get_employment_task(task.id))

    def test_village_expansion_places_blueprint_and_advances_through_shared_construction_flow(self):
        village = engine.Village()
        village.interaction_points = {"town_square_center": [(12, 12)]}
        house = engine.Building(0, 0, 5, 5, building_type="house", category="residential")
        house.residents = [SimpleNamespace(), SimpleNamespace()]
        village.add_building(house)
        village.supply["raw_log"] = 50
        self.world.chunks[0][0].village = village
        self.world.chunk_width = 1
        self.world.chunk_height = 1

        with patch.object(self.world, "_find_valid_building_spot", return_value=(8, 8)):
            self.world._plan_village_expansion(village)

        blueprint = self.world.get_blueprint_at(8, 8)
        self.assertIsNotNone(blueprint)
        self.assertEqual(blueprint.target_build, "house")
        self.assertEqual(blueprint.settlement_id, village.id)
        self.assertEqual(len(self.world.town_board.get_open_tasks(blueprint.id)), 50)

        for _ in range(5):
            self.world._advance_village_construction(village)

        self.assertIsNone(self.world.get_blueprint_at(8, 8))
        self.assertEqual(sum(1 for building in village.buildings if building.building_type == "house"), 2)
        self.assertEqual(village.supply.get("raw_log", 0), 0)

    def test_completed_non_player_workplace_syncs_noticeboard_jobs_and_starting_funds(self):
        village = engine.Village()
        self.world.chunks[0][0].village = village
        self.world.chunk_width = 1
        self.world.chunk_height = 1

        blueprint = self.world.place_construction_blueprint("farm", 6, 6)
        self.assertIsNotNone(blueprint)
        blueprint.settlement_id = village.id
        for _ in range(30):
            blueprint.deposit_item_reference(engine.ItemReference("raw_log"))
        for _ in range(10):
            blueprint.deposit_item_reference(engine.ItemReference("stone_chunk"))
        for task in list(self.world.town_board.haul_tasks):
            if task.blueprint_id == blueprint.id:
                task.status = "complete"

        completed = self.world._complete_construction_blueprint(blueprint)

        self.assertTrue(completed)
        farm = next(building for building in village.buildings if building.building_type == "farm")
        self.assertGreaterEqual(farm.building_inventory.get("money", 0), 80)
        open_jobs = self.world.town_board.get_open_employment_tasks(farm.id)
        self.assertEqual(len(open_jobs), farm.max_workers)
        self.assertTrue(all(task.profession_role == "Farmer" for task in open_jobs))

    def test_player_owned_business_pays_daily_wage_from_ledger(self):
        building = engine.Building(2, 2, 5, 5, building_type="general_store", category="commercial_workplace")
        building.building_inventory["money"] = 40
        self.world.buildings_by_id[building.id] = building
        self.world._set_building_owner(building, self.world.player)
        npc = engine.NPC(0, 0, name="Clerk")
        self.world.village_npcs = [npc]
        self.world._assign_job(npc, building, profession="Merchant", daily_wage=20)
        self.world.game_time = config.DAY_LENGTH_TICKS

        self.world._pay_daily_company_wages()

        self.assertEqual(building.building_inventory.get("money", 0), 20)
        self.assertEqual(npc.economic.money, 20)
        self.assertEqual(npc.schedule.last_paid_day, 1)

    def test_player_owned_business_without_funds_causes_worker_to_quit(self):
        building = engine.Building(2, 2, 5, 5, building_type="general_store", category="commercial_workplace")
        building.building_inventory["money"] = 5
        self.world.buildings_by_id[building.id] = building
        self.world._set_building_owner(building, self.world.player)
        npc = engine.NPC(0, 0, name="Clerk")
        self.world.village_npcs = [npc]
        self.world._assign_job(npc, building, profession="Merchant", daily_wage=20)
        self.world.game_time = config.DAY_LENGTH_TICKS

        self.world._pay_daily_company_wages()

        self.assertEqual(npc.economic.profession, "Unemployed")
        self.assertIsNone(npc.schedule.work_building_id)
        self.assertEqual(building.building_inventory.get("money", 0), 5)

    def test_knowledge_component_discards_lowest_importance_memory_when_full(self):
        npc = engine.NPC(0, 0, name="Rememberer")
        npc.knowledge.max_memory_events = 2

        low = engine.MemoryEvent("rumor", 1, None, 1, 5, headline="Low")
        high = engine.MemoryEvent("murder", 2, 3, 2, 90, headline="High")
        medium = engine.MemoryEvent("unpaid_wages", 4, 5, 3, 40, headline="Medium")

        npc.knowledge.record_event(low)
        npc.knowledge.record_event(high)
        npc.knowledge.record_event(medium)

        self.assertNotIn(low.id, npc.knowledge.known_memories)
        self.assertIn(high.id, npc.knowledge.known_memories)
        self.assertIn(medium.id, npc.knowledge.known_memories)

    def test_unpaid_wages_records_memory_event_for_worker(self):
        building = engine.Building(2, 2, 5, 5, building_type="general_store", category="commercial_workplace")
        building.building_inventory["money"] = 5
        self.world.buildings_by_id[building.id] = building
        self.world._set_building_owner(building, self.world.player)
        npc = engine.NPC(0, 0, name="Clerk")
        self.world.village_npcs = [npc]
        self.world._assign_job(npc, building, profession="Merchant", daily_wage=20)
        self.world.game_time = config.DAY_LENGTH_TICKS

        self.world._pay_daily_company_wages()

        memory_events = list(npc.knowledge.known_memories.values())
        self.assertTrue(any(memory.event_type == "unpaid_wages" for memory in memory_events))

    def test_handle_npc_death_records_murder_memory_for_killer_victim_and_witness(self):
        attacker = engine.NPC(10, 10, name="Attacker")
        victim = engine.NPC(11, 10, name="Victim")
        witness = engine.NPC(12, 10, name="Witness")
        distant = engine.NPC(50, 50, name="Far Away")
        victim.physical.is_dead = True
        self.world.npcs = [attacker, victim, witness, distant]
        self.world.village_npcs = []

        fov = engine.np.zeros((config.WORLD_HEIGHT, config.WORLD_WIDTH), dtype=bool)
        fov[10, 11] = True
        self.world.npc_fov_maps[witness.id] = fov
        far_fov = engine.np.zeros((config.WORLD_HEIGHT, config.WORLD_WIDTH), dtype=bool)
        self.world.npc_fov_maps[distant.id] = far_fov

        self.world.handle_npc_death(victim, killer_id=attacker.id)

        self.assertTrue(any(memory.event_type == "murder" for memory in attacker.knowledge.known_memories.values()))
        self.assertTrue(any(memory.event_type == "murder" for memory in victim.knowledge.known_memories.values()))
        self.assertTrue(any(memory.event_type == "murder" for memory in witness.knowledge.known_memories.values()))
        self.assertFalse(any(memory.event_type == "murder" for memory in distant.knowledge.known_memories.values()))

    def test_handle_npc_death_transfers_owned_building_to_spouse_and_clears_partner_tie(self):
        owner = engine.NPC(11, 10, name="Owner")
        spouse = engine.NPC(12, 10, name="Spouse")
        owner.physical.is_dead = True
        owner.social.family_ties["partner_id"] = spouse.id
        spouse.social.family_ties["partner_id"] = owner.id
        building = engine.Building(10, 10, 5, 5, building_type="house", category="residential")
        building.residents = [owner]
        self.world.buildings_by_id = {building.id: building}
        self.world._set_building_owner(building, owner)
        self.world.npcs = [owner, spouse]
        self.world.village_npcs = []

        self.world.handle_npc_death(owner)

        self.assertEqual(building.owner_id, spouse.id)
        self.assertFalse(building.player_owned)
        self.assertNotIn(owner, building.residents)
        self.assertIn(spouse, building.residents)
        self.assertEqual(spouse.schedule.home_building_id, building.id)
        self.assertNotIn("partner_id", spouse.social.family_ties)
        self.assertEqual(spouse.social.family_ties.get("widowed_from"), owner.id)

    def test_handle_npc_death_releases_owned_building_without_living_heir(self):
        owner = engine.NPC(11, 10, name="Owner")
        owner.physical.is_dead = True
        building = engine.Building(10, 10, 5, 5, building_type="general_store", category="commercial_workplace")
        self.world.buildings_by_id = {building.id: building}
        self.world._set_building_owner(building, owner)
        self.world.npcs = [owner]
        self.world.village_npcs = []

        self.world.handle_npc_death(owner)

        self.assertIsNone(building.owner_id)
        self.assertFalse(building.player_owned)

    def test_disguised_killer_records_unknown_subject_for_witness_memory(self):
        attacker = engine.NPC(10, 10, name="Attacker")
        attacker.add_item("hooded_cowl", 1)
        attacker.equip_item_reference("head", attacker.economic.npc_inventory.get_item_reference("hooded_cowl"))
        victim = engine.NPC(11, 10, name="Victim")
        victim.physical.is_dead = True
        witness = engine.NPC(12, 10, name="Witness")
        self.world.npcs = [attacker, victim, witness]
        self.world.village_npcs = []

        fov = engine.np.zeros((config.WORLD_HEIGHT, config.WORLD_WIDTH), dtype=bool)
        fov[10, 11] = True
        self.world.npc_fov_maps[witness.id] = fov

        self.world.handle_npc_death(victim, killer_id=attacker.id)

        witness_memories = [memory for memory in witness.knowledge.known_memories.values() if memory.event_type == "murder"]
        self.assertEqual(len(witness_memories), 1)
        self.assertEqual(witness_memories[0].subject_id, "Unknown")

    def test_knowledge_reputation_uses_memory_scores_and_disguises_return_neutral(self):
        observer = engine.NPC(0, 0, name="Observer")
        target = engine.NPC(1, 0, name="Target")
        observer.knowledge.record_event(engine.MemoryEvent("murder", target.id, 7, 1, 95, headline="Murder"))
        observer.knowledge.record_event(engine.MemoryEvent("crafted_masterwork", target.id, None, 2, 40, headline="Masterwork"))

        self.assertEqual(observer.knowledge.get_reputation_towards(target), -40)

        target.add_item("hooded_cowl", 1)
        target.equip_item_reference("head", target.economic.npc_inventory.get_item_reference("hooded_cowl"))
        self.assertEqual(observer.knowledge.get_reputation_towards(target), 0)

    def test_gossip_behavior_shares_high_importance_memory(self):
        speaker = engine.NPC(5, 5, name="Speaker")
        listener = engine.NPC(6, 5, name="Listener")
        self.world.village_npcs = [speaker, listener]
        memory = engine.MemoryEvent("murder", 1, 2, 10, 80, headline="A murder happened")
        speaker.knowledge.record_event(memory)
        self.world.game_time = (17 - ((min(speaker.id, listener.id) + max(speaker.id, listener.id)) % 17)) % 17

        shared = speaker.ai_brain.gossip_behavior.take_turn(speaker, self.world)

        self.assertTrue(shared)
        self.assertIn(memory.id, listener.knowledge.known_memories)

    def test_trade_prices_use_memory_based_markup_discount_and_disguise_neutrality(self):
        merchant = engine.NPC(0, 0, name="Merchant")
        merchant.economic.profession = "Merchant"
        village = SimpleNamespace(supply={"bread": 10}, demand={"bread": 10})

        base_price = self.world.get_dynamic_price("bread", village, merchant=merchant)

        merchant.knowledge.record_event(engine.MemoryEvent("murder", self.world.player.id, 99, 1, 95, headline="Murder"))
        self.assertEqual(self.world.get_dynamic_price("bread", village, merchant=merchant), int(base_price * 1.5))

        merchant.knowledge.known_memories.clear()
        merchant.knowledge.record_event(engine.MemoryEvent("crafted_masterwork", self.world.player.id, None, 2, 40, headline="Masterwork"))
        self.assertEqual(self.world.get_dynamic_price("bread", village, merchant=merchant), max(1, int(base_price * 0.8)))

        self.world.player.equipment.equipped_armor["head"] = "hooded_cowl"
        self.assertEqual(self.world.get_dynamic_price("bread", village, merchant=merchant), base_price)

    def test_trade_session_refuses_known_murderer_but_allows_disguised_player(self):
        merchant = engine.NPC(0, 0, name="Merchant")
        merchant.economic.profession = "Merchant"
        merchant.schedule.work_building_id = "shop_1"
        merchant.knowledge.record_event(engine.MemoryEvent("murder", self.world.player.id, 77, 1, 95, headline="Murder"))
        merchant.knowledge.record_event(engine.MemoryEvent("murder", self.world.player.id, 78, 2, 95, headline="Second Murder"))
        shop = SimpleNamespace(building_type="general_store", building_inventory={"bread": 2, "money": 50})
        self.world.trade_ui_active = True
        self.world.trade_ui_npc_target = merchant
        self.world.buildings_by_id = {"shop_1": shop}

        with patch.object(self.world, "_get_village_for_npc", return_value=SimpleNamespace(supply={"bread": 5}, demand={"bread": 5})):
            self.world.initialize_trade_session()

        self.assertFalse(self.world.trade_ui_active)
        self.assertIn("refuses to trade", self.world.chat_log[-1])

        self.world.trade_ui_active = True
        self.world.trade_ui_npc_target = merchant
        self.world.player.equipment.equipped_armor["head"] = "hooded_cowl"
        with patch.object(self.world, "_get_village_for_npc", return_value=SimpleNamespace(supply={"bread": 5}, demand={"bread": 5})):
            self.world.initialize_trade_session()

        self.assertTrue(self.world.trade_ui_active)
        self.assertTrue(self.world.trade_ui_merchant_inventory_snapshot)

    def test_give_gift_to_npc_transfers_item_reference_and_records_memory(self):
        npc = engine.NPC(1, 1, name="Recipient")
        self.world.player.add_item("iron_sword", 1)
        sword = self.world.player.get_item_reference("iron_sword")
        gift_option = next(option for option in self.world.get_social_gift_options() if option.get("item_key") == "iron_sword")

        gifted = self.world.give_gift_to_npc(npc, gift_option)

        self.assertTrue(gifted)
        self.assertFalse(self.world.player.has_item("iron_sword", 1))
        self.assertEqual(npc.economic.npc_inventory.get("iron_sword", 0), 1)
        self.assertIs(npc.economic.npc_inventory.get_item_reference("iron_sword"), sword)
        self.assertTrue(any(memory.event_type == "received_gift" for memory in npc.knowledge.known_memories.values()))
        self.assertGreater(npc.knowledge.get_reputation_towards(self.world.player), 0)

    def test_give_gift_to_npc_supports_cash_gifts(self):
        npc = engine.NPC(1, 1, name="Recipient")
        self.world.player.economic.money = 25
        gift_option = next(option for option in self.world.get_social_gift_options() if option.get("type") == "money" and option.get("amount") == 10)

        gifted = self.world.give_gift_to_npc(npc, gift_option)

        self.assertTrue(gifted)
        self.assertEqual(self.world.player.economic.money, 15)
        self.assertEqual(npc.economic.money, 10)
        self.assertGreater(npc.knowledge.get_reputation_towards(self.world.player), 0)

    def test_share_player_memory_with_npc_copies_memory_event(self):
        npc = engine.NPC(1, 1, name="Listener")
        memory = engine.MemoryEvent("unpaid_wages", 44, 2, 3, 70, headline="Workers walked out unpaid.")
        self.world.player.knowledge.record_event(memory)

        shared = self.world.share_player_memory_with_npc(npc, memory)

        self.assertTrue(shared)
        self.assertIn(memory.id, npc.knowledge.known_memories)
        self.assertEqual(npc.knowledge.get_reputation_towards(SimpleNamespace(id=44)), -20)

    def test_player_propose_to_npc_accepts_with_high_reputation_and_transfers_assets(self):
        npc = engine.NPC(1, 1, name="Beloved")
        npc.economic.money = 80
        for timestamp in range(1, 7):
            npc.knowledge.record_event(engine.MemoryEvent("received_gift", self.world.player.id, npc.id, timestamp, 40, headline=f"Gift {timestamp}"))
        building = engine.Building(0, 0, 4, 4, building_type="house", category="residential")
        self.world.buildings_by_id = {building.id: building}
        self.world._set_building_owner(building, npc)
        self.world.village_npcs = [npc]
        self.world.player.economic.money = 20

        accepted = self.world.player_propose_to_npc(npc)

        self.assertTrue(accepted)
        self.assertEqual(self.world.player.social.family_ties.get("partner_id"), npc.id)
        self.assertEqual(npc.social.family_ties.get("partner_id"), self.world.player.id)
        self.assertEqual(self.world.player.economic.money, 100)
        self.assertEqual(npc.economic.money, 0)
        self.assertEqual(building.owner_id, self.world.player.id)
        self.assertTrue(any(memory.event_type == "marriage" for memory in self.world.player.knowledge.known_memories.values()))

    def test_player_propose_to_npc_rejects_when_reputation_too_low(self):
        npc = engine.NPC(1, 1, name="Reserved")

        accepted = self.world.player_propose_to_npc(npc)

        self.assertFalse(accepted)
        self.assertNotIn("partner_id", self.world.player.social.family_ties)
        self.assertNotIn("partner_id", npc.social.family_ties)

    def test_evaluate_elections_can_choose_player_as_mayor(self):
        rival = engine.NPC(1, 1, name="Rival")
        rival.age = 30
        self.world.village_npcs = [rival]
        rival.knowledge.record_event(engine.MemoryEvent("murder", self.world.player.id, None, 1, 95, headline="Bad rumor"))
        self.world.player.social.fame = 10

        self.world.evaluate_elections(force=True)

        self.assertEqual(self.world.politics.get_office("Mayor").holder_id, self.world.player.id)

    def test_daily_governance_collects_taxes_and_pays_offices_without_minting_money(self):
        town_hall = engine.Building(0, 0, 6, 6, building_type="capital_hall", category="civic")
        town_hall.building_inventory["money"] = 100
        business = engine.Building(0, 0, 4, 4, building_type="general_store", category="commercial_workplace")
        business.building_inventory["money"] = 80
        self.world._set_building_owner(business, self.world.player)
        mayor = engine.NPC(1, 1, name="Mayor NPC")
        captain = engine.NPC(2, 2, name="Captain NPC")
        worker = engine.NPC(3, 3, name="Worker")
        mayor.age = captain.age = worker.age = 30
        mayor.economic.profession = "Mayor"
        captain.economic.profession = "Guard"
        worker.economic.profession = "Merchant"
        worker.economic.money = 50
        self.world.player.economic.profession = "Blacksmith"
        self.world.player.economic.money = 100
        self.world.buildings_by_id = {town_hall.id: town_hall, business.id: business}
        self.world.politics.town_hall_building_id = town_hall.id
        self.world.village_npcs = [mayor, captain, worker]
        self.world.politics.get_office("Mayor").holder_id = mayor.id
        self.world.politics.get_office("Captain of the Guard").holder_id = captain.id
        self.world.politics.tax_rate = 0.10
        self.world.game_time = 360

        total_before = (
            town_hall.building_inventory.get("money", 0)
            + business.building_inventory.get("money", 0)
            + self.world.player.economic.money
            + mayor.economic.money
            + captain.economic.money
            + worker.economic.money
        )

        self.world._run_daily_governance()

        total_after = (
            town_hall.building_inventory.get("money", 0)
            + business.building_inventory.get("money", 0)
            + self.world.player.economic.money
            + mayor.economic.money
            + captain.economic.money
            + worker.economic.money
        )

        self.assertEqual(total_before, total_after)
        self.assertEqual(business.building_inventory.get("money", 0), 72)
        self.assertEqual(self.world.player.economic.money, 90)
        self.assertEqual(worker.economic.money, 45)
        self.assertEqual(mayor.economic.money, 40)
        self.assertEqual(captain.economic.money, 30)
        self.assertEqual(town_hall.building_inventory.get("money", 0), 53)

    def test_adjust_city_tax_rate_broadcasts_memory_event(self):
        citizen = engine.NPC(1, 1, name="Citizen")
        self.world.village_npcs = [citizen]
        self.world.politics.get_office("Mayor").holder_id = self.world.player.id
        self.world.politics.tax_rate = 0.10

        changed = self.world.adjust_city_tax_rate(0.05)

        self.assertTrue(changed)
        self.assertEqual(self.world.politics.tax_rate, 0.15)
        self.assertTrue(any(memory.event_type == "raised_taxes" for memory in citizen.knowledge.known_memories.values()))
        self.assertLess(citizen.knowledge.get_reputation_towards(self.world.player), 0)

    def test_issue_political_warrant_deducts_treasury_and_pays_guards(self):
        town_hall = engine.Building(0, 0, 6, 6, building_type="capital_hall", category="civic")
        town_hall.building_inventory["money"] = 200
        guard = engine.NPC(1, 1, name="Guard")
        guard.age = 30
        guard.economic.profession = "Guard"
        self.world.village_npcs = [guard]
        self.world.buildings_by_id = {town_hall.id: town_hall}
        self.world.politics.town_hall_building_id = town_hall.id
        self.world.politics.get_office("Captain of the Guard").holder_id = self.world.player.id

        issued = self.world.issue_political_warrant("bounty", self.world.player.id)

        self.assertTrue(issued)
        self.assertEqual(town_hall.building_inventory.get("money", 0), 140)
        self.assertEqual(guard.economic.money, 60)
        self.assertEqual(guard.schedule.current_task, "execute_political_warrant")
        self.assertEqual(guard.task_target_entity_id, self.world.player.id)
        self.assertTrue(any(warrant.target_id == self.world.player.id for warrant in self.world.politics.active_warrants))

    def test_capital_hall_exposes_govern_action_for_player_office_holder(self):
        building = engine.Building(0, 0, 6, 6, building_type="capital_hall", category="civic")
        self.world.politics.get_office("Mayor").holder_id = self.world.player.id

        actions = self.world._get_actions_for_entity({"type": "building", "data": building, "name": building.building_type})

        self.assertIn("Govern", actions)

    def test_reputation_based_reactions_use_memory_and_disguise(self):
        guard = engine.NPC(self.world.player.x + 1, self.world.player.y, name="Guard")
        guard.economic.profession = "Guard"
        baker = engine.NPC(self.world.player.x + 2, self.world.player.y, name="Baker")
        baker.economic.profession = "Baker"
        self.world.npcs = [guard, baker]
        self.world.game_time = 10
        for npc in self.world.npcs:
            npc.knowledge.record_event(engine.MemoryEvent("murder", self.world.player.id, 55, 1, 95, headline="Murder"))
            fov = engine.np.zeros((config.WORLD_HEIGHT, config.WORLD_WIDTH), dtype=bool)
            fov[self.world.player.y, self.world.player.x] = True
            self.world.npc_fov_maps[npc.id] = fov

        self.world._handle_reputation_based_reactions()

        self.assertTrue(guard.combat.is_hostile_to_player)
        self.assertEqual(baker.schedule.current_task, "fleeing_from_player")

        guard.combat.is_hostile_to_player = False
        guard.schedule.current_task = "idle"
        baker.schedule.current_task = "idle"
        self.world.player.equipment.equipped_armor["head"] = "hooded_cowl"

        self.world._handle_reputation_based_reactions()

        self.assertFalse(guard.combat.is_hostile_to_player)
        self.assertEqual(baker.schedule.current_task, "idle")

    def test_gossip_behavior_queues_async_flavor_request(self):
        speaker = engine.NPC(5, 5, name="Speaker")
        listener = engine.NPC(6, 5, name="Listener")
        self.world.village_npcs = [speaker, listener]
        memory = engine.MemoryEvent("murder", speaker.id, listener.id, 10, 80, headline="A murder happened")
        speaker.knowledge.record_event(memory)
        self.world.game_time = (17 - ((min(speaker.id, listener.id) + max(speaker.id, listener.id)) % 17)) % 17

        with patch.object(self.world._gossip_llm_service, "submit", return_value=True) as mock_submit:
            shared = speaker.ai_brain.gossip_behavior.take_turn(speaker, self.world)

        self.assertTrue(shared)
        mock_submit.assert_called_once()
        submit_kwargs = mock_submit.call_args.kwargs
        self.assertIs(submit_kwargs["speaker"], speaker)
        self.assertIs(submit_kwargs["memory_event"], memory)
        self.assertEqual(submit_kwargs["subject_name"], speaker.name)
        self.assertEqual(submit_kwargs["target_name"], listener.name)

    def test_drain_gossip_flavor_text_queue_spawns_floating_text_and_chat_log(self):
        speaker = engine.NPC(self.world.player.x + 1, self.world.player.y, name="Speaker")
        self.world.npcs = [speaker]
        self.world.village_npcs = []
        service = MagicMock()
        service.poll_completed.return_value = [
            SimpleNamespace(
                speaker_id=speaker.id,
                speaker_position=(speaker.x, speaker.y),
                text="The miller saw blood by the ford.",
            )
        ]
        self.world._gossip_llm_service = service

        self.world._drain_gossip_flavor_text_queue()

        self.assertTrue(any(getattr(effect, "text", "") == "The miller saw blood by the ford." for effect in self.world.visual_effects))
        self.assertEqual(self.world.chat_log[-1], "Speaker: The miller saw blood by the ford.")

    def test_async_llm_gossip_service_times_out_to_fallback(self):
        service = AsyncLLMGossipService(response_timeout_seconds=0.01, request_timeout_seconds=0.5)
        speaker = engine.NPC(3, 4, name="Speaker")
        memory = engine.MemoryEvent("murder", None, 99, 1, 80, headline="A murder happened")

        with patch.object(service, "_generate_text", side_effect=lambda request: (time.sleep(0.05), "")[1]):
            submitted = service.submit(speaker=speaker, memory_event=memory, subject_name="Someone", target_name="Victim")
            results = []
            for _ in range(10):
                time.sleep(0.01)
                results = service.poll_completed()
                if results:
                    break

        self.assertTrue(submitted)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].text, "Did you hear about Victim?")
        self.assertTrue(results[0].used_fallback)

    def test_async_llm_gossip_service_calls_local_ollama_and_sanitizes_response(self):
        service = AsyncLLMGossipService(response_timeout_seconds=0.5, request_timeout_seconds=0.5)
        speaker = engine.NPC(3, 4, name="Speaker")
        memory = engine.MemoryEvent("murder", speaker.id, None, 1, 80, headline="A murder happened")

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "\"Too many words in this sentence for the strict gossip limit indeed right now\""}
        mock_response.raise_for_status.return_value = None

        with patch("services.llm_gossip.requests.post", return_value=mock_response) as mock_post:
            service.submit(speaker=speaker, memory_event=memory, subject_name=speaker.name, target_name="")
            for _ in range(20):
                results = service.poll_completed()
                if results:
                    break
                time.sleep(0.01)
            else:
                self.fail("Expected completed gossip result.")

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].used_fallback)
        self.assertLessEqual(len(results[0].text.split()), 15)
        self.assertNotIn('"', results[0].text)
        post_kwargs = mock_post.call_args.kwargs
        self.assertEqual(mock_post.call_args.args[0], "http://localhost:11434/api/generate")
        self.assertEqual(post_kwargs["json"]["model"], "llama3.2:latest")
        self.assertEqual(
            post_kwargs["json"]["system"],
            "You are a medieval villager. Write a single, short sentence of dialogue gossiping about the provided event. Do not use quotes. Keep it under 15 words.",
        )
        self.assertEqual(post_kwargs["json"]["prompt"], f"Event: {memory.event_type}, Subject: {speaker.name}.")

    def test_async_llm_gossip_service_submits_chronicle_prompt(self):
        service = AsyncLLMGossipService(response_timeout_seconds=0.5, request_timeout_seconds=0.5)
        scribe = engine.NPC(3, 4, name="Scribe")
        memories = [
            engine.MemoryEvent("murder", 1, 2, 1, 90, headline="A murder stained the square."),
            engine.MemoryEvent("unpaid_wages", 3, 4, 2, 70, headline="Workers walked out unpaid."),
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "The town remembers blood, debt, and uneasy reckonings. Scribes set it down faithfully."}
        mock_response.raise_for_status.return_value = None

        with patch("services.llm_gossip.requests.post", return_value=mock_response) as mock_post:
            submitted = service.submit_chronicle(scribe=scribe, memory_events=memories, building_id="library_1", title_hint="Year 0 Chronicle")
            for _ in range(20):
                results = service.poll_completed()
                if results:
                    break
                time.sleep(0.01)
            else:
                self.fail("Expected completed chronicle result.")

        self.assertTrue(submitted)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].request_type, "chronicle")
        self.assertIn("memory_ids", results[0].metadata)
        post_kwargs = mock_post.call_args.kwargs
        self.assertEqual(
            post_kwargs["json"]["system"],
            "You are a medieval historian. Write a single, dramatic paragraph (max 3 sentences) summarizing the following historical events for a town chronicle.",
        )
        self.assertIn("Historical Events:", post_kwargs["json"]["prompt"])
        self.assertIn("A murder stained the square.", post_kwargs["json"]["prompt"])

    def test_scribe_chronicle_completion_creates_written_book_item_reference(self):
        scribe = engine.NPC(5, 5, name="Alda")
        scribe.economic.profession = "Scribe"
        scribe.career.set_role("Scribe")
        scribe.schedule.current_task = "at work"
        library = engine.Building(4, 4, 6, 6, building_type="library", category="commercial_workplace")
        self.world.buildings_by_id[library.id] = library
        scribe.schedule.work_building_id = library.id
        self.world.npcs = [scribe]
        memories = [
            engine.MemoryEvent("murder", 1, 2, 1, 90, headline="A murder stained the square."),
            engine.MemoryEvent("unpaid_wages", 3, 4, 2, 70, headline="Workers walked out unpaid."),
        ]
        for memory in memories:
            scribe.knowledge.record_event(memory)

        service = MagicMock()
        service.submit_chronicle.return_value = True
        service.poll_completed.return_value = [
            SimpleNamespace(
                request_type="chronicle",
                speaker_id=scribe.id,
                text="The square ran red, and the town still whispers of unpaid hands.",
                metadata={
                    "building_id": library.id,
                    "memory_ids": [memory.id for memory in memories],
                    "title_hint": "Year 0 Chronicle",
                },
            )
        ]
        self.world._gossip_llm_service = service

        started = self.world.try_begin_scribe_chronicle(scribe)
        self.world._drain_gossip_flavor_text_queue()

        self.assertTrue(started)
        book = library.building_inventory.get_item_reference("book_chronicle")
        self.assertIsNotNone(book)
        self.assertEqual(book.written_text, "The square ran red, and the town still whispers of unpaid hands.")
        self.assertEqual(book.crafter_name, "Alda")
        self.assertEqual(book.title, "Year 0 Chronicle")
        self.assertIn(memories[0].id, scribe.knowledge.chronicle_written_memory_ids)

    def test_trade_purchase_preserves_written_chronicle_item_reference(self):
        merchant = engine.NPC(0, 0, name="Merchant")
        merchant.economic.profession = "Merchant"
        merchant.schedule.work_building_id = "shop_1"
        shop = SimpleNamespace(building_type="general_store", building_inventory=Inventory({"money": 0}))
        chronicle = ItemReference("book_chronicle", quality="Fine", crafter_name="Alda", written_text="A fearful year.", title="Year 0 Chronicle")
        shop.building_inventory.add_item_reference(chronicle)
        self.world.trade_ui_active = True
        self.world.trade_ui_npc_target = merchant
        self.world.trade_ui_player_selling = False
        self.world.trade_ui_merchant_inventory_snapshot = [("book_chronicle", 1, chronicle.value)]
        self.world.trade_ui_merchant_item_index = 0
        self.world.buildings_by_id = {"shop_1": shop}
        self.world.player.economic.money = chronicle.value

        self.world.handle_trade_action()

        owned_book = self.world.player.get_item_reference("book_chronicle")
        self.assertIsNotNone(owned_book)
        self.assertEqual(owned_book.written_text, "A fearful year.")
        self.assertEqual(owned_book.title, "Year 0 Chronicle")

    def test_player_attempt_read_book_uses_written_text_from_item_reference(self):
        chronicle = ItemReference("book_chronicle", crafter_name="Alda", written_text="A fearful year.", title="Year 0 Chronicle")
        self.world.player.add_item_reference(chronicle)

        self.world.player_attempt_read_book("book_chronicle")

        self.assertEqual(self.world.chat_log[-1], "Year 0 Chronicle: A fearful year.")

    def test_noticeboard_claim_marks_task_for_player_and_removes_it_from_npc_pool(self):
        blueprint = self.world.place_construction_blueprint("wooden_chair", 8, 8)
        task = self.world.town_board.get_open_tasks(blueprint.id)[0]

        claimed = self.world.claim_noticeboard_task(task.id)

        self.assertTrue(claimed)
        self.assertEqual(task.assigned_entity_id, self.world.player.id)
        self.assertEqual(task.status, "claimed")
        self.assertIn(task.id, self.world.player.knowledge.claimed_tasks)
        self.assertNotIn(task, self.world.town_board.get_open_tasks(blueprint.id))

    def test_player_deposit_resolves_matching_claimed_noticeboard_task(self):
        self.world.player.add_item("wooden_plank", 1)
        blueprint = self.world.place_construction_blueprint("wooden_chair", 9, 9)
        task = self.world.town_board.get_open_tasks(blueprint.id)[0]
        self.world.claim_noticeboard_task(task.id)

        deposited = self.world.deposit_actor_material_into_blueprint(self.world.player, blueprint, "wooden_plank")

        self.assertTrue(deposited)
        self.assertNotIn(task.id, self.world.player.knowledge.claimed_tasks)
        self.assertEqual(task.status, "complete")

    def test_player_attempt_build_places_blueprint_then_deposits_materials_one_by_one(self):
        self.world.player.add_item("wooden_plank", 2)

        self.world.player_attempt_build("wooden_chair", 9, 9)
        blueprint = self.world.get_blueprint_at(9, 9)
        self.assertIsNotNone(blueprint)
        self.assertEqual(blueprint.deposited_inventory.get("wooden_plank", 0), 0)

        self.world.player_attempt_build("wooden_chair", 9, 9)
        blueprint = self.world.get_blueprint_at(9, 9)
        self.assertIsNotNone(blueprint)
        self.assertEqual(blueprint.deposited_inventory.get("wooden_plank", 0), 1)
        self.assertIsInstance(blueprint.deposited_inventory, Inventory)

        self.world.player_attempt_build("wooden_chair", 9, 9)
        self.assertIsNone(self.world.get_blueprint_at(9, 9))
        self.assertEqual(self.world.get_tile_at(9, 9).name, DECORATION_ITEM_DEFINITIONS["wooden_chair"]["name"])

    def test_unemployed_npc_hauls_ground_material_to_blueprint_with_object_preservation(self):
        npc = engine.NPC(2, 2, name="Laborer")
        npc.economic.profession = "Unemployed"
        npc.ai_brain.assign_profession("Unemployed")
        self.world.village_npcs.append(npc)
        blueprint = self.world.place_construction_blueprint("wooden_chair", 6, 6)
        self.world.items_on_map[(2, 2)] = Inventory()
        self.world.items_on_map[(2, 2)].add_item("wooden_plank", 1, quality="Fine", crafter_name="Carpenter")
        plank = self.world.items_on_map[(2, 2)].get_item_reference("wooden_plank")

        assigned = npc.ai_brain.take_turn(npc, self.world)
        picked_up = npc.ai_brain.take_turn(npc, self.world)
        npc.x, npc.y = 6, 6
        npc.schedule.current_path = []
        deposited = npc.ai_brain.take_turn(npc, self.world)

        self.assertTrue(assigned)
        self.assertTrue(picked_up)
        self.assertTrue(deposited)
        self.assertIs(self.world.get_blueprint_at(6, 6), blueprint)
        self.assertIs(blueprint.deposited_inventory.get_item_reference("wooden_plank"), plank)
        self.assertEqual(blueprint.deposited_inventory.get("wooden_plank", 0), 1)
        self.assertEqual(len(self.world.town_board.get_open_tasks(blueprint.id)), 1)

    def test_produce_sub_task_sells_raw_log_to_lumber_mill_with_item_object_preserved(self):
        worker = engine.NPC(0, 0, name="Woodcutter")
        worker.economic.money = 0
        worker.economic.npc_inventory.add_item("raw_log", 1, quality="Masterwork", crafter_name="Woodcutter")
        item_reference = worker.economic.npc_inventory.get_item_reference("raw_log")
        lumber_mill = engine.Building(0, 0, 5, 5, building_type="lumber_mill", category="industrial_workplace")
        lumber_mill.building_inventory["money"] = 200
        sub_task_data = {
            "consumes_item_from_npc_inventory": {"raw_log": 1},
            "deposits_item_to_workplace": {"raw_log": 1},
            "produces_item_at_workplace": {},
        }

        with patch.object(self.world, "_get_village_for_npc", return_value=None):
            result = self.world._produce_sub_task_output(worker, lumber_mill, sub_task_data)

        stored_item = lumber_mill.building_inventory.get_item_reference("raw_log")
        self.assertTrue(result)
        self.assertEqual(worker.economic.money, item_reference.value)
        self.assertEqual(lumber_mill.building_inventory.get("money", 0), 200 - item_reference.value)
        self.assertIs(stored_item, item_reference)
        self.assertEqual(stored_item.crafter_name, "Woodcutter")

    def test_workplace_supply_chain_crafts_recipe_driven_goods_for_lumber_mill_foreman(self):
        foreman = engine.NPC(0, 0, name="Foreman")
        foreman.economic.profession = "Lumber Mill Foreman"
        foreman.ai_brain.assign_profession("Lumber Mill Foreman")
        lumber_mill = engine.Building(0, 0, 5, 5, building_type="lumber_mill", category="industrial_workplace")
        foreman.schedule.work_building_id = lumber_mill.id
        self.world.buildings_by_id = {lumber_mill.id: lumber_mill}
        lumber_mill.building_inventory.add_item("raw_log", 1, quality="Masterwork", crafter_name="Woodcutter")

        with patch.object(self.world, "_find_nearest_building_of_type", return_value=None), \
             patch.object(self.world, "_get_village_for_npc", return_value=None), \
             patch("entities.items.random.random", return_value=0.5):
            handled = update_npc_work_sub_tasks(self.world, foreman)

        crafted_item = lumber_mill.building_inventory.get_item_reference("wooden_plank")
        self.assertTrue(handled)
        self.assertEqual(lumber_mill.building_inventory.get("raw_log", 0), 0)
        self.assertIsNotNone(crafted_item)
        self.assertEqual(crafted_item.crafter_name, "Foreman")

    def test_workplace_supply_chain_exports_finished_goods_to_general_store(self):
        crafter = engine.NPC(0, 0, name="Smith")
        smithy = engine.Building(0, 0, 5, 5, building_type="blacksmith_shop", category="industrial_workplace")
        general_store = engine.Building(10, 0, 5, 5, building_type="general_store", category="commercial_workplace")
        general_store.building_inventory["money"] = 300
        smithy.building_inventory.add_item("shears", 1, quality="Masterwork", crafter_name="Smith")
        finished_item = smithy.building_inventory.get_item_reference("shears")

        with patch.object(self.world, "_find_nearest_building_of_type", side_effect=lambda npc, building_type: general_store if building_type == "general_store" else None), \
             patch.object(self.world, "_get_village_for_npc", return_value=None):
            exported = self.world._attempt_workplace_export(crafter, smithy)

        exported_item = general_store.building_inventory.get_item_reference("shears")
        self.assertEqual(exported, 1)
        self.assertIs(exported_item, finished_item)
        self.assertEqual(smithy.building_inventory.get("money", 0), finished_item.value)
        self.assertEqual(general_store.building_inventory.get("money", 0), 300 - finished_item.value)

    def test_handle_npc_goal_give_item_transfers_from_economic_inventory(self):
        villager = engine.NPC(0, 0, name="Helpful Villager")
        villager.economic.npc_inventory["apple"] = 2

        self.world._handle_npc_goal(villager, "give_item", "")

        self.assertEqual(villager.economic.npc_inventory["apple"], 1)
        self.assertTrue(self.world.player.has_item("apple", 1))
        self.assertIn("gave you Apple", self.world.chat_log[-1])

    def test_handle_npc_goal_give_item_requires_component_inventory(self):
        world = object.__new__(engine.World)
        world.player = engine.Player(0, 0)
        world.chat_log = []
        world.ui_requests = []
        world.add_message_to_chat_log = engine.World.add_message_to_chat_log.__get__(world, engine.World)
        world.request_close_dialogue = engine.World.request_close_dialogue.__get__(world, engine.World)
        world.get_entity_display_name = engine.World.get_entity_display_name.__get__(world, engine.World)

        npc = SimpleNamespace(
            name="Legacy Giver",
            inventory=[SimpleNamespace(name="Apple")],
            economic=SimpleNamespace(npc_inventory={}),
        )

        engine.World._handle_npc_goal(world, npc, "give_item", "")

        self.assertFalse(world.player.has_item("apple", 1))
        self.assertEqual(len(npc.inventory), 1)
        self.assertIn("has nothing to give", world.chat_log[-1])

    def test_npc_inventory_uses_dict_compatible_wrapper(self):
        npc = engine.NPC(0, 0, name="Inventory NPC")

        npc.add_item("apple", 2)
        npc.economic.npc_inventory["apple"] = npc.economic.npc_inventory.get("apple", 0) + 1

        self.assertIsInstance(npc.economic.npc_inventory, dict)
        self.assertEqual(npc.economic.npc_inventory["apple"], 3)

        npc.economic.npc_inventory["apple"] = 0
        self.assertNotIn("apple", npc.economic.npc_inventory)

    def test_npc_equipment_slots_accept_string_assignment_with_compatibility_checks(self):
        npc = engine.NPC(0, 0, name="Equipped NPC")

        npc.equipment.weapon = "rusty_sword"
        npc.equipment.body = "leather_jerkin"

        self.assertTrue(npc.equipment.weapon)
        self.assertEqual(npc.equipment.weapon, "rusty_sword")
        self.assertEqual(str(npc.equipment.body), "leather_jerkin")
        self.assertIn(npc.equipment.weapon, ITEM_DEFINITIONS)
        self.assertEqual(npc.equipment.weapon.item.name, "Rusty Sword")

    def test_npc_inventory_process_tick_rots_items_and_preserves_visual_lookup(self):
        npc = engine.NPC(0, 0, name="Perishable NPC")
        npc.add_item("apple", 2)

        with patch("entities.items.random.random", side_effect=[0.0, 1.0]):
            npc.economic.npc_inventory.process_tick()

        self.assertEqual(npc.economic.npc_inventory.get("apple", 0), 1)
        self.assertEqual(npc.economic.npc_inventory.get("rotten_food", 0), 1)
        rotten_item = npc.economic.npc_inventory.get_item_reference("rotten_food")
        self.assertIsNotNone(rotten_item)
        self.assertEqual(rotten_item.char, ITEM_DEFINITIONS["rotten_food"]["char"])
        self.assertEqual(rotten_item.color, ITEM_DEFINITIONS["rotten_food"]["color"])

    def test_item_reference_tracks_default_durability_state(self):
        npc = engine.NPC(0, 0, name="Durable NPC")
        npc.add_item("rusty_sword", 1)

        weapon = npc.economic.npc_inventory.get_item_reference("rusty_sword")

        self.assertIsNotNone(weapon)
        self.assertEqual(weapon.current_durability, ITEM_DEFINITIONS["rusty_sword"]["properties"]["max_durability"])
        self.assertEqual(weapon.age_in_ticks, 0)

    def test_item_quality_and_crafter_metadata_preserve_base_item_id(self):
        npc = engine.NPC(0, 0, name="Wally")
        npc.add_item("rusty_sword", 1, quality="Fine", crafter_name="Wally")

        weapon = npc.economic.npc_inventory.get_item_reference("rusty_sword")

        self.assertIsNotNone(weapon)
        self.assertEqual(weapon.key, "rusty_sword")
        self.assertEqual(weapon.name, "Fine Rusty Sword")
        self.assertIn("Crafted by Wally.", weapon.description)
        self.assertEqual(weapon.max_durability, 48)
        self.assertEqual(weapon.current_durability, 48)
        self.assertEqual(weapon.value, 36)

    def test_npc_craft_item_rolls_quality_and_sets_crafter_name(self):
        npc = engine.NPC(0, 0, name="Smith")
        npc.economic.profession = "Blacksmith"
        npc.economic.work_performance = 90

        with patch("entities.items.random.random", return_value=0.95):
            quality = npc.craft_item("rusty_sword", 1)

        weapon = npc.get_equipped_item_reference("weapon") or npc.economic.npc_inventory.get_item_reference("rusty_sword")
        self.assertEqual(quality, "Masterwork")
        self.assertEqual(weapon.quality, "Masterwork")
        self.assertEqual(weapon.crafter_name, "Smith")
        self.assertEqual(weapon.name, "Masterwork Rusty Sword")
        self.assertGreater(npc.skills.experience["crafting"], 0)

    def test_world_npc_schedule_update_ticks_inventory_spoilage(self):
        npc = engine.NPC(0, 0, name="Scheduled NPC")
        npc.add_item("apple", 1)
        self.world.npcs.append(npc)

        with patch("entities.items.random.random", return_value=0.0):
            self.world._update_npc_schedules()

        self.assertEqual(npc.economic.npc_inventory.get("apple", 0), 0)
        self.assertEqual(npc.economic.npc_inventory.get("rotten_food", 0), 1)

    def test_building_inventory_preserves_item_objects_when_transferred_from_npc(self):
        npc = engine.NPC(0, 0, name="Smith")
        npc.add_item("rusty_sword", 1, quality="Masterwork", crafter_name="Smith")
        sword = npc.economic.npc_inventory.get_item_reference("rusty_sword")
        sword.current_durability = 17
        building = engine.Building(0, 0, 3, 3, building_type="house")

        moved = self.world._move_item_between_inventories(
            npc.economic.npc_inventory,
            building.building_inventory,
            "rusty_sword",
            1,
        )

        stored_sword = building.building_inventory.get_item_reference("rusty_sword")
        self.assertEqual(moved, 1)
        self.assertIsInstance(building.building_inventory, dict)
        self.assertEqual(building.building_inventory.get("rusty_sword", 0), 1)
        self.assertEqual(stored_sword.quality, "Masterwork")
        self.assertEqual(stored_sword.crafter_name, "Smith")
        self.assertEqual(stored_sword.current_durability, 17)

    def test_tick_world_item_inventories_processes_building_ground_and_tile_loot(self):
        building = engine.Building(0, 0, 3, 3, building_type="house")
        building.building_inventory.add_item("apple", 1)
        self.world.buildings_by_id = {building.id: building}
        self.world.items_on_map[(4, 4)] = Inventory({"apple": 1})

        tile = self.world.get_tile_at(self.world.player.x, self.world.player.y)
        tile.properties["loot"] = Inventory({"apple": 1})

        with patch("entities.items.random.random", return_value=0.0):
            self.world._tick_world_item_inventories()

        self.assertEqual(building.building_inventory.get("rotten_food", 0), 1)
        self.assertEqual(self.world.items_on_map[(4, 4)].get("rotten_food", 0), 1)
        self.assertEqual(tile.properties["loot"].get("rotten_food", 0), 1)

    def test_npc_attempt_fish_uses_schedule_work_building_id(self):
        fisher = engine.NPC(0, 0, name="Fisher")
        fisher.schedule.work_building_id = "dock_1"
        self.world.buildings_by_id = {
            "dock_1": SimpleNamespace(building_inventory={}, building_type="dock")
        }

        with patch.object(self.world, "get_tile_at", return_value=SimpleNamespace(name="Water")), \
             patch("engine.random.random", return_value=0.0), \
             patch("engine.random.choice", return_value="fish"):
            self.world.npc_attempt_fish(fisher, 5, 5)

        self.assertEqual(self.world.buildings_by_id["dock_1"].building_inventory["raw_fish"], 1)

    def test_player_attempt_attack_marks_target_hostile_via_combat_state(self):
        target = engine.NPC(1, 1, name="Target")
        target.combat.is_hostile_to_player = False

        with patch.object(self.world, "_call_llm", return_value=None):
            self.world.player_attempt_attack(target)

        self.assertTrue(target.combat.is_hostile_to_player)

    def test_player_attack_grants_melee_skill_experience_on_hit(self):
        target = engine.NPC(1, 1, name="Target")
        starting_xp = self.world.player.skills.experience.get("melee", 0)

        with patch.object(self.world, "_call_llm", return_value=json.dumps({
            "hit": True,
            "damage_dealt": 3,
            "narrative_feedback": "You land a solid blow.",
        })):
            self.world.player_attempt_attack(target)

        self.assertGreater(self.world.player.skills.experience["melee"], starting_xp)

    def test_handle_witness_reaction_uses_schedule_state_for_reporting(self):
        witness = engine.NPC(2, 2, name="Witness")
        witness.combat.is_hostile_to_player = False

        sheriff_office = SimpleNamespace(global_center_x=10, global_center_y=12)
        with patch.object(self.world, "_call_llm", return_value=json.dumps({"reaction": "report_crime", "dialogue": "Guards!"})), \
             patch.object(self.world, "_find_nearest_building_of_type", return_value=sheriff_office):
            self.world._handle_witness_reaction(witness, "theft", self.world.player)

        self.assertEqual(witness.schedule.current_task, "going_to_report_crime")
        self.assertEqual(witness.task_target_coords, (10, 12))
        self.assertEqual(witness.schedule.current_path, [])

    def test_player_attempt_ride_animal_clears_schedule_pathing(self):
        mount = engine.Animal(3, 4, name="Deer", animal_type="deer")
        mount.is_tame = True
        mount.owner = self.world.player
        mount.schedule.current_path = [(3, 4), (4, 4)]
        mount.schedule.current_destination_coords = (4, 4)

        self.world.player_attempt_ride_animal(mount)

        self.assertEqual(mount.schedule.current_path, [])
        self.assertIsNone(mount.schedule.current_destination_coords)

    def test_handle_npc_work_sub_tasks_marks_missing_workplace_as_idle_confused(self):
        worker = engine.NPC(0, 0, name="Worker")
        worker.economic.profession = "Farmer"
        worker.schedule.work_building_id = "missing_farm"

        handled = update_npc_work_sub_tasks(self.world, worker)

        self.assertTrue(handled)
        self.assertEqual(worker.schedule.current_task, "idle_confused")

    def test_execute_completed_work_sub_task_uses_command_registry(self):
        worker = engine.NPC(0, 0, name="Miller")
        worker.economic.profession = "Miller"
        work_building = SimpleNamespace(building_inventory={"wheat": 2, "flour": 0})

        self.world._execute_completed_work_sub_task(
            worker,
            work_building,
            "mill_flour",
            {"id": "mill_flour"},
        )

        self.assertEqual(work_building.building_inventory["wheat"], 1)
        self.assertEqual(work_building.building_inventory["flour"], 1)

    def test_execute_completed_work_sub_task_degrades_and_breaks_matching_tool(self):
        from entities.tree import Tree

        worker = engine.NPC(0, 0, name="Woodcutter")
        worker.economic.profession = "Woodcutter"
        worker.add_item("axe_stone", 1)
        worker.equipment.weapon = "axe_stone"
        worker.economic.npc_inventory.get_item_reference("axe_stone").current_durability = 1
        worker.sub_task_target_coords = (2, 3)
        work_building = SimpleNamespace(building_inventory={})
        tree = Tree(2, 3)

        with patch.object(self.world, "get_tile_at", return_value=tree), \
             patch.object(self.world, "_change_map_tile"):
            self.world._execute_completed_work_sub_task(worker, work_building, "chop_trees", {})

        self.assertFalse(worker.equipment.weapon)
        self.assertEqual(worker.economic.npc_inventory.get("axe_stone", 0), 0)
        self.assertEqual(worker.economic.npc_inventory.get("broken_tool_handle", 0), 1)
        self.assertGreaterEqual(worker.economic.npc_inventory.get("raw_log", 0), 1)

    def test_npc_eat_from_inventory_reduces_physical_hunger(self):
        npc = engine.NPC(0, 0, name="Hungry NPC")
        npc.physical.hunger = 40
        inventory = Inventory({"apple": 1})

        found_food, consumed_food = self.world._npc_eat_from_inventory(npc, inventory)

        self.assertTrue(found_food)
        self.assertTrue(consumed_food)
        self.assertLess(npc.physical.hunger, 40)
        self.assertNotIn("apple", inventory)


class TestNPCBehaviorSystem(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()

        mock_npc_data = { "name": "Test NPC", "personality": "test", "dialogue": ["Hi"] }
        self.mock_call_llm.return_value = json.dumps(mock_npc_data)

        self.world = World(seed=0)

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def test_npc_seeks_warmth_when_freezing(self):
        from data.decorations import DECORATION_ITEM_DEFINITIONS
        from data.tiles import TILE_DEFINITIONS
        from tile_types import Tile
        from entities.base import NPC
        from config import NPC_SCHEDULE_UPDATE_INTERVAL

        # 1. Create a freezing environment and an NPC
        self.world.current_season_index = 3 # Winter
        npc = NPC(x=self.world.player.x + 5, y=self.world.player.y, name="Test NPC")
        npc.economic.profession = "Farmer"
        self.world.village_npcs.append(npc)

        # 2. Ensure a clear path and place a heat source
        fire_x, fire_y = npc.x + 3, npc.y
        plains_def = TILE_DEFINITIONS["plains"]
        plains_tile = Tile(char=plains_def['char'], color=plains_def['color'], passable=True, name="Plains", properties={})

        # Also clear the NPC's starting tile
        self.world.get_tile_at(npc.x, npc.y) # Ensure chunk is generated
        c_chunk_x, c_chunk_y = npc.x // config.CHUNK_SIZE, npc.y // config.CHUNK_SIZE
        c_local_x, c_local_y = npc.x % config.CHUNK_SIZE, npc.y % config.CHUNK_SIZE
        self.world.chunks[c_chunk_y][c_chunk_x].tiles[c_local_y][c_local_x] = plains_tile

        # Clear a path for the NPC
        for y_offset in range(-2, 3):
            for x_offset in range(0, 6):
                clear_x, clear_y = npc.x + x_offset, npc.y + y_offset
                self.world.get_tile_at(clear_x, clear_y) # Ensure chunk is generated
                c_chunk_x, c_chunk_y = clear_x // config.CHUNK_SIZE, clear_y // config.CHUNK_SIZE
                c_local_x, c_local_y = clear_x % config.CHUNK_SIZE, clear_y % config.CHUNK_SIZE
                self.world.chunks[c_chunk_y][c_chunk_x].tiles[c_local_y][c_local_x] = plains_tile

        fire_pit_def = DECORATION_ITEM_DEFINITIONS["fire_pit_lit"]
        fire_pit_tile = Tile(char=fire_pit_def['char'], color=fire_pit_def['color'], passable=False, name="fire_pit_lit", properties=fire_pit_def['properties'].copy())

        chunk_x, chunk_y = fire_x // config.CHUNK_SIZE, fire_y // config.CHUNK_SIZE
        local_x, local_y = fire_x % config.CHUNK_SIZE, fire_y % config.CHUNK_SIZE
        self.world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = fire_pit_tile

        # Ensure there are no random hostile creatures spawned near the NPC that would cause them to flee instead
        self.world.npcs = [n for n in self.world.npcs if n.id == npc.id]

        # 3. Manually update NPC temperature to freezing
        npc.physical.temperature = 34.0
        survival.update_entity_temperature(self.world, npc)
        self.assertIn("Freezing", npc.physical.status_effects)

        # 4. Advance time to ensure the schedule update runs
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL

        # 5. Run the NPC schedule update
        self.world._update_npc_schedules()

        # 6. Assert that the NPC is now seeking warmth and pathfinding to the fire
        self.assertEqual(npc.schedule.current_task, "seeking_warmth")
        self.assertIsNotNone(npc.schedule.current_path)
        # The path destination should be adjacent to the fire, not on it, because the fire is not passable.
        path_dest = npc.schedule.current_destination_coords
        self.assertIsNotNone(path_dest)
        self.assertTrue(abs(path_dest[0] - fire_x) + abs(path_dest[1] - fire_y) == 1)

    def test_npc_brain_consumes_food_from_inventory_and_resumes_work(self):
        npc = engine.NPC(x=self.world.player.x + 2, y=self.world.player.y, name="Hungry Worker")
        npc.schedule.current_task = "at work"
        npc.physical.hunger = 80
        npc.economic.npc_inventory.add_item("apple", 1)

        handled = npc.ai_brain.take_turn(npc, self.world)

        self.assertTrue(handled)
        self.assertLess(npc.physical.hunger, 80)
        self.assertEqual(npc.schedule.current_task, "at work")
        self.assertEqual(npc.economic.npc_inventory.get("apple", 0), 0)

    def test_npc_brain_consumes_drink_from_inventory_and_resumes_work(self):
        npc = engine.NPC(x=self.world.player.x + 2, y=self.world.player.y, name="Thirsty Worker")
        npc.schedule.current_task = "going_to_work"
        npc.physical.thirst = 85
        npc.economic.npc_inventory.add_item("water_flask", 1)

        handled = npc.ai_brain.take_turn(npc, self.world)

        self.assertTrue(handled)
        self.assertLess(npc.physical.thirst, 85)
        self.assertEqual(npc.schedule.current_task, "going_to_work")
        self.assertEqual(npc.economic.npc_inventory.get("water_flask", 0), 0)

    def test_npc_brain_seeks_water_when_desperate_without_drink(self):
        npc = engine.NPC(x=10, y=10, name="Desperate NPC")
        npc.schedule.current_task = "at work"
        npc.physical.thirst = 95

        with patch.object(self.world, "_find_nearest_water_source", return_value=(12, 10)), \
             patch.object(self.world, "get_tile_at", return_value=SimpleNamespace(passable=True, name="Well")), \
             patch.object(self.world, "calculate_path", return_value=[(10, 10), (11, 10), (12, 10)]):
            handled = npc.ai_brain.take_turn(npc, self.world)

        self.assertTrue(handled)
        self.assertEqual(npc.schedule.current_task, "seeking_water")
        self.assertEqual(npc.schedule.current_destination_coords, (12, 10))
        self.assertEqual(npc.schedule.previous_task, "at work")

    def test_npc_brain_seeks_food_source_when_desperate_without_food(self):
        npc = engine.NPC(x=10, y=10, name="Starving NPC")
        npc.schedule.current_task = "at work"
        npc.physical.hunger = 95
        tavern = engine.Building(14, 9, 4, 4, building_type="tavern", category="commercial_workplace")

        with patch.object(self.world, "_find_nearest_food_source", return_value=tavern), \
             patch.object(self.world, "calculate_path", return_value=[(10, 10), (11, 10), (12, 10), (13, 10), (14, 10)]):
            handled = npc.ai_brain.take_turn(npc, self.world)

        self.assertTrue(handled)
        self.assertEqual(npc.schedule.current_task, "seeking_food")
        self.assertEqual(npc.schedule.current_destination_coords, (tavern.global_center_x, tavern.global_center_y))
        self.assertEqual(npc.schedule.previous_task, "at work")



class TestPopulateNpcsCompatibility(unittest.TestCase):
    def test_populate_npcs_spawns_traveling_merchants_when_missing(self):
        world = engine.World.__new__(engine.World)
        world.npcs = []
        world._spawn_traveling_merchants = unittest.mock.Mock()

        world._populate_npcs()

        world._spawn_traveling_merchants.assert_called_once_with()

    def test_populate_npcs_skips_spawning_when_traveling_merchant_exists(self):
        world = engine.World.__new__(engine.World)
        world.npcs = [SimpleNamespace(economic=SimpleNamespace(profession="Traveling Merchant"))]
        world._spawn_traveling_merchants = unittest.mock.Mock()

        world._populate_npcs()

        world._spawn_traveling_merchants.assert_not_called()
