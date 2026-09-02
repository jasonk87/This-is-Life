"""The player's log carries local news, not the world's bookkeeping.

Two faults facing opposite directions, found by asking what a player would
actually see over thirty simulated days:

* Every hire anywhere in the world wrote a line to the player's log. That was
  harmless while hiring was rare, but the abstract labour market now fills posts
  in every village - measured, 52 of the 100 slots in the log were strangers
  taking jobs in settlements the player has never visited.

* Births wrote nothing at all. They reached the history ledger and the event
  system, and log_event even works out whether the player saw it, but nothing
  ever put them in front of the player. Over the same thirty days: 13 children
  born, not one mentioned.

The line drawn here is the one the world already draws for its level of detail -
chunks around the player are simulated in full, everything else is abstracted.
The ledger still records everything either way; this only decides what reaches
the four-line panel a player reads.
"""

import unittest

from config import WORLD_HEIGHT, WORLD_WIDTH
from engine import World


def far_from(world):
    """A spot in the world that is definitely not local to the player.

    Not "player.x + five chunks, clamped to the map edge": when the player spawns
    in the east that clamp collapses back to within a chunk of them, the news
    counts as local after all, and the test fails on where the world happened to
    put the player rather than on the behaviour.
    """
    player = world.player
    far_x = 20 if player.x > WORLD_WIDTH // 2 else WORLD_WIDTH - 20
    far_y = 20 if player.y > WORLD_HEIGHT // 2 else WORLD_HEIGHT - 20
    assert not world._is_local_news((far_x, far_y)), (
        "the far corner of the map counted as local to the player"
    )
    return far_x, far_y


class TestWhatCountsAsLocal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Watcher")
        cls.world._pre_simulate_world()

    def test_where_the_player_stands_is_local(self):
        player = self.world.player
        self.assertTrue(self.world._is_local_news((player.x, player.y)))

    def test_the_far_side_of_the_map_is_not(self):
        self.assertFalse(self.world._is_local_news(far_from(self.world)))

    def test_nowhere_is_not_local(self):
        self.assertFalse(self.world._is_local_news(None))

    def test_nonsense_coordinates_are_refused_rather_than_raising(self):
        self.assertFalse(self.world._is_local_news(("x", "y")))


class TestBirthsReachThePlayer(unittest.TestCase):
    def setUp(self):
        self.world = World(player_first_name="Watcher")
        self.world._pre_simulate_world()
        # Cleared so lengths mean something: chat_log caps at 100 and appending
        # to a full log pops the oldest, leaving the length unchanged.
        self.world.chat_log.clear()
        self.child = next(n for n in self.world.village_npcs if not n.physical.is_dead)

    def _record_birth_at(self, position, description):
        return self.world.record_birth_event(
            child=self.child,
            parent_ids=(1, 2),
            description=description,
            location=position,
        )

    def test_a_birth_in_the_village_is_announced(self):
        player = self.world.player
        self._record_birth_at((player.x, player.y), "A child is born to the village.")
        self.assertEqual(len(self.world.chat_log), 1)
        self.assertEqual(self.world.chat_log[-1], "A child is born to the village.")

    def test_a_birth_far_away_is_not(self):
        self._record_birth_at(far_from(self.world), "A child is born elsewhere.")
        self.assertEqual(self.world.chat_log, [])

    def test_the_world_remembers_the_distant_birth_anyway(self):
        """Quiet is not the same as forgotten - the ledger is the world's memory
        and must not depend on where the player happened to be standing."""
        before = len(self.world.history.events)
        record = self._record_birth_at(far_from(self.world), "A child is born elsewhere.")
        self.assertIsNotNone(record)
        self.assertGreater(len(self.world.history.events), before)


class TestHiringNewsIsLocalToo(unittest.TestCase):
    def setUp(self):
        self.world = World(player_first_name="Watcher")
        self.world._pre_simulate_world()
        self.world.chat_log.clear()
        self.building = next(
            b for b in self.world.buildings_by_id.values()
            if self.world._building_can_employ(b)
        )

    def _some_villager(self):
        npc = next(n for n in self.world.village_npcs if not n.physical.is_dead)
        npc.schedule.work_building_id = None
        return npc

    def test_hiring_someone_in_front_of_the_player_is_announced(self):
        npc = self._some_villager()
        player = self.world.player
        self.world._update_entity_position(npc, player.x, player.y)

        self.world._assign_job(npc, self.building, reason="test")

        self.assertTrue(self.world.chat_log, "a hire in the village said nothing")
        self.assertIn("hired", self.world.chat_log[-1].lower())

    def test_hiring_someone_far_away_is_not(self):
        npc = self._some_villager()
        self.world._update_entity_position(npc, *far_from(self.world))

        self.world._assign_job(npc, self.building, reason="test")

        self.assertEqual(
            [m for m in self.world.chat_log if "hired" in m.lower()], [],
            "a stranger three villages away announced their new job",
        )

    def test_the_employment_record_is_written_either_way(self):
        npc = self._some_villager()
        self.world._update_entity_position(npc, *far_from(self.world))
        before = len(self.world.history.events)

        self.world._assign_job(npc, self.building, reason="test")

        self.assertGreater(
            len(self.world.history.events), before,
            "the world stopped recording employment when it stopped announcing it",
        )


if __name__ == "__main__":
    unittest.main()
