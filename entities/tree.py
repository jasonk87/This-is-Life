"""
This module defines the Tree classes, which are specialized Tile objects
representing different types of trees in the game world.
"""
import random
from tile_types import Tile
from data.dawnlike import TREE_SPRITES
from data.tiles import COLORS

class Tree(Tile):
    """A base class for trees in the game."""
    def __init__(self, x, y, tree_type="oak"):
        super().__init__(
            char=TREE_SPRITES["tree_generic"],
            color=COLORS["forest_fg"],
            passable=False,
            name=f"{tree_type.capitalize()} Tree",
            properties={"blocks_fov": True}
        )
        self.x = x
        self.y = y
        self.tree_type = tree_type
        self.is_choppable = True
        self.resource_yield = {"raw_log": 1}
        self.becomes_on_chop_key = "stump_generic"
        self.regrowth_timer = -1

    def chop(self):
        """
        Marks the tree as chopped and returns its resource yield.
        The actual tile transformation to a stump is handled by the engine.
        """
        if self.is_choppable:
            self.is_choppable = False
            yields = dict(self.resource_yield)
            if random.random() < 0.25:
                yields["sapling"] = yields.get("sapling", 0) + 1
            return yields
        return {}

    def get_description(self):
        """Returns a description of the tree."""
        return self.name

class OakTree(Tree):
    """Represents an oak tree."""
    def __init__(self, x, y):
        super().__init__(x, y, "oak")
        self.char = TREE_SPRITES["oak_tree"]
        self.color = (0, 100, 0)
        self.resource_yield = {"raw_log": 3, "acorn": 1}

class AppleTree(Tree):
    """Represents an apple tree."""
    def __init__(self, x, y):
        super().__init__(x, y, "apple")
        self.char = TREE_SPRITES["apple_tree"]
        self.color = (0, 150, 0)
        self.resource_yield = {"raw_log": 2, "apple": 2}

class PearTree(Tree):
    """Represents a pear tree."""
    def __init__(self, x, y):
        super().__init__(x, y, "pear")
        self.char = TREE_SPRITES["pear_tree"]
        self.color = (0, 120, 0)
        self.resource_yield = {"raw_log": 2, "pear": 2}
