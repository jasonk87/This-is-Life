import unittest

import engine
from tests.world_cache import fresh_world


class TextFormatterTests(unittest.TestCase):
    def setUp(self):
        self.world = fresh_world(seed=3, player_first_name='Ada', pre_simulate=False)
        self.formatter = self.world.text

    def test_weather_changed_uses_definition_name(self):
        self.assertEqual(self.formatter.weather_changed("rain"), "The weather has changed to Rain.")

    def test_entity_attack_uses_display_names(self):
        attacker = engine.NPC(1, 1, name="Ada Graves")
        attacker.economic.profession = "Farmer"
        target = engine.NPC(
            2,
            2,
            name="Mother Family_9990",
            family_ties={"relation_to_player": "mother"},
            player_id=self.world.player.id,
        )

        self.assertEqual(
            self.formatter.entity_attacks(attacker, target, 4),
            "Ada Graves (Farmer) attacks Mother for 4 damage!",
        )

    def test_entity_reports_crimes_uses_display_name(self):
        npc = engine.NPC(1, 1, name="Theo Fletcher")
        npc.economic.profession = "Sheriff"
        self.assertEqual(
            self.formatter.entity_reports_your_crimes(npc),
            "Theo Fletcher (Sheriff) reports your crimes to the authorities!",
        )


if __name__ == "__main__":
    unittest.main()
