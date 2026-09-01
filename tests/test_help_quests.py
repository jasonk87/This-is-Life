"""A desperate villager can actually ask the player for help.

run_npc_proactive_help_seeking_policy is the branch for someone who is starving
or parched AND cannot fix it themselves - they do not know where any food or
water is. It fires at hunger or thirst of 90.

It sat *after* evaluate_needs_utility in the scheduling flow, and that claims the
turn and returns at 70. So the policy was never once reached at the level it
requires: measured, an NPC at hunger 95 with no known food source generated
nothing across 40 scheduling passes. The entire "villager walks up and asks you
for help" quest line could not happen.
"""

import unittest

from config import DAY_LENGTH_TICKS
from engine import World
from simulation.systems import scheduling
from simulation.systems.scheduling import run_npc_humanoid_scheduling_flow


def _accepted_quest_record(quest):
    """The shape the dialogue acceptance path stores in active_quests."""
    return {
        "title": quest.title,
        "description": quest.description,
        "type": quest.type,
        "quest_giver_id": quest.quest_giver_id,
        "item_to_fetch_key": quest.item_key,
        "item_fetch_count": quest.required_count,
        "progress": 0,
    }


class TestDesperateVillagersAskForHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()

    def _starving_villager(self, world=None):
        world = world or self.world
        npc = next(
            n for n in world.village_npcs
            if not n.physical.is_dead and not getattr(n, "active_quest", None)
        )
        npc.is_sleeping = False
        npc.knowledge.known_locations.pop("the tavern", None)
        npc.knowledge.known_locations.pop("bakery", None)
        npc.physical.hunger = 95
        return npc

    def _run_until_quest(self, npc, world=None, attempts=200):
        """Drive the help-seeking policy directly, for the reason above."""
        world = world or self.world
        for _ in range(attempts):
            scheduling.run_npc_proactive_help_seeking_policy(world, npc)
            quest = getattr(npc, "active_quest", None)
            if quest:
                return quest
        return None

    def test_a_starving_villager_who_knows_no_food_source_asks_for_help(self):
        """Drives the policy directly. Whether the whole flow reaches it is a
        separate question with its own test below - going through the flow here
        made this flaky, because an NPC who happens to be carrying a grudge or a
        pending social reaction returns from an earlier branch every time."""
        npc = self._starving_villager()
        quest = None
        for _ in range(200):
            scheduling.run_npc_proactive_help_seeking_policy(self.world, npc)
            quest = getattr(npc, "active_quest", None)
            if quest:
                break
        self.assertIsNotNone(quest, "no help was ever asked for at hunger 95")
        self.assertEqual(quest.quest_giver_id, npc.id)
        self.assertGreater(quest.required_count, 0)

    def test_help_seeking_is_reached_before_the_needs_system_claims_the_turn(self):
        """Asserted by observation, not by reading the source - an earlier version of
        this test searched the function text and was fooled by a comment naming the
        very symbol it was looking for."""
        world = World(player_first_name="Tester")
        world._pre_simulate_world()
        npc = self._starving_villager(world)

        order = []
        real_needs = scheduling.evaluate_needs_utility
        real_help = scheduling.run_npc_proactive_help_seeking_policy

        def watched_needs(*args, **kwargs):
            order.append("needs")
            return real_needs(*args, **kwargs)

        def watched_help(*args, **kwargs):
            order.append("help")
            return real_help(*args, **kwargs)

        scheduling.evaluate_needs_utility = watched_needs
        scheduling.run_npc_proactive_help_seeking_policy = watched_help
        try:
            run_npc_humanoid_scheduling_flow(world, npc, world.game_time % DAY_LENGTH_TICKS)
        finally:
            scheduling.evaluate_needs_utility = real_needs
            scheduling.run_npc_proactive_help_seeking_policy = real_help

        self.assertIn("help", order, "the help policy was never reached at all")
        if "needs" in order:
            self.assertLess(
                order.index("help"), order.index("needs"),
                "the needs system ran first, which is what made the help quest unreachable",
            )

    def test_a_villager_who_knows_where_food_is_does_not_beg(self):
        world = World(player_first_name="Tester")
        world._pre_simulate_world()
        npc = self._starving_villager(world)
        npc.knowledge.known_locations["the tavern"] = (npc.x, npc.y)

        self.assertIsNone(
            self._run_until_quest(npc, world, attempts=60),
            "someone who knows where the tavern is still begged for food",
        )

    def test_a_well_fed_villager_does_not_beg(self):
        world = World(player_first_name="Tester")
        world._pre_simulate_world()
        npc = self._starving_villager(world)
        npc.physical.hunger = 10
        npc.physical.thirst = 10

        self.assertIsNone(self._run_until_quest(npc, world, attempts=60))

    def test_the_quest_can_be_handed_in(self):
        world = World(player_first_name="Tester")
        world._pre_simulate_world()
        npc = self._starving_villager(world)
        quest = self._run_until_quest(npc, world)
        self.assertIsNotNone(quest)

        world.player.knowledge.active_quests[quest.id] = _accepted_quest_record(quest)
        world.player.add_item(quest.item_key, quest.required_count)

        world.complete_quest(quest.id, npc)

        self.assertNotIn(
            quest.id, world.player.knowledge.active_quests,
            "the quest stayed active after being fulfilled",
        )


if __name__ == "__main__":
    unittest.main()
