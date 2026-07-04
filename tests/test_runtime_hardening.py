import unittest

from engine import NPC, World
from entities.items import Inventory, ItemReference
from simulation.systems.interaction import ActionIntent


class TestRuntimeHardening(unittest.TestCase):
    def test_hunger_override_can_find_item_reference_food(self):
        world = World(seed=123)
        npc = NPC(10, 10, name="Hungry NPC")
        world.village_npcs.append(npc)

        inv = Inventory()
        inv.add_item_reference(ItemReference("processed_meat"))
        world.items_on_map[(11, 10)] = inv

        target = world._find_nearest_edible_food_target(npc)

        self.assertIsNotNone(target)
        self.assertEqual(target["item_key"], "processed_meat")
        self.assertEqual(target["coords"], (11, 10))

    def test_validation_warning_keys_aggregate_repeated_survival_warnings(self):
        world = World(seed=123)

        world._warn_simulation_validation(
            "survival_override_no_valid_target",
            (1, "cold"),
            "No valid warmth/shelter target found.",
        )
        world._warn_simulation_validation(
            "survival_override_no_valid_target",
            (1, "cold"),
            "No valid warmth/shelter target found.",
        )

        key = ("survival_override_no_valid_target", (1, "cold"))
        self.assertEqual(world.validation_warning_counts[key], 2)
        self.assertEqual(len(world.validation_warnings), 1)

    def test_inventory_backed_ground_items_resolve_and_inspect_as_resource(self):
        world = World(seed=123)
        pos = (world.player.x + 1, world.player.y)
        inv = Inventory()
        inv.add_item_reference(ItemReference("processed_meat"))
        world.items_on_map[pos] = inv

        selection = world.resolve_selection_target(pos)
        payload = world.build_inspection_payload(selection)

        self.assertEqual(selection["target_type"], "resource")
        self.assertEqual(payload["item_key"], "processed_meat")
        self.assertTrue(payload["edible"])

    def test_contextual_chop_command_routes_to_interaction_resolver(self):
        world = World(seed=123)
        player = world.player
        pos = (player.x + 1, player.y)
        tile = world.get_tile_at(*pos)
        tile.properties = dict(getattr(tile, "properties", {}) or {}, is_tree=True)

        selection = world.resolve_selection_target(pos)
        command = next(
            cmd for cmd in world.get_available_player_commands(selection, player_id=player.id)
            if cmd["command_id"] == "chop"
        )
        result = world.execute_player_command(command, player_id=player.id)

        self.assertTrue(result.success)
        self.assertEqual(result.intent.action_type, "chop_tree")

    def test_eating_interaction_accepts_inventory_item_reference(self):
        world = World(seed=123)
        player = world.player
        pos = (player.x, player.y)
        inv = Inventory()
        inv.add_item_reference(ItemReference("processed_meat"))
        world.items_on_map[pos] = inv

        intent = ActionIntent(
            actor_id=player.id,
            action_type="eat_food",
            target_pos=pos,
            payload={
                "food_id": f"ground:{pos[0]}:{pos[1]}:processed_meat",
                "food_pos": pos,
                "item_key": "processed_meat",
                "nutrition_value": 0.2,
                "eat_work_required": 1,
            },
        )
        result = world.interaction_resolver.resolve(intent, world)

        self.assertTrue(result.success)
        self.assertEqual(result.intent.action_type, "eat_food")


if __name__ == "__main__":
    unittest.main()
