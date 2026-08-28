"""Tests for the Appearance component (entities/base.py) and the
appearance-overlay rendering pipeline (data/dawnlike.py +
rendering/console_renderer.py) added to support hair/facial-hair overlays,
mirroring the existing equipment-overlay mechanism.

Scope note: as of this test file's introduction, HAIR_SPRITES and
BEARD_SPRITES in data/dawnlike.py are intentionally empty - the current
DawnLike tile sheet has no separable hair/beard art to catalogue (see the
comments above those tables). Several tests below temporarily monkeypatch
a fake entry into those tables purely to exercise the compositing/z-order
mechanism end-to-end; this is a test-only stand-in for verifying the
pipeline works, not a claim that real hair/beard art exists yet.
"""
import random
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import data.dawnlike as dawnlike
import rendering.console_renderer as console_renderer
from data.dawnlike import _get_appearance_overlays, _get_equipment_overlays
from entities.base import (
    Appearance,
    Equipment,
    NPC,
    roll_appearance,
)
from entities.items import EquipmentSlot


class TestAppearanceComponent(unittest.TestCase):
    def test_default_appearance_is_all_none(self):
        appearance = Appearance()
        self.assertEqual(appearance.hairstyle, "none")
        self.assertEqual(appearance.facial_hair, "none")
        self.assertEqual(appearance.hair_color, "brown")
        self.assertEqual(appearance.skin_tone, "medium")

    def test_npc_construction_seeds_an_appearance_component(self):
        npc = NPC(0, 0, name="Villager")
        self.assertIsInstance(npc.appearance, Appearance)
        self.assertIn(npc.appearance.hairstyle, dawnlike.HAIR_SPRITES.keys() | {
            "none", "short", "long", "braided", "curly", "bald",
        })

    def test_npc_setstate_backfills_missing_appearance_for_old_saves(self):
        npc = NPC(0, 0, name="Villager")
        state = npc.__dict__.copy()
        del state["appearance"]  # simulate a pre-Appearance save

        restored = NPC.__new__(NPC)
        restored.__setstate__(state)

        self.assertTrue(hasattr(restored, "appearance"))
        self.assertIsInstance(restored.appearance, Appearance)


class TestRollAppearanceDistribution(unittest.TestCase):
    """"Reasonable random distribution, not everyone bearded" - statistical
    sanity checks over many rolls rather than a single deterministic
    assertion, since roll_appearance is intentionally randomized."""

    def test_adult_male_facial_hair_is_neither_universal_nor_impossible(self):
        random.seed(1234)
        rolls = [roll_appearance(gender="male", age=35).facial_hair for _ in range(500)]
        bearded_count = sum(1 for f in rolls if f != "none")
        self.assertGreater(bearded_count, 0, "no adult male ever rolled facial hair - distribution is broken")
        self.assertLess(bearded_count, len(rolls), "every adult male rolled facial hair - not 'not everyone bearded'")
        # Roughly 45% of adult males should roll SOME facial hair per the
        # weights in roll_appearance; allow generous slack for randomness.
        self.assertTrue(0.25 < bearded_count / len(rolls) < 0.65, bearded_count / len(rolls))

    def test_children_never_roll_facial_hair(self):
        random.seed(99)
        rolls = [roll_appearance(gender="male", age=10).facial_hair for _ in range(200)]
        self.assertTrue(all(f == "none" for f in rolls))

    def test_hairstyle_has_variety_not_a_single_fixed_value(self):
        random.seed(42)
        rolls = {roll_appearance(gender="female", age=28).hairstyle for _ in range(200)}
        self.assertGreater(len(rolls), 1)

    def test_returns_appearance_instance(self):
        self.assertIsInstance(roll_appearance("male", 40), Appearance)
        self.assertIsInstance(roll_appearance(None, None), Appearance)


