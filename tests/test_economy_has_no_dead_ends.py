"""Anything the world consumes, the world can also make.

A resource that is consumed and never produced does not announce itself. The
game runs, nothing errors, and a production chain simply stops for good once the
starting stock is spent - after which every item downstream of it becomes
permanently unmakeable. Two of these were found by watching a village's stores
drift over simulated days, which is an expensive way to learn something that is
plain in the data:

* coal. Consumed one lump per ingot by the blacksmith's smelt_ingot, produced by
  nothing. The world's entire supply was the 10-25 lumps seeded into each
  blacksmith shop at generation. Measured over two days, ore climbed 154 -> 291
  while ingots fell 36 -> 46 -> 1 as the last coal burned, and sword,
  breastplate, shears, helmet and anvil all became unmakeable.
* stone_chunk. Consumed by four construction recipes and by the forge, seeded
  into mines and smithies and produced by nothing. A settlement that built its
  clinic and its fire pits was simply done building.
* herb_generic. The rag half of "a stick with oil-soaked rags", obtainable only
  by planting one, which requires already having one.

This asserts the property directly, off the data, in milliseconds - rather than
waiting for a multi-day simulation to show a number sagging.

Producers are gathered from every route the game actually has, which is the
fiddly part: sub-task outputs and deposits, the completion commands in
work_subtasks.py, crafting recipes, tile harvests, tiles that yield as you walk
through them, animal loot tables and shearing. An earlier version of this check
knew only about sub-task data and reported five dead ends, three of which were
perfectly well supplied by paths it could not see. A checker that cries wolf is
worse than none.
"""

import unittest

from data.animals import ANIMAL_DEFINITIONS
from data.construction import CONSTRUCTION_RECIPES
from data.items import ITEM_DEFINITIONS
from data.professions import PROFESSIONS
from data.tiles import TILE_DEFINITIONS
from work_subtasks import (
    AddItemToNpcInventorySubTaskCommand,
    WorkBuildingConversionSubTaskCommand,
    create_completed_work_sub_task_commands,
)

# Produced by a completion command's own code rather than by any data it
# carries, so there is nothing to introspect. Kept explicit and short.
CODE_PATH_PRODUCERS = {
    "raw_log": "work_subtasks.ChopTreesSubTaskCommand",
    "raw_fish": "work_subtasks.FishAtSpotSubTaskCommand",
    "medicinal_herb": "simulation.systems.medical foraging",
}


def _producers():
    produced = {}

    def note(item, source):
        produced.setdefault(item, set()).add(source)

    for profession, data in PROFESSIONS.items():
        for step in data.get("sub_tasks", []):
            where = f"{profession}.{step['id']}"
            for field in ("produces_item_at_workplace", "deposits_item_to_workplace"):
                for item in (step.get(field) or {}):
                    note(item, where)

    for step_id, command in create_completed_work_sub_task_commands().items():
        if isinstance(command, AddItemToNpcInventorySubTaskCommand):
            note(command.item_key, f"command:{step_id}")
        elif isinstance(command, WorkBuildingConversionSubTaskCommand):
            note(command.produced_item, f"command:{step_id}")

    for item, source in CODE_PATH_PRODUCERS.items():
        note(item, source)

    for key, definition in ITEM_DEFINITIONS.items():
        if definition.get("crafting_recipe"):
            note(key, "crafting")

    for definition in TILE_DEFINITIONS.values():
        properties = definition.get("properties") or {}
        harvested = properties.get("harvest_yield_item_key")
        if harvested:
            note(harvested, "tile harvest")
        walked = properties.get("yields_on_pass_through") or {}
        if walked.get("item_key"):
            note(walked["item_key"], "walked through")

    for definition in ANIMAL_DEFINITIONS.values():
        for item in (definition.get("loot_drops") or {}):
            note(item, "butchering")
        shearable = definition.get("shearable") or {}
        if shearable.get("item_yield"):
            note(shearable["item_yield"], "shearing")

    return produced


def _consumers():
    consumed = {}

    def note(item, source):
        consumed.setdefault(item, set()).add(source)

    for profession, data in PROFESSIONS.items():
        for step in data.get("sub_tasks", []):
            where = f"{profession}.{step['id']}"
            for field in ("consumes_item_from_workplace", "consumes_item_from_npc_inventory"):
                for item in (step.get(field) or {}):
                    note(item, where)

    for step_id, command in create_completed_work_sub_task_commands().items():
        if isinstance(command, WorkBuildingConversionSubTaskCommand):
            note(command.consumed_item, f"command:{step_id}")

    for key, definition in ITEM_DEFINITIONS.items():
        for ingredient in (definition.get("crafting_recipe") or {}):
            note(ingredient, f"recipe:{key}")

    for key, recipe in CONSTRUCTION_RECIPES.items():
        for item in (recipe.get("materials") or {}):
            note(item, f"build:{key}")

    return consumed


class TestNothingIsConsumedWithoutBeingMade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.produced = _producers()
        cls.consumed = _consumers()

    def test_the_check_is_looking_at_something(self):
        """Guards the guard. If either side came back empty - a renamed data
        table, a moved module - every assertion below would pass while checking
        nothing at all."""
        self.assertGreater(len(self.produced), 20, "found almost nothing produced")
        self.assertGreater(len(self.consumed), 10, "found almost nothing consumed")

    def test_every_consumed_item_has_a_producer(self):
        for item, consumers in sorted(self.consumed.items()):
            with self.subTest(item=item):
                self.assertIn(
                    item, self.produced,
                    f"{item} is consumed by {sorted(consumers)[:4]} and nothing in "
                    f"the world produces it, so every chain behind it stops for "
                    f"good once the starting stock is spent",
                )

    def test_the_resources_that_were_dead_ends_stay_fixed(self):
        """Named individually, because each was found the expensive way."""
        for item in ("coal", "stone_chunk", "herb_generic"):
            with self.subTest(item=item):
                self.assertIn(
                    item, self.produced,
                    f"{item} has lost its producer again",
                )

    def test_every_crafting_ingredient_is_a_real_item(self):
        """A recipe naming an item that does not exist is unmakeable in a
        quieter way, and reads as a typo rather than a design gap."""
        for key, definition in ITEM_DEFINITIONS.items():
            for ingredient in (definition.get("crafting_recipe") or {}):
                with self.subTest(recipe=key, ingredient=ingredient):
                    self.assertIn(ingredient, ITEM_DEFINITIONS)

    def test_every_construction_material_is_a_real_item(self):
        for key, recipe in CONSTRUCTION_RECIPES.items():
            for item in (recipe.get("materials") or {}):
                with self.subTest(recipe=key, material=item):
                    self.assertIn(item, ITEM_DEFINITIONS)

    def test_every_sub_task_item_is_a_real_item(self):
        for profession, data in PROFESSIONS.items():
            for step in data.get("sub_tasks", []):
                for field in (
                    "produces_item_at_workplace", "deposits_item_to_workplace",
                    "consumes_item_from_workplace", "consumes_item_from_npc_inventory",
                ):
                    for item in (step.get(field) or {}):
                        with self.subTest(step=f"{profession}.{step['id']}", item=item):
                            self.assertIn(item, ITEM_DEFINITIONS)


if __name__ == "__main__":
    unittest.main()
