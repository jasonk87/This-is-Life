import unittest
from types import SimpleNamespace

import engine
from engine import World
import main


class TestFamilyNpcLlmJsonFallback(unittest.TestCase):
    """Bug-hunt audit item 6: World._create_family_npc's LLM JSON-parse
    fallback used a bare `except:`, silently swallowing everything
    (including real bugs unrelated to bad LLM output). Narrowed to
    (json.JSONDecodeError, TypeError) - those are the two ways
    json.loads(llm_response) can actually fail here: malformed/non-JSON
    text (JSONDecodeError) or a non-string response such as None
    (TypeError). These tests confirm the fallback still works for both of
    those real cases, and that the narrowing didn't just relabel the same
    bare catch under a different name."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=2020)
        self.home_building = next(iter(self.world.buildings_by_id.values()))

    def test_malformed_json_response_falls_back_to_default_npc_data(self):
        self.world._call_llm_for_worldgen = lambda prompt: "not valid json at all {{{"

        npc = self.world._create_family_npc("Mother", "Test", self.home_building, {})

        self.assertTrue(npc.name.endswith("Test"))
        self.assertEqual(npc.dialogue, ["Hello, dear."])
        self.assertEqual(npc.social.personality, "friendly")

    def test_non_string_llm_response_falls_back_to_default_npc_data(self):
        """json.loads(None) raises TypeError, not JSONDecodeError - this
        confirms both branches of the narrowed except tuple are needed."""
        self.world._call_llm_for_worldgen = lambda prompt: None

        npc = self.world._create_family_npc("Father", "Test", self.home_building, {})

        self.assertTrue(npc.name.endswith("Test"))
        self.assertEqual(npc.dialogue, ["Hello, dear."])

    def test_valid_json_response_is_used_directly_not_the_fallback(self):
        self.world._call_llm_for_worldgen = (
            lambda prompt: '{"name": "Custom Name", "dialogue": ["Hi there."], "personality": "grumpy"}'
        )

        npc = self.world._create_family_npc("Brother", "Test", self.home_building, {})

        self.assertEqual(npc.name, "Custom Name")
        self.assertEqual(npc.dialogue, ["Hi there."])
        self.assertEqual(npc.social.personality, "grumpy")


class TestDialogueInputShiftModFallback(unittest.TestCase):
    """Bug-hunt audit item 6: handle_dialogue_input's SDL-modifier-key
    fallback (used when a TextInput event lacks proper mod bindings) had a
    bare `except:` around `bool(mod & 3)`. Narrowed to
    (TypeError, AttributeError) - TypeError is the real failure mode (a
    non-int mod value can't be bitwise-anded), AttributeError covers a
    stranger event object shape even though getattr's own default already
    handles a plain missing attribute. These tests confirm the fallback
    still degrades to shifted=False for a malformed mod value instead of
    crashing, and that normal shifted/unshifted typing is unaffected."""

    def setUp(self):
        # handle_dialogue_input's elif chain checks tcod.event.KeySym.SPACE
        # before reaching the fallback branch these tests exercise, so the
        # constant has to exist. Real tcod defines it - as an enum member,
        # which cannot be reassigned - while the headless compat shim in
        # tcod_compat does not. Patch it in only when it's genuinely
        # missing; unconditionally assigning raises AttributeError
        # ("cannot reassign member 'SPACE'") once real tcod is installed.
        if not hasattr(main.tcod.event.KeySym, "SPACE"):
            main.tcod.event.KeySym.SPACE = 32
            self.addCleanup(delattr, main.tcod.event.KeySym, "SPACE")

    def _dialogue_world(self):
        return SimpleNamespace(
            chat_ui_input_line="",
            chat_ui_history=[],
            chat_ui_target_npc=None,
        )

    def test_non_int_mod_value_falls_back_to_unshifted_typing(self):
        world = self._dialogue_world()
        event = SimpleNamespace(sym=ord("a"), mod="not-a-number")

        main.handle_dialogue_input(event, world, SimpleNamespace())

        self.assertEqual(world.chat_ui_input_line, "a")

    def test_normal_shift_modifier_still_uppercases(self):
        world = self._dialogue_world()
        event = SimpleNamespace(sym=ord("a"), mod=1)  # KMOD_LSHIFT

        main.handle_dialogue_input(event, world, SimpleNamespace())

        self.assertEqual(world.chat_ui_input_line, "A")

    def test_no_modifier_types_lowercase_unaffected(self):
        world = self._dialogue_world()
        event = SimpleNamespace(sym=ord("a"), mod=0)

        main.handle_dialogue_input(event, world, SimpleNamespace())

        self.assertEqual(world.chat_ui_input_line, "a")


if __name__ == "__main__":
    unittest.main()
