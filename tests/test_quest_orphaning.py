import unittest

import engine
from engine import NPC, World


class TestQuestOrphanedByGiverDeath(unittest.TestCase):
    """Bug-hunt audit item 3a: when a quest-giver NPC dies, their active
    quest used to just sit in player.knowledge.active_quests forever with
    no failure state and no notice - confirmed live before this fix (the
    quest survived a real handle_npc_death call untouched, and there was no
    route back to it since complete_quest can only be reached through
    dialogue with the now-dead, now-removed-from-village_npcs giver)."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=801)
        self.world._change_map_tile = lambda *a, **k: None
        self.world._update_entity_position = lambda e, x, y: (setattr(e, "x", x), setattr(e, "y", y))

    def _giver(self, name="QuestGiver"):
        npc = NPC(0, 0, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        self.world.village_npcs.append(npc)
        return npc

    def test_dialogue_offered_fetch_quest_fails_when_giver_dies(self):
        """Uses the real key ('quest_giver_id') set by the dialogue accept
        flow at engine.py's chat-response handler."""
        giver = self._giver()
        self.world.player.knowledge.active_quests["fetch_1"] = {
            "title": "Fetch me some bread",
            "type": "fetch",
            "item_to_fetch_key": "bread",
            "item_fetch_count": 1,
            "quest_giver_id": giver.id,
        }

        self.world.handle_npc_death(giver, killer_id=None, cause_of_death="test")

        self.assertNotIn("fetch_1", self.world.player.knowledge.active_quests)
        self.assertIn("fetch_1", self.world.player.knowledge.failed_quests)

    def test_mercenary_contract_quest_fails_when_giver_dies(self):
        """Uses the OTHER real key ('giver_id') set by the mercenary
        contract acceptance flow - a pre-existing inconsistency in the
        codebase between the two quest-acceptance sites, both are checked."""
        giver = self._giver()
        self.world.player.knowledge.active_quests["contract_1"] = {
            "title": "Mercenary: Defend the Village",
            "type": "kill",
            "target_faction_id": "rival_village",
            "target_count": 3,
            "progress": 1,
            "reward_money": 100,
            "giver_id": giver.id,
        }

        self.world.handle_npc_death(giver, killer_id=None, cause_of_death="test")

        self.assertNotIn("contract_1", self.world.player.knowledge.active_quests)
        self.assertIn("contract_1", self.world.player.knowledge.failed_quests)

    def test_player_is_notified_when_a_quest_fails(self):
        giver = self._giver("Old Man Willow")
        self.world.player.knowledge.active_quests["fetch_2"] = {
            "title": "Fetch me some bread",
            "type": "fetch",
            "quest_giver_id": giver.id,
        }
        self.world.handle_npc_death(giver, killer_id=None, cause_of_death="test")

        latest_messages = " ".join(self.world.chat_log)
        self.assertIn("Fetch me some bread", latest_messages)
        self.assertIn("Old Man Willow", latest_messages)

    def test_unrelated_active_quest_survives_a_different_npcs_death(self):
        giver = self._giver("Real Giver")
        bystander = self._giver("Bystander")
        self.world.player.knowledge.active_quests["fetch_3"] = {
            "title": "Fetch me some bread",
            "type": "fetch",
            "quest_giver_id": giver.id,
        }

        self.world.handle_npc_death(bystander, killer_id=None, cause_of_death="test")

        self.assertIn("fetch_3", self.world.player.knowledge.active_quests)
        self.assertNotIn("fetch_3", self.world.player.knowledge.failed_quests)

    def test_noticeboard_quest_with_no_giver_is_untouched_by_any_death(self):
        """Noticeboard shortage quests aren't tied to any one NPC (no
        quest_giver_id/giver_id at all) - nothing should ever fail them via
        this path."""
        giver = self._giver()
        self.world.player.knowledge.active_quests["shortage_1"] = {
            "title": "Supply Bread",
            "type": "fetch",
            "item_to_fetch_key": "bread",
            "item_fetch_count": 5,
        }

        self.world.handle_npc_death(giver, killer_id=None, cause_of_death="test")

        self.assertIn("shortage_1", self.world.player.knowledge.active_quests)

    def test_animal_deaths_never_touch_quests(self):
        """Cheap guard in handle_npc_death skips the whole check for
        Animal deaths, which can never be quest givers."""
        from entities.animal import Animal

        giver = self._giver()
        self.world.player.knowledge.active_quests["fetch_4"] = {
            "title": "Fetch me some bread",
            "type": "fetch",
            "quest_giver_id": giver.id,
        }
        deer = Animal(0, 0, name="Deer", animal_type="deer")
        self.world.village_npcs.append(deer)

        self.world.handle_npc_death(deer, killer_id=None, cause_of_death="test")

        self.assertIn("fetch_4", self.world.player.knowledge.active_quests)

    def test_quest_can_still_be_completed_via_dialogue_before_the_giver_dies(self):
        """Baseline: confirms this fix doesn't interfere with the normal,
        successful completion path."""
        giver = self._giver()
        self.world.player.knowledge.active_quests["fetch_5"] = {
            "title": "Fetch me some bread",
            "type": "fetch",
            "item_to_fetch_key": "bread",
            "item_fetch_count": 1,
            "quest_giver_id": giver.id,
        }
        self.world.player.add_item("bread", 1)

        self.world.complete_quest("fetch_5", giver)

        self.assertNotIn("fetch_5", self.world.player.knowledge.active_quests)
        self.assertIn("fetch_5", self.world.player.knowledge.completed_quests)
        self.assertNotIn("fetch_5", self.world.player.knowledge.failed_quests)


if __name__ == "__main__":
    unittest.main()
