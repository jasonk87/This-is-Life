# entities/tree.py

from tile_types import Tile
from data.tiles import COLORS

class Tree(Tile):
    def __init__(self, x, y, tree_type="oak"):
        self.x = x
        self.y = y
        self.tree_type = tree_type
        self.char = ord('T') # Default tree character
        self.color = COLORS["forest_fg"] # Default tree color
        self.passable = False
        self.name = f"{tree_type.capitalize()} Tree"
        self.drops = {} # Dictionary to store potential drops and their quantities

class OakTree(Tree):
    def __init__(self, x, y):
        super().__init__(x, y, "oak")
        self.char = ord('O')
        self.color = (0, 100, 0) # Darker green for oak
        self.drops = {"acorn": 1, "wood": 1} # Example drops

class AppleTree(Tree):
    def __init__(self, x, y):
        super().__init__(x, y, "apple")
        self.char = ord('A')
        self.color = (0, 150, 0) # Lighter green for apple tree
        self.drops = {"apple": 1, "wood": 1} # Example drops

class PearTree(Tree):
    def __init__(self, x, y):
        super().__init__(x, y, "pear")
        self.char = ord('P')
        self.color = (0, 120, 0) # Medium green for pear tree
        self.drops = {"pear": 1, "wood": 1} # Example drops
