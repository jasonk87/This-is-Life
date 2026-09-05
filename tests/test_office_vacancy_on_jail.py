import unittest
from unittest.mock import MagicMock

import engine
from engine import NPC, Building, World
from tests.world_cache import fresh_world


class TestVacateOfficesHeldBy(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=97, pre_simulate=False)

    def _make_npc(self, name="Officeholder"):
        return NPC(0, 0, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)

    def test_clears_the_office_the_entity_holds(self):
        npc = self._make_npc()
        self.world.politics.offices["Mayor"].holder_id = npc.id

        self.world._vacate_offices_held_by(npc)

        self.assertIsNone(self.world.politics.offices["Mayor"].holder_id)

    def test_clears_multiple_offices_if_somehow_held_simultaneously(self):
        npc = self._make_npc()
        self.world.politics.offices["Mayor"].holder_id = npc.id
        self.world.politics.offices["Captain of the Guard"].holder_id = npc.id

        self.world._vacate_offices_held_by(npc)

        self.assertIsNone(self.world.politics.offices["Mayor"].holder_id)
        self.assertIsNone(self.world.politics.offices["Captain of the Guard"].holder_id)

    def test_does_not_touch_offices_held_by_someone_else(self):
        npc = self._make_npc("Suspect")
        other = self._make_npc("Innocent Mayor")
        self.world.politics.offices["Mayor"].holder_id = other.id

        self.world._vacate_offices_held_by(npc)

        self.assertEqual(self.world.politics.offices["Mayor"].holder_id, other.id)

    def test_entity_holding_no_office_is_a_no_op(self):
        npc = self._make_npc()
        holder_before = self.world.politics.offices["Mayor"].holder_id
        self.world._vacate_offices_held_by(npc)  # no exception, nothing to clear
        self.assertEqual(self.world.politics.offices["Mayor"].holder_id, holder_before)

    def test_entity_with_no_id_is_a_no_op(self):
        fake = MagicMock(spec=[])  # no .id attribute at all
        self.world.politics.offices["Mayor"].holder_id = 999
        self.world._vacate_offices_held_by(fake)
        self.assertEqual(self.world.politics.offices["Mayor"].holder_id, 999)


class TestJailingVacatesOffice(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=101, pre_simulate=False)
        self.world._change_map_tile = MagicMock()
        self.world._update_entity_position = MagicMock(side_effect=lambda e, x, y: (setattr(e, "x", x), setattr(e, "y", y)))

    def test_jailing_an_npc_officeholder_vacates_their_office(self):
        from engine import Building

        mayor = NPC(0, 0, name="Corrupt Mayor", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        mayor.economic.bounty = 150
        self.world.politics.offices["Mayor"].holder_id = mayor.id

        office = Building(0, 0, 6, 6, building_type="sheriff_office", category="civic")
        self.world.buildings_by_id[office.id] = office

        self.world._serve_npc_jail_time(mayor)

        self.assertTrue(mayor.schedule.is_jailed)
        self.assertIsNone(self.world.politics.offices["Mayor"].holder_id)

    def test_jailing_a_non_officeholder_npc_leaves_offices_untouched(self):
        from engine import Building

        mayor = NPC(0, 0, name="Mayor", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        self.world.politics.offices["Mayor"].holder_id = mayor.id

        suspect = NPC(0, 0, name="Unrelated Thief", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        suspect.economic.bounty = 150

        office = Building(0, 0, 6, 6, building_type="sheriff_office", category="civic")
        self.world.buildings_by_id[office.id] = office

        self.world._serve_npc_jail_time(suspect)

        self.assertEqual(self.world.politics.offices["Mayor"].holder_id, mayor.id)

    def test_no_sheriff_office_fallback_does_not_vacate_office(self):
        """If there's nowhere to actually hold the NPC, _serve_npc_jail_time
        falls back to just halving their bounty and letting them go - they
        were never really jailed, so their office shouldn't be vacated."""
        mayor = NPC(0, 0, name="Mayor", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        mayor.economic.bounty = 150
        self.world.politics.offices["Mayor"].holder_id = mayor.id
        self.world.buildings_by_id = {}  # no sheriff_office anywhere

        self.world._serve_npc_jail_time(mayor)

        self.assertFalse(mayor.schedule.is_jailed)
        self.assertEqual(self.world.politics.offices["Mayor"].holder_id, mayor.id)

    def test_vacated_office_is_refilled_by_the_next_election_cycle(self):
        """Confirms the fix reuses the existing vacancy-fill flow rather than
        leaving the office permanently empty - evaluate_elections() already
        fills any office whose holder_id is None."""
        from engine import Building

        mayor = NPC(5, 5, name="Corrupt Mayor", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        mayor.economic.bounty = 150
        mayor.social.fame = 0
        self.world.village_npcs.append(mayor)
        self.world.politics.offices["Mayor"].holder_id = mayor.id

        office = Building(0, 0, 6, 6, building_type="sheriff_office", category="civic")
        self.world.buildings_by_id[office.id] = office

        self.world._serve_npc_jail_time(mayor)
        self.assertIsNone(self.world.politics.offices["Mayor"].holder_id)

        self.world.evaluate_elections()

        # Some candidate (player or another villager) now holds the office -
        # the point is it's no longer sitting vacant with a jailed ex-mayor
        # nominally still attached.
        self.assertIsNotNone(self.world.politics.offices["Mayor"].holder_id)


class TestPlayerJailingVacatesOfficeAndDoesNotCrash(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=103, pre_simulate=False)
        self.world._change_map_tile = MagicMock()

    def test_serve_jail_time_completes_without_crashing(self):
        """Regression test: serve_jail_time previously had no return after
        setting up the jail cell and fell straight into unreachable code
        from an unrelated, now-missing method (referencing undefined names
        like contract_id/turn_in_npc), so it always raised NameError when
        actually called. This is the first test to exercise it end-to-end."""
        from engine import Building

        office = Building(0, 0, 6, 6, building_type="sheriff_office", category="civic")
        self.world.buildings_by_id[office.id] = office
        self.world.player.economic.bounty = 150

        try:
            self.world.serve_jail_time()
        except NameError as exc:
            self.fail(f"serve_jail_time() raised NameError (the old orphaned-code bug): {exc}")

        self.assertTrue(self.world.player.state.is_jailed)
        self.assertEqual(self.world.player.economic.bounty, 0)

    def test_serve_jail_time_vacates_an_office_the_player_holds(self):
        from engine import Building

        office = Building(0, 0, 6, 6, building_type="sheriff_office", category="civic")
        self.world.buildings_by_id[office.id] = office
        self.world.player.economic.bounty = 150
        self.world.politics.offices["Mayor"].holder_id = self.world.player.id

        self.world.serve_jail_time()

        self.assertIsNone(self.world.politics.offices["Mayor"].holder_id)


class TestVacatedOfficeStopsSalary(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=107, pre_simulate=False)

    def test_pay_daily_civic_salaries_skips_a_vacated_office(self):
        town_hall = Building(0, 0, 6, 6, building_type="town_hall", category="civic")
        self.world._set_trade_money_balance(town_hall, 1000)

        mayor = NPC(0, 0, name="Jailed Mayor", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        self.world.politics.offices["Mayor"].holder_id = mayor.id
        self.world._vacate_offices_held_by(mayor)  # simulates the jailing side-effect

        mayor_balance_before = self.world._get_trade_money_balance(mayor)
        self.world._pay_daily_civic_salaries(town_hall)

        self.assertEqual(self.world._get_trade_money_balance(mayor), mayor_balance_before)


if __name__ == "__main__":
    unittest.main()
