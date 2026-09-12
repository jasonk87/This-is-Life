"""Villagers do not freeze to death on a spring afternoon.

The thermal model set a person's target body temperature to the temperature of
the air around them:

    target_temp_equilibrium = ambient_temperature + total_insulation

Nothing in the game reaches the 35-38.5C band that counts as healthy. The
warmest season modifier is Summer at 25, the default insulation is 2, and a
plains chunk adds nothing - so the warmest equilibrium any villager could have
is 27, and the ordinary one is lower. Measured: on a Spring day an NPC's body
temperature fell from 37.0 to 17.04 within about 120 ticks and stayed there,
carrying "Freezing" permanently.

Freezing costs 1 HP every 576 ticks - 25 a day against 35 max HP. So every
villager in the world was quietly dying of cold in mild weather, and a two-day
run of the detailed simulation took a village from 116 alive to 16.

Nothing caught it. test_long_run_health runs a month, but through the *abstract*
daily systems - it advances the clock and calls process_abstract_simulation and
friends directly, never run_world_tick - so it never touches per-tick survival.
The only test that does tick for real ran 600 ticks, which is not long enough to
kill anyone at 1 HP per 576.

The model now holds a body near 37 and lets the environment push it off that
mark, weakly. Ordinary weather is survivable; a winter night, a mountain or a
snowfield is not; a fire fixes it; a desert at midday in summer is its own
problem.
"""

import unittest

from config import DAY_LENGTH_TICKS
from engine import World
from tests.world_cache import fresh_world
from entities.metabolism import (
    AMBIENT_COUPLING,
    COMFORTABLE_AMBIENT,
    NORMAL_BODY_TEMPERATURE,
    body_equilibrium_temperature,
)
from simulation.systems.survival import (
    apply_temperature_effects,
    update_entity_temperature,
    update_npc_survival,
)

FREEZING_BELOW = 35.0
OVERHEATING_ABOVE = 38.5
DEFAULT_INSULATION = 2.0


class TestTheEquilibriumIsABodyNotTheAir(unittest.TestCase):
    def test_a_comfortable_room_holds_a_normal_temperature(self):
        self.assertAlmostEqual(
            body_equilibrium_temperature(COMFORTABLE_AMBIENT, 0.0),
            NORMAL_BODY_TEMPERATURE,
            places=6,
        )

    def test_ordinary_weather_is_survivable(self):
        """Every season, at every time of day the sun is up or the night is
        ordinary, on the plains where the villages are."""
        for label, ambient in (
            ("spring day", 15), ("spring night", 7), ("spring deep night", 5),
            ("summer day", 25), ("summer night", 17),
            ("autumn day", 10), ("autumn night", 2),
        ):
            temperature = body_equilibrium_temperature(ambient, DEFAULT_INSULATION)
            with self.subTest(weather=label):
                self.assertGreaterEqual(
                    temperature, FREEZING_BELOW,
                    f"{label} (ambient {ambient}) settles a body at {temperature:.2f}, "
                    f"which is freezing",
                )
                self.assertLessEqual(temperature, OVERHEATING_ABOVE, label)

    def test_real_cold_is_still_dangerous(self):
        """The point is not to make cold harmless."""
        for label, ambient in (
            ("winter deep night", -15),
            ("mountain in winter at night", -23),
            ("snowfield in winter", -30),
        ):
            with self.subTest(weather=label):
                self.assertLess(
                    body_equilibrium_temperature(ambient, DEFAULT_INSULATION),
                    FREEZING_BELOW,
                    f"{label} left a body comfortable",
                )

    def test_a_fire_rescues_someone_from_a_winter_night(self):
        """Ambient 10 is a winter night beside a hearth: -15 outside, lifted by
        the hearth's heat and capped at the comfort ceiling."""
        self.assertGreaterEqual(
            body_equilibrium_temperature(10, DEFAULT_INSULATION), FREEZING_BELOW
        )

    def test_insulation_helps(self):
        bare = body_equilibrium_temperature(-10, 0.0)
        wrapped = body_equilibrium_temperature(-10, 12.0)
        self.assertGreater(wrapped, bare)

    def test_winter_clothes_do_not_generate_heat_in_a_mild_room(self):
        for ambient in (5, 15, 20, 25, 30):
            for insulation in (2, 12, 24, 40):
                with self.subTest(ambient=ambient, insulation=insulation):
                    temperature = body_equilibrium_temperature(ambient, insulation)
                    self.assertLessEqual(temperature, OVERHEATING_ABOVE)
                    self.assertGreaterEqual(temperature, FREEZING_BELOW)

    def test_real_heat_remains_dangerous_and_heavy_clothes_make_it_worse(self):
        bare = body_equilibrium_temperature(40, 0)
        wrapped = body_equilibrium_temperature(40, 20)
        self.assertGreater(bare, OVERHEATING_ABOVE)
        self.assertGreater(wrapped, bare)

    def test_the_coupling_is_weak_enough_to_be_a_body(self):
        """A guard on the constant itself: at coupling 1.0 this is the old bug
        again, whatever the rest of the arithmetic says."""
        self.assertLess(AMBIENT_COUPLING, 0.5)


