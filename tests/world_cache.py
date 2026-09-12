"""Hand out pre-simulated worlds without generating one every time.

Generating a world and pre-simulating it costs about 3.5 seconds, and the suite
does it a great many times - 77 pre-simulations are written in the test source,
and a dozen of those sit in setUp, which unittest runs once per test method
rather than once per class. That is minutes of the suite spent building the same
handful of worlds over and over.

Restoring one from a pickle costs about 0.4 seconds instead, a bit under nine
times cheaper. The world is pickled once, while it is still untouched, and every
caller after that gets `pickle.loads` of that blob.

Isolation is unchanged, which is the point: `pickle.loads` builds a brand new
object graph each time, so a test that moves villagers around, changes their
professions or ticks the clock is mutating its own copy exactly as it was
before. Nothing is shared between callers, so no test can see another's
leftovers. The cached blob is taken *before* the first caller gets its world, so
even the first test cannot contaminate the cache.

Use it anywhere a test currently writes:

    world = World(seed=5)
    world._pre_simulate_world()

as:

    world = fresh_world(seed=5)
"""

from __future__ import annotations

import pickle
import random
import entities.base as entity_ids
import simulation.ids as object_ids
import copy

from engine import World

_BLOBS: dict[tuple, tuple[bytes, tuple, int, str, object]] = {}

# Keys whose world would not pickle, so we stop trying. A test that builds its
# world inside `patch(...)` - test_ecosystem and test_knowledge_travel both do -
# gets a world holding MagicMocks, which pickle refuses. Those worlds should not
# be shared anyway: the mocks belong to the one test that installed them.
_UNCACHEABLE: set[tuple] = set()


def fresh_world(seed: int = 5, *, pre_simulate: bool = True, **world_kwargs):
    """A pre-simulated world, freshly restored and safe to mutate."""
    key = (seed, pre_simulate, tuple(sorted(world_kwargs.items())))

    cached = _BLOBS.get(key)
    if cached is not None:
        blob, rng_state, next_id, prefix, counter = cached
        # The global RNG state matters as much as the world does. Generating a
        # world seeds `random` and then draws from it a specific number of
        # times, so a caller that ticks the world afterwards is drawing from a
        # stream in a known position. Restoring the world without restoring that
        # position hands them a different stream, and anything decided by a coin
        # flip over the next few hundred ticks diverges.
        #
        # Found the hard way: caching the world alone broke three tests that had
        # passed for weeks - a blacksmith's fetch step and a healer's foraging,
        # both of which depend on hundreds of ticks of random choices going the
        # way they went when the test was written.
        #
        # Restored *after* the load, not before: unpickling a world runs its
        # __setstate__, which reserves entity ids and starts a fresh id series,
        # and anything that draws from `random` on the way through would
        # otherwise leave the caller at a different point in the stream than a
        # freshly generated world would.
        world = pickle.loads(blob)
        random.setstate(rng_state)
        # A cache hit substitutes for fresh generation, which resets entity ids.
        # Restoring only random's state made deterministic newborns inherit the
        # previous test world's allocator position. This is NOT save loading:
        # production __setstate__ still reserves ids monotonically.
        entity_ids._next_entity_id = next_id
        # Construction and hauling also allocate ids after generation. Save
        # loading intentionally randomizes that series; a generation cache
        # must instead resume the original series, just as an uncached call.
        object_ids._prefix = prefix
        object_ids._counter = copy.copy(counter)
        return world

    world = World(seed=seed, **world_kwargs)
    if pre_simulate:
        world._pre_simulate_world()

    # Cache before returning, so the copy kept for later callers is one that
    # nothing has had a chance to touch - and capture the RNG exactly where
    # generation left it, which is where the first caller starts from.
    if key not in _UNCACHEABLE:
        try:
            _BLOBS[key] = (
                pickle.dumps(world, protocol=pickle.HIGHEST_PROTOCOL),
                random.getstate(),
                entity_ids._next_entity_id,
                object_ids._prefix,
                copy.copy(object_ids._counter),
            )
        except (pickle.PicklingError, TypeError, AttributeError):
            # Not cacheable, but still a perfectly good world - hand it back and
            # generate one again next time rather than failing the caller.
            _UNCACHEABLE.add(key)
    return world


def cache_size() -> int:
    """How many distinct worlds are being held. Used by this module's tests."""
    return len(_BLOBS)


def clear_cache() -> None:
    _BLOBS.clear()
