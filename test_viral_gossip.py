
import unittest
from unittest.mock import MagicMock, patch
from engine import World, NPC, Player, Event

class MockWorld(World):
    def __init__(self):
        self.game_time = 1000
        self.village_npcs = []
        self.npcs = []
        self.global_events = []
        self.player = MagicMock(spec=Player)
        self.player.id = 1
        self.player.name = "Player" # Fix for name sort
        self.buildings_by_id = {}
        self.add_message_to_chat_log = MagicMock()
        self.chunks = [[MagicMock()]]
        self.chunk_width = 1
        self.chunk_height = 1
        # Mock methods
        self._get_village_for_npc = MagicMock(return_value=None)
        self._call_ollama = MagicMock(return_value='"He is a great hero."') # Return JSON string usually, but prompt dependent. Prompt output is raw string.
        # Chat UI
        self.chat_ui_history = []
        self.player_fov_map = MagicMock()
        self.npc_fov_maps = {}
        self.items_on_map = {}

    def get_entity_by_id(self, entity_id):
        if entity_id == self.player.id: return self.player
        for n in self.village_npcs + self.npcs:
            if n.id == entity_id: return n
        return None

    # We need to include the helper method we are testing if we don't import World fully?
    # No, MockWorld inherits World, so it has _get_most_interesting_known_event if engine.py is correct.

class TestViralGossip(unittest.TestCase):
    def setUp(self):
        self.world = MockWorld()

    def test_viral_spread(self):
        # Create chain of NPCs
        npc_a = NPC(0, 0, "A")
        npc_b = NPC(1, 0, "B") # Adjacent
        npc_c = NPC(2, 0, "C") # Adjacent to B

        # Initialize knowledge dicts (just in case)
        npc_a.knowledge.known_events = {}
        npc_b.knowledge.known_events = {}
        npc_c.knowledge.known_events = {}

        self.world.village_npcs.extend([npc_a, npc_b, npc_c])

        # Event X: High impact (death)
        event_x = Event("entity_death", "King died", 999, self.world.game_time - 10)
        npc_a.knowledge.known_events[event_x.id] = event_x

        # 1. A socializes with B
        # Force A to socialize with B
        npc_a.schedule.current_task = "socializing"
        npc_a.task_target_entity_id = npc_b.id
        # Position them
        npc_a.x, npc_a.y = 0, 0
        npc_b.x, npc_b.y = 1, 0
        # Give dummy path to trigger arrival logic in _update_npc_movement
        npc_a.schedule.current_path = [(0,0)]

        # Run movement/social logic
        self.world._update_npc_movement()

        # Verify B knows X
        self.assertIn(event_x.id, npc_b.knowledge.known_events, "B should have learned event X from A")

        # 2. B socializes with C
        # B is now the active sharer
        npc_b.schedule.current_task = "socializing"
        npc_b.task_target_entity_id = npc_c.id
        npc_b.x, npc_b.y = 1, 0
        npc_c.x, npc_c.y = 2, 0
        npc_b.schedule.current_path = [(1,0)] # Dummy path

        # A is done
        npc_a.schedule.current_task = "idle"
        npc_a.schedule.current_path = []

        self.world._update_npc_movement()

        # Verify C knows X
        self.assertIn(event_x.id, npc_c.knowledge.known_events, "C should have learned event X from B")

    def test_ask_about(self):
        npc = NPC(0, 0, "Loremaster")
        subject = NPC(0, 0, "Hero")
        self.world.village_npcs.extend([npc, subject])

        event = Event("combat_attack", "Hero fought Wolf", subject.id, self.world.game_time - 10)
        npc.knowledge.known_events[event.id] = event

        # Mock chat history
        self.world.chat_ui_history = []

        # Player asks
        self.world.continue_npc_dialogue(npc, "Who is Hero?")

        # Verify response
        # Note: _call_ollama mock returns "He is a great hero." (JSON encoded string if json.loads used, raw string otherwise?)
        # continue_npc_dialogue uses _call_ollama(prompt) which returns string.
        # It does NOT json.loads the "Ask About" response.
        # So mock should return just the text.

        self.assertEqual(self.world.chat_ui_history[-1], (npc.name, '"He is a great hero."'))

if __name__ == '__main__':
    unittest.main()