class TestGetAppearanceOverlays(unittest.TestCase):
    def _entity(self, *, hairstyle="none", facial_hair="none", head_item_key=None):
        equipment = Equipment()
        if head_item_key:
            equipment.head = EquipmentSlot(head_item_key)
        return SimpleNamespace(
            appearance=Appearance(hairstyle=hairstyle, facial_hair=facial_hair),
            equipment=equipment,
        )

    def test_entity_without_appearance_component_returns_empty(self):
        entity = SimpleNamespace(equipment=Equipment())
        self.assertEqual(_get_appearance_overlays(entity), [])

    def test_none_hairstyle_and_facial_hair_returns_empty(self):
        entity = self._entity(hairstyle="none", facial_hair="none")
        self.assertEqual(_get_appearance_overlays(entity), [])

    def test_uncatalogued_hairstyle_is_a_graceful_no_op(self):
        # As of this writing HAIR_SPRITES is empty, so any hairstyle value
        # (however plausible) currently produces no overlay. This proves
        # the "no source art yet" state doesn't crash the renderer.
        entity = self._entity(hairstyle="short", facial_hair="full_beard")
        self.assertEqual(_get_appearance_overlays(entity), [])

    def test_catalogued_hair_and_beard_are_returned_with_correct_anchors(self):
        entity = self._entity(hairstyle="short", facial_hair="full_beard")
        fake_hair_codepoint = 0xE100
        fake_beard_codepoint = 0xE101
        with patch.dict(dawnlike.HAIR_SPRITES, {"short": fake_hair_codepoint}), \
             patch.dict(dawnlike.BEARD_SPRITES, {"full_beard": fake_beard_codepoint}):
            overlays = _get_appearance_overlays(entity)

        codepoints = {entry[0] for entry in overlays}
        self.assertEqual(codepoints, {fake_hair_codepoint, fake_beard_codepoint})
        for codepoint, ax, ay, z in overlays:
            self.assertTrue(0.0 <= ax <= 1.0)
            self.assertTrue(0.0 <= ay <= 1.0)
            if codepoint == fake_hair_codepoint:
                self.assertEqual((ax, ay, z), dawnlike.HAIR_OVERLAY_ANCHOR)
            else:
                self.assertEqual((ax, ay, z), dawnlike.BEARD_OVERLAY_ANCHOR)

    def test_equipped_headwear_suppresses_hair_but_not_beard(self):
        entity = self._entity(hairstyle="short", facial_hair="full_beard", head_item_key="iron_helmet")
        with patch.dict(dawnlike.HAIR_SPRITES, {"short": 0xE100}), \
             patch.dict(dawnlike.BEARD_SPRITES, {"full_beard": 0xE101}):
            overlays = _get_appearance_overlays(entity)

        codepoints = {entry[0] for entry in overlays}
        self.assertNotIn(0xE100, codepoints, "hair should be suppressed under equipped headwear")
        self.assertIn(0xE101, codepoints, "beard should still render under headwear")

    def test_equipped_armor_dict_head_slot_also_suppresses_hair(self):
        # Older/player-side head equipment is sometimes tracked via the
        # equipped_armor dict rather than the EquipmentSlot dataclass field
        # (see Equipment.equipped_armor) - both paths should suppress hair.
        equipment = Equipment()
        equipment.equipped_armor["head"] = "hooded_cowl"
        entity = SimpleNamespace(
            appearance=Appearance(hairstyle="short", facial_hair="none"),
            equipment=equipment,
        )
        with patch.dict(dawnlike.HAIR_SPRITES, {"short": 0xE100}):
            overlays = _get_appearance_overlays(entity)
        self.assertEqual(overlays, [])

    def test_overlays_are_sorted_by_z_order(self):
        entity = self._entity(hairstyle="short", facial_hair="full_beard")
        with patch.dict(dawnlike.HAIR_SPRITES, {"short": 0xE100}), \
             patch.dict(dawnlike.BEARD_SPRITES, {"full_beard": 0xE101}), \
             patch.object(dawnlike, "HAIR_OVERLAY_ANCHOR", (0.3, 0.05, 0)), \
             patch.object(dawnlike, "BEARD_OVERLAY_ANCHOR", (0.32, 0.2, 1)):
            overlays = _get_appearance_overlays(entity)
        self.assertEqual([entry[3] for entry in overlays], sorted(entry[3] for entry in overlays))


