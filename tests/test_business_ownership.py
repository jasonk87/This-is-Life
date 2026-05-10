import unittest
from engine import World, Building, NPC, EmploymentTask
import config

class TestBusinessOwnership(unittest.TestCase):
    def setUp(self):
        import engine
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=42)
        self.world.villages = []

        from simulation.world_model import Village
        self.village = Village()
        self.world.villages.append(self.village)

        self.building = Building(0, 0, 5, 5, building_type="lumber_mill", category="commercial_workplace")
        self.village.add_building(self.building)
        self.world.buildings_by_id[self.building.id] = self.building

        self.npc = NPC(0, 0, name="Boss NPC")
        self.npc.economic.money = 100
        self.world.village_npcs.append(self.npc)

        # assign village to chunks
        from simulation.world_model import Chunk
        chunk = Chunk("plains")
        chunk.village = self.village
        self.world.chunks = [[chunk]]
        self.world.chunk_width = 1
        self.world.chunk_height = 1

    def test_owner_posts_job_when_understaffed(self):
        self.building.owner_id = self.npc.id
        self.building.max_workers = 2

        # Give village a noticeboard so handle_npc_job_seeking works
        self.village.interaction_points["noticeboard"] = [(1, 1)]

        # Advance day to trigger career logic
        self.world.game_time = config.DAY_LENGTH_TICKS
        self.world._update_npc_careers()

        # Check if job was posted
        tasks = self.world.town_board.get_open_employment_tasks(self.building.id)
        self.assertTrue(len(tasks) > 0)
        self.assertEqual(tasks[0].poster_entity_id, self.npc.id)

        # Check if boss got assigned to their own business
        self.assertEqual(self.npc.schedule.work_building_id, self.building.id)

    def test_owner_does_not_post_job_if_staffed(self):
        self.building.owner_id = self.npc.id
        self.building.max_workers = 1 # owner is the 1 worker

        self.village.interaction_points["noticeboard"] = [(1, 1)]

        self.world.game_time = config.DAY_LENGTH_TICKS
        self.world._update_npc_careers()

        tasks = self.world.town_board.get_open_employment_tasks(self.building.id)
        self.assertEqual(len(tasks), 0)

    def test_owner_delegates_labor_when_staffed(self):
        self.building.owner_id = self.npc.id
        self.building.max_workers = 3

        # Add another worker
        worker = NPC(0, 0, name="Worker NPC")
        self.world.village_npcs.append(worker)
        worker.schedule.work_building_id = self.building.id
        worker.economic.profession = "Woodcutter"
        worker.physical.is_dead = False
        self.npc.physical.is_dead = False

        self.npc.schedule.work_building_id = self.building.id
        self.npc.economic.profession = "Lumber Mill Foreman"

        from simulation.systems.work import update_npc_work_sub_tasks

        # Owner should get management tasks
        self.building.work_zone_tiles["manager_spot"] = [(1,1)]

        self.world.get_tile_at = lambda x, y: type("MockTile", (), {"passable": True, "name": "plains", "is_hazard": False, "properties": {}})()
        self.world.calculate_path = lambda sx, sy, ex, ey: [(sx, sy), (ex, ey)]
        update_npc_work_sub_tasks(self.world, self.npc)

        self.assertIn(self.npc.current_sub_task, ["manage_business_inspect", "manage_business_supervise"])

    def test_production_stalls_and_hauls_missing_inputs(self):
        # Setup a blacksmith that needs iron_ore
        blacksmith = Building(0, 0, 5, 5, building_type="blacksmith_shop", category="commercial_workplace")
        self.village.add_building(blacksmith)
        self.world.buildings_by_id[blacksmith.id] = blacksmith

        # Add a worker
        smith = NPC(0, 0, name="Smith")
        smith.schedule.work_building_id = blacksmith.id
        smith.economic.profession = "Blacksmith"
        self.world.village_npcs.append(smith)

        # Setup a general store with iron_ore
        store = Building(10, 10, 5, 5, building_type="general_store", category="commercial_workplace")
        self.village.add_building(store)
        self.world.buildings_by_id[store.id] = store

        from entities.items import ItemReference
        for _ in range(3):
            store.building_inventory.add_item_reference(ItemReference("iron_ore"))
            store.building_inventory.add_item_reference(ItemReference("coal"))

        blacksmith.building_inventory["money"] = 100
        blacksmith.owner_id = self.npc.id # NPC owns it

        # Trigger work chain
        self.world._attempt_workplace_supply_chain_actions(smith, blacksmith)

        total_store = store.building_inventory.get("iron_ore", 0) + store.building_inventory.get("coal", 0)
        self.assertTrue(total_store < 6) # It had 6 total

        total_smith = blacksmith.building_inventory.get("iron_ore", 0) + blacksmith.building_inventory.get("coal", 0)
        self.assertTrue(total_smith > 0)

if __name__ == '__main__':
    unittest.main()
