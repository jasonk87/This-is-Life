"""Both scripted quests can actually be offered, and both can be finished.

The game ships two written quests. Only one was reachable.

The offer was hard-coded: the code named kill_wolves_01 and the Sheriff directly,
so the other quest - a Healer asking for herbs - was never offered by anything at
all, despite carrying a giver role, offer dialogue, accept lines and rewards.
Nobody noticed because until recently no village generated a clinic, so no world
had a Healer to be disappointed by.

The Healer's quest also asked for the wrong herb. It wanted five `herb_generic`,
which nothing in the world produces - it exists only as something a player can
plant if they somehow already have some. The herb this game actually grows,
forages and sells is `medicinal_herb`: the Healer forages it and the clinic
stocks it, so the quest can now be finished by buying from the person who set it.

Offering is driven by the definitions now, so a third quest needs a data entry
and not a branch.

Offering was also the whole of it. Nothing recorded that a scripted quest had
been offered, so saying "accept" only ever matched the dynamic help-quest path -
which reads an object on the NPC that a scripted offer never creates. Neither
written quest had ever entered a player's quest log, which also made
complete_quest's is_static_quest branch dead code.

And the wolf hunt could not have progressed even so: kills were counted only for
quests carrying a target_faction_id, which is what the mercenary contract uses.
The scripted hunt names its quarry - "Dire Wolf" - and nothing compared it.
"""

import unittest

from data.items import ITEM_DEFINITIONS
from data.quests import QUEST_DEFINITIONS
from engine import World
from tests.world_cache import fresh_world


class TestEveryScriptedQuestIsCompletable(unittest.TestCase):
    """Whatever a quest asks for has to be obtainable, or it is decoration."""

    @classmethod
    def setUpClass(cls):
        cls.world = fresh_world(seed=5)

    def _world_stock_of(self, item_key):
        return sum(
            int(b.building_inventory.get(item_key, 0) or 0)
            for b in self.world.buildings_by_id.values()
        )

    def test_every_fetch_quest_asks_for_something_that_exists(self):
        for quest_id, quest in QUEST_DEFINITIONS.items():
            if quest.get("type") != "fetch":
                continue
            item_key = quest.get("item_to_fetch_key")
            with self.subTest(quest=quest_id):
                self.assertIn(
                    item_key, ITEM_DEFINITIONS,
                    f"{quest_id} asks for {item_key!r}, which is not an item",
                )

    def test_every_fetch_quest_asks_for_something_a_player_can_get(self):
        """The distinction that mattered: herb_generic is a defined item and is
        still unobtainable, because nothing produces it."""
        for quest_id, quest in QUEST_DEFINITIONS.items():
            if quest.get("type") != "fetch":
                continue
            item_key = quest.get("item_to_fetch_key")
            wanted = int(quest.get("item_fetch_count", 1))
            with self.subTest(quest=quest_id):
                self.assertGreaterEqual(
                    self._world_stock_of(item_key), wanted,
                    f"{quest_id} wants {wanted} x {item_key} and the world holds "
                    f"fewer than that anywhere",
                )

    def test_every_quest_names_a_giver_role_that_exists_in_a_village(self):
        professions = {
            n.economic.profession for n in self.world.village_npcs
            if not n.physical.is_dead
        }
        buildings = {b.building_type for b in self.world.buildings_by_id.values()}
        for quest_id, quest in QUEST_DEFINITIONS.items():
            role = quest.get("quest_giver_id_or_role")
            with self.subTest(quest=quest_id):
                self.assertTrue(role, f"{quest_id} names no giver")
                # Either somebody already holds the role, or there is a workplace
                # that hires for it - professions fill in over the first days.
                hireable = {
                    "Sheriff": "sheriff_office",
                    "Healer": "clinic",
                }.get(role)
                self.assertTrue(
                    role in professions or (hireable and hireable in buildings),
                    f"{quest_id} is given by a {role}, and this world has neither "
                    f"one nor anywhere to hire one",
                )


class TestOfferingIsDrivenByTheDefinitions(unittest.TestCase):
    def setUp(self):
        self.world = fresh_world(seed=5)
        self.world.chat_ui_history = []

    def test_both_quests_name_a_role_the_offer_loop_can_match(self):
        """The loop matches quest_giver_id_or_role against a profession. A quest
        whose giver is not a profession name can never be offered, which is the
        failure this replaces."""
        for quest_id, quest in QUEST_DEFINITIONS.items():
            role = quest.get("quest_giver_id_or_role")
            with self.subTest(quest=quest_id):
                self.assertIsInstance(role, str)
                self.assertTrue(role.strip())

    def test_no_quest_is_offered_by_a_hard_coded_profession_only(self):
        """Guards the regression directly: if someone reintroduces a branch that
        names one quest, the other stops being offered and this notices."""
        import inspect

        import engine

        source = inspect.getsource(engine.World)
        self.assertNotIn(
            'QUEST_DEFINITIONS.get("kill_wolves_01")', source,
            "quest offering names a single quest in code again",
        )