class TestAppearanceAndEquipmentOverlaysComposeTogether(unittest.TestCase):
    """Integration-level check that the merge in
    console_renderer._draw_entities (appearance overlays + equipment
    overlays, sorted once by z_order) produces a single correctly-ordered
    stamping pass, using real EQUIPMENT_OVERLAY_SPRITES entries alongside a
    monkeypatched appearance entry."""

    def test_merged_and_sorted_like_the_renderer_does(self):
        equipment = Equipment()
        equipment.body = EquipmentSlot("leather_jerkin")  # real z=0 equipment overlay
        equipment.weapon = EquipmentSlot("iron_sword")  # real z=2 equipment overlay
        entity = SimpleNamespace(
            appearance=Appearance(hairstyle="short", facial_hair="none"),
            equipment=equipment,
        )

        with patch.dict(dawnlike.HAIR_SPRITES, {"short": 0xE100}):
            appearance_overlays = _get_appearance_overlays(entity)
            equipment_overlays = _get_equipment_overlays(entity)
            merged = appearance_overlays + equipment_overlays
            merged.sort(key=lambda entry: entry[3])

        z_orders = [entry[3] for entry in merged]
        self.assertEqual(z_orders, sorted(z_orders))
        # Hair (z=0) and body armor (z=0) both precede the weapon (z=2).
        self.assertEqual(z_orders[-1], 2)
        self.assertIn(0xE100, {entry[0] for entry in merged})


class TestDrawEntitiesStampsAppearanceOverlays(unittest.TestCase):
    """Renderer-level check that _draw_entities (console_renderer.py)
    actually calls the new appearance-overlay function and stamps its
    results alongside equipment overlays - the "wire it in" half of this
    feature, as opposed to the data-layer tests above."""

    def test_appearance_and_equipment_overlays_both_get_stamped(self):
        class FakeConsole:
            def __init__(self):
                self.print_calls = []
                self.bg = np.zeros((2, 2, 3), dtype=np.uint8)

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

        player = SimpleNamespace(
            x=0, y=0, render_x=0.0, render_y=0.0,
            state=SimpleNamespace(is_riding=False),
            render_order=SimpleNamespace(value=1),
            physical=SimpleNamespace(is_dead=False),
        )
        world = SimpleNamespace(npcs=[], village_npcs=[], player=player)
        console = FakeConsole()

        with patch("rendering.console_renderer.is_visible", return_value=True), \
             patch("rendering.console_renderer.get_entity_sprite", return_value=ord("@")), \
             patch("rendering.console_renderer._get_appearance_overlays", return_value=[(0xE100, 0.3, 0.05, 0)]), \
             patch("rendering.console_renderer._get_equipment_overlays", return_value=[(0xE200, 0.6, 0.35, 2)]):
            console_renderer._draw_entities(console, world, 0, 0)

        drawn_strings = [call["string"] for call in console.print_calls]
        self.assertIn("@", drawn_strings)
        self.assertIn(chr(0xE100), drawn_strings)
        self.assertIn(chr(0xE200), drawn_strings)
        # Appearance overlay (z=0) must be stamped before the equipment
        # overlay (z=2) - proves the merge+sort in _draw_entities, not just
        # that both happened to appear somewhere in the call list.
        self.assertLess(drawn_strings.index(chr(0xE100)), drawn_strings.index(chr(0xE200)))

    def test_dead_entities_get_no_overlays_stamped(self):
        class FakeConsole:
            def __init__(self):
                self.print_calls = []
                self.bg = np.zeros((2, 2, 3), dtype=np.uint8)

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

        player = SimpleNamespace(
            x=0, y=0, render_x=0.0, render_y=0.0,
            state=SimpleNamespace(is_riding=False),
            render_order=SimpleNamespace(value=1),
            physical=SimpleNamespace(is_dead=True),
        )
        world = SimpleNamespace(npcs=[], village_npcs=[], player=player)
        console = FakeConsole()

        appearance_overlay_call_count = 0

        def _tracking_appearance_overlays(_entity):
            nonlocal appearance_overlay_call_count
            appearance_overlay_call_count += 1
            return [(0xE100, 0.3, 0.05, 0)]

        with patch("rendering.console_renderer.is_visible", return_value=True), \
             patch("rendering.console_renderer.get_entity_sprite", return_value=ord("@")), \
             patch("rendering.console_renderer._get_appearance_overlays", side_effect=_tracking_appearance_overlays), \
             patch("rendering.console_renderer._get_equipment_overlays", return_value=[]):
            console_renderer._draw_entities(console, world, 0, 0)

        self.assertEqual(appearance_overlay_call_count, 0)
        self.assertNotIn(chr(0xE100), [call["string"] for call in console.print_calls])


if __name__ == "__main__":
    unittest.main()
