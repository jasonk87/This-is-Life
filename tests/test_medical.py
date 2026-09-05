import unittest
from unittest.mock import MagicMock, patch
import engine
from entities.base import NPC
from tests.world_cache import fresh_world

class TestMedicalSystem(unittest.TestCase):
    def test_broken_leg_treatment(self):
        world = fresh_world(seed=13, pre_simulate=False)
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
        self.assertEqual(patient.schedule.current_task, "resting_in_bed")

        healer.task_timer = 0 # Timer must be 0 for it to trigger the completion logic. Actually, if timer > 0 it decrements. If it is 0, it completes.
        world.game_time += engine.NPC_SCHEDULE_UPDATE_INTERVAL
        world._update_npc_schedules()

        self.assertEqual(healer.schedule.current_task, "idle")
        self.assertNotIn("broken_leg", patient.physical.status_effects)
        self.assertGreater(patient.combat.body_parts_hp["left_leg"], 0)
        self.assertEqual(patient.economic.money, 10)
        self.assertEqual(healer.economic.money, 10)

    def test_broken_leg_patient_paths_to_clinic(self):
        world = fresh_world(seed=13, pre_simulate=False)
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


    def test_healer_forages_and_crafts(self):
        """Forage, then turn the herbs into a salve.

        The clinic is built before the healer starts rather than half way
        through. It used to be added between the forage and the craft, which
        worked only because the healer spent an idle tick in between: the forage
        payout is now settled before they choose their next task - it had to be,
        or the arrival was overwritten by a fresh forage target and no herb was
        ever gathered - so a healer holding herbs goes straight on to crafting.
        Deciding to craft with no clinic in the world sends them to their own
        feet, which is the fallback branch and not what this test is about.
        """
        world = fresh_world(seed=13, pre_simulate=False)
        healer = engine.NPC(x=11, y=10, name="Healer NPC")
        healer.economic.profession = "Healer"
        healer.economic.money = 0

        world.village_npcs = [healer]
        world.npcs = []
        world.game_time += engine.NPC_SCHEDULE_UPDATE_INTERVAL
        world._update_npc_fov = MagicMock()
        world._update_entity_temperature = MagicMock()
        world._apply_temperature_effects = MagicMock()

        clinic = engine.Building(11, 11, 5, 5, building_type="clinic", category="civic_workplace")
        clinic.id = "clinic_1"
        clinic.work_zone_tiles["alchemy_station"] = [(11, 11)]
        world.buildings_by_id[clinic.id] = clinic
        village = engine.Village()
        village.buildings.append(clinic)
        world._get_village_for_npc = MagicMock(return_value=village)

        # Mock calculate path to allow foraging
        world.calculate_path = MagicMock(return_value=[(11, 10), (12, 10)])

        world._update_npc_schedules()

        # 1. Should start foraging
        self.assertEqual(healer.schedule.current_task, "foraging_for_herbs")

        # Arrive at foraging spot
        healer.schedule.current_path = []
        world.game_time += engine.NPC_SCHEDULE_UPDATE_INTERVAL
        world._update_npc_schedules()

        # 2. Should have herbs, and having them, move straight on to crafting
        self.assertGreaterEqual(healer.economic.npc_inventory.get("medicinal_herb", 0), 2)
        self.assertEqual(healer.schedule.current_task, "crafting_medical_supplies")
        self.assertEqual(healer.schedule.current_destination_coords, (11, 11))

        # Move to the alchemy station
        healer.schedule.current_path = []
        healer.x, healer.y = 11, 11
        world.game_time += engine.NPC_SCHEDULE_UPDATE_INTERVAL
        world._update_npc_schedules()

        # 3. Standing at the station, working the craft timer down
        self.assertEqual(healer.schedule.current_task, "crafting_medical_supplies")

        # Advance timer
        healer.task_timer = 1
        world.game_time += engine.NPC_SCHEDULE_UPDATE_INTERVAL
        with patch("entities.items.random.random", return_value=0.95):
            world._update_npc_schedules()

        # 4. Should finish crafting, become idle, and have 1 salve
        self.assertEqual(healer.schedule.current_task, "idle")
        self.assertEqual(healer.economic.npc_inventory.get("healing_salve", 0), 1)
        salve = healer.economic.npc_inventory.get_item_reference("healing_salve")
        self.assertIsNotNone(salve)
        self.assertEqual(salve.crafter_name, "Healer NPC")
        self.assertEqual(salve.quality, "Fine")

if __name__ == '__main__':
    unittest.main()
