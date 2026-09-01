"""Shared post-unpickle migration helpers.

Background (see the integrated-simulation bug-hunt audit): pickle restores
an object by replaying its OLD __dict__ directly - it never calls
__init__. That means any attribute/field added to a class AFTER a save
file was written is simply absent from the restored instance's __dict__,
and the very next line of code that touches it raises AttributeError.

World.__setstate__ (engine.py) already solves this for the top-level World
object with a hand-maintained `getattr(self, "x", default)` list. This
module gives every nested per-entity dataclass (Schedule, SocialState,
EconomicState, CombatStats, etc.) the same protection generically, driven
from each dataclass's own declared field defaults, so it doesn't need
hand-updating every time a new field is added - unlike World's list, which
does. NPC itself isn't a dataclass (its ~100+ attributes are plain
`self.x = ...` assignments in __init__, not dataclass fields), so it uses a
different, complementary strategy - see backfill_missing_plain_attributes
below and its use in NPC.__setstate__.
"""
from __future__ import annotations

import copy
from dataclasses import fields, MISSING


def backfill_missing_dataclass_fields(instance) -> None:
    """Fill in any dataclass field missing from instance.__dict__ using
    that field's own declared default/default_factory. Fields with neither
    (required, no-default fields) are left alone - there's no sensible
    value to invent for those, and leaving them missing surfaces a clear
    AttributeError immediately rather than silently guessing wrong."""
    for f in fields(instance):
        if f.name in instance.__dict__:
            continue
        if f.default_factory is not MISSING:  # type: ignore[misc]
            instance.__dict__[f.name] = f.default_factory()
        elif f.default is not MISSING:
            instance.__dict__[f.name] = f.default
        # else: required field with no default - nothing safe to backfill.


def dataclass_setstate(instance, state) -> None:
    """Standard __setstate__ body for a plain (non-frozen) dataclass:
    restore whatever pickle saved, then backfill anything the class has
    grown since the save was made. Use as:

        def __setstate__(self, state):
            dataclass_setstate(self, state)
    """
    instance.__dict__.update(state)
    backfill_missing_dataclass_fields(instance)


def backfill_missing_plain_attributes(instance, template, *, skip: frozenset[str] = frozenset()) -> None:
    """For a plain (non-dataclass) class like NPC, whose __init__ sets a
    large number of literal instance attributes rather than declared
    dataclass fields: copy any attribute present on `template` (a freshly
    constructed "defaults" instance of the same class) but missing from
    `instance`, so an object unpickled from before that attribute existed
    gets the same default __init__ would have given it.

    `skip` should list identity/random-per-instance attributes (id, x, y,
    name, age, gender, sprite char/color, etc.) that have existed since the
    class's earliest version and must NEVER be copied from a template even
    if somehow absent - those are never legitimately "missing" from a real
    save, and copying template values for them would be a correctness bug,
    not a safe default. Mutable values (list/dict/set) are deep-copied so
    the restored instance doesn't end up sharing containers with the
    template (or with any other instance backfilled from it).
    """
    for name, value in template.__dict__.items():
        if name in skip or name in instance.__dict__:
            continue
        instance.__dict__[name] = copy.deepcopy(value) if isinstance(value, (list, dict, set)) else value
