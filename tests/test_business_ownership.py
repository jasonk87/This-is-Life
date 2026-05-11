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

        # Ensure chunk is INACTIVE so it uses abstract fallback transfer
        self.world._is_building_active = lambda b: False

        # Trigger work chain
        self.world._attempt_workplace_supply_chain_actions(smith, blacksmith)

        total_store = store.building_inventory.get("iron_ore", 0) + store.building_inventory.get("coal", 0)
        self.assertTrue(total_store < 6) # It had 6 total

        total_smith = blacksmith.building_inventory.get("iron_ore", 0) + blacksmith.building_inventory.get("coal", 0)
        self.assertTrue(total_smith > 0)
        self.assertEqual(len(self.world.town_board.delivery_tasks), 0)

    def test_production_stalls_and_creates_delivery_task_when_active(self):
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
        store.building_inventory.add_item_reference(ItemReference("iron_ore"))

        blacksmith.building_inventory["money"] = 100
        blacksmith.owner_id = self.npc.id

        # Ensure chunk IS ACTIVE
        self.world._is_building_active = lambda b: True

        # Trigger work chain
        self.world._attempt_workplace_supply_chain_actions(smith, blacksmith)

        # In active mode, inventory should NOT transfer instantly
        self.assertEqual(store.building_inventory.get("iron_ore", 0), 1)
        self.assertEqual(blacksmith.building_inventory.get("iron_ore", 0), 0)

        # Instead, a delivery task should be created
        tasks = self.world.town_board.get_open_delivery_tasks(blacksmith.id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].item_key, "iron_ore")
        self.assertEqual(tasks[0].source_building_id, store.id)

    def test_full_physical_delivery_lifecycle(self):
        # Setup a blacksmith that needs iron_ore
        blacksmith = Building(0, 0, 5, 5, building_type="blacksmith_shop", category="commercial_workplace")
        self.village.add_building(blacksmith)
        self.world.buildings_by_id[blacksmith.id] = blacksmith

        # Add a laborer to perform the delivery
        laborer = NPC(5, 5, name="Laborer")
        laborer.economic.profession = "Laborer"
        self.world.village_npcs.append(laborer)

        # Setup an owner
        owner = NPC(1, 1, name="Owner")
        owner.schedule.work_building_id = blacksmith.id
        owner.economic.profession = "Blacksmith"
        self.world.village_npcs.append(owner)
        blacksmith.owner_id = owner.id
        blacksmith.building_inventory["money"] = 100

        # Setup a general store with iron_ore
        store = Building(10, 10, 5, 5, building_type="general_store", category="commercial_workplace")
        store.global_center_x, store.global_center_y = 12, 12 # Explicitly set coordinates for movement
        blacksmith.global_center_x, blacksmith.global_center_y = 2, 2

        self.village.add_building(store)
        self.world.buildings_by_id[store.id] = store

        from entities.items import ItemReference
        store.building_inventory.add_item_reference(ItemReference("iron_ore"))

        self.world._is_building_active = lambda b: True

        # Generate the task
        self.world._attempt_workplace_supply_chain_actions(owner, blacksmith)

        # Confirm task exists
        tasks = self.world.town_board.get_open_delivery_tasks()
        self.assertEqual(len(tasks), 1)
        task = tasks[0]

        # Laborer claims the task
        self.world.calculate_path = lambda sx, sy, ex, ey: [(sx, sy), (ex, ey)]
        claimed = self.world._assign_delivery_task_to_npc(laborer)
        self.assertTrue(claimed)
        self.assertEqual(task.status, "going_to_source")
        self.assertEqual(laborer.schedule.current_task, "hauling_to_source")
        self.assertTrue(laborer.schedule.current_path)
        self.assertEqual(store.building_inventory.get("iron_ore", 0), 1)
        self.assertEqual(blacksmith.building_inventory.get("iron_ore", 0), 0)

        # Verify Owner ignores the task because laborer is available / owner evaluates false
        owner_claimed = self.world._assign_delivery_task_to_npc(owner)
        self.assertFalse(owner_claimed)

        # Path to source
        laborer.x, laborer.y = store.global_center_x, store.global_center_y

        # Handle delivery logic at source
        handled = self.world._handle_npc_delivery_task(laborer)
        self.assertTrue(handled)
        self.assertEqual(laborer.schedule.current_task, "hauling_to_delivery_destination")
        self.assertEqual(task.status, "carrying")
        self.assertIn("Carrying iron_ore", laborer.current_sub_task)
        self.assertTrue(laborer.schedule.current_path)

        # Verify inventory logic: store lost item, laborer gained it, blacksmith still missing it
        self.assertEqual(store.building_inventory.get("iron_ore", 0), 0)
        self.assertEqual(laborer.economic.npc_inventory.get("iron_ore", 0), 1)
        self.assertEqual(blacksmith.building_inventory.get("iron_ore", 0), 0)

        # Path to destination
        laborer.x, laborer.y = blacksmith.global_center_x, blacksmith.global_center_y

        # Handle delivery logic at destination
        handled_dropoff = self.world._handle_npc_delivery_task(laborer)
        self.assertTrue(handled_dropoff)
        self.assertEqual(laborer.schedule.current_task, "idle") # Handled and cleared

        # Verify final state: laborer lost item, blacksmith gained item, task complete
        self.assertEqual(laborer.economic.npc_inventory.get("iron_ore", 0), 0)
        self.assertEqual(blacksmith.building_inventory.get("iron_ore", 0), 1)
        self.assertEqual(len(self.world.town_board.delivery_tasks), 0) # Task was purged on completion
        self.assertTrue(store.building_inventory.get("money", 0) > 0) # Assumes base price was > 0, store gained money

    def test_delivery_missing_source_item_fails_and_clears_npc(self):
        blacksmith = Building(0, 0, 5, 5, building_type="blacksmith_shop", category="commercial_workplace")
        store = Building(10, 10, 5, 5, building_type="general_store", category="commercial_workplace")
        blacksmith.global_center_x, blacksmith.global_center_y = 2, 2
        store.global_center_x, store.global_center_y = 12, 12
        self.village.add_building(blacksmith)
        self.village.add_building(store)
        self.world.buildings_by_id[blacksmith.id] = blacksmith
        self.world.buildings_by_id[store.id] = store

        laborer = NPC(5, 5, name="Helper")
        laborer.economic.profession = "Helper"
        self.world.village_npcs.append(laborer)

        from entities.items import ItemReference
        store.building_inventory.add_item_reference(ItemReference("iron_ore"))
        task = self.world.town_board.post_delivery_task(store.id, blacksmith.id, "iron_ore", 1, self.world.game_time)
        self.world.calculate_path = lambda sx, sy, ex, ey: [(sx, sy), (ex, ey)]

        self.assertTrue(self.world._assign_delivery_task_to_npc(laborer))
        store.building_inventory.pop_item_reference("iron_ore")
        laborer.x, laborer.y = store.global_center_x, store.global_center_y

        self.assertFalse(self.world._handle_npc_delivery_task(laborer))
        self.assertEqual(laborer.schedule.current_task, "idle")
        self.assertIsNone(laborer.task_context)
        self.assertIsNone(self.world.town_board.get_delivery_task(task.id))
        self.assertEqual(blacksmith.building_inventory.get("iron_ore", 0), 0)

    def test_duplicate_delivery_task_is_not_spammed_every_tick(self):
        blacksmith = Building(0, 0, 5, 5, building_type="blacksmith_shop", category="commercial_workplace")
        store = Building(10, 10, 5, 5, building_type="general_store", category="commercial_workplace")
        self.village.add_building(blacksmith)
        self.village.add_building(store)
        self.world.buildings_by_id[blacksmith.id] = blacksmith
        self.world.buildings_by_id[store.id] = store
        smith = NPC(0, 0, name="Smith")
        smith.schedule.work_building_id = blacksmith.id
        smith.economic.profession = "Blacksmith"
        self.world.village_npcs.append(smith)

        from entities.items import ItemReference
        store.building_inventory.add_item_reference(ItemReference("iron_ore"))
        blacksmith.building_inventory["money"] = 100
        blacksmith.owner_id = self.npc.id
        self.world._is_building_active = lambda b: True

        for tick in range(3):
            self.world.game_time = tick
            self.world._attempt_workplace_supply_chain_actions(smith, blacksmith)

        tasks = self.world.town_board.get_active_delivery_tasks(blacksmith.id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].source_building_id, store.id)
        self.assertEqual(store.building_inventory.get("iron_ore", 0), 1)
        self.assertEqual(blacksmith.building_inventory.get("iron_ore", 0), 0)

    def test_owner_waits_for_available_laborer_to_claim_delivery(self):
        blacksmith = Building(0, 0, 5, 5, building_type="blacksmith_shop", category="commercial_workplace")
        store = Building(10, 10, 5, 5, building_type="general_store", category="commercial_workplace")
        self.village.add_building(blacksmith)
        self.village.add_building(store)
        self.world.buildings_by_id[blacksmith.id] = blacksmith
        self.world.buildings_by_id[store.id] = store

        owner = NPC(1, 1, name="Owner")
        owner.schedule.work_building_id = blacksmith.id
        owner.economic.profession = "Blacksmith"
        blacksmith.owner_id = owner.id
        laborer = NPC(5, 5, name="Porter")
        laborer.economic.profession = "Porter"
        self.world.village_npcs.extend([owner, laborer])

        from entities.items import ItemReference
        store.building_inventory.add_item_reference(ItemReference("iron_ore"))
        task = self.world.town_board.post_delivery_task(store.id, blacksmith.id, "iron_ore", 1, self.world.game_time)
        self.world.calculate_path = lambda sx, sy, ex, ey: [(sx, sy), (ex, ey)]

        self.assertFalse(self.world._assign_delivery_task_to_npc(owner))
        self.assertEqual(task.status, "open")
        self.assertTrue(self.world._assign_delivery_task_to_npc(laborer))
        self.assertEqual(task.assigned_entity_id, laborer.id)

    def test_workplace_production_resumes_after_delivered_input(self):
        blacksmith = Building(0, 0, 5, 5, building_type="blacksmith_shop", category="commercial_workplace")
        store = Building(10, 10, 5, 5, building_type="general_store", category="commercial_workplace")
        blacksmith.global_center_x, blacksmith.global_center_y = 2, 2
        store.global_center_x, store.global_center_y = 12, 12
        self.village.add_building(blacksmith)
        self.village.add_building(store)
        self.world.buildings_by_id[blacksmith.id] = blacksmith
        self.world.buildings_by_id[store.id] = store

        smith = NPC(0, 0, name="Smith")
        smith.schedule.work_building_id = blacksmith.id
        smith.economic.profession = "Blacksmith"
        laborer = NPC(5, 5, name="Laborer")
        laborer.economic.profession = "Laborer"
        self.world.village_npcs.extend([smith, laborer])

        from entities.items import ItemReference
        blacksmith.building_inventory.add_item_reference(ItemReference("iron_ore"))
        blacksmith.building_inventory.add_item_reference(ItemReference("coal"))
        store.building_inventory.add_item_reference(ItemReference("iron_ore"))
        blacksmith.building_inventory["money"] = 100
        blacksmith.owner_id = self.npc.id
        self.world._is_building_active = lambda b: True
        self.world.calculate_path = lambda sx, sy, ex, ey: [(sx, sy), (ex, ey)]

        self.assertTrue(self.world._attempt_workplace_supply_chain_actions(smith, blacksmith))
        self.assertEqual(blacksmith.building_inventory.get("iron_ingot", 0), 0)
        self.assertTrue(self.world._assign_delivery_task_to_npc(laborer))
        laborer.x, laborer.y = store.global_center_x, store.global_center_y
        self.assertTrue(self.world._handle_npc_delivery_task(laborer))
        laborer.x, laborer.y = blacksmith.global_center_x, blacksmith.global_center_y
        self.assertTrue(self.world._handle_npc_delivery_task(laborer))

        self.assertTrue(self.world._attempt_workplace_supply_chain_actions(smith, blacksmith))
        self.assertEqual(blacksmith.building_inventory.get("iron_ingot", 0), 1)

if __name__ == '__main__':
    unittest.main()
