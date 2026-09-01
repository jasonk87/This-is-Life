"""Interact (E) reaches what is around the player, not only what is straight ahead.

Interaction used to act on the single tile the player last stepped towards, so
walking north up to a door on your left left you pressing E at a blank wall.
"""

import unittest
from types import SimpleNamespace

import main
from config import CHUNK_SIZE
from engine import World


class _FakeTile:
    def __init__(self, name="Plains", passable=True, **properties):
        self.name = name
        self.passable = passable
        self.properties = properties
        self.is_choppable = False


class _FakeWorld:
    """Just enough world for the interaction classifier."""

    def __init__(self, tiles, player_x=5, player_y=5, facing=(0, -1), interactables=None):
        self.tiles = tiles
        self.all_npcs = []
        self.toggled_doors = []
        self.messages = []
        # Tiles the fallback interaction menu should consider non-empty.
        self.interactables = interactables or {}
        self.interaction_context = {}
        self.player = SimpleNamespace(
            x=player_x,
            y=player_y,
            state=SimpleNamespace(last_dx=facing[0], last_dy=facing[1]),
            has_item=lambda item_key: False,
        )

    def get_tile_at(self, x, y):
        return self.tiles.get((x, y))

    def player_attempt_toggle_door(self, x, y):
        self.toggled_doors.append((x, y))

    def add_message_to_chat_log(self, message, category=None):
        self.messages.append(message)

    def _get_interactables_at(self, x, y):
        if (x, y) not in self.interactables:
            return []
        return [{"type": "tile", "data": self.tiles.get((x, y)), "name": "ground"}]

    def _get_actions_for_entity(self, entity):
        return ["Examine"]


class TestFacingOrder(unittest.TestCase):
    def test_every_neighbour_is_offered_exactly_once(self):
        for facing in [(0, -1), (0, 1), (1, 0), (-1, 0), (0, 0)]:
            offsets = main._neighbour_offsets_by_facing(*facing)
            self.assertEqual(len(offsets), 8, f"facing {facing}")
            self.assertEqual(len(set(offsets)), 8, f"facing {facing} repeats an offset")
            self.assertNotIn((0, 0), offsets)

    def test_the_tile_straight_ahead_comes_first(self):
        for facing in [(0, -1), (0, 1), (1, 0), (-1, 0)]:
            self.assertEqual(main._neighbour_offsets_by_facing(*facing)[0], facing)

    def test_what_is_behind_comes_last(self):
        for facing in [(0, -1), (0, 1), (1, 0), (-1, 0)]:
            offsets = main._neighbour_offsets_by_facing(*facing)
            behind = (-facing[0], -facing[1])
            self.assertGreater(
                offsets.index(behind),
                offsets.index(facing),
                "the tile behind should be considered after the one ahead",
            )

    def test_a_player_who_has_not_moved_still_gets_an_order(self):
        self.assertEqual(len(main._neighbour_offsets_by_facing(0, 0)), 8)

    def test_the_players_own_tile_is_considered_last(self):
        world = _FakeWorld({})
        candidates = main._smart_interaction_candidates(world)
        self.assertEqual(candidates[-1], (world.player.x, world.player.y))
        self.assertEqual(len(candidates), 9)


class TestSmartInteractionReach(unittest.TestCase):
    def test_a_door_beside_the_player_is_reached(self):
        """Walking north with the door on your left: E should still open it."""
        world = _FakeWorld(
            {
                (5, 5): _FakeTile("Plains"),
                (5, 4): _FakeTile("Plains"),  # straight ahead, nothing to do
                (4, 5): _FakeTile("Door", passable=False, is_door=True),
            },
            facing=(0, -1),
        )
        self.assertTrue(main.execute_smart_interaction(world, None))
        self.assertEqual(world.toggled_doors, [(4, 5)])

    def test_the_tile_ahead_still_wins_when_it_has_an_action(self):
        world = _FakeWorld(
            {
                (5, 5): _FakeTile("Plains"),
                (5, 4): _FakeTile("Door", passable=False, is_door=True),
                (4, 5): _FakeTile("Door", passable=False, is_door=True),
            },
            facing=(0, -1),
        )
        main.execute_smart_interaction(world, None)
        self.assertEqual(world.toggled_doors, [(5, 4)], "the door ahead should win")

    def test_a_door_behind_the_player_is_still_reached(self):
        world = _FakeWorld(
            {
                (5, 5): _FakeTile("Plains"),
                (5, 4): _FakeTile("Plains"),
                (5, 6): _FakeTile("Door", passable=False, is_door=True),
            },
            facing=(0, -1),
        )
        main.execute_smart_interaction(world, None)
        self.assertEqual(world.toggled_doors, [(5, 6)])

    def test_nothing_to_do_anywhere_takes_no_turn(self):
        world = _FakeWorld({(5, 5): _FakeTile("Plains"), (5, 4): _FakeTile("Plains")})
        self.assertFalse(main.execute_smart_interaction(world, None))
        self.assertEqual(world.toggled_doors, [])

    def test_the_fallback_menu_opens_on_a_tile_that_actually_holds_something(self):
        """Standing on a dropped item and facing empty ground should still offer it."""
        world = _FakeWorld(
            {(5, 5): _FakeTile("Plains"), (5, 4): _FakeTile("Plains")},
            facing=(0, -1),
            interactables={(5, 5): True},
        )
        self.assertFalse(main.execute_smart_interaction(world, None))
        self.assertTrue(world.interaction_context.get("active"))
        self.assertEqual(
            (world.interaction_context["x"], world.interaction_context["y"]), (5, 5)
        )


