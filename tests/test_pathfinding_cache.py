import time
import unittest

import engine
from engine import World


class TestPathfindingTileCostCache(unittest.TestCase):
    """Bug-hunt audit item 4: calculate_path rebuilt its full local cost
    grid from scratch on every call (measured ~0.5s for a 300-tile path in
    the sandbox), with no caching. _get_pathfinding_tile_cost adds a
    per-tick cache; these tests confirm calculate_path's actual RESULTS are
    unaffected (this is a performance fix only) and that the cache behaves
    as designed (populated, reused, invalidated on tick change)."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=901)

    def test_cache_starts_empty_and_populates_on_use(self):
        self.assertEqual(self.world._pathfinding_tile_cost_cache, {})
        self.world._get_pathfinding_tile_cost(10, 10)
        self.assertIn((10, 10), self.world._pathfinding_tile_cost_cache)

    def test_repeated_lookup_of_same_tile_is_cached_and_consistent(self):
        first = self.world._get_pathfinding_tile_cost(20, 20)
        second = self.world._get_pathfinding_tile_cost(20, 20)
        self.assertEqual(first, second)

    def test_cache_is_invalidated_when_game_time_advances(self):
        self.world._get_pathfinding_tile_cost(5, 5)
        self.assertIn((5, 5), self.world._pathfinding_tile_cost_cache)

        self.world.game_time += 1
        self.world._get_pathfinding_tile_cost(6, 6)

        # The old entry for (5, 5) should have been wiped alongside the
        # rest of the previous tick's cache, not merely left stale.
        self.assertNotIn((5, 5), self.world._pathfinding_tile_cost_cache)
        self.assertIn((6, 6), self.world._pathfinding_tile_cost_cache)

    def test_cache_survives_pickle_roundtrip_as_empty_dict(self):
        """__setstate__ resets the cache rather than restoring stale
        pickled entries - it's a pure performance cache, never meant to be
        persisted, so this just confirms loading an old save doesn't crash
        or restore garbage."""
        import pickle

        self.world._get_pathfinding_tile_cost(1, 1)
        data = pickle.dumps(self.world)
        restored = pickle.loads(data)
        self.assertEqual(restored._pathfinding_tile_cost_cache, {})

    def _pick_far_apart_walkable_points(self):
        start = (self.world.player.x, self.world.player.y)
        for radius in (150, 100, 60, 30):
            end = (start[0] + radius, start[1] + radius)
            end_tile = self.world.get_tile_at(*end)
            if end_tile and end_tile.passable:
                return start, end
        # Fallback: just use the player's own tile twice (trivial path).
        return start, start

    def test_calculate_path_results_are_identical_to_uncached_reference(self):
        """Rebuild the exact pre-fix inline cost-grid logic as a local
        reference implementation and confirm calculate_path (now routed
        through the cache) returns byte-for-byte identical paths for
        several start/end pairs."""
        import numpy as np
        import tcod

        def reference_calculate_path(world, start_x, start_y, end_x, end_y):
            start_tile = world.get_tile_at(start_x, start_y)
            if not (start_tile and start_tile.passable):
                return []

            padding = 15
            min_x = max(0, min(start_x, end_x) - padding)
            max_x = min(engine.WORLD_WIDTH - 1, max(start_x, end_x) + padding)
            min_y = max(0, min(start_y, end_y) - padding)
            max_y = min(engine.WORLD_HEIGHT - 1, max(start_y, end_y) + padding)

            local_width = max_x - min_x + 1
            local_height = max_y - min_y + 1
            cost = np.ones((local_height, local_width), dtype=np.float32)

            for y_local in range(local_height):
                for x_local in range(local_width):
                    x_world, y_world = min_x + x_local, min_y + y_local
                    tile = world.get_tile_at(x_world, y_world)
                    if not tile or not tile.passable:
                        cost[y_local, x_local] = 0
                    else:
                        base_cost = 1.0
                        if hasattr(tile, "properties") and tile.properties:
                            base_cost = float(tile.properties.get("movement_cost", 1.0))
                        if tile.is_hazard:
                            hazard_cost_value = 50
                            if tile.hazard_type == "fire_trap_active":
                                hazard_cost_value = 100
                            elif tile.hazard_type == "water_deep":
                                hazard_cost_value = 75
                            cost[y_local, x_local] = base_cost + hazard_cost_value
                        else:
                            cost[y_local, x_local] = base_cost

            astar = tcod.path.AStar(cost=cost, diagonal=1.41)
            start_x_local, start_y_local = start_x - min_x, start_y - min_y
            end_x_local, end_y_local = end_x - min_x, end_y - min_y
            try:
                path_indices_local = astar.get_path(start_x_local, start_y_local, end_x_local, end_y_local)
                return [(min_x + int(p[1]), min_y + int(p[0])) for p in path_indices_local]
            except IndexError:
                return []

        start, end = self._pick_far_apart_walkable_points()
        pairs = [
            (start[0], start[1], end[0], end[1]),
            (start[0], start[1], start[0] + 10, start[1]),
            (start[0], start[1], start[0], start[1] + 10),
        ]

        for sx, sy, ex, ey in pairs:
            with self.subTest(start=(sx, sy), end=(ex, ey)):
                expected = reference_calculate_path(self.world, sx, sy, ex, ey)
                actual = self.world.calculate_path(sx, sy, ex, ey)
                self.assertEqual(actual, expected)

    def test_second_call_over_overlapping_region_is_not_slower_due_to_cache(self):
        """Not a strict perf assertion (sandbox timing can be noisy), just
        confirms the cache actually gets populated by a real calculate_path
        call - the meaningful timing comparison is reported separately."""
        start, end = self._pick_far_apart_walkable_points()
        self.world.calculate_path(start[0], start[1], end[0], end[1])
        self.assertGreater(len(self.world._pathfinding_tile_cost_cache), 1)


if __name__ == "__main__":
    unittest.main()
