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

    def test_non_predator_species_recovery_is_unaffected_by_this_change(self):
        # count=20, capacity=40 stays above the pre-existing sparse-population
        # threshold (capacity // 3 == 13), isolating this test to just the
        # new predator-prey logic rather than the older sparse-recovery halving.
        deer = self._seed("deer", count=20, capacity=40)
        self._seed("wolf", count=18, capacity=18)  # at capacity, irrelevant to deer

        self.ecology._recover_wildlife_populations(self.world)

        # Deer has no prey_species entry, so its recovery is untouched by
        # the new predator-prey logic - identical to pre-change behavior.
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
