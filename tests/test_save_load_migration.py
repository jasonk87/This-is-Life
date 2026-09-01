import copy
import pickle
import unittest

import engine
from engine import NPC, World
from entities.social import GrudgeRecord
from simulation.careers import CareerHistoryEntry


class TestNestedDataclassBackfillOnUnpickle(unittest.TestCase):
    """Regression coverage for the save/load migration bug found in the
    integrated-simulation bug-hunt audit: pickle bypasses __init__ entirely
    on load, replaying only the OLD __dict__ - so any field added to a
    dataclass (or plain attribute added to NPC) after a save was written is
    simply absent from the restored instance, and the next real production
    code that touches it throws AttributeError. World.__setstate__ already
    had a migration pattern for World-level fields; these tests confirm the
    same protection now exists for the nested per-entity components, using
    the SAME real production methods that were confirmed to crash before
    this fix (record_trait_pressure, _accrue_crime_bounty, career.set_role)."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=901)

    def _make_npc(self, personality="chaotic drifter"):
        return NPC(0, 0, name="Legacy", dialogue=["Hi"], personality=personality, player_id=self.world.player.id)

    def _pickle_roundtrip_with_deleted_attrs(self, npc, deletions: list[tuple[str, str]]):
        """deletions is a list of (component_attr_path, field_name) pairs,
        e.g. ("social", "trait_pressure") - simulates an old save made
        before that field existed by deleting it from __dict__ post-hoc,
        exactly like a genuinely older pickle would look."""
        for path, field_name in deletions:
            obj = npc
            for part in path.split("."):
                obj = getattr(obj, part)
            del obj.__dict__[field_name]
        return pickle.loads(pickle.dumps(npc))

    def test_record_trait_pressure_no_longer_crashes_on_a_legacy_npc(self):
        """This is the exact crash confirmed during the audit."""
        npc = self._make_npc()
        restored = self._pickle_roundtrip_with_deleted_attrs(npc, [
            ("social", "trait_pressure"),
            ("social", "activated_traits"),
        ])

        activated = restored.record_trait_pressure("lawful")

        self.assertFalse(activated)
        self.assertEqual(restored.social.trait_pressure, {"lawful": 1})

    def test_has_trait_no_longer_crashes_on_a_legacy_npc_with_no_matching_base_string(self):
        """has_trait's substring check on the base personality can mask the
        crash if the word happens to match - use a neutral personality so
        it actually falls through to reading activated_traits."""
        npc = self._make_npc(personality="villager")
        restored = self._pickle_roundtrip_with_deleted_attrs(npc, [
            ("social", "activated_traits"),
        ])

        self.assertFalse(restored.has_trait("chaotic"))

    def test_accrue_crime_bounty_no_longer_crashes_on_a_legacy_npc(self):
        npc = self._make_npc()
        restored = self._pickle_roundtrip_with_deleted_attrs(npc, [
            ("schedule", "crime_kinds_since_last_jailing"),
            ("schedule", "jail_intake_crime_kinds"),
            ("schedule", "jail_intake_bounty"),
        ])

        self.world._accrue_crime_bounty(restored, "theft")

        self.assertEqual(restored.economic.bounty, 30)
        self.assertEqual(restored.schedule.crime_kinds_since_last_jailing, ["theft"])

    def test_career_set_role_no_longer_crashes_on_a_legacy_npc(self):
        npc = self._make_npc()
        restored = self._pickle_roundtrip_with_deleted_attrs(npc, [("career", "history")])

        restored.career.set_role("Farmer", reason="test")

        self.assertEqual(len(restored.career.history), 1)
        self.assertEqual(restored.career.history[0].role, "Farmer")

    def test_knowledge_active_quests_backfilled_on_a_legacy_npc(self):
        npc = self._make_npc()
        restored = self._pickle_roundtrip_with_deleted_attrs(npc, [("knowledge", "active_quests")])

        restored.knowledge.active_quests["q1"] = {"type": "fetch"}

        self.assertEqual(restored.knowledge.active_quests, {"q1": {"type": "fetch"}})

    def test_plain_npc_level_attributes_are_backfilled(self):
        """Attributes that live directly on NPC (not inside a component
        dataclass) - cold_exposure, actor_work_profile, etc. - added
        incrementally over the project's history, same risk class."""
        npc = self._make_npc()
        del npc.__dict__["cold_exposure"]
        del npc.__dict__["actor_work_profile"]
        del npc.__dict__["specialization_pressure"]

        restored = pickle.loads(pickle.dumps(npc))

        self.assertEqual(restored.cold_exposure, 0.0)
        self.assertIn("dominant_work_tag", restored.actor_work_profile)
        self.assertEqual(
            restored.specialization_pressure,
            {"woodcutting": 0.0, "hauling": 0.0, "construction": 0.0, "crafting": 0.0},
        )

    def test_backfilled_mutable_defaults_are_not_shared_between_instances(self):
        """The plain-attribute backfill copies from a shared lazy template -
        confirm two separately-restored legacy NPCs don't end up sharing
        the SAME list/dict object for a backfilled attribute (which would
        make mutating one silently corrupt the other)."""
        npc_a = self._make_npc()
        npc_b = self._make_npc()
        del npc_a.__dict__["specialization_pressure"]
        del npc_b.__dict__["specialization_pressure"]

        restored_a = pickle.loads(pickle.dumps(npc_a))
        restored_b = pickle.loads(pickle.dumps(npc_b))

        restored_a.specialization_pressure["woodcutting"] = 99.0

        self.assertEqual(restored_b.specialization_pressure["woodcutting"], 0.0)

    def test_identity_fields_are_never_overwritten_by_the_template(self):
        """Sanity check on the denylist: even if somehow triggered, the
        backfill must never clobber a restored NPC's real identity."""
        npc = self._make_npc(personality="a very specific villager")
        npc.name = "Definitely Not The Template"
        restored = pickle.loads(pickle.dumps(npc))

        self.assertEqual(restored.name, "Definitely Not The Template")
        self.assertEqual(restored.x, 0)
        self.assertEqual(restored.y, 0)
        self.assertEqual(restored.social.personality, "a very specific villager")

    def test_whole_missing_component_is_recreated_with_defaults(self):
        """More extreme case: an entire component attribute (not just one
        field inside it) is absent - still shouldn't crash."""
        npc = self._make_npc()
        del npc.__dict__["schedule"]

        restored = pickle.loads(pickle.dumps(npc))

        self.assertIsNotNone(restored.schedule)
        self.assertFalse(restored.schedule.is_jailed)

    def test_full_npc_roundtrip_still_works_normally_with_nothing_missing(self):
        """Baseline: a completely normal, up-to-date pickle round-trip
        (nothing deleted) still preserves state correctly - the migration
        machinery shouldn't change behavior for a save made under current
        code."""
        npc = self._make_npc()
        npc.economic.money = 456
        npc.social.trait_pressure["greedy"] = 2

        restored = pickle.loads(pickle.dumps(npc))

        self.assertEqual(restored.economic.money, 456)
        self.assertEqual(restored.social.trait_pressure, {"greedy": 2})


class TestOtherDataclassesBackfillOnUnpickle(unittest.TestCase):
    """A sampling of the other, non-NPC dataclasses that gained the same
    generic __setstate__ backfill (CareerHistoryEntry, GrudgeRecord),
    confirming the shared helper works outside of entities/base.py too."""

    def test_career_history_entry_backfills_a_missing_field(self):
        entry = CareerHistoryEntry(role="Farmer", reason="test", game_time=5)
        del entry.__dict__["game_time"]

        restored = pickle.loads(pickle.dumps(entry))

        self.assertIsNone(restored.game_time)
        self.assertEqual(restored.role, "Farmer")

    def test_grudge_record_backfills_a_missing_field(self):
        grudge = GrudgeRecord(target_id=7, reason="attacked_me", severity=80)
        del grudge.__dict__["persistent"]

        restored = pickle.loads(pickle.dumps(grudge))

        self.assertFalse(restored.persistent)
        self.assertEqual(grudge.target_id, 7)


if __name__ == "__main__":
    unittest.main()