class TestAVillagerSurvivesTheDayTheyAreStandingIn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = fresh_world(seed=5)

    def test_the_season_this_world_starts_in_is_a_mild_one(self):
        """Anchors what the next test is actually asserting."""
        season = self.world.seasons[self.world.current_season_index]
        self.assertIn(season, ("Spring", "Summer", "Autumn"))

    def test_standing_outdoors_does_not_drive_a_body_to_the_air_temperature(self):
        """The measured regression, directly: 37.0 to 17.04 in 120 updates."""
        npc = next(n for n in self.world.village_npcs if not n.physical.is_dead)
        npc.physical.temperature = NORMAL_BODY_TEMPERATURE
        for _ in range(200):
            update_entity_temperature(self.world, npc, update_world_ambient=False)

        self.assertGreater(
            npc.physical.temperature, FREEZING_BELOW,
            f"a villager settled at {npc.physical.temperature:.2f}C in mild weather",
        )
        self.assertNotIn("Freezing", npc.physical.status_effects)

    def test_a_day_of_mild_weather_kills_nobody(self):
        """A full day of survival ticks over a sample of the village.

        Driven directly rather than through run_world_tick so that this stays a
        few seconds rather than half an hour: the thing under test is the
        thermal loop, and that is exactly what it exercises.
        """
        world = self.world
        sample = [n for n in world.village_npcs if not n.physical.is_dead][:25]
        self.assertTrue(sample)
        for npc in sample:
            npc.physical.temperature = NORMAL_BODY_TEMPERATURE
        start_hp = {npc.id: npc.combat.hp for npc in sample}

        step = max(1, DAY_LENGTH_TICKS // 25)
        for _ in range(25):
            world.game_time += step
            for npc in sample:
                update_npc_survival(world, npc)
                apply_temperature_effects(world, npc, is_player=False)

        died = [npc.name for npc in sample if npc.physical.is_dead or npc.combat.hp <= 0]
        self.assertEqual(
            died, [],
            f"{len(died)} of {len(sample)} villagers died of the weather in one "
            f"ordinary day: {died[:5]}",
        )
        frozen = [
            npc.name for npc in sample if "Freezing" in npc.physical.status_effects
        ]
        self.assertEqual(
            frozen, [],
            f"{len(frozen)} of {len(sample)} villagers are freezing in mild weather",
        )
        lost = [
            npc.name for npc in sample if npc.combat.hp < start_hp[npc.id]
        ]
        self.assertEqual(
            lost, [],
            f"villagers lost health to the weather on a mild day: {lost[:5]}",
        )


if __name__ == "__main__":
    unittest.main()
