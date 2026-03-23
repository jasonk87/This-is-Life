
import unittest
from unittest.mock import MagicMock
from engine import World, NPC, Player, Event, DireWolf
from simulation.history import HistoryLedger

class MockWorld(World):
    def __init__(self):
        self.game_time = 0
        self.history = HistoryLedger()
        self.global_events = self.history.events
        self.books = self.history.books
        self.player = MagicMock()
        self.player.id = 1
        self.player.social.reputation = {}
        self.player.social.fame = 0
        self.player.social.infamy = 0
        self.player_fov_map = MagicMock()
        # We need this map for simple boolean checks in log_event
        self.player_fov_map.__getitem__ = MagicMock(return_value=False)

        self.village_npcs = []
        self.npcs = []
        self.chunk_width = 1
        self.chunk_height = 1
        self.chunks = [[MagicMock()]]
        self.buildings_by_id = {}
        self.add_message_to_chat_log = MagicMock()
        self.interaction_context = {"active": False, "target_entities": []}
        self.chat_ui_target_npc = None
        self.chat_ui_active = False
        self.trade_ui_npc_target = None
        self.trade_ui_active = False
        self.last_talked_to_npc = None
        self.entity_positions_dirty = True
        self.entity_chunks_dirty = True
        self.entity_positions = {}
        self.entities_by_chunk = {}

    def get_entity_by_id(self, entity_id):
        pass # To be mocked

class TestOmniscience(unittest.TestCase):
    def setUp(self):
        self.world = MockWorld()
        # Mock get_entity_by_id
        self.world.get_entity_by_id = MagicMock()

        # Mock add_message
        self.world.add_message_to_chat_log = MagicMock()

    def test_secret_murder_no_infamy(self):
        # Setup victim
        victim = NPC(x=10, y=10, name="Victim")
        victim.id = 2
        victim.economic.profession = "Villager"
        victim.combat.is_hostile_to_player = False

        # Mock witnesses: None
        self.world._get_witnesses_to_action = MagicMock(return_value=[])
        self.world.get_entity_by_id.side_effect = lambda id: self.world.player if id == 1 else victim

        # Player kills victim
        # Calling handle_npc_death directly, simulating player as killer
        self.world.handle_npc_death(victim, killer_id=1)

        # Check event
        self.assertEqual(len(self.world.global_events), 1)
        event = self.world.global_events[0]
        self.assertFalse(event.public_knowledge, "Secret murder should not be public knowledge")

        # Check Infamy
        self.assertEqual(self.world.player.social.infamy, 0, "Player should not gain infamy for secret murder")

    def test_public_heroic_kill_fame_gain(self):
        # Setup monster
        monster = DireWolf(x=10, y=10)
        monster.id = 3

        # Setup witness
        witness = NPC(x=12, y=10, name="Witness")
        witness.id = 4

        # Mock witnesses: Witness present
        self.world._get_witnesses_to_action = MagicMock(return_value=[witness])
        self.world.get_entity_by_id.side_effect = lambda id: self.world.player if id == 1 else monster

        # Player kills monster
        self.world.handle_npc_death(monster, killer_id=1)

        # Check event
        self.assertEqual(len(self.world.global_events), 1)
        event = self.world.global_events[0]
        self.assertTrue(event.public_knowledge, "Witnessed kill should be public knowledge")

        # Check Fame
        self.assertEqual(self.world.player.social.fame, 20, "Player should gain fame for witnessed monster kill")

if __name__ == '__main__':
    unittest.main()
