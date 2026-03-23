import unittest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace
import json
import math
import uuid

import engine
from engine import World
import main
import rendering.console_renderer as console_renderer
from save_manager import save_game, load_game
from data.items import ITEM_DEFINITIONS
from data.decorations import DECORATION_ITEM_DEFINITIONS
import config
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
            handled = self.world._handle_npc_work_sub_tasks(foreman)

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

    def test_handle_npc_goal_give_item_supports_legacy_inventory_entries(self):
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

        self.assertTrue(world.player.has_item("apple", 1))
        self.assertEqual(npc.inventory, [])
        self.assertIn("gave you Apple", world.chat_log[-1])

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

        handled = self.world._handle_npc_work_sub_tasks(worker)

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
        self.world._update_npc_temperature(npc)
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
        npc.schedule.current_task = "Working (Farmer)"
        npc.physical.hunger = 80
        npc.economic.npc_inventory.add_item("apple", 1)

        handled = npc.ai_brain.take_turn(npc, self.world)

        self.assertTrue(handled)
        self.assertLess(npc.physical.hunger, 80)
        self.assertEqual(npc.schedule.current_task, "Working (Farmer)")
        self.assertEqual(npc.economic.npc_inventory.get("apple", 0), 0)

    def test_npc_brain_consumes_drink_from_inventory_and_resumes_work(self):
        npc = engine.NPC(x=self.world.player.x + 2, y=self.world.player.y, name="Thirsty Worker")
        npc.schedule.current_task = "going to work"
        npc.physical.thirst = 85
        npc.economic.npc_inventory.add_item("water_flask", 1)

        handled = npc.ai_brain.take_turn(npc, self.world)

        self.assertTrue(handled)
        self.assertLess(npc.physical.thirst, 85)
        self.assertEqual(npc.schedule.current_task, "going to work")
        self.assertEqual(npc.economic.npc_inventory.get("water_flask", 0), 0)

    def test_npc_brain_seeks_water_when_desperate_without_drink(self):
        npc = engine.NPC(x=10, y=10, name="Desperate NPC")
        npc.schedule.current_task = "Working (Blacksmith)"
        npc.physical.thirst = 95

        with patch.object(self.world, "_find_nearest_water_source", return_value=(12, 10)), \
             patch.object(self.world, "get_tile_at", return_value=SimpleNamespace(passable=True, name="Well")), \
             patch.object(self.world, "calculate_path", return_value=[(10, 10), (11, 10), (12, 10)]):
            handled = npc.ai_brain.take_turn(npc, self.world)

        self.assertTrue(handled)
        self.assertEqual(npc.schedule.current_task, "seeking_water")
        self.assertEqual(npc.schedule.current_destination_coords, (12, 10))
        self.assertEqual(npc.schedule.previous_task, "Working (Blacksmith)")

    def test_npc_brain_seeks_food_source_when_desperate_without_food(self):
        npc = engine.NPC(x=10, y=10, name="Starving NPC")
        npc.schedule.current_task = "Working (Miller)"
        npc.physical.hunger = 95
        tavern = engine.Building(14, 9, 4, 4, building_type="tavern", category="commercial_workplace")

        with patch.object(self.world, "_find_nearest_food_source", return_value=tavern), \
             patch.object(self.world, "calculate_path", return_value=[(10, 10), (11, 10), (12, 10), (13, 10), (14, 10)]):
            handled = npc.ai_brain.take_turn(npc, self.world)

        self.assertTrue(handled)
        self.assertEqual(npc.schedule.current_task, "seeking_food")
        self.assertEqual(npc.schedule.current_destination_coords, (tavern.global_center_x, tavern.global_center_y))
        self.assertEqual(npc.schedule.previous_task, "Working (Miller)")



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
