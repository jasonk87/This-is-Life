import unittest
from unittest.mock import MagicMock, patch

import engine
from engine import NPC, Player, World
from entities.animal import Animal


class TestAccrueCrimeBounty(unittest.TestCase):
    """_accrue_crime_bounty is the shared bounty-math helper used by every
    crime path (player witnessed-crime flow, NPC theft/assault/murder)."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=7)

    def _make_npc(self, name="Suspect"):
        npc = NPC(0, 0, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        return npc

    def test_theft_adds_30(self):
        npc = self._make_npc()
        self.world._accrue_crime_bounty(npc, "theft")
        self.assertEqual(npc.economic.bounty, 30)

    def test_assault_adds_50(self):
        npc = self._make_npc()
        self.world._accrue_crime_bounty(npc, "assault")
        self.assertEqual(npc.economic.bounty, 50)

    def test_murder_adds_100(self):
        npc = self._make_npc()
        self.world._accrue_crime_bounty(npc, "murder")
        self.assertEqual(npc.economic.bounty, 100)

    def test_unknown_crime_kind_is_a_no_op(self):
        npc = self._make_npc()
        self.world._accrue_crime_bounty(npc, "jaywalking")
        self.assertEqual(npc.economic.bounty, 0)

    def test_bounty_accumulates_across_multiple_crimes(self):
        npc = self._make_npc()
        self.world._accrue_crime_bounty(npc, "theft")
        self.world._accrue_crime_bounty(npc, "theft")
        self.world._accrue_crime_bounty(npc, "assault")
        self.assertEqual(npc.economic.bounty, 110)

    def test_works_for_player_criminal_too(self):
        self.world._accrue_crime_bounty(self.world.player, "murder")
        self.assertEqual(self.world.player.economic.bounty, 100)


class TestTheftCrimeHook(unittest.TestCase):
    """_execute_steal_food's 'caught stealing' branch should now actually
    record the crime and add bounty instead of being a no-op stub."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=11)

    def test_caught_stealing_adds_theft_bounty(self):
        from simulation.systems.utility_ai import _execute_steal_food
        from engine import Building

        thief = NPC(5, 5, name="Thief", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        building = Building(0, 0, 5, 5, building_type="general_store", category="commercial")
        building.building_inventory["bread"] = 3
        self.world._get_building_global_center_coords = MagicMock(return_value=(5, 5))

        with patch.object(self.world, "_get_village_for_npc") as mock_village:
            fake_village = MagicMock()
            fake_village.buildings = [building]
            mock_village.return_value = fake_village
            with patch("simulation.systems.utility_ai.random.random", return_value=0.0):
                _execute_steal_food(self.world, thief)

        self.assertEqual(thief.economic.bounty, 30)

    def test_uncaught_theft_adds_no_bounty(self):
        from simulation.systems.utility_ai import _execute_steal_food
        from engine import Building

        thief = NPC(5, 5, name="Thief", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        building = Building(0, 0, 5, 5, building_type="general_store", category="commercial")
        building.building_inventory["bread"] = 3
        self.world._get_building_global_center_coords = MagicMock(return_value=(5, 5))

        with patch.object(self.world, "_get_village_for_npc") as mock_village:
            fake_village = MagicMock()
            fake_village.buildings = [building]
            mock_village.return_value = fake_village
            with patch("simulation.systems.utility_ai.random.random", return_value=0.99):
                _execute_steal_food(self.world, thief)

        self.assertEqual(thief.economic.bounty, 0)


class TestNpcAttemptAttackNpcCrimeAndArrest(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=17)
        self.world.player_fov_map = MagicMock()
        self.world.player_fov_map.__getitem__ = MagicMock(return_value=False)

    def _make_npc(self, name, x=0, y=0):
        npc = NPC(x, y, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        return npc

    def test_civilian_assault_records_crime_and_bounty(self):
        attacker = self._make_npc("Aggressor")
        victim = self._make_npc("Victim")
        with patch.object(self.world, "_get_witnesses_to_action", return_value=[]):
            self.world.npc_attempt_attack_npc(attacker, victim)
        self.assertEqual(attacker.economic.bounty, 50)

    def test_guard_executing_warrant_is_not_recorded_as_crime(self):
        guard = self._make_npc("Guard")
        guard.economic.profession = "Guard"
        guard.schedule.current_task = "execute_political_warrant"
        target = self._make_npc("Target")
        with patch.object(self.world, "_get_witnesses_to_action", return_value=[]):
            self.world.npc_attempt_attack_npc(guard, target)
        self.assertEqual(guard.economic.bounty, 0)

    def test_raider_faction_combat_is_not_recorded_as_crime(self):
        raider = self._make_npc("Raider")
        raider.faction_id = "village_a"
        raider.enemy_faction_id = "village_b"
        defender = self._make_npc("Defender")
        with patch.object(self.world, "_get_witnesses_to_action", return_value=[]):
            self.world.npc_attempt_attack_npc(raider, defender)
        self.assertEqual(raider.economic.bounty, 0)

    def test_animal_predation_is_not_recorded_as_crime(self):
        wolf = Animal(0, 0, name="Wolf", animal_type="wolf")
        villager = self._make_npc("Villager")
        with patch.object(self.world, "_get_witnesses_to_action", return_value=[]):
            self.world.npc_attempt_attack_npc(wolf, villager)
        self.assertEqual(wolf.economic.bounty, 0)

    def test_guard_arrests_wanted_target_instead_of_attacking(self):
        guard = self._make_npc("Guard", x=0, y=0)
        guard.economic.profession = "Guard"
        guard.schedule.current_task = "execute_political_warrant"
        guard.task_target_entity_id = 12345
        suspect = self._make_npc("Suspect", x=1, y=0)
        suspect.economic.bounty = 150
        self.world.buildings_by_id = {}  # No sheriff office -> arrest halves bounty, no jailing

        hp_before = suspect.combat.hp
        self.world.npc_attempt_attack_npc(guard, suspect)

        self.assertEqual(suspect.combat.hp, hp_before)  # not attacked
        self.assertEqual(suspect.economic.bounty, 75)  # halved by _serve_npc_jail_time's no-office fallback
        self.assertIsNone(guard.task_target_entity_id)
        self.assertEqual(guard.schedule.current_task, "idle")

    def test_guard_does_not_arrest_already_jailed_target(self):
        guard = self._make_npc("Guard", x=0, y=0)
        guard.economic.profession = "Guard"
        target = self._make_npc("Target", x=1, y=0)
        target.economic.bounty = 150
        target.schedule.is_jailed = True

        with patch.object(self.world, "_get_witnesses_to_action", return_value=[]):
            self.world.npc_attempt_attack_npc(guard, target)

        # Falls through to the ordinary civilian-assault crime-recording path
        # (guard attacking someone isn't itself flagged as a crime for the
        # guard here, since it's still a Sheriff/Guard profession - this test
        # only confirms the arrest branch was skipped, not re-attacked-as-arrest).
        self.assertEqual(target.schedule.is_jailed, True)


class TestFindWantedNpcInSight(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=23)

    def _make_npc(self, name, x, y, profession="Farmer", bounty=0, jailed=False, dead=False):
        npc = NPC(x, y, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        npc.economic.profession = profession
        npc.economic.bounty = bounty
        npc.schedule.is_jailed = jailed
        npc.physical.is_dead = dead
        return npc

    def _all_visible_fov(self):
        class AlwaysVisible:
            def __getitem__(self, key):
                return True
        return AlwaysVisible()

    def test_finds_nearest_wanted_npc_in_fov(self):
        guard = self._make_npc("Guard", 0, 0, profession="Guard")
        near = self._make_npc("Near Suspect", 1, 0, bounty=100)
        far = self._make_npc("Far Suspect", 10, 0, bounty=100)
        self.world.village_npcs = [guard, near, far]
        self.world.npc_fov_maps = {guard.id: self._all_visible_fov()}

        result = self.world._find_wanted_npc_in_sight(guard)
        self.assertIs(result, near)

    def test_ignores_npc_below_bounty_threshold(self):
        guard = self._make_npc("Guard", 0, 0, profession="Guard")
        petty = self._make_npc("Petty Suspect", 1, 0, bounty=99)
        self.world.village_npcs = [guard, petty]
        self.world.npc_fov_maps = {guard.id: self._all_visible_fov()}

        self.assertIsNone(self.world._find_wanted_npc_in_sight(guard))

    def test_ignores_already_jailed_npc(self):
        guard = self._make_npc("Guard", 0, 0, profession="Guard")
        jailed = self._make_npc("Jailed Suspect", 1, 0, bounty=200, jailed=True)
        self.world.village_npcs = [guard, jailed]
        self.world.npc_fov_maps = {guard.id: self._all_visible_fov()}

        self.assertIsNone(self.world._find_wanted_npc_in_sight(guard))

    def test_ignores_other_guards_even_if_wanted(self):
        guard = self._make_npc("Guard", 0, 0, profession="Guard")
        wanted_guard = self._make_npc("Corrupt Guard", 1, 0, profession="Guard", bounty=200)
        self.world.village_npcs = [guard, wanted_guard]
        self.world.npc_fov_maps = {guard.id: self._all_visible_fov()}

        self.assertIsNone(self.world._find_wanted_npc_in_sight(guard))

    def test_no_fov_map_returns_none(self):
        guard = self._make_npc("Guard", 0, 0, profession="Guard")
        self.world.village_npcs = [guard]
        self.world.npc_fov_maps = {}

        self.assertIsNone(self.world._find_wanted_npc_in_sight(guard))


class TestServeNpcJailTime(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=29)

    def _make_npc(self, name="Suspect", x=0, y=0, bounty=150):
        npc = NPC(x, y, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        npc.economic.bounty = bounty
        return npc

    def test_no_sheriff_office_halves_bounty_and_does_not_jail(self):
        npc = self._make_npc(bounty=150)
        self.world.buildings_by_id = {}

        self.world._serve_npc_jail_time(npc)

        self.assertEqual(npc.economic.bounty, 75)
        self.assertFalse(npc.schedule.is_jailed)

    def test_with_sheriff_office_jails_npc_and_clears_bounty(self):
        from engine import Building

        npc = self._make_npc(bounty=150)
        office = Building(0, 0, 6, 6, building_type="sheriff_office", category="civic")
        self.world.buildings_by_id = {office.id: office}
        self.world._change_map_tile = MagicMock()
        self.world._update_entity_position = MagicMock(side_effect=lambda e, x, y: setattr(e, "x", x) or setattr(e, "y", y))

        self.world._serve_npc_jail_time(npc)

        self.assertTrue(npc.schedule.is_jailed)
        self.assertEqual(npc.schedule.jail_time_remaining, engine.NPC_JAIL_DURATION_TICKS)
        self.assertIsNotNone(npc.schedule.jail_cell_coords)
        self.assertEqual(npc.economic.bounty, 0)
        self.assertEqual(npc.schedule.current_task, "jailed")

    def test_release_restores_idle_and_moves_to_cell_door(self):
        npc = self._make_npc()
        npc.schedule.is_jailed = True
        npc.schedule.jail_cell_coords = (5, 5)
        npc.schedule.jail_time_remaining = 0
        self.world._update_entity_position = MagicMock(side_effect=lambda e, x, y: setattr(e, "x", x) or setattr(e, "y", y))

        self.world._release_npc_from_jail(npc)

        self.assertFalse(npc.schedule.is_jailed)
        self.assertIsNone(npc.schedule.jail_cell_coords)
        self.assertEqual(npc.schedule.current_task, "idle")
        self.assertEqual((npc.x, npc.y), (5, 5))


class TestJailTimeTicksDownDuringScheduleUpdate(unittest.TestCase):
    """Integration check: a jailed NPC's jail_time_remaining actually
    decrements via _update_npc_schedules, and they're auto-released at 0 -
    unlike the player, who has no such auto-release and can only escape via
    lockpicking. This is a deliberate, flagged judgment call: NPCs have no
    equivalent of player-driven lockpicking, so a real timer is the only way
    an NPC sentence ever ends."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=31)
        self.world._update_entity_temperature = MagicMock()
        self.world._apply_temperature_effects = MagicMock()
        self.world._update_npc_fov = MagicMock()
        self.world.calculate_path = MagicMock(return_value=[])

    def test_jailed_npc_is_skipped_and_counted_down(self):
        npc = NPC(3, 3, name="Jailed NPC", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        npc.schedule.is_jailed = True
        npc.schedule.jail_cell_coords = (4, 4)
        npc.schedule.jail_time_remaining = 3
        npc.physical.temperature = 37.0

        self.world.village_npcs = [npc]
        self.world.npcs = []

        self.world._update_npc_schedules()
        self.assertEqual(npc.schedule.jail_time_remaining, 2)
        self.assertTrue(npc.schedule.is_jailed)

    def test_jailed_npc_released_when_timer_hits_zero(self):
        npc = NPC(3, 3, name="Jailed NPC", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        npc.schedule.is_jailed = True
        npc.schedule.jail_cell_coords = (4, 4)
        npc.schedule.jail_time_remaining = 1
        npc.physical.temperature = 37.0

        self.world.village_npcs = [npc]
        self.world.npcs = []

        self.world._update_npc_schedules()
        self.assertFalse(npc.schedule.is_jailed)
        self.assertEqual(npc.schedule.current_task, "idle")


class TestMurderAddsBounty(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=37)

    def test_witnessed_npc_murder_adds_bounty_to_killer(self):
        killer = NPC(2, 2, name="Killer", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        victim = NPC(2, 2, name="Victim", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        victim.physical.is_dead = True
        self.world.village_npcs = [killer, victim]

        with patch.object(self.world, "_get_witnesses_to_action", return_value=[]), \
             patch.object(self.world, "record_death_event") as mock_record_death:
            fake_event = MagicMock()
            fake_event.public_knowledge = True
            fake_event.id = "death-1"
            mock_record_death.return_value = fake_event
            self.world.handle_npc_death(victim, killer_id=killer.id, cause_of_death="killed")

        self.assertEqual(killer.economic.bounty, 100)


if __name__ == "__main__":
    unittest.main()
