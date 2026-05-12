import unittest
from simulation.systems.interaction import ActionIntent, ActionResult, InteractionResolver, ChopTreeInteraction

class MockTile:
    def __init__(self, is_door=False, is_open=False, is_tree=False, hint=None):
        self.properties = {}
        if is_door:
            self.properties["is_door"] = True
            self.properties["is_open"] = is_open
            self.properties["opens_to"] = "open_door_def"
        if is_tree:
            self.properties["is_tree"] = True
        if hint:
            self.properties["interaction_hint"] = hint

class MockActor:
    def __init__(self, id, x, y):
        self.id = id
        self.x = x
        self.y = y
        self.physical = type("Physical", (), {"is_dead": False})()

class MockWorld:
    def __init__(self):
        self.actors = {}
        self.tiles = {}

        self.CHUNK_SIZE = 32
        class MockChunk:
            def __init__(self):
                self.tiles = [[type("Tile", (), {"blocks_fov": False})() for _ in range(32)] for _ in range(32)]

        self.chunks = {0: {0: MockChunk()}}
        self.transparency_map = {}
        self.items_on_map = {}
        self.changed_tiles = []

    def get_entity_by_id(self, entity_id):
        return self.actors.get(entity_id)

    def get_tile_at(self, x, y):
        return self.tiles.get((x, y))

    def _change_map_tile(self, coords, new_tile_def):
        self.changed_tiles.append((coords, new_tile_def))

class TestInteraction(unittest.TestCase):
    def setUp(self):
        self.world = MockWorld()
        self.resolver = InteractionResolver()
        self.player = MockActor("player", 10, 10)
        self.npc = MockActor("npc", 10, 10)
        self.world.actors["player"] = self.player
        self.world.actors["npc"] = self.npc

        import data.decorations
        import data.tiles
        data.decorations.DECORATION_ITEM_DEFINITIONS = {
            "open_door_def": {
                "char": "'", "color": (100, 100, 100), "passable": True, "name": "open door", "properties": {"is_door": True, "is_open": True}
            }
        }

        data.tiles.TILE_DEFINITIONS = {
            "stump_generic": {
                "char": "s", "color": (100, 50, 0), "passable": True, "name": "tree stump", "properties": {}
            }
        }

        import data.items
        data.items.ITEM_DEFINITIONS = {
            "raw_log": {
                "name": "Raw Log"
            }
        }

    def test_intent_serialization(self):
        intent = ActionIntent(actor_id="123", action_type="test", source="player", payload={"k": "v"})
        self.assertEqual(intent.actor_id, "123")
        self.assertEqual(intent.action_type, "test")
        self.assertEqual(intent.payload, {"k": "v"})

    def test_missing_actor(self):
        intent = ActionIntent(actor_id="missing", action_type="open_door", target_pos=(11, 10))
        result = self.resolver.resolve(intent, self.world)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "actor_not_found")

    def test_unreachable_target(self):
        self.world.tiles[(15, 10)] = MockTile(is_door=True)
        intent = ActionIntent(actor_id="player", action_type="open_door", target_pos=(15, 10))
        result = self.resolver.resolve(intent, self.world)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "target_unreachable")

    def test_open_door_parity(self):
        # Player style
        self.world.tiles[(11, 10)] = MockTile(is_door=True, is_open=False)
        player_intent = ActionIntent(actor_id="player", action_type="open_door", target_pos=(11, 10), source="player")
        player_result = self.resolver.resolve(player_intent, self.world)

        self.assertTrue(player_result.success)
        self.assertIn("open_door", player_result.cues_to_fire)
        self.assertEqual(player_result.traces_to_log[0][0], "door_opened")

        # Reset world door
        self.world.tiles[(11, 10)] = MockTile(is_door=True, is_open=False)

        # NPC style
        npc_intent = ActionIntent(actor_id="npc", action_type="open_door", target_pos=(11, 10), source="npc")
        npc_result = self.resolver.resolve(npc_intent, self.world)

        self.assertTrue(npc_result.success)
        self.assertIn("open_door", npc_result.cues_to_fire)
        self.assertEqual(npc_result.traces_to_log[0][0], "door_opened")

    def test_chop_tree_flow(self):
        self.world.tiles[(11, 10)] = MockTile(is_tree=True)
        intent = ActionIntent(actor_id="player", action_type="chop_tree", target_pos=(11, 10))

        result = self.resolver.resolve(intent, self.world)
        self.assertTrue(result.success)
        self.assertIsNotNone(result.started_interaction_id)

        iid = result.started_interaction_id

        for _ in range(9):
            adv_res = self.resolver.advance_active_interaction(iid, self.world)
            self.assertTrue(adv_res.success)
            self.assertIn("chop_tree", adv_res.cues_to_fire)

        comp_res = self.resolver.advance_active_interaction(iid, self.world)
        self.assertTrue(comp_res.success)
        self.assertIn("chop_tree", comp_res.cues_to_fire)
        self.assertTrue(any(t[0] == "tree_chopped" for t in comp_res.traces_to_log))
        self.assertNotIn(iid, self.resolver.active_interactions)

        # Verify _change_map_tile was called
        self.assertEqual(len(self.world.changed_tiles), 1)
        self.assertEqual(self.world.changed_tiles[0][0], (11, 10))
        self.assertEqual(self.world.changed_tiles[0][1]["name"], "tree stump")

        # Verify raw_log was spawned
        inv = self.world.items_on_map.get((11, 10))
        self.assertIsNotNone(inv)

    def test_chop_tree_cancellation(self):
        self.world.tiles[(11, 10)] = MockTile(is_tree=True)
        intent = ActionIntent(actor_id="player", action_type="chop_tree", target_pos=(11, 10))

        result = self.resolver.resolve(intent, self.world)
        iid = result.started_interaction_id

        # Advance 1 tick
        self.resolver.advance_active_interaction(iid, self.world)

        # Remove tree
        self.world.tiles[(11, 10)] = MockTile(is_tree=False)

        # Advance again, should cancel
        cancel_res = self.resolver.advance_active_interaction(iid, self.world)
        self.assertFalse(cancel_res.success)
        self.assertEqual(cancel_res.reason, "cannot_continue")
        self.assertNotIn(iid, self.resolver.active_interactions)

if __name__ == '__main__':
    unittest.main()
