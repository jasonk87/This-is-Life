import unittest
from unittest.mock import patch

from simulation.ecology import EcologySystem, RegionalWildlifePopulation, WILDLIFE_SPECIES


class TestPreyAvailabilityRatioUnit(unittest.TestCase):
    """Direct unit tests of EcologySystem._prey_availability_ratio - the pure
    helper computing how well-fed a predator's prey base is, with no World
    or chunk scaffolding needed."""

    def setUp(self):
        self.ecology = EcologySystem()

    def _population(self, species_key, count, capacity):
        return RegionalWildlifePopulation(
            region_id="test_region",
            species_key=species_key,
            population_count=count,
            carrying_capacity=capacity,
        )

    def test_non_predator_species_returns_none(self):
        region_populations = {"deer": self._population("deer", 20, 40)}

        ratio = self.ecology._prey_availability_ratio(region_populations, "deer")

        self.assertIsNone(ratio)

    def test_full_prey_capacity_gives_ratio_of_one(self):
        region_populations = {
            "wolf": self._population("wolf", 5, 10),
            "deer": self._population("deer", 40, 40),
            "rabbit": self._population("rabbit", 60, 60),
            "turkey": self._population("turkey", 22, 22),
        }

        ratio = self.ecology._prey_availability_ratio(region_populations, "wolf")

        self.assertEqual(ratio, 1.0)

    def test_half_depleted_prey_gives_ratio_of_half(self):
        region_populations = {
            "wolf": self._population("wolf", 5, 10),
            "deer": self._population("deer", 20, 40),
            "rabbit": self._population("rabbit", 30, 60),
            "turkey": self._population("turkey", 11, 22),
        }

        ratio = self.ecology._prey_availability_ratio(region_populations, "wolf")

        self.assertAlmostEqual(ratio, 0.5)

    def test_fully_depleted_prey_gives_ratio_of_zero(self):
        region_populations = {
            "wolf": self._population("wolf", 5, 10),
            "deer": self._population("deer", 0, 40),
            "rabbit": self._population("rabbit", 0, 60),
            "turkey": self._population("turkey", 0, 22),
        }

        ratio = self.ecology._prey_availability_ratio(region_populations, "wolf")

        self.assertEqual(ratio, 0.0)

    def test_missing_prey_species_in_region_is_skipped_not_penalized(self):
        # Mountain-biome-style region: only deer (mountain-capable) and wolf
        # exist; rabbit/turkey have no mountain base_population and are
        # simply absent from region_populations, as ensure_region_wildlife
        # would leave them.
        region_populations = {
            "wolf": self._population("wolf", 5, 10),
            "deer": self._population("deer", 10, 10),
        }

        ratio = self.ecology._prey_availability_ratio(region_populations, "wolf")

        self.assertEqual(ratio, 1.0)

    def test_no_trackable_prey_data_at_all_defaults_to_no_penalty(self):
        region_populations = {"wolf": self._population("wolf", 5, 10)}

        ratio = self.ecology._prey_availability_ratio(region_populations, "wolf")

        self.assertEqual(ratio, 1.0)


