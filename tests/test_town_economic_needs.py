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

if __name__ == '__main__':
    unittest.main()
