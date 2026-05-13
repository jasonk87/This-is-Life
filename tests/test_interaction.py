import unittest
from types import SimpleNamespace

from entities.items import Inventory, ItemReference
from simulation.systems.interaction import ActionIntent, ActionResult, InteractionResolver


class TestTile:
    def __init__(self, *, is_door=False, is_open=False, is_tree=False, opens_to="open_door_def"):
        self.properties = {}
        if is_door:
            self.properties.update({"is_door": True, "is_open": is_open, "opens_to": opens_to})
        if is_tree:
            self.properties["is_tree"] = True


class TestActor:
    def __init__(self, actor_id, x, y):
        self.id = actor_id
        self.x = x
        self.y = y
        self.physical = SimpleNamespace(is_dead=False)
        self.economic = SimpleNamespace(npc_inventory=Inventory())


class TestWorld:
    def __init__(self):
        self.actors = {}
        self.tiles = {}
        self.transparency_map = {}
        self.items_on_map = {}
        self.changed_tiles = []

    def get_entity_by_id(self, entity_id):
        return self.actors.get(entity_id)

    def get_tile_at(self, x, y):
        return self.tiles.get((x, y))

    def _change_map_tile(self, coords, new_tile_def):
        self.changed_tiles.append((coords, new_tile_def))
        self.tiles[coords] = TestTile()
        self.tiles[coords].properties = dict(new_tile_def.get("properties", {}))


