import unittest
from types import SimpleNamespace
from unittest.mock import patch

from engine import World, Building, NPC, ItemReference
from entities.items import Inventory
from simulation.world_model import Village
from tests.world_cache import fresh_world


class TestConstructionFoundation(unittest.TestCase):
    def setUp(self):
        import engine
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=123, pre_simulate=False)
        self.world.village_npcs.clear()
        self.world.npcs.clear()
        self.village = Village()
        self.village.interaction_points = {"town_square_center": [(12, 12)]}
        self.world.chunks[0][0].village = self.village
        self.world.chunk_width = 1
        self.world.chunk_height = 1
        self.world.calculate_path = lambda sx, sy, ex, ey: [(sx, sy), (ex, ey)]
        from simulation.systems.interaction import InteractionResolver
        self.world.interaction_resolver = InteractionResolver()

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
        from simulation.systems.tick import run_world_tick
        run_world_tick(self.world)

        total_progress = sum(c.build_progress for c in blueprint.components)
        self.assertGreater(total_progress, 0)
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

    def test_construction_advances_through_run_world_tick(self):
        blueprint = self.world.place_construction_blueprint("wooden_chair", 8, 8)
        blueprint.required_work = 20
        for comp in blueprint.components:
            for item_key, qty in comp.required_materials.items():
                for _ in range(qty):
                    comp.deposit_item_reference(ItemReference(item_key))
        blueprint.refresh_status()

        builder = NPC(8, 8, name="Builder")
        builder.economic.profession = "Builder"
        self.world.village_npcs.append(builder)
        self.assertTrue(self.world._assign_construction_task_to_npc(builder))

        from simulation.systems.tick import run_world_tick

        comp = blueprint.components[0]
        initial_progress = comp.build_progress
        self.assertEqual(initial_progress, 0)

        found_active_interaction = False
        completed = False

        for _ in range(100):
            if getattr(builder.schedule, "active_interaction_id", None) is None:
                self.world._handle_npc_construction_task(builder)
                if getattr(builder.schedule, "current_destination_coords", None):
                    builder.x, builder.y = builder.schedule.current_destination_coords
                    builder.schedule.current_destination_coords = None
                    builder.schedule.current_path = []
                self.world._handle_npc_construction_task(builder)

            run_world_tick(self.world)

            if getattr(builder.schedule, "active_interaction_id", None):
                found_active_interaction = True

            if comp.status == "complete":
                completed = True
                break

        self.assertTrue(found_active_interaction, "Builder did not start an interaction")
        self.assertTrue(completed, "Component did not complete naturally via ticks")
        self.assertGreater(comp.build_progress, initial_progress)

    def test_runtime_tick_advances_active_build_interaction_without_world_method(self):
        blueprint = self.world.place_construction_blueprint("wooden_chair", 8, 8)
        for comp in blueprint.components:
            comp.required_work = 20
            for item_key, qty in comp.required_materials.items():
                for _ in range(qty):
                    comp.deposit_item_reference(ItemReference(item_key))
        blueprint.refresh_status()

        builder = NPC(8, 8, name="Runtime Builder")
        builder.economic.profession = "Builder"
        self.world.village_npcs.append(builder)
        self.assertTrue(self.world._assign_construction_task_to_npc(builder))
        self.assertTrue(self.world._handle_npc_construction_task(builder))

        interaction_id = getattr(builder.schedule, "active_interaction_id", None)
        self.assertIsNotNone(interaction_id)
        self.assertIn(interaction_id, self.world.interaction_resolver.active_interactions)

        component = blueprint.components[0]
        initial_remaining_work = component.required_work - component.build_progress

        from simulation.systems.tick import run_world_tick

        with patch.object(self.world, "advance_active_interactions", side_effect=AssertionError("sandbox helper should not drive runtime advancement")):
            run_world_tick(self.world)

        self.assertLess(component.required_work - component.build_progress, initial_remaining_work)
        self.assertGreater(component.build_progress, 0)
        self.assertIn("build_progress", [entry["trace_type"] for entry in self.world.interaction_trace_log])
        self.assertIn("build", [entry["cue"] for entry in self.world.animation_cue_log])

        for _ in range(10):
            if component.status == "complete":
                break
            run_world_tick(self.world)

        self.assertEqual(component.status, "complete")

    def test_runtime_interruption_preserves_partial_build_state(self):
        blueprint = self.world.place_construction_blueprint("wooden_chair", 8, 8)
        for comp in blueprint.components:
            comp.required_work = 30
            for item_key, qty in comp.required_materials.items():
                for _ in range(qty):
                    comp.deposit_item_reference(ItemReference(item_key))
        blueprint.refresh_status()

        builder = NPC(8, 8, name="Interruptible Builder")
        builder.economic.profession = "Builder"
        self.world.village_npcs.append(builder)
        self.assertTrue(self.world._assign_construction_task_to_npc(builder))
        self.assertTrue(self.world._handle_npc_construction_task(builder))

        from simulation.systems.tick import run_world_tick

        run_world_tick(self.world)
        component = blueprint.components[0]
        progress_after_tick = component.build_progress
        delivered_after_tick = dict(component.deposited_inventory)

        cancel_result = self.world.interaction_resolver.cancel_actor_interaction(builder.id, self.world, "unit_test_interrupt")

        self.assertIsNotNone(cancel_result)
        self.assertGreater(progress_after_tick, 0)
        self.assertLess(progress_after_tick, component.required_work)
        self.assertEqual(component.build_progress, progress_after_tick)
        self.assertEqual(dict(component.deposited_inventory), delivered_after_tick)
        self.assertFalse(component.needs_material("wooden_plank"))

    def test_component_claim_prevents_duplicate_build_interactions(self):
        blueprint = self.world.place_construction_blueprint("wooden_chair", 8, 8)
        component = blueprint.components[0]
        component.required_work = 30
        for item_key, qty in component.required_materials.items():
            for _ in range(qty):
                component.deposit_item_reference(ItemReference(item_key))
        blueprint.refresh_status()

        first_builder = NPC(8, 8, name="First Builder")
        first_builder.economic.profession = "Builder"
        second_builder = NPC(8, 8, name="Second Builder")
        second_builder.economic.profession = "Builder"
        self.world.village_npcs.extend([first_builder, second_builder])

        self.assertTrue(self.world._assign_construction_task_to_npc(first_builder))
        self.assertTrue(self.world._handle_npc_construction_task(first_builder))
        self.assertEqual(component.claimed_by_actor_id, first_builder.id)

        self.assertTrue(self.world._assign_construction_task_to_npc(second_builder))
        self.assertFalse(self.world._handle_npc_construction_task(second_builder))

        active_builds = [
            interaction for interaction in self.world.interaction_resolver.active_interactions.values()
            if getattr(interaction, "action_type", None) == "build" and getattr(interaction, "component_id", None) == component.id
        ]
        self.assertEqual(len(active_builds), 1)
        self.assertEqual(active_builds[0].actor_id, first_builder.id)
        self.assertIn("component_claimed", [entry["trace_type"] for entry in self.world.interaction_trace_log])

    def test_interrupted_component_claim_expires_and_allows_resume(self):
        blueprint = self.world.place_construction_blueprint("wooden_chair", 8, 8)
        component = blueprint.components[0]
        component.required_work = 30
        for item_key, qty in component.required_materials.items():
            for _ in range(qty):
                component.deposit_item_reference(ItemReference(item_key))
        blueprint.refresh_status()

        first_builder = NPC(8, 8, name="Interrupted Builder")
        first_builder.economic.profession = "Builder"
        second_builder = NPC(8, 8, name="Resuming Builder")
        second_builder.economic.profession = "Builder"
        self.world.village_npcs.extend([first_builder, second_builder])

        self.assertTrue(self.world._assign_construction_task_to_npc(first_builder))
        self.assertTrue(self.world._handle_npc_construction_task(first_builder))

        from simulation.systems.tick import run_world_tick

        run_world_tick(self.world)
        progress_after_tick = component.build_progress
        delivered_after_tick = dict(component.deposited_inventory)
        cancel_result = self.world.interaction_resolver.cancel_actor_interaction(first_builder.id, self.world, "survival_override")

        self.assertIsNotNone(cancel_result)
        self.assertEqual(component.claimed_by_actor_id, first_builder.id)
        self.assertGreater(progress_after_tick, 0)

        self.assertTrue(self.world._assign_construction_task_to_npc(second_builder))
        self.assertFalse(self.world._handle_npc_construction_task(second_builder))
        self.assertEqual(component.claimed_by_actor_id, first_builder.id)

        self.world.game_time = (component.claim_expiration_tick or self.world.game_time) + 1
        self.assertTrue(self.world._assign_construction_task_to_npc(second_builder))
        self.assertTrue(self.world._handle_npc_construction_task(second_builder))

        self.assertEqual(component.claimed_by_actor_id, second_builder.id)
        self.assertEqual(component.build_progress, progress_after_tick)
        self.assertEqual(dict(component.deposited_inventory), delivered_after_tick)
        trace_types = [entry["trace_type"] for entry in self.world.interaction_trace_log]
        self.assertIn("component_claim_expired", trace_types)

    def test_interrupted_builder_is_removed_from_assigned_workers(self):
        """Regression test for the stale-claim bug found via _debug_test.py:
        blueprint.assigned_workers is a coarser, separate tracking list from
        the component-level claim above (see World._assign_construction_task_to_npc,
        which appends here just for being "sent toward" a blueprint - and,
        since an earlier fix, has an early-return fast path that treats
        anyone still in this list as permanently already-assigned). Before
        this fix, BuildInteraction.cancel() only ever released the
        fine-grained component claim (and only for a few reasons that never
        included "survival_override") - it never touched assigned_workers
        at all, for any reason. That meant an interrupted builder stayed in
        assigned_workers forever, even long after their own component claim
        had expired and someone else had taken over the work, and even
        after their own survival need was resolved and they were free to
        do real work again - the fast path would just keep sending them
        back to "constructing_site" for a blueprint they weren't actually
        assigned to anymore."""
        blueprint = self.world.place_construction_blueprint("wooden_chair", 8, 8)
        component = blueprint.components[0]
        component.required_work = 30
        for item_key, qty in component.required_materials.items():
            for _ in range(qty):
                component.deposit_item_reference(ItemReference(item_key))
        blueprint.refresh_status()

        first_builder = NPC(8, 8, name="Interrupted Builder")
        first_builder.economic.profession = "Builder"
        second_builder = NPC(8, 8, name="Resuming Builder")
        second_builder.economic.profession = "Builder"
        self.world.village_npcs.extend([first_builder, second_builder])

        self.assertTrue(self.world._assign_construction_task_to_npc(first_builder))
        self.assertTrue(self.world._handle_npc_construction_task(first_builder))

        from simulation.systems.tick import run_world_tick
        run_world_tick(self.world)

        self.assertIn(first_builder.id, blueprint.assigned_workers)

        cancel_result = self.world.interaction_resolver.cancel_actor_interaction(
            first_builder.id, self.world, "survival_override"
        )
        self.assertIsNotNone(cancel_result)

        # The bug: this used to still be True after cancellation.
        self.assertNotIn(first_builder.id, blueprint.assigned_workers)
        # The component claim itself is untouched by a survival_override
        # cancel - that grace-period/resume behavior is intentional and
        # covered separately by test_interrupted_component_claim_expires_and_allows_resume.
        self.assertEqual(component.claimed_by_actor_id, first_builder.id)

        # second_builder can be freshly assigned (sent toward the blueprint)
        # without inheriting a stale double-entry alongside first_builder.
        self.assertTrue(self.world._assign_construction_task_to_npc(second_builder))
        self.assertEqual(set(blueprint.assigned_workers), {second_builder.id})
        # But can't actually start building yet - first_builder's component
        # claim is still active (unchanged from before this fix).
        self.assertFalse(self.world._handle_npc_construction_task(second_builder))

    def test_interrupted_builder_is_not_stuck_reporting_as_already_assigned(self):
        """Follow-up consequence of the same bug: _assign_construction_task_to_npc
        has an early-return fast path (added separately, to stop re-scanning
        every blueprint each tick for an already-assigned worker) that
        treats presence in ANY buildable blueprint's assigned_workers as
        "already working this, don't re-evaluate" - it just sets
        current_task = "constructing_site" and returns True without
        checking distance, materials, or anything else. Before this fix,
        an interrupted builder's stale assigned_workers entry meant that
        fast path kept firing for them forever, even long after they were
        genuinely free again. This asserts the exact condition that fast
        path checks (npc.id in some buildable blueprint's assigned_workers)
        is false once the interruption has been cancelled."""
        blueprint = self.world.place_construction_blueprint("wooden_chair", 8, 8)
        component = blueprint.components[0]
        component.required_work = 30
        for item_key, qty in component.required_materials.items():
            for _ in range(qty):
                component.deposit_item_reference(ItemReference(item_key))
        blueprint.refresh_status()

        builder = NPC(8, 8, name="Interrupted Builder")
        builder.economic.profession = "Builder"
        self.world.village_npcs.append(builder)

        self.assertTrue(self.world._assign_construction_task_to_npc(builder))
        self.assertTrue(self.world._handle_npc_construction_task(builder))

        from simulation.systems.tick import run_world_tick
        run_world_tick(self.world)

        self.world.interaction_resolver.cancel_actor_interaction(builder.id, self.world, "survival_override")
        builder.schedule.current_task = "idle"  # simulate the survival system moving them on to eat/drink

        for candidate_blueprint in self.world._get_buildable_blueprints():
            self.assertNotIn(
                builder.id,
                candidate_blueprint.assigned_workers,
                "interrupted builder should not still be reported as assigned to any blueprint",
            )

    def test_completed_construction_integrates_real_building(self):
        blueprint = self.world.place_construction_blueprint("workshop", 8, 8)
        blueprint.required_work = 20
        for comp in blueprint.components:
            for item_key, qty in comp.required_materials.items():
                for _ in range(qty):
                    comp.deposit_item_reference(ItemReference(item_key))
        blueprint.refresh_status()

        builder = NPC(8, 8, name="Builder")
        builder.economic.profession = "Builder"
        self.world.village_npcs.append(builder)
        self.assertTrue(self.world._assign_construction_task_to_npc(builder))

        from simulation.systems.tick import run_world_tick

        safety_counter = 0
        while self.world.get_blueprint_at(8, 8) is not None and safety_counter < 3000:
            safety_counter += 1

            # The test normally calls `_handle_npc_construction_task` directly because it mocks the schedule.
            # But the reviewer requested we use `run_world_tick`.
            # We can still manually call the specific task logic since that's what `process_macro_daily_tick` would do.
            self.world._handle_npc_construction_task(builder)

            if builder.schedule.current_destination_coords:
                builder.x, builder.y = builder.schedule.current_destination_coords
                builder.schedule.current_destination_coords = None
                builder.schedule.current_path = []
                self.world._handle_npc_construction_task(builder)

            # This is the vital part: The tick loop naturally advances the interaction!
            run_world_tick(self.world)

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
        for comp in blueprint.components:
            for item_key, qty in comp.required_materials.items():
                for _ in range(qty):
                    comp.deposit_item_reference(ItemReference(item_key))
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

        # Force same settlement association
        with patch.object(self.world, '_get_village_for_npc') as mock_village:
            mock_village.return_value = SimpleNamespace(id=blueprint.settlement_id)

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
            # The settlement check may not have been executed if the path logic shortcuts, but we want to ensure we set it up anyway

    def test_reachable_local_laborer_receives_priority(self):
        blueprint = self.world.place_construction_blueprint("wooden_chair", 21, 21)
        self._fully_supply_blueprint(blueprint)
        manager = NPC(1, 1, name="Manager")
        manager.economic.profession = "Manager"
        self.world.village_npcs.append(manager)

        laborer = NPC(22, 22, name="Laborer")
        laborer.economic.profession = "Laborer"
        self.world.village_npcs.append(laborer)

        # Force same settlement association
        with patch.object(self.world, '_get_village_for_npc') as mock_village:
            mock_village.return_value = SimpleNamespace(id=blueprint.settlement_id)

        with patch.object(self.world, 'calculate_path', return_value=[(22,22), (21,21)]):
            # Manager should defer to reachable laborer
            self.assertFalse(self.world._assign_construction_task_to_npc(manager))
            self.assertTrue(self.world._assign_construction_task_to_npc(laborer))
            self.assertEqual(blueprint.assigned_workers, [laborer.id])

    def test_building_placement_rejects_chunk_crossing(self):
        from config import CHUNK_SIZE

        # 1. Attempt to place a building right on the chunk border
        border_x = CHUNK_SIZE - 2
        border_y = CHUNK_SIZE - 2

        blueprint = self.world.place_construction_blueprint("workshop", border_x, border_y)
        self.assertIsNone(blueprint, "Building footprint crossing chunk border should be rejected.")
        self.assertFalse(any(b.building_type == "workshop" for b in self.village.buildings), "No partial building should be created.")

        # 2. Attempt to place a valid building inside the chunk
        valid_x = 5
        valid_y = 5

        blueprint2 = self.world.place_construction_blueprint("workshop", valid_x, valid_y)
        self.assertIsNotNone(blueprint2, "Valid in-chunk placement should succeed.")

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

    def test_completed_construction_spawns_spark_particle_burst_at_blueprint_position(self):
        blueprint = self.world.place_construction_blueprint("workshop", 8, 8, owner_id=self.world.player.id, requester_id=self.world.player.id)
        self._fully_supply_blueprint(blueprint)
        blueprint_x, blueprint_y = blueprint.x, blueprint.y

        self.assertTrue(self.world._complete_construction_blueprint(blueprint))

        burst_effects = [e for e in self.world.visual_effects if getattr(e, "effect_type", None) == "particle_burst"]
        self.assertEqual(len(burst_effects), 1)
        self.assertEqual(burst_effects[0].kind, "spark")
        self.assertEqual((burst_effects[0].x, burst_effects[0].y), (float(blueprint_x), float(blueprint_y)))

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
    def test_stockpile_inventory_operations_validate_and_trace(self):
        stockpile = self.world.create_stockpile(4, 4, accepted_item_types={"raw_log"}, max_item_count=2, village_id=self.village.id)

        self.assertEqual(stockpile.stockpile_id in self.world.stockpiles_by_id, True)
        self.assertEqual(self.world.deposit_item_into_stockpile(stockpile.stockpile_id, "raw_log", 2), 2)
        self.assertEqual(stockpile.quantity("raw_log"), 2)
        self.assertEqual(self.world.deposit_item_into_stockpile(stockpile.stockpile_id, "stone_chunk", 1), 0)
        self.assertEqual(self.world.deposit_item_into_stockpile(stockpile.stockpile_id, "raw_log", 1), 0)
        self.assertIs(self.world.find_stockpile_for_item("raw_log", require_available=True), stockpile)

        trace_types = [entry["trace_type"] for entry in self.world.interaction_trace_log]
        self.assertIn("stockpile_created", trace_types)
        self.assertIn("stockpile_deposit", trace_types)
        warning_types = [entry["warning_type"] for entry in self.world.validation_warnings]
        self.assertIn("unsupported_stockpile_item", warning_types)
        self.assertIn("full_stockpile", warning_types)

    def test_hauler_prefers_stockpile_and_delivers_to_component_without_duplicate_reservation(self):
        blueprint = self.world.place_construction_blueprint("wooden_chair", 8, 8)
        stockpile = self.world.create_stockpile(3, 3, accepted_item_types={"wooden_plank"}, max_item_count=10)
        self.world.deposit_item_into_stockpile(stockpile.stockpile_id, "wooden_plank", 1)

        first = NPC(3, 3, name="First Hauler")
        second = NPC(3, 3, name="Second Hauler")
        first.economic.profession = "Laborer"
        second.economic.profession = "Laborer"
        self.world.village_npcs.extend([first, second])

        self.assertTrue(self.world._assign_haul_task_to_npc(first))
        self.assertEqual(first.task_context_data["source"]["source_type"], "stockpile")
        self.assertEqual(stockpile.available_quantity("wooden_plank"), 0)
        self.assertFalse(self.world._assign_haul_task_to_npc(second))

        self.assertTrue(self.world._handle_npc_hauling_task(first))
        self.assertEqual(stockpile.quantity("wooden_plank"), 0)
        first.x, first.y = 8, 8
        first.schedule.current_path = []
        self.assertTrue(self.world._handle_npc_hauling_task(first))
        self.assertEqual(blueprint.delivered_materials.get("wooden_plank", 0), 1)

        trace_types = [entry["trace_type"] for entry in self.world.interaction_trace_log]
        self.assertIn("stockpile_reservation_created", trace_types)
        self.assertIn("stockpile_withdraw", trace_types)
        self.assertIn("haul_delivered", trace_types)


if __name__ == "__main__":
    unittest.main()