class TestPredatorPressureRatioUnit(unittest.TestCase):
    """Direct unit tests of EcologySystem._predator_pressure_ratio - the
    reciprocal of _prey_availability_ratio, computing how much predator
    pressure a PREY species is under."""

    def setUp(self):
        self.ecology = EcologySystem()

    def _population(self, species_key, count, capacity):
        return RegionalWildlifePopulation(
            region_id="test_region",
            species_key=species_key,
            population_count=count,
            carrying_capacity=capacity,
        )

    def test_species_with_no_predator_returns_none(self):
        # Nothing preys on wolves in WILDLIFE_SPECIES today.
        region_populations = {"wolf": self._population("wolf", 5, 10)}

        ratio = self.ecology._predator_pressure_ratio(region_populations, "wolf")

        self.assertIsNone(ratio)

    def test_predator_at_full_capacity_gives_pressure_of_one(self):
        region_populations = {
            "wolf": self._population("wolf", 18, 18),
            "deer": self._population("deer", 20, 40),
        }

        ratio = self.ecology._predator_pressure_ratio(region_populations, "deer")

        self.assertEqual(ratio, 1.0)

    def test_predator_at_half_capacity_gives_pressure_of_half(self):
        region_populations = {
            "wolf": self._population("wolf", 9, 18),
            "deer": self._population("deer", 20, 40),
        }

        ratio = self.ecology._predator_pressure_ratio(region_populations, "deer")

        self.assertAlmostEqual(ratio, 0.5)

    def test_no_predators_present_gives_pressure_of_zero(self):
        region_populations = {
            "wolf": self._population("wolf", 0, 18),
            "deer": self._population("deer", 20, 40),
        }

        ratio = self.ecology._predator_pressure_ratio(region_populations, "deer")

        self.assertEqual(ratio, 0.0)

    def test_missing_predator_population_in_region_is_skipped_not_penalized(self):
        # A region with deer but genuinely no wolf population tracked at all.
        region_populations = {"deer": self._population("deer", 20, 40)}

        ratio = self.ecology._predator_pressure_ratio(region_populations, "deer")

        self.assertIsNone(ratio)


class TestPreyRecoveryConstrainedByPredatorPressure(unittest.TestCase):
    """Integration-level tests of _recover_wildlife_populations, confirming
    prey (deer/rabbit/turkey) recovery is now also gated by predator
    pressure - closing the previously one-directional predator-prey gap."""

    def setUp(self):
        self.ecology = EcologySystem()
        self.region_id = "test_region"
        self.world = type("FakeWorld", (), {"game_time": 1000})()

    def _seed(self, species_key, count, capacity):
        population = RegionalWildlifePopulation(
            region_id=self.region_id,
            species_key=species_key,
            population_count=count,
            carrying_capacity=capacity,
            reproduction_rate=WILDLIFE_SPECIES[species_key]["recovery_rate"],
        )
        self.ecology.regional_wildlife.setdefault(self.region_id, {})[species_key] = population
        return population

    def test_prey_grows_when_predator_pressure_is_low(self):
        deer = self._seed("deer", count=20, capacity=40)
        self._seed("wolf", count=0, capacity=18)

        with patch("random.random", return_value=0.99):  # still < growth_chance of 1.0
            self.ecology._recover_wildlife_populations(self.world)

        self.assertGreater(deer.population_count, 20)

    def test_prey_growth_withheld_when_predator_pressure_is_maxed(self):
        deer = self._seed("deer", count=20, capacity=40)
        self._seed("wolf", count=18, capacity=18)  # wolves at their own full capacity

        self.ecology._recover_wildlife_populations(self.world)

        self.assertEqual(deer.population_count, 20)

    def test_prey_population_is_never_actively_reduced_by_predator_pressure(self):
        """No extra abstract die-off on top of real hunt/kill events: even
        with max predator pressure, prey only ever stalls, never drops."""
        deer = self._seed("deer", count=20, capacity=40)
        self._seed("wolf", count=18, capacity=18)

        for _ in range(5):
            self.world.game_time += 1000
            self.ecology._recover_wildlife_populations(self.world)

        self.assertGreaterEqual(deer.population_count, 20)

    def test_predator_species_recovery_is_unaffected_by_this_reciprocal_change(self):
        # Wolves have no predator of their own, so _predator_pressure_ratio
        # returns None for "wolf" and this new block is a no-op for them -
        # their recovery is still governed solely by the pre-existing
        # predator-side (prey-availability) check.
        wolf = self._seed("wolf", count=5, capacity=18)
        self._seed("deer", count=40, capacity=40)
        self._seed("rabbit", count=60, capacity=60)
        self._seed("turkey", count=22, capacity=22)

        with patch("random.random", return_value=0.99):
            self.ecology._recover_wildlife_populations(self.world)

        self.assertGreater(wolf.population_count, 5)

    def test_prey_never_drops_below_zero_recovery_floor_regardless_of_pressure(self):
        rabbit = self._seed("rabbit", count=0, capacity=60)
        self._seed("wolf", count=18, capacity=18)

        self.ecology._recover_wildlife_populations(self.world)

        self.assertEqual(rabbit.population_count, 0)


