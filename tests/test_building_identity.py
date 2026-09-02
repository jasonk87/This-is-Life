"""A player standing in a shop can tell they are in one.

Two places told the player what they were standing on and neither told them what
they were standing *in*. The status panel reported the floor - a player inside
the bakery read "Wood Floor" - and inspecting a tile reported "Tile (201, 61)".
The building's identity appeared only if they happened to hover the mouse over
it.

That was survivable while shops sold nothing. It is not now: a shopkeeper trades
out of the building's stock, so finding the bakery is how you buy bread.
"""

import unittest

from engine import World
from rendering.console_renderer import _get_focus_summary


class TestTheStatusPanelNamesTheBuilding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Looker")
        cls.world._pre_simulate_world()

    def _stand_in(self, building_type):
        building = next(
            (b for b in self.world.buildings_by_id.values()
             if b.building_type == building_type),
            None,
        )
        if building is None:
            self.skipTest(f"no {building_type} in this world")
        self.world._update_entity_position(
            self.world.player, building.global_origin_x + 1, building.global_origin_y + 1
        )
        return building

    def test_standing_in_the_bakery_says_bakery(self):
        self._stand_in("bakery")
        standing_on, _ = _get_focus_summary(self.world)
        self.assertIn("Bakery", standing_on, f"the panel read {standing_on!r}")

    def test_standing_in_the_tavern_says_tavern(self):
        self._stand_in("tavern")
        standing_on, _ = _get_focus_summary(self.world)
        self.assertIn("Tavern", standing_on, f"the panel read {standing_on!r}")

    def test_it_still_names_the_ground_underfoot(self):
        """The floor was the only thing it reported and remains useful - a stone
        floor and a wooden one are not the same to walk on."""
        building = self._stand_in("bakery")
        tile = self.world.get_tile_at(self.world.player.x, self.world.player.y)
        standing_on, _ = _get_focus_summary(self.world)
        self.assertIn(tile.name, standing_on)
        del building

    def test_outdoors_it_says_only_the_ground(self):
        world = World(player_first_name="Wanderer")
        world._pre_simulate_world()
        player = world.player
        spot = None
        for radius in range(2, 40):
            for dx in (-radius, radius):
                candidate = (player.x + dx, player.y)
                if world.get_building_at(*candidate) is None:
                    tile = world.get_tile_at(*candidate)
                    if tile is not None:
                        spot = candidate
                        break
            if spot:
                break
        if spot is None:
            self.skipTest("could not find open ground near the player")

        world._update_entity_position(player, *spot)
        standing_on, _ = _get_focus_summary(world)
        self.assertNotIn(" - ", standing_on, f"open ground reported {standing_on!r}")


class TestInspectingATileNamesTheBuilding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Looker")
        cls.world._pre_simulate_world()

    def _plain_tile_inside(self, building):
        for dy in range(building.height):
            for dx in range(building.width):
                position = (building.global_origin_x + dx, building.global_origin_y + dy)
                selection = self.world.resolve_selection_target(position)
                if selection and selection.get("target_type") == "tile":
                    return selection
        return None

    def test_a_tile_in_the_bakery_reports_the_bakery(self):
        bakery = next(
            (b for b in self.world.buildings_by_id.values() if b.building_type == "bakery"),
            None,
        )
        if bakery is None:
            self.skipTest("no bakery in this world")
        selection = self._plain_tile_inside(bakery)
        if selection is None:
            self.skipTest("every tile in the bakery was occupied by something else")

        payload = self.world.build_inspection_payload(selection)

        self.assertEqual(payload["building_type"], "bakery")
        self.assertEqual(payload["building_id"], bakery.id)
        self.assertIn("Bakery", payload["display_name"])

    def test_open_ground_still_reports_a_plain_tile(self):
        player = self.world.player
        for radius in range(2, 40):
            position = (player.x + radius, player.y)
            if self.world.get_building_at(*position) is not None:
                continue
            selection = self.world.resolve_selection_target(position)
            if not selection or selection.get("target_type") != "tile":
                continue
            payload = self.world.build_inspection_payload(selection)
            self.assertIsNone(payload["building_type"])
            self.assertIn("Tile", payload["display_name"])
            return
        self.skipTest("could not find open ground near the player")

    def test_the_shelter_fields_are_untouched(self):
        """This branch already reported shelter and warmth; naming the building
        must not have displaced any of it.

        Uses a nearby tile rather than the one the player is standing on. The
        player is an actor at their own position, so resolve_selection_target
        there always answers "actor" - the earlier version of this guarded on
        getting a tile and therefore skipped on every single run, which is worse
        than failing: it looked like coverage and was not.
        """
        player = self.world.player
        selection = None
        for radius in range(1, 30):
            for dx, dy in ((radius, 0), (-radius, 0), (0, radius), (0, -radius)):
                candidate = self.world.resolve_selection_target((player.x + dx, player.y + dy))
                if candidate and candidate.get("target_type") == "tile":
                    selection = candidate
                    break
            if selection:
                break
        self.assertIsNotNone(selection, "found no plain tile anywhere near the player")

        payload = self.world.build_inspection_payload(selection)
        for key in ("sheltered", "shelter_id", "exposure_modifier", "recovery_modifier", "warmth_sources"):
            self.assertIn(key, payload)


if __name__ == "__main__":
    unittest.main()
