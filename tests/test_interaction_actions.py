"""Every action the menu can execute is one the world can actually offer.

main.py's interaction menu maps 31 action names to handlers. `Fish` and
`Smoke Meat` were in that map, with `player_attempt_fish` and
`player_attempt_smoke` fully implemented behind them - and nothing in
`_get_actions_for_entity` ever offered either. A player could build a smoking
rack (it has a construction recipe) and get no option from it; they could stand
on a riverbank holding a rod and be offered only "Examine".
"""

import re
import unittest
from unittest.mock import patch
from pathlib import Path

from config import CHUNK_SIZE
from engine import TILE_DEFINITIONS, Tile, World
from work_subtasks import create_completed_work_sub_task_commands

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _menu_action_names():
    """The action names main.py's interaction menu can execute."""
    source = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
    start = source.index("action_map = {")
    end = source.index("}", source.index('"Loot Chest"'))
    return set(re.findall(r'"([^"]+)": lambda', source[start:end]))


class TestActionsAreReachable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")

    def _actions_for_tile(self, name, **properties):
        tile = Tile(char="#", color=(200, 150, 100), passable=True, name=name, properties=properties)
        return self.world._get_actions_for_entity({"type": "tile", "data": tile, "name": name})

    def test_a_smoking_rack_offers_smoking(self):
        """It has a construction recipe, so a player can build one and expect it to work."""
        self.assertIn("Smoke Meat", self._actions_for_tile("Smoking Rack", interaction_hint="smoke"))
        self.assertIn(
            "Smoke Meat",
            self._actions_for_tile("Smoking Rack", workstation_type="smoking_rack"),
        )

    def test_water_offers_fishing_only_with_a_rod(self):
        self.assertNotIn("Fish", self._actions_for_tile("Water"))
        self.world.player.add_item("fishing_rod", 1)
        try:
            self.assertIn("Fish", self._actions_for_tile("Water"))
            self.assertIn("Fish", self._actions_for_tile("Deep Water"))
        finally:
            self.world.player.remove_item("fishing_rod", 1)

    def test_dry_land_never_offers_fishing(self):
        self.world.player.add_item("fishing_rod", 1)
        try:
            self.assertNotIn("Fish", self._actions_for_tile("Plains"))
        finally:
            self.world.player.remove_item("fishing_rod", 1)

    def test_examine_is_always_available(self):
        self.assertIn("Examine", self._actions_for_tile("Plains"))


class TestLockpickingAndPlanting(unittest.TestCase):
    """Both had an implementation, an item to gate them, and tile data to act on."""

    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")

    def _actions_for_tile(self, name, **properties):
        tile = Tile(char="#", color=(1, 1, 1), passable=True, name=name, properties=properties)
        return self.world._get_actions_for_entity({"type": "tile", "data": tile, "name": name})

    def test_a_locked_chest_offers_picking_only_with_a_lockpick(self):
        locked = dict(is_lockable=True, is_locked=True, lock_difficulty=3)
        self.assertNotIn("Pick Lock", self._actions_for_tile("Treasure Chest", **locked))
        self.world.player.add_item("lockpick", 1)
        try:
            self.assertIn("Pick Lock", self._actions_for_tile("Treasure Chest", **locked))
        finally:
            self.world.player.remove_item("lockpick", 1)

    def test_an_unlocked_chest_offers_no_picking(self):
        self.world.player.add_item("lockpick", 1)
        try:
            actions = self._actions_for_tile("Treasure Chest", is_lockable=True, is_locked=False)
            self.assertNotIn("Pick Lock", actions)
            self.assertIn("Loot Chest", actions, "picking should not have displaced looting")
        finally:
            self.world.player.remove_item("lockpick", 1)

    def test_planting_needs_a_sapling_and_open_ground(self):
        self.assertNotIn("Plant Sapling", self._actions_for_tile("Plains"))
        self.world.player.add_item("sapling", 1)
        try:
            self.assertIn("Plant Sapling", self._actions_for_tile("Plains"))
            self.assertIn("Plant Sapling", self._actions_for_tile("Tilled Soil"))
            self.assertNotIn("Plant Sapling", self._actions_for_tile("Water"))
        finally:
            self.world.player.remove_item("sapling", 1)

    def test_planting_a_sapling_changes_the_ground(self):
        world = World(player_first_name="Planter")
        world.player.add_item("sapling", 1)
        target = None
        for offset in range(1, 12):
            for spot in ((world.player.x + offset, world.player.y), (world.player.x, world.player.y + offset)):
                tile = world.get_tile_at(*spot)
                if tile is not None and tile.name == "Plains":
                    target = spot
                    break
            if target:
                break
        if target is None:
            self.skipTest("no open ground near the player in this world")

        world.player_attempt_plant_sapling(*target)

        self.assertEqual(world.player.economic.inventory.get("sapling", 0), 0, "the sapling was not used")
        self.assertEqual(world.get_tile_at(*target).name, "Sapling")