class TestPredatorConstrainedRecovery(unittest.TestCase):
    """Integration-level tests of _recover_wildlife_populations, confirming
    predator (wolf) growth is gated by prey availability while every other
    species' recovery math is completely unaffected."""

    def setUp(self):
        self.ecology = EcologySystem()
        self.region_id = "test_region"
        self.world = type("FakeWorld", (), {"game_time": 1000})()

    def _seed(self, species_key, count, capacity):
        population = RegionalWildlifePopulation(
            region_id=self.region_id,
            species_key=species_key,
            population_count=count,
            carrying_capacity=capacity,
            reproduction_rate=WILDLIFE_SPECIES[species_key]["recovery_rate"],
        )
        self.ecology.regional_wildlife.setdefault(self.region_id, {})[species_key] = population
        return population

    def test_predator_grows_when_prey_is_abundant(self):
        wolf = self._seed("wolf", count=5, capacity=18)
        self._seed("deer", count=10, capacity=10)
        self._seed("rabbit", count=60, capacity=60)
        self._seed("turkey", count=22, capacity=22)

        with patch("random.random", return_value=0.99):  # still < growth_chance of 1.0
            self.ecology._recover_wildlife_populations(self.world)

        self.assertGreater(wolf.population_count, 5)

    def test_predator_growth_withheld_when_prey_fully_depleted(self):
        wolf = self._seed("wolf", count=5, capacity=18)
        self._seed("deer", count=0, capacity=10)
        self._seed("rabbit", count=0, capacity=60)
        self._seed("turkey", count=0, capacity=22)

        self.ecology._recover_wildlife_populations(self.world)

        self.assertEqual(wolf.population_count, 5)

    def test_predator_population_is_never_actively_reduced_by_scarcity(self):
        """No starvation die-off: even with zero prey, an existing predator
        population only ever stalls, it never drops below where it started."""
        wolf = self._seed("wolf", count=5, capacity=18)
        self._seed("deer", count=0, capacity=10)
        self._seed("rabbit", count=0, capacity=60)
        self._seed("turkey", count=0, capacity=22)

        for _ in range(5):
            self.world.game_time += 1000
            self.ecology._recover_wildlife_populations(self.world)

        self.assertGreaterEqual(wolf.population_count, 5)

    def test_non_predator_species_recovery_is_unaffected_by_low_predator_pressure(self):
        # count=20, capacity=40 stays above the pre-existing sparse-population
        # threshold (capacity // 3 == 13), isolating this test to just the
        # predator-prey logic rather than the older sparse-recovery halving.
        # Wolf pressure is 0 here (no wolves at all) - deer has no
        # prey_species entry of its OWN (isn't a predator), and isn't under
        # any predator pressure either, so its recovery is identical to
        # pre-change behavior. See TestPreyRecoveryConstrainedByPredatorPressure
        # below for the case where wolf pressure is actually high.
        deer = self._seed("deer", count=20, capacity=40)
        self._seed("wolf", count=0, capacity=18)

        self.ecology._recover_wildlife_populations(self.world)

        self.assertEqual(deer.population_count, 20 + WILDLIFE_SPECIES["deer"]["recovery_rate"])

    def test_predator_never_exceeds_its_own_carrying_capacity_regardless_of_prey(self):
        wolf = self._seed("wolf", count=18, capacity=18)
        self._seed("deer", count=40, capacity=40)
        self._seed("rabbit", count=60, capacity=60)
        self._seed("turkey", count=22, capacity=22)

        self.ecology._recover_wildlife_populations(self.world)

        self.assertEqual(wolf.population_count, 18)


if __name__ == "__main__":
    unittest.main()
