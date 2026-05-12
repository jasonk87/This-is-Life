import unittest
from types import SimpleNamespace
from unittest.mock import patch

from engine import World, Building, NPC, ItemReference
from entities.items import Inventory
from simulation.world_model import Village


class TestConstructionFoundation(unittest.TestCase):
    def setUp(self):
        import engine
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=123)
        self.village = Village()
        self.village.interaction_points = {"town_square_center": [(12, 12)]}
        self.world.chunks[0][0].village = self.village
        self.world.chunk_width = 1
        self.world.chunk_height = 1
        self.world.calculate_path = lambda sx, sy, ex, ey: [(sx, sy), (ex, ey)]

    def test_construction_site_tracks_lifecycle_fields_and_does_not_complete_on_placement(self):
        blueprint = self.world.place_construction_blueprint("house", 8, 8, owner_id=7, requester_id=8)

        self.assertIsNotNone(blueprint)
        self.assertEqual(blueprint.target_build, "house")
        self.assertEqual(blueprint.owner_id, 7)
        self.assertEqual(blueprint.requester_id, 8)
        self.assertEqual(blueprint.status, "awaiting_materials")
        self.assertEqual(blueprint.construction_stage, "planning")
        self.assertEqual(blueprint.build_progress, 0)
        self.assertEqual(blueprint.remaining_materials(), {"raw_log": 50})
        self.assertEqual(len(self.world.town_board.get_open_tasks(blueprint.id)), 50)

    def test_material_delivery_enables_building_but_does_not_instantly_complete(self):
        blueprint = self.world.place_construction_blueprint("wooden_chair", 8, 8)

        blueprint.deposit_item_reference(ItemReference("wooden_plank"))
        blueprint.deposit_item_reference(ItemReference("wooden_plank"))
        blueprint.refresh_status()
        self.world._refresh_blueprint_map_marker(blueprint)

        self.assertTrue(blueprint.has_all_materials())
        self.assertEqual(blueprint.status, "building")
        self.assertEqual(blueprint.construction_stage, "foundation")
        self.assertEqual(blueprint.build_progress, 0)
        self.assertIs(self.world.get_blueprint_at(8, 8), blueprint)

    def test_active_hauler_delivers_material_then_builder_advances_stages(self):
        blueprint = self.world.place_construction_blueprint("wooden_chair", 8, 8)
        blueprint.required_work = 30
        self.world.items_on_map[(2, 2)] = Inventory()
        self.world.items_on_map[(2, 2)].add_item("wooden_plank", 2)

        laborer = NPC(2, 2, name="Laborer")
        laborer.economic.profession = "Laborer"
        self.world.village_npcs.append(laborer)

        self.assertTrue(self.world._assign_haul_task_to_npc(laborer))
        self.assertEqual(laborer.schedule.current_task, "hauling_to_source")
        self.assertTrue(self.world._handle_npc_hauling_task(laborer))
        laborer.x, laborer.y = 8, 8
        laborer.schedule.current_path = []
        self.assertTrue(self.world._handle_npc_hauling_task(laborer))
        self.assertEqual(blueprint.delivered_materials.get("wooden_plank", 0), 1)
        self.assertIs(self.world.get_blueprint_at(8, 8), blueprint)

        # Deliver the second material so construction work, not delivery, gates completion.
        laborer.x, laborer.y = 2, 2
        self.assertTrue(self.world._assign_haul_task_to_npc(laborer))
        self.assertTrue(self.world._handle_npc_hauling_task(laborer))
        laborer.x, laborer.y = 8, 8
        laborer.schedule.current_path = []
        self.assertTrue(self.world._handle_npc_hauling_task(laborer))
        self.assertTrue(blueprint.has_all_materials())
        self.assertEqual(blueprint.build_progress, 0)

        self.assertTrue(self.world._assign_construction_task_to_npc(laborer))
        self.assertEqual(laborer.schedule.current_task, "constructing_site")
        self.assertTrue(self.world._handle_npc_construction_task(laborer))
        self.assertGreater(blueprint.build_progress, 0)
        self.assertIn(blueprint.construction_stage, {"foundation", "framing", "finishing"})

    def test_stalled_construction_due_to_material_shortage_is_visible(self):
        house = Building(0, 0, 5, 5, building_type="house", category="residential")
        house.residents = [SimpleNamespace(), SimpleNamespace()]
        self.village.add_building(house)

        with patch.object(self.world, "_find_valid_building_spot", return_value=(10, 10)):
            self.world._plan_village_expansion(self.village)

        blueprint = self.world.get_blueprint_at(10, 10)
        self.assertIsNotNone(blueprint)
        self.assertEqual(blueprint.status, "awaiting_materials")
        self.assertIn("Awaiting raw_log", blueprint.stalled_reason)
        self.assertEqual(blueprint.build_progress, 0)

    def test_owner_supervises_while_laborer_claims_build_work_first(self):
        blueprint = self.world.place_construction_blueprint("wooden_chair", 8, 8)
        blueprint.required_work = 20
        blueprint.deposit_item_reference(ItemReference("wooden_plank"))
        blueprint.deposit_item_reference(ItemReference("wooden_plank"))
        blueprint.refresh_status()

        owner = NPC(1, 1, name="Owner")
        owner.economic.profession = "Manager"
        laborer = NPC(2, 2, name="Helper")
        laborer.economic.profession = "Helper"
        self.world.village_npcs.extend([owner, laborer])

        self.assertFalse(self.world._assign_construction_task_to_npc(owner))
        self.assertEqual(blueprint.assigned_workers, [])
        self.assertTrue(self.world._assign_construction_task_to_npc(laborer))
        self.assertEqual(blueprint.assigned_workers, [laborer.id])

    def test_autonomous_npc_can_start_pressure_driven_home_project(self):
        house = Building(0, 0, 5, 5, building_type="house", category="residential")
        house.residents = [SimpleNamespace(), SimpleNamespace()]
        self.village.add_building(house)
        foreman = NPC(5, 5, name="Foreman")
        foreman.economic.profession = "Foreman"

        with patch.object(self.world, "_get_village_for_npc", return_value=self.village), \
             patch.object(self.world, "_find_valid_building_spot", return_value=(14, 14)):
            blueprint = self.world._npc_maybe_start_construction_project(foreman)

        self.assertIsNotNone(blueprint)
        self.assertEqual(blueprint.target_build, "house")
        self.assertEqual(blueprint.owner_id, foreman.id)
        self.assertEqual(blueprint.requester_id, foreman.id)
        self.assertEqual(blueprint.settlement_id, self.village.id)

    def test_completed_construction_integrates_real_building(self):
        blueprint = self.world.place_construction_blueprint("workshop", 8, 8)
        blueprint.required_work = 20
        for item_key, qty in blueprint.required_materials.items():
            for _ in range(qty):
                blueprint.deposit_item_reference(ItemReference(item_key))
        blueprint.refresh_status()

        builder = NPC(8, 8, name="Builder")
        builder.economic.profession = "Builder"
        self.world.village_npcs.append(builder)
        self.assertTrue(self.world._assign_construction_task_to_npc(builder))
        self.assertTrue(self.world._handle_npc_construction_task(builder))
        self.assertTrue(self.world._handle_npc_construction_task(builder))

        self.assertIsNone(self.world.get_blueprint_at(8, 8))
        self.assertTrue(any(b.building_type == "workshop" for b in self.village.buildings))

    def test_offscreen_fallback_obeys_materials_and_work_before_completion(self):
        house = Building(0, 0, 5, 5, building_type="house", category="residential")
        house.residents = [SimpleNamespace(), SimpleNamespace()]
        self.village.add_building(house)
        self.village.supply["raw_log"] = 50
        self.world._is_blueprint_active = lambda blueprint: False

        with patch.object(self.world, "_find_valid_building_spot", return_value=(16, 16)):
            self.world._plan_village_expansion(self.village)

        for _ in range(5):
            self.world._advance_village_construction(self.village)
        blueprint = self.world.get_blueprint_at(16, 16)
        self.assertIsNotNone(blueprint)
        self.assertTrue(blueprint.has_all_materials())
        self.assertLess(blueprint.build_progress, blueprint.required_work)

        for _ in range(3):
            self.world._advance_village_construction(self.village)

        self.assertIsNone(self.world.get_blueprint_at(16, 16))
        self.assertEqual(sum(1 for b in self.village.buildings if b.building_type == "house"), 2)


    def _fully_supply_blueprint(self, blueprint):
        for item_key, qty in blueprint.required_materials.items():
            for _ in range(qty):
                blueprint.deposit_item_reference(ItemReference(item_key))
        blueprint.refresh_status()

    def test_non_construction_professions_do_not_claim_build_work(self):
        for index, profession in enumerate(["Farmer", "Baker", "Guard", "Blacksmith", "Tavern Keeper"]):
            with self.subTest(profession=profession):
                blueprint = self.world.place_construction_blueprint("wooden_chair", 20 + index, 20)
                self._fully_supply_blueprint(blueprint)
                npc = NPC(2, 2, name=profession)
                npc.economic.profession = profession
                self.world.village_npcs.append(npc)

                self.assertFalse(self.world._assign_construction_task_to_npc(npc))
                self.assertEqual(blueprint.assigned_workers, [])

                self.world.village_npcs.remove(npc)
                self.world.blueprints_by_id.pop(blueprint.id, None)
                self.world.blueprint_positions.pop((blueprint.x, blueprint.y), None)

    def test_manager_construction_fallback_only_without_eligible_worker(self):
        blueprint = self.world.place_construction_blueprint("wooden_chair", 21, 21)
        self._fully_supply_blueprint(blueprint)
        manager = NPC(1, 1, name="Manager")
        manager.economic.profession = "Manager"
        self.world.village_npcs.append(manager)

        self.assertTrue(self.world._assign_construction_task_to_npc(manager))
        self.assertEqual(blueprint.assigned_workers, [manager.id])

    def test_construction_deferral_ignores_unreachable_workers(self):
        blueprint = self.world.place_construction_blueprint("wooden_chair", 21, 21)
        self._fully_supply_blueprint(blueprint)
        manager = NPC(1, 1, name="Manager")
        manager.economic.profession = "Manager"
        self.world.village_npcs.append(manager)

        laborer = NPC(25, 25, name="Laborer")
        laborer.economic.profession = "Laborer"
        self.world.village_npcs.append(laborer)

        # Block the path so laborer cannot reach the blueprint
        with patch.object(self.world, 'calculate_path') as mock_path:
            # For the laborer's reachability check, return empty path (unreachable)
            # For the manager, return a valid path
            def path_side_effect(start_x, start_y, end_x, end_y):
                if start_x == laborer.x and start_y == laborer.y:
                    return []
                return [(start_x, start_y), (end_x, end_y)]
            mock_path.side_effect = path_side_effect

            self.assertTrue(self.world._assign_construction_task_to_npc(manager))
            self.assertEqual(blueprint.assigned_workers, [manager.id])

    def test_reachable_local_laborer_receives_priority(self):
        blueprint = self.world.place_construction_blueprint("wooden_chair", 21, 21)
        self._fully_supply_blueprint(blueprint)
        manager = NPC(1, 1, name="Manager")
        manager.economic.profession = "Manager"
        self.world.village_npcs.append(manager)

        laborer = NPC(22, 22, name="Laborer")
        laborer.economic.profession = "Laborer"
        self.world.village_npcs.append(laborer)

        with patch.object(self.world, 'calculate_path', return_value=[(22,22), (21,21)]):
            # Manager should defer to reachable laborer
            self.assertFalse(self.world._assign_construction_task_to_npc(manager))
            self.assertTrue(self.world._assign_construction_task_to_npc(laborer))
            self.assertEqual(blueprint.assigned_workers, [laborer.id])

    def test_building_placement_rejects_chunk_crossing(self):
        from config import CHUNK_SIZE
        # Attempt to place a building right on the chunk border
        border_x = CHUNK_SIZE - 2
        border_y = CHUNK_SIZE - 2

        blueprint = self.world.place_construction_blueprint("workshop", border_x, border_y)
        self.assertIsNone(blueprint, "Building footprint crossing chunk border should be rejected.")

    def test_completed_npc_owned_construction_preserves_ownership_and_claim(self):
        self.village.region_id = "region-test"
        owner = NPC(8, 8, name="Workshop Owner")
        owner.economic.profession = "Unemployed"
        self.world.village_npcs.append(owner)
        blueprint = self.world.place_construction_blueprint("workshop", 8, 8, owner_id=owner.id, requester_id=owner.id)
        claim_id = blueprint.territory_claim_id
        self._fully_supply_blueprint(blueprint)

        self.assertTrue(self.world._complete_construction_blueprint(blueprint))
        completed = next(b for b in self.village.buildings if b.building_type == "workshop")
        self.assertEqual(completed.owner_id, owner.id)
        self.assertEqual(completed.requester_id, owner.id)
        self.assertFalse(completed.player_owned)
        self.assertEqual(completed.settlement_id, self.village.id)
        self.assertEqual(completed.region_id, "region-test")
        self.assertEqual(completed.territory_claim_id, claim_id)
        self.assertEqual(self.world.land_claims_by_id[claim_id].owner_id, completed.id)

    def test_completed_player_owned_construction_preserves_player_ownership(self):
        blueprint = self.world.place_construction_blueprint("workshop", 8, 8, owner_id=self.world.player.id, requester_id=self.world.player.id)
        self._fully_supply_blueprint(blueprint)

        self.assertTrue(self.world._complete_construction_blueprint(blueprint))
        completed = next(b for b in self.village.buildings if b.building_type == "workshop")
        self.assertEqual(completed.owner_id, self.world.player.id)
        self.assertEqual(completed.requester_id, self.world.player.id)
        self.assertTrue(completed.player_owned)

    def test_owner_built_workplace_activates_owner_management_without_public_vacancy(self):
        owner = NPC(8, 8, name="Owner Builder")
        owner.economic.profession = "Unemployed"
        self.world.village_npcs.append(owner)
        blueprint = self.world.place_construction_blueprint("workshop", 8, 8, owner_id=owner.id, requester_id=owner.id)
        self._fully_supply_blueprint(blueprint)

        self.assertTrue(self.world._complete_construction_blueprint(blueprint))
        completed = next(b for b in self.village.buildings if b.building_type == "workshop")
        self.assertEqual(owner.schedule.work_building_id, completed.id)
        self.assertNotEqual(owner.economic.profession, "Unemployed")
        self.assertEqual(self.world.town_board.get_open_employment_tasks(completed.id), [])

if __name__ == "__main__":
    unittest.main()
