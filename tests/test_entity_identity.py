"""An entity's id belongs to that entity and to no one else.

Entities took `id(self)` as their id. That is a memory address, and CPython
hands the same address straight back out once an object is freed. Creating 6000
NPCs while letting them fall out of scope produced 119 distinct ids and 5881
collisions.

In a running game the dead are cleared out every hundred ticks and children are
born, so a newborn could be issued the id of a villager who died minutes
earlier. Everything in this game that remembers a person remembers an id:
relationship scores, family ties, quest givers, warrants, employment records,
witness lists. All of it would have quietly transferred to whoever inherited the
address.

A counter instead, restarted per world so a seed builds the same village, and
pushed past whatever a loaded save already contains.

Reproducibility was the thread that led here, and it took two fixes. Entity ids
were the first: with them the same seed produced the same villagers, professions,
ages and building layout. The same villagers still turned up in a different
village each run, because villages, regions, buildings and claims took
uuid.uuid4() ids - which draw from os.urandom and ignore random.seed - and
several code paths order by them. Those now come from simulation/ids.py, and a
seeded world is reproducible.

The tick loop is still not reproducible run to run even with a fully pinned
world. That is a separate thread and nothing here claims to have fixed it.
"""

import gc
import os
import random
import unittest

from engine import World
from entities.base import (
    NPC,
    next_entity_id,
    reserve_entity_ids_above,
    reset_entity_ids,
)
from save_manager import load_game, save_game
from simulation.ids import new_id as new_world_id


class TestIdsAreNotAddresses(unittest.TestCase):
    def test_an_id_is_not_the_objects_memory_address(self):
        npc = NPC(0, 0, name="Someone")
        self.assertNotEqual(
            npc.id, id(npc),
            "the id is the memory address again, which CPython reuses",
        )

    def test_ids_survive_their_owners_being_collected(self):
        """The actual bug, reproduced. Nothing here holds a reference to the
        NPCs, so their addresses are free to be handed out again."""
        # Fifty rounds is a thousand entities. The bug this pins produced 119
        # distinct ids out of 6000 - a collision rate near 98% - so a thousand is
        # overwhelming evidence, and the original two hundred rounds cost the
        # suite two minutes to be more overwhelming still.
        seen = set()
        collisions = 0
        for round_number in range(50):
            batch = [NPC(0, 0, name=f"n{round_number}_{i}") for i in range(20)]
            for npc in batch:
                if npc.id in seen:
                    collisions += 1
                seen.add(npc.id)
            del batch, npc
            gc.collect()

        self.assertEqual(collisions, 0, f"{collisions} entities shared an id")
        self.assertEqual(len(seen), 50 * 20)

    def test_the_player_gets_one_too(self):
        world = World(seed=17)
        self.assertNotEqual(world.player.id, id(world.player))
        villager_ids = {n.id for n in world.village_npcs}
        self.assertNotIn(
            world.player.id, villager_ids,
            "the player shares an id with one of the villagers",
        )


class TestTheCounter(unittest.TestCase):
    def test_resetting_starts_again(self):
        reset_entity_ids()
        first = next_entity_id()
        reset_entity_ids()
        self.assertEqual(next_entity_id(), first)

    def test_reserving_clears_a_floor(self):
        reset_entity_ids()
        reserve_entity_ids_above(5000)
        self.assertGreater(next_entity_id(), 5000)

    def test_reserving_below_the_current_point_is_ignored(self):
        reset_entity_ids()
        reserve_entity_ids_above(500)
        high = next_entity_id()
        reserve_entity_ids_above(1)
        self.assertGreater(
            next_entity_id(), high,
            "a low reservation wound the counter backwards onto ids in use",
        )

    def test_nonsense_reservations_do_not_raise(self):
        reset_entity_ids()
        reserve_entity_ids_above(None)
        reserve_entity_ids_above("later")
        self.assertIsInstance(next_entity_id(), int)

    def test_a_new_world_numbers_from_the_start(self):
        first = World(seed=21)
        second = World(seed=21)
        self.assertEqual(
            [n.id for n in first.village_npcs][:5],
            [n.id for n in second.village_npcs][:5],
            "the same seed numbered its villagers differently",
        )