class TestInteraction(unittest.TestCase):
    def setUp(self):
        self.world = TestWorld()
        self.resolver = InteractionResolver()
        self.player = TestActor("player", 10, 10)
        self.npc = TestActor("npc", 10, 10)
        self.world.actors["player"] = self.player
        self.world.actors["npc"] = self.npc

        import data.decorations
        import data.items
        import data.tiles

        self._original_door_defs = data.decorations.DECORATION_ITEM_DEFINITIONS
        self._original_tile_defs = data.tiles.TILE_DEFINITIONS
        self._original_item_defs = data.items.ITEM_DEFINITIONS

        data.decorations.DECORATION_ITEM_DEFINITIONS = {
            "open_door_def": {
                "char": "'",
                "color": (100, 100, 100),
                "passable": True,
                "name": "open door",
                "properties": {"is_door": True, "is_open": True},
            }
        }
        data.tiles.TILE_DEFINITIONS = {
            "stump_generic": {
                "char": "s",
                "color": (100, 50, 0),
                "passable": True,
                "name": "tree stump",
                "properties": {},
            }
        }
        data.items.ITEM_DEFINITIONS = {"raw_log": {"name": "Raw Log"}, "apple": {"name": "Apple"}}

    def tearDown(self):
        import data.decorations
        import data.items
        import data.tiles

        data.decorations.DECORATION_ITEM_DEFINITIONS = self._original_door_defs
        data.tiles.TILE_DEFINITIONS = self._original_tile_defs
        data.items.ITEM_DEFINITIONS = self._original_item_defs

    def _closed_door_at(self, coords=(11, 10)):
        self.world.tiles[coords] = TestTile(is_door=True, is_open=False)

    def _resolve_open_door(self, actor_id, source):
        self._closed_door_at()
        intent = ActionIntent(actor_id=actor_id, action_type="open_door", target_pos=(11, 10), source=source)
        return self.resolver.resolve(intent, self.world)

    def test_action_intent_construction(self):
        intent = ActionIntent(actor_id="123", action_type="test", source="player", payload={"k": "v"})
        self.assertEqual(intent.actor_id, "123")
        self.assertEqual(intent.action_type, "test")
        self.assertEqual(intent.source, "player")
        self.assertEqual(intent.payload, {"k": "v"})

    def test_action_result_construction(self):
        intent = ActionIntent(actor_id="123", action_type="test")
        result = ActionResult(
            success=True,
            intent=intent,
            cues_to_fire=["cue"],
            traces_to_log=[("trace", {"value": 1})],
            consumed_time=1,
            metadata={"ok": True},
        )
        self.assertTrue(result.success)
        self.assertIs(result.intent, intent)
        self.assertEqual(result.cues_to_fire, ["cue"])
        self.assertEqual(result.traces_to_log, [("trace", {"value": 1})])
        self.assertEqual(result.consumed_time, 1)
        self.assertEqual(result.metadata, {"ok": True})

    def test_resolver_rejects_missing_actor(self):
        intent = ActionIntent(actor_id="missing", action_type="open_door", target_pos=(11, 10))
        result = self.resolver.resolve(intent, self.world)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "actor_not_found")

    def test_resolver_rejects_unreachable_target(self):
        self.world.tiles[(15, 10)] = TestTile(is_door=True)
        intent = ActionIntent(actor_id="player", action_type="open_door", target_pos=(15, 10))
        result = self.resolver.resolve(intent, self.world)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "target_unreachable")

    def test_player_source_open_door_parity(self):
        player_result = self._resolve_open_door("player", "player")
        npc_result = self._resolve_open_door("npc", "npc")

        self.assertTrue(player_result.success)
        self.assertEqual(player_result.success, npc_result.success)
        self.assertEqual(player_result.cues_to_fire, npc_result.cues_to_fire)
        self.assertEqual([trace[0] for trace in player_result.traces_to_log], [trace[0] for trace in npc_result.traces_to_log])

    def test_npc_source_open_door_parity(self):
        npc_result = self._resolve_open_door("npc", "npc")
        player_result = self._resolve_open_door("player", "player")

        self.assertTrue(npc_result.success)
        self.assertEqual(npc_result.success, player_result.success)
        self.assertEqual(npc_result.cues_to_fire, player_result.cues_to_fire)
        self.assertEqual([trace[0] for trace in npc_result.traces_to_log], [trace[0] for trace in player_result.traces_to_log])

    def test_pickup_item_parity(self):
        player_source = Inventory()
        player_source.add_item_reference(ItemReference("apple"))
        self.world.items_on_map[(11, 10)] = player_source
        player_result = self.resolver.resolve(
            ActionIntent(
                actor_id="player",
                action_type="pickup_item",
                target_pos=(11, 10),
                source="player",
                payload={"item_key": "apple"},
            ),
            self.world,
        )

        npc_source = Inventory()
        npc_source.add_item_reference(ItemReference("apple"))
        self.world.items_on_map[(11, 10)] = npc_source
        npc_result = self.resolver.resolve(
            ActionIntent(
                actor_id="npc",
                action_type="pickup_item",
                target_pos=(11, 10),
                source="npc",
                payload={"item_key": "apple"},
            ),
            self.world,
        )

        self.assertTrue(player_result.success)
        self.assertEqual(player_result.success, npc_result.success)
        self.assertEqual(player_result.cues_to_fire, npc_result.cues_to_fire)
        self.assertEqual([trace[0] for trace in player_result.traces_to_log], [trace[0] for trace in npc_result.traces_to_log])
        self.assertEqual(self.player.economic.npc_inventory.get("apple"), 1)
        self.assertEqual(self.npc.economic.npc_inventory.get("apple"), 1)

    def test_chop_tree_starts_active_interaction(self):
        self.world.tiles[(11, 10)] = TestTile(is_tree=True)
        result = self.resolver.resolve(ActionIntent(actor_id="player", action_type="chop_tree", target_pos=(11, 10)), self.world)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.started_interaction_id)
        self.assertIn(result.started_interaction_id, self.resolver.active_interactions)

    def test_chop_tree_advances_work(self):
        self.world.tiles[(11, 10)] = TestTile(is_tree=True)
        result = self.resolver.resolve(ActionIntent(actor_id="player", action_type="chop_tree", target_pos=(11, 10)), self.world)

        advance_result = self.resolver.advance_active_interaction(result.started_interaction_id, self.world)

        self.assertTrue(advance_result.success)
        self.assertIn("chop_tree", advance_result.cues_to_fire)
        self.assertEqual(advance_result.metadata["remaining_work"], 9)
        self.assertIn(result.started_interaction_id, self.resolver.active_interactions)

    def test_chop_tree_completion_uses_canonical_outputs(self):
        self.world.tiles[(11, 10)] = TestTile(is_tree=True)
        result = self.resolver.resolve(ActionIntent(actor_id="player", action_type="chop_tree", target_pos=(11, 10)), self.world)
        interaction_id = result.started_interaction_id

        for _ in range(10):
            complete_result = self.resolver.advance_active_interaction(interaction_id, self.world)

        self.assertTrue(complete_result.success)
        self.assertIn("chop_tree", complete_result.cues_to_fire)
        self.assertTrue(any(trace[0] == "tree_chopped" for trace in complete_result.traces_to_log))
        self.assertNotIn(interaction_id, self.resolver.active_interactions)
        self.assertEqual(self.world.changed_tiles[0][1]["name"], "tree stump")
        self.assertEqual(self.world.items_on_map[(11, 10)].get("raw_log"), 1)

    def test_target_disappearing_cancels_cleanly(self):
        self.world.tiles[(11, 10)] = TestTile(is_tree=True)
        result = self.resolver.resolve(ActionIntent(actor_id="player", action_type="chop_tree", target_pos=(11, 10)), self.world)
        interaction_id = result.started_interaction_id
        self.resolver.advance_active_interaction(interaction_id, self.world)

        self.world.tiles[(11, 10)] = TestTile(is_tree=False)
        cancel_result = self.resolver.advance_active_interaction(interaction_id, self.world)

        self.assertFalse(cancel_result.success)
        self.assertEqual(cancel_result.reason, "cannot_continue")
        self.assertNotIn(interaction_id, self.resolver.active_interactions)


if __name__ == "__main__":
    unittest.main()
