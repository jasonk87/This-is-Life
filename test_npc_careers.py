
import unittest
from unittest.mock import MagicMock, patch
from entities.base import NPC
from engine import Building, Village, World, Player
from config import DAY_LENGTH_TICKS

# Create a dummy World class that bypasses heavy initialization
class MockWorld(World):
    def __init__(self):
        # Bypass World.__init__ to avoid generation
        self.game_time = 0
        self.village_npcs = []
        self.buildings_by_id = {}
        self.add_message_to_chat_log = MagicMock()
        self.chunks = [[MagicMock() for _ in range(1)] for _ in range(1)] # Minimal chunk map
        self.player = MagicMock(spec=Player)
        self.player.id = 1
        self.global_events = [] # Initialize for logging
        # We need to mock _get_village_for_npc since it checks chunks
        self._get_village_for_npc = MagicMock()

    # Re-enable the method we want to test (it's inherited, but we can ensure it's using the real one)
    # Since we didn't override it, it uses the one from World.

class TestNPCProfessionDynamics(unittest.TestCase):
    def setUp(self):
        self.world = MockWorld()

        # Create a village
        self.village = Village()
        self.village.buildings = []

        # Create a workplace building (e.g., Tavern)
        self.tavern = Building(10, 10, 10, 10, building_type="tavern", category="commercial_workplace")
        self.tavern.id = "tavern_1"
        self.tavern.max_workers = 2
        self.tavern.occupants = []

        self.village.buildings.append(self.tavern)
        self.world.buildings_by_id[self.tavern.id] = self.tavern

        # Mock _get_village_for_npc to return our test village
        self.world._get_village_for_npc.return_value = self.village

        # Create an NPC who works there
        self.npc = NPC(x=15, y=15, name="Worker NPC")
        self.npc.economic.profession = "Tavern Keeper"
        self.npc.schedule.work_building_id = self.tavern.id
        self.npc.economic.job_satisfaction = 50

        self.tavern.occupants.append(self.npc)
        self.world.village_npcs.append(self.npc)

    def test_npc_quits_job_due_to_dissatisfaction(self):
        # Set satisfaction very low to trigger quitting
        # Set to 0 to ensure even with random positive fluctuation (max +5), it stays < 10
        self.npc.economic.job_satisfaction = 0

        # Run the career update
        # Set game_time to exactly DAY_LENGTH_TICKS to trigger the update
        self.world.game_time = DAY_LENGTH_TICKS

        # Debug: Print satisfaction before update
        # print(f"DEBUG TEST: Satisfaction before: {self.npc.economic.job_satisfaction}")

        self.world._update_npc_careers()

        # Debug: Print satisfaction and profession after update
        # print(f"DEBUG TEST: Satisfaction after: {self.npc.economic.job_satisfaction}, Profession: {self.npc.economic.profession}")

        # Assert NPC is now unemployed
        self.assertEqual(self.npc.economic.profession, "Unemployed")
        self.assertIsNone(self.npc.schedule.work_building_id)

        # We no longer check for removal from self.tavern.occupants because hiring/firing
        # only affects schedule/assignment, not physical presence.

        # Check if message was logged
        quit_msg = f"{self.npc.name} has quit their job as a Tavern Keeper due to low satisfaction."
        self.world.add_message_to_chat_log.assert_any_call(quit_msg)

    def test_npc_finds_new_job(self):
        # Start with an unemployed NPC
        self.npc.economic.profession = "Unemployed"
        self.npc.schedule.work_building_id = None

        # Ensure vacancy logic (based on schedule ID, not occupants)
        # No other NPCs are assigned to self.tavern.id in setup

        self.world.game_time = DAY_LENGTH_TICKS
        self.world._update_npc_careers()

        # NPC should have found the open job at the tavern
        # Note: In the logic, professions are assigned based on building type mapping.
        # Tavern maps to "Tavern Keeper"
        self.assertEqual(self.npc.economic.profession, "Tavern Keeper")
        self.assertEqual(self.npc.schedule.work_building_id, self.tavern.id)
        # self.assertIn(self.npc, self.tavern.occupants) # Removed assertion: hiring doesn't teleport NPC
        self.assertEqual(self.npc.economic.job_satisfaction, 70) # Honeymoon reset

        hire_msg = f"{self.npc.name} has been hired as a Tavern Keeper."
        self.world.add_message_to_chat_log.assert_any_call(hire_msg)

    def test_npc_does_not_quit_if_satisfied(self):
        self.npc.economic.job_satisfaction = 80
        self.world.game_time = DAY_LENGTH_TICKS
        self.world._update_npc_careers()

        self.assertEqual(self.npc.economic.profession, "Tavern Keeper")
        # self.assertIn(self.npc, self.tavern.occupants) # Removed assertion: unrelated to career logic

if __name__ == '__main__':
    unittest.main()
