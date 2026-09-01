"""The player can actually use what they are carrying.

The inventory menu only scrolled - Up, Down, Escape. There was no key to eat,
drink, equip or light anything, and World.use_item, which does all of that, had
no caller anywhere in the game. A player could carry a full pack of bread and
starve holding it.
"""

import unittest

import main
from engine import World
from rendering import console_renderer as cr
from tcod_compat import tcod


def _key(sym):
    return tcod.event.KeyDown(sym=sym, scancode=0, mod=0)


class TestInventoryUse(unittest.TestCase):
    def setUp(self):
        self.world = World(player_first_name="Tester")
        main._ensure_zoom_state(self.world)
        self.console = main.create_console()
        self.world.game_state = "INVENTORY_MENU"

    def _open(self):
        """Draw the menu, which is what works out where the item rows are."""
        cr.draw_inventory_menu(self.console, self.world)
        return self.world.interaction_context.get("inventory_selectable") or []

    def _select(self, item_key):
        selectable = self._open()
        self.assertIn(item_key, selectable, f"{item_key} is not selectable")
        self.world.interaction_context["inventory_selected_index"] = selectable.index(item_key)

    def test_eating_reduces_hunger_and_consumes_the_food(self):
        player = self.world.player
        player.add_item("bread", 3)
        player.physical.hunger = 80

        self._select("bread")
        main.handle_inventory_menu_input(_key(tcod.event.KeySym.RETURN), self.world)

        self.assertLess(player.physical.hunger, 80, "eating did not reduce hunger")
        self.assertEqual(player.economic.inventory.get("bread", 0), 2, "the loaf was not eaten")

    def test_armour_can_be_equipped_from_the_pack(self):
        player = self.world.player
        player.add_item("leather_jerkin", 1)

        self._select("leather_jerkin")
        main.handle_inventory_menu_input(_key(tcod.event.KeySym.RETURN), self.world)

        self.assertEqual(player.equipment.equipped_armor.get("body"), "leather_jerkin")

    def test_a_torch_can_be_lit(self):
        player = self.world.player
        player.add_item("unlit_torch", 1)

        self._select("unlit_torch")
        main.handle_inventory_menu_input(_key(tcod.event.KeySym.RETURN), self.world)

        self.assertIsNotNone(player.equipment.equipped_light_item_key)

    def test_selection_moves_and_wraps(self):
        player = self.world.player
        player.add_item("bread", 1)
        player.add_item("unlit_torch", 1)
        selectable = self._open()
        self.assertGreater(len(selectable), 1)

        self.world.interaction_context["inventory_selected_index"] = 0
        main.handle_inventory_menu_input(_key(tcod.event.KeySym.DOWN), self.world)
        self.assertEqual(self.world.interaction_context["inventory_selected_index"], 1)

        self.world.interaction_context["inventory_selected_index"] = 0
        main.handle_inventory_menu_input(_key(tcod.event.KeySym.UP), self.world)
        self.assertEqual(
            self.world.interaction_context["inventory_selected_index"], len(selectable) - 1,
            "selection did not wrap round the top",
        )

    def test_an_empty_pack_says_so_rather_than_failing(self):
        self._open()
        main.handle_inventory_menu_input(_key(tcod.event.KeySym.RETURN), self.world)
        self.assertIn("nothing to use", self.world.chat_log[-1].lower())

    def test_escape_still_closes_the_menu(self):
        main.handle_inventory_menu_input(_key(tcod.event.KeySym.ESCAPE), self.world)
        self.assertEqual(self.world.game_state, "PLAYING")


class TestUseItemMessaging(unittest.TestCase):
    """A refusal should say why, once."""

    def setUp(self):
        self.world = World(player_first_name="Tester")

    def _last_messages(self, count):
        return [str(m) for m in self.world.chat_log[-count:]]

    def test_declining_to_eat_when_full_does_not_also_claim_confusion(self):
        player = self.world.player
        player.add_item("bread", 1)
        player.physical.hunger = 0
        before = len(self.world.chat_log)

        self.world.use_item("bread")

        messages = self._last_messages(len(self.world.chat_log) - before)
        self.assertTrue(any("not hungry enough" in m for m in messages))
        self.assertFalse(
            any("can't figure out how to use" in m for m in messages),
            f"a precise refusal was followed by a contradictory one: {messages}",
        )

    def test_a_genuinely_unusable_item_still_says_so(self):
        player = self.world.player
        player.add_item("iron_ingot", 1)
        before = len(self.world.chat_log)

        self.world.use_item("iron_ingot")

        messages = self._last_messages(len(self.world.chat_log) - before)
        self.assertTrue(messages, "using an inert item said nothing at all")


if __name__ == "__main__":
    unittest.main()
