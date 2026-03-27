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
import config
from tcod_compat import tcod
import tile_types

class TestGame(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()
        # Canned response for NPC generation
        mock_npc_data = {
            "name": "Test NPC",
            "personality": "test",
            "family_ties": "none",
            "attitude_to_player": "neutral",
            "dialogue": ["Hello."],
            "wealth_level": "average",
            "combat_behavior": "defensive",
            "base_attack_name": "fists"
        }
        self.mock_call_llm.return_value = json.dumps(mock_npc_data)

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def test_world_initialization(self):
        try:
            world = World()
            self.assertIsNotNone(world)
            self.assertIsNotNone(world.player)
        except Exception as e:
            self.fail(f"World initialization failed with an exception: {e}")



class TestWorldOccupancyMap(unittest.TestCase):
    def test_update_entity_position_keeps_occupancy_map_in_sync(self):
        world = object.__new__(engine.World)
        npc = SimpleNamespace(id=2, x=3, y=4, physical=SimpleNamespace(is_dead=False))
        new_coords = (config.CHUNK_SIZE + 1, 6)
        world.player = SimpleNamespace(id=1, x=1, y=1)
        world.village_npcs = [npc]
        world.npcs = []
        world.entity_positions = {(1, 1): 1, (3, 4): 2}
        world.entity_positions_dirty = False
        world.entity_chunks_dirty = False
        world.entities_by_chunk = {(0, 0): {1, 2}}

        engine.World._update_entity_position(world, npc, *new_coords)

        self.assertNotIn((3, 4), world.entity_positions)
        self.assertEqual(world.entity_positions[new_coords], 2)
        self.assertEqual((npc.x, npc.y), new_coords)
        self.assertEqual(world.entities_by_chunk[(0, 0)], {1})
        self.assertEqual(world.entities_by_chunk[(1, 0)], {2})

    def test_update_npc_movement_updates_occupancy_map_after_move(self):
        npc = SimpleNamespace(
            id=2,
            x=3,
            y=4,
            speed=1,
            task_target_entity_id=None,
            physical=SimpleNamespace(is_dead=False),
            schedule=SimpleNamespace(
                current_task="wandering",
                current_path=[(3, 4), (4, 4)],
                current_destination_coords=(4, 4),
            ),
            economic=SimpleNamespace(profession="Villager"),
        )
        world = object.__new__(engine.World)
        world.player = SimpleNamespace(id=1, x=10, y=10)
        world.village_npcs = [npc]
        world.npcs = []
        world.entity_positions = {(10, 10): 1, (3, 4): 2}
        world.entity_positions_dirty = False
        world.entity_chunks_dirty = False
        world.entities_by_chunk = {(0, 0): {2}, (1, 1): {1}}
        world.add_message_to_chat_log = unittest.mock.Mock()
        world.get_tile_at = lambda x, y: SimpleNamespace(passable=True)
        world._is_predator = lambda entity: False

        engine.World._update_npc_movement(world)

        self.assertEqual((npc.x, npc.y), (4, 4))
        self.assertNotIn((3, 4), world.entity_positions)
        self.assertEqual(world.entity_positions[(4, 4)], 2)
        self.assertEqual(npc.schedule.current_path, [])
        self.assertIn(2, world.entities_by_chunk[(0, 0)])

    def test_update_npc_movement_waits_in_queue_when_tile_is_temporarily_blocked(self):
        blocker = SimpleNamespace(
            id=2,
            x=4,
            y=4,
            speed=1,
            task_target_entity_id=None,
            physical=SimpleNamespace(is_dead=False),
            schedule=SimpleNamespace(
                current_task="wandering",
                current_path=[],
                current_destination_coords=None,
                path_blocked_turns=0,
                last_blocked_position=None,
            ),
            economic=SimpleNamespace(profession="Villager"),
        )
        follower = SimpleNamespace(
            id=3,
            x=3,
            y=4,
            speed=1,
            task_target_entity_id=None,
            physical=SimpleNamespace(is_dead=False),
            schedule=SimpleNamespace(
                current_task="wandering",
                current_path=[(3, 4), (4, 4), (5, 4)],
                current_destination_coords=(5, 4),
                path_blocked_turns=0,
                last_blocked_position=None,
            ),
            economic=SimpleNamespace(profession="Villager"),
        )
        world = object.__new__(engine.World)
        world.player = SimpleNamespace(id=1, x=10, y=10)
        world.village_npcs = [blocker, follower]
        world.npcs = []
        world.entity_positions = {(10, 10): 1, (4, 4): 2, (3, 4): 3}
        world.entity_positions_dirty = False
        world.entity_chunks_dirty = False
        world.entities_by_chunk = {(0, 0): {2, 3}, (1, 1): {1}}
        world.add_message_to_chat_log = unittest.mock.Mock()
        world.get_tile_at = lambda x, y: SimpleNamespace(passable=True)
        world._is_predator = lambda entity: False
        world.get_entity_by_id = lambda entity_id: {1: world.player, 2: blocker, 3: follower}.get(entity_id)

        engine.World._update_npc_movement(world)

        self.assertEqual((follower.x, follower.y), (3, 4))
        self.assertEqual(follower.schedule.current_path, [(3, 4), (4, 4), (5, 4)])
        self.assertEqual(follower.schedule.path_blocked_turns, 1)
        self.assertEqual(follower.schedule.last_blocked_position, (4, 4))


class TestChunkSleepWakeAndAbstractSimulation(unittest.TestCase):
    def make_minimal_world(self):
        world = object.__new__(engine.World)
        world.player = SimpleNamespace(id=1, x=0, y=0)
        world.npcs = []
        world.village_npcs = []
        world.entity_positions = {(0, 0): 1}
        world.entity_positions_dirty = False
        world.entity_chunks_dirty = False
        world.entities_by_chunk = {(0, 0): {1}}
        world.npc_fov_maps = {}
        world.buildings_by_id = {}
        world.chunk_width = 8
        world.chunk_height = 8
        world.chunk_manager = engine.ChunkManager(config.CHUNK_SIZE, world.chunk_width, world.chunk_height)
        world.chunk_manager.update_for_player(world.player.x, world.player.y, force=True)
        world.last_abstract_simulation_hour = -1
        world.ensure_player_surroundings_generated = MagicMock()
        world.get_tile_at = lambda x, y: SimpleNamespace(passable=True, name="Plains")
        return world

    def test_sleep_and_wake_entity_preserve_state_and_strip_heavy_runtime_bits(self):
        world = self.make_minimal_world()
        npc = engine.NPC(config.CHUNK_SIZE * 4, config.CHUNK_SIZE * 4, name="Sleeper")
        world.village_npcs = [npc]
        world.entity_positions[(npc.x, npc.y)] = npc.id
        world.entities_by_chunk[(4, 4)] = {npc.id}
        world.npc_fov_maps[npc.id] = "cached"
        npc.economic.money = 37
        npc.economic.npc_inventory.add_item_reference(engine.ItemReference("axe_stone", quality="Fine"))
        inventory_ref = npc.economic.npc_inventory.get_item_reference("axe_stone")
        npc.knowledge.known_locations["work"] = (npc.x, npc.y)
        npc.social.relationships[world.player.id] = 68
        original_brain = npc.ai_brain

        slept = engine.World.sleep_entity(world, npc)

        self.assertTrue(slept)
        self.assertTrue(npc.is_sleeping)
        self.assertTrue(npc.render_disabled)
        self.assertIsNone(npc.ai_brain)
        self.assertEqual((npc.macro_x, npc.macro_y), (config.CHUNK_SIZE * 4, config.CHUNK_SIZE * 4))
        self.assertNotIn((npc.x, npc.y), world.entity_positions)
        self.assertNotIn(npc.id, world.npc_fov_maps)
        self.assertEqual(npc.economic.money, 37)
        self.assertEqual(npc.social.relationships[world.player.id], 68)
        self.assertEqual(npc.knowledge.known_locations["work"], (config.CHUNK_SIZE * 4, config.CHUNK_SIZE * 4))
        self.assertIs(npc.economic.npc_inventory.get_item_reference("axe_stone"), inventory_ref)

        woke = engine.World.wake_entity(world, npc)

        self.assertTrue(woke)
        self.assertFalse(npc.is_sleeping)
        self.assertFalse(npc.render_disabled)
        self.assertIs(npc.ai_brain, original_brain)
        self.assertIn((npc.x, npc.y), world.entity_positions)
        self.assertIs(npc.economic.npc_inventory.get_item_reference("axe_stone"), inventory_ref)

    def test_refresh_chunk_activity_sleeps_and_wakes_entities_as_player_crosses_boundary(self):
        world = self.make_minimal_world()
        nearby_npc = engine.NPC(2, 2, name="Nearby")
        far_npc = engine.NPC(config.CHUNK_SIZE * 4, config.CHUNK_SIZE * 4, name="Far")
        world.village_npcs = [nearby_npc, far_npc]
        world.entity_positions[(nearby_npc.x, nearby_npc.y)] = nearby_npc.id
        world.entity_positions[(far_npc.x, far_npc.y)] = far_npc.id
        world.entities_by_chunk[(0, 0)].add(nearby_npc.id)
        world.entities_by_chunk[(4, 4)] = {far_npc.id}

        engine.World._refresh_chunk_activity(world, force=True)

        self.assertFalse(nearby_npc.is_sleeping)
        self.assertTrue(far_npc.is_sleeping)

        world.player.x = config.CHUNK_SIZE * 4
        world.player.y = config.CHUNK_SIZE * 4
        engine.World._refresh_chunk_activity(world, force=True)

        self.assertTrue(nearby_npc.is_sleeping)
        self.assertFalse(far_npc.is_sleeping)
        self.assertIn((far_npc.x, far_npc.y), world.entity_positions)

    def test_update_npc_movement_skips_sleeping_entities(self):
        world = self.make_minimal_world()
        sleeping_npc = SimpleNamespace(
            id=2,
            x=3,
            y=4,
            macro_x=3,
            macro_y=4,
            is_sleeping=True,
            speed=1,
            task_target_entity_id=None,
            physical=SimpleNamespace(is_dead=False),
            schedule=SimpleNamespace(
                current_task="wandering",
                current_path=[(3, 4), (4, 4)],
                current_destination_coords=(4, 4),
                path_blocked_turns=0,
                last_blocked_position=None,
            ),
            economic=SimpleNamespace(profession="Villager"),
        )
        world.village_npcs = [sleeping_npc]
        world.entity_positions[(sleeping_npc.x, sleeping_npc.y)] = sleeping_npc.id
        world.entities_by_chunk[(0, 0)].add(sleeping_npc.id)
        world.add_message_to_chat_log = MagicMock()
        world._is_predator = lambda entity: False

        engine.World._update_npc_movement(world)

        self.assertEqual((sleeping_npc.x, sleeping_npc.y), (3, 4))
        self.assertEqual(sleeping_npc.schedule.current_path, [(3, 4), (4, 4)])

    def test_process_abstract_simulation_updates_sleeping_workers_and_inactive_buildings_hourly(self):
        world = self.make_minimal_world()
        building = engine.Building(
            0,
            0,
            5,
            5,
            building_type="farm",
            category="agricultural_workplace",
            global_chunk_x_start=config.CHUNK_SIZE * 3,
            global_chunk_y_start=config.CHUNK_SIZE * 3,
        )
        building.building_inventory["money"] = 120
        world.buildings_by_id[building.id] = building

        npc = engine.NPC(building.global_center_x, building.global_center_y, name="Farm Sleeper")
        npc.economic.profession = "Farmer"
        npc.economic.daily_wage = 24
        npc.schedule.work_building_id = building.id
        npc.is_sleeping = True
        npc.ai_brain = None
        world.village_npcs = [npc]

        hourly_tick = max(1, config.DAY_LENGTH_TICKS // 24)
        world.game_time = int(config.DAY_LENGTH_TICKS * config.WORK_START_TIME_RATIO) + hourly_tick

        engine.World.process_abstract_simulation(world)

        self.assertGreater(npc.economic.money, 0)
        self.assertGreater(npc.physical.hunger, 0)
        self.assertLess(building.building_inventory.get("money", 0), 120)
        self.assertGreater(building.building_inventory.get("wheat", 0), 0)


class TestAnimationSync(unittest.TestCase):
    def test_update_animations_snaps_large_position_gaps_to_target(self):
        world = object.__new__(engine.World)
        world.player = SimpleNamespace(x=25, y=30, render_x=0.0, render_y=0.0)
        world.npcs = []
        world.village_npcs = []
        world.visual_effects = []

        engine.World.update_animations(world, 0.016)

        self.assertEqual((world.player.render_x, world.player.render_y), (25.0, 30.0))


class TestBuildingEntranceIntegrity(unittest.TestCase):
    def make_world(self):
        world = object.__new__(engine.World)
        world.chunk_width = 1
        world.chunk_height = 1
        plains_def = engine.TILE_DEFINITIONS["plains"]
        tiles = [
            [
                engine.Tile(
                    plains_def["char"],
                    plains_def["color"],
                    plains_def["passable"],
                    plains_def["name"],
                    plains_def.get("properties", {}),
                )
                for _ in range(config.CHUNK_SIZE)
            ]
            for _ in range(config.CHUNK_SIZE)
        ]
        world.chunks = [[SimpleNamespace(tiles=tiles, is_terrain_generated=True, poi_type="village", village=None)]]
        world.transparency_map = engine.np.full((config.WORLD_HEIGHT, config.WORLD_WIDTH), fill_value=True, order="F")
        world.buildings_by_id = {}
        world.player = SimpleNamespace(
            id=1,
            x=0,
            y=0,
            social=SimpleNamespace(family_ties={}),
        )
        world.entity_positions = {(0, 0): 1}
        world.entities_by_chunk = {(0, 0): {1}}
        world._refresh_chunk_activity = lambda *args, **kwargs: None
        world._ensure_entity_positions_current = lambda *args, **kwargs: None
        world.add_message_to_chat_log = lambda *args, **kwargs: None
        world.get_entity_by_id = lambda entity_id: None
        world._generate_chunk_detail = lambda chunk, chunk_x, chunk_y: setattr(chunk, "is_terrain_generated", True)
        return world

    def make_building(self, building_type="general_store"):
        return engine.Building(
            10,
            10,
            7,
            6,
            building_type=building_type,
            category="workplace" if building_type != "house" else "residential",
            global_chunk_x_start=0,
            global_chunk_y_start=0,
        )

    def get_candidate_for_entrance(self, world, building, entrance):
        return next(
            candidate
            for candidate in engine.World._get_building_entrance_candidates(world, building)
            if candidate["door"] == entrance
        )

    def test_enterable_building_gets_usable_entrance_with_interior_and_exterior_connection(self):
        world = self.make_world()
        building = self.make_building("general_store")

        engine.World._draw_building(world, world.chunks[0][0].tiles, building, "wood_wall")

        entrance = building.interaction_points.get("entrance")
        self.assertIsNotNone(entrance)
        candidate = self.get_candidate_for_entrance(world, building, entrance)
        door_tile = world.get_tile_at(*candidate["door"])
        inside_tile = world.get_tile_at(*candidate["inside"])
        outside_tile = world.get_tile_at(*candidate["outside"])

        self.assertTrue(door_tile.properties.get("is_door"))
        self.assertTrue(inside_tile.passable)
        self.assertTrue(outside_tile.passable)
        self.assertFalse(building.contains_global_coords(*candidate["outside"]))

    def test_entrance_repair_restores_door_and_walkable_approach_after_overwrite(self):
        world = self.make_world()
        building = self.make_building("library")

        engine.World._draw_building(world, world.chunks[0][0].tiles, building, "stone_wall")
        original_entrance = building.interaction_points["entrance"]
        candidate = self.get_candidate_for_entrance(world, building, original_entrance)

        engine.World._change_map_tile(world, candidate["door"], engine.TILE_DEFINITIONS["stone_wall"])
        engine.World._change_map_tile(world, candidate["inside"], engine.DECORATION_ITEM_DEFINITIONS["chest_wooden"])

        repaired_entrance = engine.World._ensure_building_entrance_integrity(world, building)

        self.assertEqual(repaired_entrance, original_entrance)
        self.assertTrue(world.get_tile_at(*candidate["door"]).properties.get("is_door"))
        self.assertTrue(world.get_tile_at(*candidate["inside"]).passable)

    def test_starting_home_spawn_uses_tile_with_reliable_egress(self):
        world = self.make_world()
        building = self.make_building("house")
        building.category = "residential"
        world.buildings_by_id[building.id] = building

        engine.World._draw_building(world, world.chunks[0][0].tiles, building, "wood_wall")
        center = (building.global_center_x, building.global_center_y)
        engine.World._change_map_tile(world, center, engine.DECORATION_ITEM_DEFINITIONS["chest_wooden"])

        relative = SimpleNamespace(schedule=SimpleNamespace(home_building_id=building.id))
        world.player.social.family_ties = {"mother_id": relative.schedule.home_building_id}
        world.get_entity_by_id = lambda entity_id: relative if entity_id == building.id else None
        chosen_positions = []
        world._update_entity_position = lambda entity, x, y: chosen_positions.append((x, y))

        engine.World._find_starting_position(world)

        entrance = building.interaction_points["entrance"]
        candidate = self.get_candidate_for_entrance(world, building, entrance)
        self.assertEqual(chosen_positions[0], candidate["inside"])
        self.assertTrue(
            engine.World._building_interior_path_exists(
                world,
                building,
                chosen_positions[0],
                candidate["inside"],
            )
        )

    def test_player_door_toggle_keeps_open_state_passability_and_transparency_in_sync(self):
        world = self.make_world()
        building = self.make_building("house")

        engine.World._draw_building(world, world.chunks[0][0].tiles, building, "wood_wall")
        door_x, door_y = building.interaction_points["entrance"]

        self.assertFalse(world.get_tile_at(door_x, door_y).passable)
        engine.World.player_attempt_toggle_door(world, door_x, door_y)
        self.assertTrue(world.get_tile_at(door_x, door_y).passable)
        self.assertTrue(world.transparency_map[door_y, door_x])

        engine.World.player_attempt_toggle_door(world, door_x, door_y)
        self.assertFalse(world.get_tile_at(door_x, door_y).passable)
        self.assertFalse(world.transparency_map[door_y, door_x])

    def test_entrance_selection_is_deterministic_for_matching_buildings(self):
        first_world = self.make_world()
        second_world = self.make_world()
        first_building = self.make_building("general_store")
        second_building = self.make_building("general_store")

        engine.World._draw_building(first_world, first_world.chunks[0][0].tiles, first_building, "wood_wall")
        engine.World._draw_building(second_world, second_world.chunks[0][0].tiles, second_building, "wood_wall")

        self.assertEqual(
            first_building.interaction_points.get("entrance"),
            second_building.interaction_points.get("entrance"),
        )


class TestInteriorFurnishingIntegrity(unittest.TestCase):
    def make_world(self, llm_response="{}"):
        world = object.__new__(engine.World)
        world.chunk_width = 1
        world.chunk_height = 1
        plains_def = engine.TILE_DEFINITIONS["plains"]
        tiles = [
            [
                engine.Tile(
                    plains_def["char"],
                    plains_def["color"],
                    plains_def["passable"],
                    plains_def["name"],
                    plains_def.get("properties", {}),
                )
                for _ in range(config.CHUNK_SIZE)
            ]
            for _ in range(config.CHUNK_SIZE)
        ]
        village = SimpleNamespace(buildings=[], interaction_points={}, lore="")
        chunk = SimpleNamespace(
            tiles=tiles,
            is_terrain_generated=True,
            poi_type="village",
            village=village,
        )
        world.chunks = [[chunk]]
        world.transparency_map = engine.np.full((config.WORLD_HEIGHT, config.WORLD_WIDTH), fill_value=True, order="F")
        world.buildings_by_id = {}
        world._call_llm_for_worldgen = lambda prompt: llm_response
        world.add_message_to_chat_log = lambda *args, **kwargs: None
        return world

    def make_building(self, building_type, *, category="residential", width=7, height=6):
        return engine.Building(
            10,
            10,
            width,
            height,
            building_type=building_type,
            category=category,
            global_chunk_x_start=0,
            global_chunk_y_start=0,
        )

    def collect_interior_furniture(self, world, building):
        furniture_names = {
            engine.DECORATION_ITEM_DEFINITIONS[key]["name"]
            for key in ["bed_simple", "wooden_table", "wooden_chair", "chest_wooden", "wall_shelf", "workbench", "fire_pit_simple"]
        }
        found = []
        for y in range(building.global_origin_y + 1, building.global_origin_y + building.height - 1):
            for x in range(building.global_origin_x + 1, building.global_origin_x + building.width - 1):
                tile = world.get_tile_at(x, y)
                if tile and tile.name in furniture_names:
                    found.append((x, y, tile.name))
        return found

    def test_supported_house_is_furnished_during_village_render(self):
        world = self.make_world()
        building = self.make_building("house", category="residential")
        world.chunks[0][0].village.buildings = [building]

        engine.World._render_village_tiles(world, world.chunks[0][0])

        furniture = self.collect_interior_furniture(world, building)
        self.assertTrue(building.interior_decorated)
        self.assertGreaterEqual(len(furniture), 2)

    def test_unsupported_work_building_uses_deterministic_fallback_when_llm_is_empty(self):
        world = self.make_world(llm_response="{}")
        building = self.make_building("general_store", category="commercial_workplace", width=8, height=6)
        world.chunks[0][0].village.buildings = [building]

        engine.World._render_village_tiles(world, world.chunks[0][0])

        furniture = self.collect_interior_furniture(world, building)
        self.assertTrue(furniture)
        self.assertTrue(any(name == engine.DECORATION_ITEM_DEFINITIONS["wooden_table"]["name"] for _, _, name in furniture))

    def test_furniture_tiles_land_on_valid_interior_coordinates(self):
        world = self.make_world(llm_response="{}")
        building = self.make_building("library", category="civic_workplace", width=8, height=6)
        world.chunks[0][0].village.buildings = [building]

        engine.World._render_village_tiles(world, world.chunks[0][0])

        furniture = self.collect_interior_furniture(world, building)
        self.assertTrue(furniture)
        for x, y, _ in furniture:
            self.assertTrue(building.global_origin_x < x < building.global_origin_x + building.width - 1)
            self.assertTrue(building.global_origin_y < y < building.global_origin_y + building.height - 1)

    def test_generation_flow_leaves_furniture_in_chunk_tiles_after_building_render(self):
        world = self.make_world(llm_response="{}")
        building = self.make_building("blacksmith_shop", category="industrial_workplace", width=7, height=6)
        world.chunks[0][0].village.buildings = [building]

        engine.World._render_village_tiles(world, world.chunks[0][0])

        furniture = self.collect_interior_furniture(world, building)
        self.assertTrue(furniture)
        for x, y, _ in furniture:
            tile = world.chunks[0][0].tiles[y][x]
            self.assertNotEqual(tile.name, engine.TILE_DEFINITIONS["wood_floor"]["name"])

    def test_furnished_layout_is_deterministic(self):
        first_world = self.make_world(llm_response="{}")
        second_world = self.make_world(llm_response="{}")
        first_building = self.make_building("general_store", category="commercial_workplace", width=8, height=6)
        second_building = self.make_building("general_store", category="commercial_workplace", width=8, height=6)
        first_world.chunks[0][0].village.buildings = [first_building]
        second_world.chunks[0][0].village.buildings = [second_building]

        engine.World._render_village_tiles(first_world, first_world.chunks[0][0])
        engine.World._render_village_tiles(second_world, second_world.chunks[0][0])

        self.assertEqual(
            self.collect_interior_furniture(first_world, first_building),
            self.collect_interior_furniture(second_world, second_building),
        )