class TestMenuAndWorldAgree(unittest.TestCase):
    """The two halves of the interaction system must not drift apart."""

    def test_the_menu_can_execute_everything_it_might_be_offered(self):
        world = World(player_first_name="Tester")
        world.player.add_item("fishing_rod", 1)
        world.player.add_item("stone_hoe", 1)
        world.player.add_item("wheat_seeds", 1)
        world.player.add_item("lockpick", 1)
        world.player.add_item("sapling", 1)

        offered = set()
        for name, properties in (
            ("Water", {}),
            ("Deep Water", {}),
            ("Plains", {}),
            ("Tilled Soil", {}),
            ("Wheat", {}),
            ("Smoking Rack", {"interaction_hint": "smoke"}),
            ("Forge", {"interaction_hint": "forge"}),
            ("Chair", {"interaction_hint": "sit"}),
            ("Bed", {"interaction_hint": "sleep"}),
            ("Noticeboard", {"interaction_hint": "noticeboard"}),
            ("Treasure Chest", {}),
            ("Animal Corpse", {}),
            ("Door", {"is_door": True}),
            ("Treasure Chest", {"is_lockable": True, "is_locked": True}),
        ):
            tile = Tile(char="#", color=(1, 1, 1), passable=True, name=name, properties=properties)
            offered |= set(world._get_actions_for_entity({"type": "tile", "data": tile, "name": name}))

        unexecutable = offered - _menu_action_names()
        self.assertEqual(
            unexecutable, set(),
            f"the world offers actions the menu cannot run: {sorted(unexecutable)}",
        )

    def test_the_recovered_actions_are_all_in_the_menu(self):
        """Guards the other direction - each was executable but unreachable."""
        names = _menu_action_names()
        for action in ("Fish", "Smoke Meat", "Pick Lock", "Plant Sapling"):
            self.assertIn(action, names)


