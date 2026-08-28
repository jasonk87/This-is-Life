"""World generation invariants a playable world depends on.

These pin two defects found together: elevation noise was sampled over less
than one period, so a map was a single gradient whose seed decided whether
it was almost all ocean or almost all land; and village placement only
considered plains, so a watery map produced no settlements whatsoever - a
world with no NPCs, quests or economy. Roughly one seed in thirteen was
unplayable.
"""

import numpy as np
import pytest

import config
import world_generation
from world_generation import WorldGenerator

# Enough seeds to catch a regression that only shows up on unlucky maps,
# few enough to stay quick.
SAMPLE_SEEDS = list(range(30))


def _generator(seed):
    return WorldGenerator(config.WORLD_WIDTH_CHUNKS, config.WORLD_HEIGHT_CHUNKS, seed=seed)


@pytest.mark.parametrize("seed", SAMPLE_SEEDS)
def test_every_world_has_at_least_one_village(seed):
    assert _generator(seed).village_coords, (
        f"seed {seed} generated a world with no villages at all - no NPCs, "
        "quests or economy would exist in it"
    )


@pytest.mark.parametrize("seed", SAMPLE_SEEDS)
def test_every_world_has_both_land_and_water(seed):
    elevation = np.asarray(_generator(seed).elevation_map)
    land_fraction = float((elevation >= config.ELEVATION_WATER).mean())

    assert 0.10 < land_fraction < 0.95, (
        f"seed {seed} produced {land_fraction:.0%} land; a map that is "
        "nearly all ocean or nearly all continent has no coastline to play on"
    )


@pytest.mark.parametrize("seed", SAMPLE_SEEDS)
def test_villages_are_placed_inland_not_on_the_border(seed):
    generator = _generator(seed)
    for x, y in generator.village_coords:
        assert 1 <= x < generator.width - 1
        assert 1 <= y < generator.height - 1


@pytest.mark.parametrize("seed", SAMPLE_SEEDS)
def test_villages_are_never_placed_on_water(seed):
    generator = _generator(seed)
    for x, y in generator.village_coords:
        assert generator.get_biome_at(x, y) in WorldGenerator.HABITABLE_BIOMES


def test_plains_are_preferred_when_the_map_offers_plenty():
    """The fallback to harsher biomes must not displace good farmland on a
    map that has plenty of it."""
    for seed in SAMPLE_SEEDS:
        generator = _generator(seed)
        plains = generator._candidate_village_coords(("plains",))
        if len(plains) < 8:
            continue
        biomes = [generator.get_biome_at(x, y) for x, y in generator.village_coords]
        assert biomes.count("plains") == len(biomes), (
            f"seed {seed} has {len(plains)} plains chunks but sited a village elsewhere"
        )
        return
    pytest.skip("no sampled seed had enough plains to exercise the preference")


def test_noise_scale_spans_more_than_one_period():
    """Guards the actual root cause rather than only its symptom.

    The world samples noise at chunk_index * NOISE_SCALE, so the map spans
    (chunks - 1) * NOISE_SCALE of the noise field. Below ~1.0 the whole
    world sits inside a single smooth gradient.
    """
    span = (config.WORLD_WIDTH_CHUNKS - 1) * config.NOISE_SCALE

    assert span > 1.0, (
        f"world spans only {span:.2f} of the noise field; every map will be "
        "one gradient and the seed alone decides land vs ocean"
    )


def test_village_selection_returns_empty_rather_than_raising_on_a_dead_map():
    """A map with no habitable chunks should degrade, not explode."""
    generator = _generator(SAMPLE_SEEDS[0])
    generator.get_biome_at = lambda x, y: "deep_water"

    assert generator._select_village_coords() == set()


def _passable_ratio(world, x0, y0, x1, y1):
    total = passable = 0
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            tile = world.get_tile_at(x, y)
            total += 1
            if tile and tile.passable:
                passable += 1
    return passable / total


def _terrain_signature(world, x0, y0, x1, y1):
    return tuple(
        getattr(world.get_tile_at(x, y), "name", None)
        for y in range(y0, y1 + 1)
        for x in range(x0, x1 + 1)
    )


class TestTerrainRngIsolation:
    """Terrain generation must not draw from the module-level `random`.

    It used to, which meant a test pinning random.random() - an ordinary way
    to make a probabilistic branch deterministic - silently made every
    "if random.random() < density" obstacle check fire. Chunks generated
    inside such a patch came out packed with trees and often had no walkable
    route through them, which broke tests that had nothing to do with terrain.
    """

    def test_frozen_random_does_not_change_generated_terrain(self):
        from unittest.mock import patch

        import engine
        from engine import World

        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False

        normal = World(seed=9001)
        normal_ratio = _passable_ratio(normal, 5, 5, 20, 20)

        frozen = World(seed=9001)
        with patch("random.random", return_value=0.0):
            frozen_ratio = _passable_ratio(frozen, 5, 5, 20, 20)

        assert frozen_ratio == normal_ratio, (
            f"terrain changed under a pinned RNG ({frozen_ratio:.0%} passable vs "
            f"{normal_ratio:.0%}); generation is still reading module-level random"
        )

    def test_terrain_is_identical_regardless_of_visit_order(self):
        """A chunk's contents should depend on where it is, not on when it
        was first looked at."""
        import engine
        from engine import World

        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False

        first = World(seed=9002)
        first_signature = _terrain_signature(first, 45, 45, 55, 55)

        second = World(seed=9002)
        # Touch several other chunks before the region under test, so a
        # visit-order-dependent generator would diverge here.
        for x, y in [(5, 5), (120, 90), (200, 10), (30, 160)]:
            second.get_tile_at(x, y)
        second_signature = _terrain_signature(second, 45, 45, 55, 55)

        assert first_signature == second_signature


def test_generated_villages_have_a_town_square():
    """`town_square_center` is read in ~20 places across engine.py and
    simulation/systems/scheduling.py - children playing during leisure,
    festival crowds, guards rallying to an alarm, raiding parties mustering
    - but nothing ever wrote it, so all of that was dead in a generated
    world. It must be present, and shaped like the other interaction
    points (a list of coordinates, whose [0] readers index).
    """
    import engine
    from engine import World

    engine.ENABLE_OLLAMA_CONNECTION = False
    engine.ENABLE_LLM_CONNECTION = False
    world = World(seed=3002)

    villages = [v for v in world.villages if v.buildings]
    assert villages, "seed generated no villages to check"

    for village in villages:
        points = village.interaction_points
        assert "town_square_center" in points, "village generated without a town square"
        coords = points["town_square_center"]
        assert isinstance(coords, list) and coords, "town square must be a non-empty list of coords"
        x, y = coords[0]
        assert isinstance(x, int) and isinstance(y, int)

    # The shared accessor every consumer should be going through.
    anchor = world._get_village_anchor_coords(villages[0])
    assert anchor == tuple(villages[0].interaction_points["town_square_center"][0])