class TestAScriptedQuestCanBeTakenAndFinished(unittest.TestCase):
    """The three steps a quest needs: offered, accepted, completed."""

    def setUp(self):
        self.world = fresh_world(seed=5)
        self.world.chat_ui_history = []
        self.giver = next(n for n in self.world.village_npcs if not n.physical.is_dead)

    def _offer(self, quest_id):
        """What the dialogue path does when it offers, without driving the whole
        conversation."""
        self.giver.offered_quest_id = quest_id
        return QUEST_DEFINITIONS[quest_id]

    def test_accepting_puts_the_quest_in_the_log(self):
        self._offer("fetch_herbs_01")
        self.world.chat_ui_active = True
        self.world.chat_ui_target_npc = self.giver

        self.world.continue_npc_dialogue(self.giver, "accept")

        self.assertIn(
            "fetch_herbs_01", self.world.player.knowledge.active_quests,
            "saying accept to a scripted offer did not put it in the quest log",
        )

    def test_declining_leaves_the_log_empty(self):
        self._offer("fetch_herbs_01")
        self.world.chat_ui_active = True
        self.world.chat_ui_target_npc = self.giver

        self.world.continue_npc_dialogue(self.giver, "decline")

        self.assertNotIn("fetch_herbs_01", self.world.player.knowledge.active_quests)
        self.assertIsNone(getattr(self.giver, "offered_quest_id", None))

    def test_an_accepted_quest_carries_what_completion_needs(self):
        """complete_quest reads these keys; a missing one fails at hand-in, which
        is the worst moment to find out."""
        self._offer("kill_wolves_01")
        self.world.chat_ui_active = True
        self.world.chat_ui_target_npc = self.giver

        self.world.continue_npc_dialogue(self.giver, "accept")

        entry = self.world.player.knowledge.active_quests.get("kill_wolves_01")
        self.assertIsNotNone(entry)
        for key in ("title", "type", "quest_giver_id", "target_count", "progress"):
            self.assertIn(key, entry)

    def test_a_kill_of_the_named_quarry_counts(self):
        quest = QUEST_DEFINITIONS["kill_wolves_01"]
        self.world.player.knowledge.active_quests["kill_wolves_01"] = {
            "title": quest["title"], "description": "", "type": "kill",
            "quest_giver_id": self.giver.id,
            "target_npc_name_prefix": quest["target_npc_name_prefix"],
            "target_count": quest["target_count"], "progress": 0,
        }
        from engine import DireWolf

        wolf = DireWolf(self.world.player.x + 2, self.world.player.y)
        self.world.npcs.append(wolf)
        self.world.handle_npc_death(wolf, killer_id=self.world.player.id)

        self.assertEqual(
            self.world.player.knowledge.active_quests["kill_wolves_01"]["progress"], 1,
            "killing a Dire Wolf did not count towards the wolf hunt",
        )

    def test_killing_something_else_does_not_count(self):
        quest = QUEST_DEFINITIONS["kill_wolves_01"]
        self.world.player.knowledge.active_quests["kill_wolves_01"] = {
            "title": quest["title"], "description": "", "type": "kill",
            "quest_giver_id": self.giver.id,
            "target_npc_name_prefix": quest["target_npc_name_prefix"],
            "target_count": quest["target_count"], "progress": 0,
        }
        bystander = next(
            n for n in self.world.village_npcs
            if not n.physical.is_dead and n is not self.giver
        )
        self.world.handle_npc_death(bystander, killer_id=self.world.player.id)

        self.assertEqual(
            self.world.player.knowledge.active_quests["kill_wolves_01"]["progress"], 0,
            "killing a villager counted towards a wolf hunt",
        )

    def test_handing_in_a_fetch_quest_pays_out(self):
        quest = QUEST_DEFINITIONS["fetch_herbs_01"]
        item_key = quest["item_to_fetch_key"]
        count = int(quest["item_fetch_count"])
        self.world.player.knowledge.active_quests["fetch_herbs_01"] = {
            "title": quest["title"], "description": "", "type": "fetch",
            "quest_giver_id": self.giver.id,
            "item_to_fetch_key": item_key, "item_fetch_count": count,
            "progress": 0,
        }
        self.world.player.add_item(item_key, count)
        money_before = self.world.player.economic.money

        self.world.complete_quest("fetch_herbs_01", self.giver)

        self.assertNotIn(
            "fetch_herbs_01", self.world.player.knowledge.active_quests,
            "the quest stayed active after being handed in",
        )
        self.assertGreater(
            self.world.player.economic.money, money_before,
            "handing in the herbs paid nothing",
        )


if __name__ == "__main__":
    unittest.main()