class TestFishermenCatchFish(unittest.TestCase):
    """The Fisherman profession worked a full day and the village never saw a fish."""

    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()
        cls.commands = create_completed_work_sub_task_commands()

    def test_the_fishing_sub_task_has_a_completion_command(self):
        """It declares no produces_item_at_workplace, so the default one makes nothing."""
        self.assertIn("fish_at_spot", self.commands)

    def _water_beside(self, x, y):
        """Put water at a known spot so the geometry is not left to world generation."""
        world = self.world
        world.get_tile_at(x, y)  # ensure the chunk exists
        chunk = world.chunks[y // CHUNK_SIZE][x // CHUNK_SIZE]
        chunk.tiles[y % CHUNK_SIZE][x % CHUNK_SIZE] = Tile(
            char="~", color=(40, 90, 200), passable=False, name="Water", properties={}
        )
        return x, y

    def test_a_fisherman_on_the_bank_lands_a_catch(self):
        world = self.world
        water = self._water_beside(world.player.x + 4, world.player.y + 4)
        npc = next(n for n in world.village_npcs if not n.physical.is_dead)
        npc.economic.profession = "Fisherman"
        building = next(iter(world.buildings_by_id.values()))
        npc.schedule.work_building_id = building.id
        npc.x, npc.y = water[0] - 1, water[1]

        def raw_stock():
            return sum(
                quantity for key, quantity in dict(building.building_inventory).items()
                if str(key).startswith("raw_") and isinstance(quantity, int)
            )

        before = raw_stock()
        with patch("engine.random.random", return_value=0.0):
            completed = self.commands["fish_at_spot"].execute(world, npc, building, {})

        self.assertTrue(completed)
        self.assertGreater(raw_stock(), before, "the catch never reached the workplace")

    def test_fishing_far_from_water_catches_nothing(self):
        world = self.world
        npc = next(n for n in world.village_npcs if not n.physical.is_dead)
        building = next(iter(world.buildings_by_id.values()))
        npc.x, npc.y = 1, 1
        if world.find_water_near(npc.x, npc.y) is not None:
            self.skipTest("that corner of this world has water in it")
        self.assertFalse(self.commands["fish_at_spot"].execute(world, npc, building, {}))


class TestAFireCanBeLit(unittest.TestCase):
    """A fire pit is described as providing "warmth and light" and could do
    neither.

    The unlit tile carries becomes_lit and an interaction_hint of light_fire;
    nothing read either one, so a player could follow the construction recipe,
    build a fire pit, and stand next to a cold ring of stones with no option but
    Examine. It is not only comfort: the lit tile is workstation_type "fire",
    which is what all four cooking recipes require, and no other tile in a
    generated world carried it.
    """

    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")

    def _tile(self, x, y, key):
        from data.decorations import DECORATION_ITEM_DEFINITIONS

        self.world.get_tile_at(x, y)
        self.world._change_map_tile((x, y), DECORATION_ITEM_DEFINITIONS[key])
        return self.world.get_tile_at(x, y)

    def test_an_unlit_pit_offers_lighting(self):
        tile = Tile(
            char="#", color=(1, 1, 1), passable=True, name="Simple Fire Pit",
            properties={"interaction_hint": "light_fire", "becomes_lit": "fire_pit_lit"},
        )
        actions = self.world._get_actions_for_entity(
            {"type": "tile", "data": tile, "name": tile.name}
        )
        self.assertIn("Light Fire", actions)

    def test_a_lit_fire_offers_putting_it_out(self):
        tile = Tile(
            char="#", color=(1, 1, 1), passable=False, name="Lit Fire Pit",
            properties={"extinguishes_to": "fire_pit_simple"},
        )
        actions = self.world._get_actions_for_entity(
            {"type": "tile", "data": tile, "name": tile.name}
        )
        self.assertIn("Extinguish Fire", actions)

    def test_lighting_needs_fuel(self):
        player = self.world.player
        x, y = player.x + 2, player.y
        self._tile(x, y, "fire_pit_simple")
        while player.has_item("raw_log", 1):
            player.remove_item("raw_log", 1)

        self.world.player_attempt_light_fire(x, y)

        self.assertEqual(self.world.get_tile_at(x, y).name, "Simple Fire Pit")

    def test_lighting_produces_heat_and_a_cooking_station(self):
        player = self.world.player
        x, y = player.x + 3, player.y
        self._tile(x, y, "fire_pit_simple")
        player.add_item("raw_log", 1)

        self.world.player_attempt_light_fire(x, y)

        tile = self.world.get_tile_at(x, y)
        self.assertTrue(tile.properties.get("heat_source"), "a lit fire gives no heat")
        self.assertEqual(
            tile.properties.get("workstation_type"), "fire",
            "a lit fire is not a cooking station, so the cooking recipes stay unreachable",
        )

    def test_putting_it_out_gives_back_the_pit(self):
        player = self.world.player
        x, y = player.x + 4, player.y
        self._tile(x, y, "fire_pit_simple")
        player.add_item("raw_log", 1)
        self.world.player_attempt_light_fire(x, y)

        self.world.player_attempt_extinguish_fire(x, y)

        self.assertEqual(self.world.get_tile_at(x, y).name, "Simple Fire Pit")

    def test_lighting_something_that_is_not_a_fire_does_nothing(self):
        player = self.world.player
        x, y = player.x + 5, player.y
        self.world._change_map_tile((x, y), TILE_DEFINITIONS["plains"])
        player.add_item("raw_log", 1)
        before = self.world.get_tile_at(x, y).name

        self.world.player_attempt_light_fire(x, y)

        self.assertEqual(self.world.get_tile_at(x, y).name, before)


if __name__ == "__main__":
    unittest.main()
