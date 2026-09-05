"""A worker can reach the station their trade depends on.

Three separate faults, each of which silently stopped a profession. None threw,
none logged, and none were visible from any test that only asked whether a
building existed.

1. Furniture was placed on work zones. The interior decorators filled rooms
   without consulting work_zone_tiles, and a work zone is the tile a worker
   walks to and stands on. Measured on a generated world: 20 of 102 zones had
   no reachable tile left at all - every bakery oven, every forge, every anvil,
   every clinic bed and every alchemy station in the world was under a table, a
   workbench or a chest.

2. Doors were bricked up by later neighbours. A door is cut while its building
   is drawn; the buildings drawn after it can be placed flush against that
   doorway. Every bakery in every seed opened directly into the butcher shop's
   outer wall, so no baker could enter their own bakery.

3. Zone coordinates outlived their footprint. Zones are written as fixed offsets
   from the origin while the size comes from a blueprint that can change. The
   clinic's alchemy station was written as +5 when the clinic was seven tiles
   wide; at six tiles wide, +5 is the east wall, and every alchemy station in
   the world was inside it.

The shared shape is worth naming: none of these could be caught by asking
whether a blacksmith exists. They need asking whether the blacksmith can get to
the anvil.
"""

import unittest

from data.decorations import DECORATION_ITEM_DEFINITIONS
from engine import World
from tests.world_cache import fresh_world

SEEDS = (5, 11)


def _worlds():
    worlds = {}
    for seed in SEEDS:
        world = fresh_world(seed=seed)
        worlds[seed] = world
    return worlds


class TestWorkZonesAreStandable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worlds = _worlds()

    def test_no_zone_is_sealed(self):
        """A zone whose every tile is impassable is a trade that has stopped."""
        for seed, world in self.worlds.items():
            for building in world.buildings_by_id.values():
                for tag, coords in (building.work_zone_tiles or {}).items():
                    if not coords:
                        continue
                    if not all(building.contains_global_coords(x, y) for x, y in coords):
                        continue  # farm fields and other deliberately outdoor zones
                    standable = [
                        (x, y) for x, y in coords
                        if (tile := world.get_tile_at(x, y)) is not None and tile.passable
                    ]
                    with self.subTest(seed=seed, building=building.building_type, zone=tag):
                        self.assertTrue(
                            standable,
                            f"{building.building_type}.{tag} at {coords[0]} has no tile a "
                            f"worker can stand on",
                        )

    def test_furniture_is_never_placed_on_a_zone(self):
        """The guard, stated as the property it protects."""
        for seed, world in self.worlds.items():
            for building in world.buildings_by_id.values():
                occupied = world._building_work_zone_coords(building)
                for x, y in occupied:
                    if not building.contains_global_coords(x, y):
                        continue
                    tile = world.get_tile_at(x, y)
                    if tile is None or tile.passable:
                        continue
                    with self.subTest(seed=seed, building=building.building_type):
                        self.assertIn(
                            "Wall", tile.name,
                            f"{building.building_type} has {tile.name!r} sitting on a work "
                            f"zone at {(x, y)}",
                        )

    def test_the_clinics_alchemy_station_is_not_in_the_wall(self):
        """Named directly: it is the one that came from a resize, and a resize
        can happen again."""
        for seed, world in self.worlds.items():
            for building in world.buildings_by_id.values():
                if building.building_type != "clinic":
                    continue
                coords = building.work_zone_tiles.get("alchemy_station")
                self.assertTrue(coords, f"seed {seed}: clinic has no alchemy station")
                x, y = coords[0]
                offset_x = x - building.global_origin_x
                with self.subTest(seed=seed):
                    self.assertLess(
                        offset_x, building.width - 1,
                        f"the alchemy station is at +{offset_x} in a building "
                        f"{building.width} wide, which is the wall",
                    )