class TestLoadingASaveDoesNotReissueIds(unittest.TestCase):
    """The case the reservation exists for: a save written after this change
    holds counter ids, and the counter restarts with the process."""

    def setUp(self):
        self.world = World(seed=31)
        self.save_name = "test_identity_save.sav"

    def tearDown(self):
        path = os.path.join("saves", self.save_name)
        if os.path.exists(path):
            os.remove(path)

    def test_someone_born_after_loading_gets_a_fresh_id(self):
        self.assertTrue(save_game(self.world, self.save_name))
        reset_entity_ids()  # as a new process would
        loaded = load_game(self.save_name)
        self.assertIsNotNone(loaded)

        existing = {n.id for n in loaded.village_npcs} | {loaded.player.id}
        self.assertTrue(existing, "the loaded world had no entities")

        newborn = NPC(0, 0, name="Newborn")
        self.assertNotIn(
            newborn.id, existing,
            "an entity created after loading was issued an id already in use",
        )

    def test_the_loaded_entities_keep_their_own_ids(self):
        before = sorted(n.id for n in self.world.village_npcs)
        self.assertTrue(save_game(self.world, self.save_name))
        loaded = load_game(self.save_name)
        self.assertIsNotNone(loaded)
        self.assertEqual(sorted(n.id for n in loaded.village_npcs), before)


class TestSeededWorldsMatchWhereTheyCan(unittest.TestCase):
    """What the id fix bought, stated honestly - see the note at the top of this
    file for what is still not reproducible and why."""

    def test_the_same_seed_builds_the_same_population(self):
        def population(seed):
            random.seed(seed)
            world = World(player_first_name="Twin")
            return sorted(
                (n.id, n.name, n.age, n.economic.profession) for n in world.village_npcs
            )

        self.assertEqual(population(99), population(99))

    def test_the_same_seed_builds_the_same_buildings(self):
        def layout(seed):
            random.seed(seed)
            world = World(player_first_name="Twin")
            return sorted(
                (b.building_type, b.x, b.y) for b in world.buildings_by_id.values()
            )

        self.assertEqual(layout(99), layout(99))


class TestASeededWorldIsReproducible(unittest.TestCase):
    """What the two id fixes together bought.

    Before them, two worlds from one seed differed. The population was already
    identical once entity ids came from a counter; the villages themselves only
    lined up once their ids stopped coming from uuid4.
    """

    @staticmethod
    def _fingerprint(seed):
        world = World(seed=seed)
        return (
            sorted((n.id, n.name, n.age, n.x, n.y) for n in world.village_npcs),
            sorted((b.building_type, b.x, b.y) for b in world.buildings_by_id.values()),
        )

    def test_one_seed_builds_one_world(self):
        self.assertEqual(self._fingerprint(99), self._fingerprint(99))

    def test_different_seeds_build_different_worlds(self):
        """The other half - reproducible must not mean identical for everyone."""
        self.assertNotEqual(self._fingerprint(99), self._fingerprint(100))

    def test_world_object_ids_are_stable_for_a_seed(self):
        def village_ids(seed):
            world = World(seed=seed)
            return sorted(
                chunk.village.id
                for row in world.chunks for chunk in row
                if getattr(chunk, "village", None) is not None
            )

        self.assertEqual(village_ids(99), village_ids(99))

    def test_a_world_loaded_from_a_save_does_not_reissue_world_object_ids(self):
        import os as _os

        world = World(seed=41)
        save_name = "test_world_ids_save.sav"
        try:
            self.assertTrue(save_game(world, save_name))
            loaded = load_game(save_name)
            self.assertIsNotNone(loaded)

            existing = {
                chunk.village.id
                for row in loaded.chunks for chunk in row
                if getattr(chunk, "village", None) is not None
            }
            existing |= set(loaded.buildings_by_id)
            self.assertTrue(existing, "the loaded world had no world objects")

            fresh = {new_world_id() for _ in range(50)}
            self.assertFalse(
                fresh & existing,
                "an id minted after loading was already in use in the save",
            )
        finally:
            path = _os.path.join("saves", save_name)
            if _os.path.exists(path):
                _os.remove(path)


if __name__ == "__main__":
    unittest.main()
