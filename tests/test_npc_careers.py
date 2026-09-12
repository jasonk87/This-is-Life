
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from entities.base import NPC, next_entity_id
from engine import Building, Village, World, Player
from config import DAY_LENGTH_TICKS
from simulation.careers import (
    entity_has_any_profession,
    entity_has_capability,
    entity_has_profession,
    resolve_profession_for_building,
    set_entity_profession,
    get_roles_for_building,
)

# Create a dummy World class that bypasses heavy initialization
class TownBoardStub:
    def __init__(self):
        self.tasks = []
        self.economic_needs = []
        self.next_id = 1
    def get_open_employment_tasks(self, building_id=None):
        if building_id:
            return [t for t in self.tasks if getattr(t, 'target_building_id', None) == building_id]
        return self.tasks
    def post_employment(self, building_id, role, wage):
        task = MagicMock()
        task.id = self.next_id
        task.target_building_id = building_id
        task.role = role
        task.wage = wage
        task.profession_role = role
        task.daily_wage = wage
        self.tasks.append(task)
        self.next_id += 1
        return task
    def remove_employment_task(self, task_id):
        self.tasks = [t for t in self.tasks if t.id != task_id]
    def claim_employment_task(self, task, npc_id):
        self.remove_employment_task(task.id)
        return True
    def complete_employment_task(self, task_id):
        pass

class MockWorld(World):
    def __init__(self):
        # Bypass World.__init__ to avoid generation
        self.game_time = 0
        self.village_npcs = []
        self.npcs = []
        self.buildings_by_id = {}
        self.add_message_to_chat_log = MagicMock()
        self.chunks = [[MagicMock() for _ in range(1)] for _ in range(1)] # Minimal chunk map
        self.player = MagicMock(spec=Player)
        # Use the same allocator as real entities: a fresh worker process may
        # otherwise also give the first NPC id 1 and misidentify them as You.
        self.player.id = next_entity_id()
        self.player.economic = SimpleNamespace(job_building_id=None)
        self.player.physical = SimpleNamespace(is_dead=False)
        self.town_board = TownBoardStub()
        self.player.world_ref = self
        self.player_fov_map = MagicMock()
        self.player_fov_map.__getitem__ = MagicMock(return_value=False)
        self.global_events = [] # Initialize for logging
        self.chunk_width = 1
        self.chunk_height = 1
        self.npc_fov_maps = {}
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
        self.tavern.settlement_id = getattr(self.village, 'id', None)
        self.tavern.max_workers = 2
        self.tavern.occupants = []


        self.village.interaction_points = {"noticeboard": [(15, 15)]}

        # We also need self.world.town_board.get_open_employment_tasks to return our task
        # But _sync_village_employment_tasks is called inside _update_npc_careers which updates town_board
        # Actually town_board is a MagicMock, so get_open_employment_tasks() won't return anything real unless configured.
        self.village.buildings.append(self.tavern)
        self.world.buildings_by_id[self.tavern.id] = self.tavern

        # Mock _get_village_for_npc to return our test village
        self.world._get_village_for_npc.return_value = self.village

        # Create an NPC who works there
        self.npc = NPC(x=15, y=15, name="Worker NPC")
        set_entity_profession(self.npc, "Tavern Keeper")
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
        quit_msg = f"{self.npc.get_display_name(viewer=self.world.player)} has quit their job as a Tavern Keeper due to low satisfaction."
        self.world.add_message_to_chat_log.assert_any_call(quit_msg)

    def test_npc_finds_new_job(self):
        # Start with an unemployed NPC
        set_entity_profession(self.npc, "Unemployed")
        self.npc.schedule.work_building_id = None
        self.npc.economic.days_unemployed = 2

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

        hire_msg = f"{self.npc.get_display_name(viewer=self.world.player)} has been hired as a Tavern Keeper."
        self.world.add_message_to_chat_log.assert_any_call(hire_msg)

    def test_npc_does_not_quit_if_satisfied(self):
        self.npc.economic.job_satisfaction = 80
        self.world.game_time = DAY_LENGTH_TICKS
        self.world._update_npc_careers()

        self.assertEqual(self.npc.economic.profession, "Tavern Keeper")
        # self.assertIn(self.npc, self.tavern.occupants) # Removed assertion: unrelated to career logic

    def test_resolve_profession_for_building_supports_lead_and_worker_roles(self):
        self.assertEqual(resolve_profession_for_building("lumber_mill", []), "Lumber Mill Foreman")
        self.assertEqual(
            resolve_profession_for_building("lumber_mill", ["Lumber Mill Foreman"]),
            "Woodcutter",
        )

    def test_unknown_building_fallback_roles_are_title_case_strings(self):
        self.assertEqual(resolve_profession_for_building("warehouse"), "Warehouse")
        self.assertEqual(get_roles_for_building("warehouse"), ["Warehouse"])
        self.assertEqual(resolve_profession_for_building("workshop"), "Workshop")
        self.assertEqual(get_roles_for_building("workshop"), ["Workshop"])

    def test_unknown_building_role_options_are_flat_strings(self):
        roles = get_roles_for_building("unknown_building")

        self.assertEqual(roles, ["Unknown Building"])
        self.assertTrue(all(isinstance(role, str) for role in roles))
        self.assertTrue(all(not isinstance(role, (tuple, list)) for role in roles))

    def test_profession_capabilities_are_queryable(self):
        set_entity_profession(self.npc, "Merchant")
        self.assertTrue(entity_has_capability(self.npc, "trade"))
        self.assertTrue(entity_has_profession(self.npc, "Merchant"))
        self.assertTrue(entity_has_any_profession(self.npc, ["Merchant", "Scribe"]))

    def test_butcher_shop_role_resolution_overrides_generic_shop(self):
        self.assertEqual(resolve_profession_for_building("butcher_shop", []), "Butcher")
        self.assertEqual(resolve_profession_for_building("butcher_shop", ["Butcher"]), "Hunter")
        self.assertEqual(get_roles_for_building("butcher_shop"), ["Butcher", "Hunter"])

    def test_generic_shop_and_market_fallback_to_merchant(self):
        self.assertEqual(resolve_profession_for_building("tailor_shop"), "Merchant")
        self.assertEqual(get_roles_for_building("tailor_shop"), ["Merchant"])
        self.assertEqual(resolve_profession_for_building("farmers_market"), "Merchant")
        self.assertEqual(get_roles_for_building("farmers_market"), ["Merchant"])

if __name__ == '__main__':
    unittest.main()
