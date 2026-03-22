import unittest
from unittest.mock import MagicMock
import engine
from entities.base import NPC

class TestMedicalSystem(unittest.TestCase):
    def test_broken_leg_treatment(self):
        world = engine.World(seed=13)
        patient = engine.NPC(x=10, y=10, name="Injured NPC")
        patient.combat.max_hp = 30
        patient.combat.hp = 30
        patient.physical.status_effects.append("broken_leg")
        patient.combat.body_parts_hp["left_leg"] = 0
        patient.economic.money = 20
        patient.original_speed = 1.0
        patient.speed = 0.5
        patient.physical.temperature = 37.0 # Prevent Freezing/seeking_warmth

        healer = engine.NPC(x=11, y=10, name="Healer NPC")
        healer.economic.profession = "Healer"
        healer.economic.money = 0
        healer.physical.temperature = 37.0

        # Override update temp so they don't freeze and override tasks
        world._update_entity_temperature = MagicMock()
        world._apply_temperature_effects = MagicMock() # Prevent freezing applying damage or status

        world.village_npcs = [patient, healer]
        world.npcs = []
        world.game_time += engine.NPC_SCHEDULE_UPDATE_INTERVAL
        world._update_npc_fov = MagicMock()

        # No clinic, no path -> resting_in_bed
        world.calculate_path = MagicMock(return_value=[])
        world._update_npc_schedules()

        self.assertEqual(healer.schedule.current_task, "treating_patient")
        self.assertEqual(healer.task_target_entity_id, patient.id)
        self.assertEqual(patient.schedule.current_task, "waiting_for_treatment")

        healer.task_timer = 0 # Timer must be 0 for it to trigger the completion logic. Actually, if timer > 0 it decrements. If it is 0, it completes.
        world.game_time += engine.NPC_SCHEDULE_UPDATE_INTERVAL
        world._update_npc_schedules()

        self.assertEqual(healer.schedule.current_task, "idle")
        self.assertNotIn("broken_leg", patient.physical.status_effects)
        self.assertGreater(patient.combat.body_parts_hp["left_leg"], 0)
        self.assertEqual(patient.economic.money, 10)
        self.assertEqual(healer.economic.money, 10)

    def test_broken_leg_patient_paths_to_clinic(self):
        world = engine.World(seed=13)
        patient = engine.NPC(x=5, y=5, name="Injured NPC")
        patient.physical.status_effects.append("broken_leg")

        clinic = engine.Building(20, 20, 5, 5, building_type="clinic", category="civic_workplace")
        clinic.id = "clinic_1"
        world.buildings_by_id[clinic.id] = clinic

        village = engine.Village()
        village.buildings.append(clinic)
        world._get_village_for_npc = MagicMock(return_value=village)

        world.village_npcs = [patient]
        world.npcs = []
        world.game_time += engine.NPC_SCHEDULE_UPDATE_INTERVAL
        world._update_npc_fov = MagicMock()
        world._update_entity_temperature = MagicMock()
        world._apply_temperature_effects = MagicMock()

        world.calculate_path = MagicMock(return_value=[(5,5), (20,20)])
        world._update_npc_schedules()

        self.assertEqual(patient.schedule.current_task, "seeking_healer")
        self.assertEqual(patient.schedule.current_destination_coords, (clinic.global_center_x, clinic.global_center_y))

if __name__ == '__main__':
    unittest.main()
