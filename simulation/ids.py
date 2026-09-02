"""Ids for world objects: villages, buildings, claims, warrants, records.

These used to be `str(uuid.uuid4())`, which draws from os.urandom and ignores
random.seed. That made a seeded world unreproducible: with entity ids fixed, the
same seed already produced the same villagers, professions, ages and building
layout, but the same villagers turned up in a *different village* each run,
because several code paths order by these ids. Substituting a deterministic
stand-in for uuid4 and regenerating made two seeded worlds identical, which is
what pinned the cause.

So: a counter, prefixed. The prefix keeps ids from different worlds apart, and
matters most after loading a save - a loaded world carries ids made during its
own generation, and anything created afterwards takes a fresh prefix so it cannot
collide with them however far the counter has been wound back.

Ids stay opaque strings. Nothing reads their shape; they are dictionary keys and
save fields.

Not solved by this: the tick loop is still not reproducible run to run, even with
a fully pinned world. That is a separate thread and this does not claim to have
fixed it.
"""

from __future__ import annotations

import itertools
import uuid

_prefix = "w"
_counter = itertools.count(1)


def new_id() -> str:
    """A world-object id: unique within a world, stable for a given seed."""
    return f"{_prefix}{next(_counter):x}"


def reset_ids(seed: object = None) -> None:
    """Begin a new id series for a freshly generated world.

    Called from World.__init__ with the world seed, so the same seed produces
    the same ids. Called with nothing after loading a save, which takes a random
    prefix instead - a loaded world already holds ids from its own generation
    and nothing made afterwards may repeat one.
    """
    global _prefix, _counter
    if seed is None:
        _prefix = f"{uuid.uuid4().hex[:8]}-"
    else:
        _prefix = f"{abs(hash(str(seed))) & 0xFFFFFFFF:08x}-"
    _counter = itertools.count(1)


def current_prefix() -> str:
    """Exposed for tests that need to tell one id series from another."""
    return _prefix