class TestEveryBuildingCanBeEntered(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worlds = _worlds()

    @staticmethod
    def _usable_doors(world, building):
        origin_x, origin_y = building.global_origin_x, building.global_origin_y
        usable = []
        for dx in range(building.width):
            for dy in range(building.height):
                if not (dx in (0, building.width - 1) or dy in (0, building.height - 1)):
                    continue
                tile = world.get_tile_at(origin_x + dx, origin_y + dy)
                if tile is None or "Door" not in tile.name:
                    continue
                door = (origin_x + dx, origin_y + dy)
                for nx, ny in (
                    (door[0] + 1, door[1]), (door[0] - 1, door[1]),
                    (door[0], door[1] + 1), (door[0], door[1] - 1),
                ):
                    if building.contains_global_coords(nx, ny):
                        continue
                    outside = world.get_tile_at(nx, ny)
                    if outside is not None and outside.passable:
                        usable.append(door)
                        break
        return usable

    def test_no_building_is_bricked_in(self):
        for seed, world in self.worlds.items():
            for building in world.buildings_by_id.values():
                with self.subTest(seed=seed, building=building.building_type):
                    self.assertTrue(
                        self._usable_doors(world, building),
                        f"{building.building_type} at "
                        f"{(building.global_origin_x, building.global_origin_y)} has no door "
                        f"opening onto anything a villager can walk on",
                    )

    def test_a_worker_can_walk_from_the_door_to_the_station(self):
        """The whole point, end to end: through the doorway and up to the tile
        the sub-task system will send them to."""
        for seed, world in self.worlds.items():
            for building in world.buildings_by_id.values():
                doors = self._usable_doors(world, building)
                if not doors:
                    continue
                door_x, door_y = doors[0]
                start = None
                for nx, ny in (
                    (door_x + 1, door_y), (door_x - 1, door_y),
                    (door_x, door_y + 1), (door_x, door_y - 1),
                ):
                    if building.contains_global_coords(nx, ny):
                        continue
                    tile = world.get_tile_at(nx, ny)
                    if tile is not None and tile.passable:
                        start = (nx, ny)
                        break
                if start is None:
                    continue
                for tag, coords in (building.work_zone_tiles or {}).items():
                    if not coords:
                        continue
                    if not all(building.contains_global_coords(x, y) for x, y in coords):
                        continue
                    with self.subTest(seed=seed, building=building.building_type, zone=tag):
                        self.assertTrue(
                            any(world.calculate_path(start[0], start[1], x, y) for x, y in coords),
                            f"nothing can walk from the {building.building_type} doorstep to "
                            f"its {tag}",
                        )


class TestNoRoomIsWalledOff(unittest.TestCase):
    """Every tile of floor can be reached from the front door.

    Furniture is impassable, and the decorators place it without checking what
    it separates. This is the property that keeps that honest: a bed, a bench or
    a hearth may stand anywhere it likes as long as nothing ends up behind it.

    It also guards the hearth. A fireplace is a real heat source - it is what the
    temperature system, NPC warmth-seeking and the sensory description all read -
    and giving houses one meant putting an impassable tile against an interior
    wall in every dining room in the world.
    """

    @classmethod
    def setUpClass(cls):
        cls.worlds = _worlds()

    @staticmethod
    def _interior(world, building):
        floor = set()
        for dy in range(1, building.height - 1):
            for dx in range(1, building.width - 1):
                spot = (building.global_origin_x + dx, building.global_origin_y + dy)
                tile = world.get_tile_at(*spot)
                if tile is not None and tile.passable:
                    floor.add(spot)
        return floor

    @staticmethod
    def _doorside_seeds(world, building, floor):
        seeds = []
        for dx in range(building.width):
            for dy in range(building.height):
                if not (dx in (0, building.width - 1) or dy in (0, building.height - 1)):
                    continue
                tile = world.get_tile_at(
                    building.global_origin_x + dx, building.global_origin_y + dy
                )
                if tile is None or "Door" not in tile.name:
                    continue
                door = (building.global_origin_x + dx, building.global_origin_y + dy)
                for neighbour in (
                    (door[0] + 1, door[1]), (door[0] - 1, door[1]),
                    (door[0], door[1] + 1), (door[0], door[1] - 1),
                ):
                    if neighbour in floor:
                        seeds.append(neighbour)
        return seeds

    def test_no_floor_tile_is_cut_off_from_the_door(self):
        for seed, world in self.worlds.items():
            for building in world.buildings_by_id.values():
                floor = self._interior(world, building)
                if not floor:
                    continue
                seeds = self._doorside_seeds(world, building, floor)
                if not seeds:
                    continue
                reached = set(seeds)
                queue = list(seeds)
                while queue:
                    x, y = queue.pop()
                    for neighbour in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                        if neighbour in floor and neighbour not in reached:
                            reached.add(neighbour)
                            queue.append(neighbour)
                with self.subTest(seed=seed, building=building.building_type):
                    self.assertEqual(
                        floor - reached, set(),
                        f"{building.building_type} has floor no one can walk to from "
                        f"its own door",
                    )


class TestHomesHaveAHearth(unittest.TestCase):
    """Warmth had nothing to read.

    heat_source is consumed in four places - the temperature term in survival,
    _find_nearest_heat_source, the sensory description and the tile inspection
    payload - and a generated world contained zero tiles carrying it. The
    architecture layer does declare a fireplace role for dining rooms and tavern
    floors; decoration turned it into an unlit fire pit, which is scenery.
    """

    @classmethod
    def setUpClass(cls):
        cls.world = fresh_world(seed=5)

    def _heat_sources(self):
        found = []
        for row in self.world.chunks:
            for chunk in row:
                if not chunk.is_terrain_generated or not chunk.tiles:
                    continue
                for tiles_row in chunk.tiles:
                    for tile in tiles_row:
                        if tile is None:
                            continue
                        properties = getattr(tile, "properties", None) or {}
                        if properties.get("heat_source"):
                            found.append(tile.name)
        return found

    def test_the_world_contains_heat_sources_at_all(self):
        self.assertTrue(
            self._heat_sources(),
            "no tile anywhere in the world carries heat_source, so every system "
            "that reads it is dead code",
        )

    def test_a_hearth_actually_lights_the_room_at_night(self):
        """rendering.lighting knows exactly two light-emitting tiles - the
        fireplace and the lit fire pit - and no generated world contained either,
        so the light map it builds had nothing to build from and every interior
        at midnight was the same flat gloom."""
        import numpy as np

        from rendering import lighting

        self.assertTrue(
            lighting.LIGHT_EMITTING_TILE_NAMES,
            "the renderer knows of no light-emitting tiles at all",
        )

        hearth = None
        for chunk_y, row in enumerate(self.world.chunks):
            for chunk_x, chunk in enumerate(row):
                if not chunk.is_terrain_generated or not chunk.tiles:
                    continue
                for tile_y, tiles_row in enumerate(chunk.tiles):
                    for tile_x, tile in enumerate(tiles_row):
                        if tile is not None and tile.name in lighting.LIGHT_EMITTING_TILE_NAMES:
                            hearth = (chunk_x * 40 + tile_x, chunk_y * 40 + tile_y)
                            break
                    if hearth:
                        break
                if hearth:
                    break
            if hearth:
                break
        self.assertIsNotNone(hearth, "no light source anywhere in the world")

        bounds = (hearth[0] - 12, hearth[1] - 8, hearth[0] + 12, hearth[1] + 8)
        sources = lighting.collect_tile_light_sources(
            self.world, bounds, get_tile_at=self.world.get_tile_at
        )
        self.assertTrue(sources, "a hearth in view contributed no light source")

        ambient = lighting.ambient_for_light_level("NIGHT")
        strength, warm, _tint = lighting.build_light_map(
            sources,
            np.arange(bounds[0], bounds[2] + 1),
            np.arange(bounds[1], bounds[3] + 1),
            ambient,
        )
        self.assertGreater(
            float(strength.max()), 0.0,
            "the light map around a lit hearth is as dark as the street",
        )
        self.assertGreater(float(warm.max()), 0.0, "firelight carries no warm tint")

    def _a_hearth_and_a_spot_near_it(self):
        """A hearth, and a standable tile a few paces away in the same room."""
        for building in self.world.buildings_by_id.values():
            hearth = None
            for dy in range(building.height):
                for dx in range(building.width):
                    spot = (building.global_origin_x + dx, building.global_origin_y + dy)
                    tile = self.world.get_tile_at(*spot)
                    properties = getattr(tile, "properties", None) or {}
                    if properties.get("heat_source"):
                        hearth = spot
                        break
                if hearth:
                    break
            if hearth is None:
                continue
            for dy in range(1, building.height - 1):
                for dx in range(1, building.width - 1):
                    spot = (building.global_origin_x + dx, building.global_origin_y + dy)
                    tile = self.world.get_tile_at(*spot)
                    if tile is None or not tile.passable:
                        continue
                    if max(abs(spot[0] - hearth[0]), abs(spot[1] - hearth[1])) < 2:
                        continue
                    return hearth, spot
        return None, None

    def test_a_freezing_villager_walks_to_the_fire(self):
        """The behaviour the hearth unlocks.

        A freezing NPC asks for the nearest heat source and walks to it. That
        lookup returned None in every world, every time, so the branch fell
        through to "go home" - and home was exactly as cold, because it had no
        hearth either.
        """
        from simulation.systems.survival import update_npc_environmental_tasks

        hearth, standing = self._a_hearth_and_a_spot_near_it()
        self.assertIsNotNone(hearth, "no hearth in any building to walk to")

        npc = next(n for n in self.world.village_npcs if not n.physical.is_dead)
        npc.is_sleeping = False
        self.world._update_entity_position(npc, *standing)
        npc.schedule.current_task = None
        npc.schedule.current_path = []
        npc.schedule.current_destination_coords = None
        if "Freezing" not in npc.physical.status_effects:
            npc.physical.status_effects.append("Freezing")

        self.assertIsNotNone(
            self.world._find_nearest_heat_source(npc),
            "a villager standing in the same room as a lit hearth cannot find it",
        )

        update_npc_environmental_tasks(self.world, npc)

        self.assertEqual(npc.schedule.current_task, "seeking_warmth")
        self.assertIsNotNone(
            npc.schedule.current_destination_coords,
            "the villager decided to seek warmth and was given nowhere to go",
        )
        destination = npc.schedule.current_destination_coords
        self.assertLessEqual(
            max(abs(destination[0] - hearth[0]), abs(destination[1] - hearth[1])), 1,
            f"they set off for {destination}, which is not beside the fire at {hearth}",
        )

    def test_a_villager_can_find_somewhere_warm(self):
        living = [n for n in self.world.village_npcs if not n.physical.is_dead]
        self.assertTrue(living)
        found = sum(
            1 for npc in living[:25]
            if self.world._find_nearest_heat_source(npc) is not None
        )
        self.assertGreater(
            found, 0,
            "not one villager can find a heat source anywhere near them",
        )


class TestAWorkplaceLooksLikeOne(unittest.TestCase):
    """The fixtures a building is named for are drawn.

    Fifteen of the thirty-one decoration types never appeared anywhere in a
    generated world. Some are event-driven - corpses, lit fires, rubble - but
    the forge and the anvil were simply never placed, so a blacksmith's shop was
    a room with a table in it.
    """

    @classmethod
    def setUpClass(cls):
        cls.world = fresh_world(seed=5)

    def _contents(self, building):
        names = set()
        for dy in range(building.height):
            for dx in range(building.width):
                tile = self.world.get_tile_at(
                    building.global_origin_x + dx, building.global_origin_y + dy
                )
                if tile is not None:
                    names.add(tile.name)
        return names

    def test_the_blacksmith_has_a_forge_and_an_anvil(self):
        smithy = next(
            (b for b in self.world.buildings_by_id.values()
             if b.building_type == "blacksmith_shop"),
            None,
        )
        self.assertIsNotNone(smithy, "no blacksmith in this world")
        contents = self._contents(smithy)
        self.assertIn(DECORATION_ITEM_DEFINITIONS["forge"]["name"], contents)
        self.assertIn(DECORATION_ITEM_DEFINITIONS["anvil"]["name"], contents)

    def test_fixtures_did_not_replace_the_zone_they_belong_to(self):
        """They go beside the zone, never on it - otherwise the fix for the
        missing forge would re-create the bug it was found next to."""
        smithy = next(
            b for b in self.world.buildings_by_id.values()
            if b.building_type == "blacksmith_shop"
        )
        for tag in ("forge", "anvil"):
            x, y = smithy.work_zone_tiles[tag][0]
            tile = self.world.get_tile_at(x, y)
            with self.subTest(zone=tag):
                self.assertTrue(
                    tile.passable,
                    f"the {tag} fixture was placed on the {tag} work zone",
                )


if __name__ == "__main__":
    unittest.main()