class TestSmartInteractionInAGeneratedWorld(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()
        main._ensure_zoom_state(cls.world)
        cls.world._ensure_entity_positions_current()
        cls.setup = cls._find_door_with_a_free_neighbour()

    @classmethod
    def _find_door_with_a_free_neighbour(cls):
        """A door, a free tile beside it, and a facing that leaves the door the only option.

        Requiring the door to be the *only* actionable neighbour keeps the test
        about reach. Otherwise a villager standing on the far side, or a
        choppable tree, is a legitimate thing for E to pick instead, and the
        test would fail for a reason that is not a bug.
        """
        world = cls.world
        for chunk_y, row in enumerate(world.chunks):
            for chunk_x, chunk in enumerate(row):
                if not chunk.is_terrain_generated:
                    continue
                for local_y in range(CHUNK_SIZE):
                    for local_x in range(CHUNK_SIZE):
                        x = chunk_x * CHUNK_SIZE + local_x
                        y = chunk_y * CHUNK_SIZE + local_y
                        tile = world.get_tile_at(x, y)
                        if not (tile and tile.properties.get("is_door")):
                            continue
                        for stand_x, stand_y in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                            neighbour = world.get_tile_at(stand_x, stand_y)
                            if not (
                                neighbour
                                and neighbour.passable
                                and world.entity_positions.get((stand_x, stand_y)) is None
                            ):
                                continue
                            facing = cls._facing_away_from(stand_x, stand_y, x, y)
                            if facing is None:
                                continue
                            if cls._only_actionable_neighbour(stand_x, stand_y, facing) != (x, y):
                                continue
                            return (x, y), (stand_x, stand_y), facing
        return None

    @classmethod
    def _facing_away_from(cls, stand_x, stand_y, door_x, door_y):
        for facing_x, facing_y in ((0, -1), (0, 1), (1, 0), (-1, 0)):
            if (stand_x + facing_x, stand_y + facing_y) != (door_x, door_y):
                return facing_x, facing_y
        return None

    @classmethod
    def _only_actionable_neighbour(cls, stand_x, stand_y, facing):
        """The single tile around (stand_x, stand_y) E could act on, or None if not exactly one."""
        world = cls.world
        previous = (world.player.x, world.player.y, world.player.state.last_dx, world.player.state.last_dy)
        world.player.x, world.player.y = stand_x, stand_y
        world.player.state.last_dx, world.player.state.last_dy = facing
        try:
            actionable = [
                (x, y)
                for x, y in main._smart_interaction_candidates(world)
                if main._classify_smart_action(world, x, y, None) is not None
            ]
        finally:
            world.player.x, world.player.y = previous[0], previous[1]
            world.player.state.last_dx, world.player.state.last_dy = previous[2], previous[3]
        return actionable[0] if len(actionable) == 1 else None

    def test_a_real_door_beside_the_player_opens(self):
        if self.setup is None:
            self.skipTest("generated world exposed no unambiguous door")
        (door_x, door_y), (stand_x, stand_y), facing = self.setup
        world = self.world
        world._update_entity_position(world.player, stand_x, stand_y)
        world.player.state.last_dx, world.player.state.last_dy = facing

        self.assertNotEqual(
            (stand_x + facing[0], stand_y + facing[1]),
            (door_x, door_y),
            "the player should not be facing the door",
        )
        before = world.get_tile_at(door_x, door_y).passable
        main.execute_smart_interaction(world, None)
        self.assertNotEqual(
            world.get_tile_at(door_x, door_y).passable,
            before,
            "E did not reach the door beside the player",
        )


if __name__ == "__main__":
    unittest.main()
