import unittest
from engine import World
from simulation.world_model import Village
from simulation.systems.economy import _update_village_economic_needs
from entities.base import NPC
import engine

class TestTownEconomicNeeds(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=42)
        self.village = Village()
        self.world.villages.append(self.village)

    def test_detect_food_shortage(self):
        # Setup high demand, no supply
        self.village.demand["bread"] = 10
        self.village.supply["bread"] = 0

        _update_village_economic_needs(self.world, self.village)

        needs = self.world.town_board.economic_needs
        self.assertTrue(any(n.type == "shortage" and n.target_key == "bread" for n in needs))

    def test_detect_service_shortage(self):
        # We need a blacksmith, and we have a building
        from simulation.world_model import Building
        b = Building(0, 0, 5, 5, building_type="blacksmith_shop")
        self.village.add_building(b)
        self.world.buildings_by_id[b.id] = b

        # No blacksmith npc
        self.world.village_npcs = []

        _update_village_economic_needs(self.world, self.village)

        needs = self.world.town_board.economic_needs
        self.assertTrue(any(n.type == "service" and n.target_key == "Blacksmith" for n in needs))

        # Now add one
        npc = NPC(0, 0)
        npc.economic.profession = "Blacksmith"
        npc.schedule.work_building_id = b.id
        self.world.village_npcs.append(npc)

        _update_village_economic_needs(self.world, self.village)

        needs = self.world.town_board.economic_needs
        self.assertFalse(any(n.type == "service" and n.target_key == "Blacksmith" for n in needs))


    def test_wage_pressure_hook(self):
        from simulation.world_model import TownEconomicNeed

        base_wage = self.world._get_employment_daily_wage("Blacksmith", village=self.village)

        # Add economic need
        need = TownEconomicNeed(type="service", target_key="Blacksmith", settlement_id=self.village.id)
        self.world.town_board.economic_needs.append(need)

        # Check that wage increases
        pressure_wage = self.world._get_employment_daily_wage("Blacksmith", village=self.village)
        self.assertGreater(pressure_wage, base_wage)
        self.assertEqual(pressure_wage, int(base_wage * 1.5))

    def test_npc_evaluates_opportunity(self):
        from simulation.world_model import TownEconomicNeed
        from config import CHUNK_SIZE

        npc = self.world.village_npcs[0]
        village = self.world._get_village_for_npc(npc)

        # Important: the `handle_npc_job_seeking` uses `npc.x, npc.y` to compare with the noticeboard coords.
        # But noticeboard coords might be non-integers if something is weird, though they shouldn't be.
        board_coords = village.interaction_points.get("noticeboard", [(0,0)])[0]
        npc.x = int(board_coords[0])
        npc.y = int(board_coords[1])

        self.world._set_entity_profession(npc, "Unemployed")

        need = TownEconomicNeed(type="service", target_key="Blacksmith", settlement_id=village.id)
        self.world.town_board.economic_needs = [need]
        self.world.town_board.employment_tasks = []

        res = self.world.handle_npc_job_seeking(npc)
        self.assertTrue(res, "NPC should have picked up a job")
        self.assertEqual(npc.economic.profession, "Blacksmith")
        self.assertEqual(len(self.world.town_board.economic_needs), 0)


if __name__ == '__main__':
    unittest.main()
