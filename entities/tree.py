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
        # self.drops = {} # Replaced by resource_yield for clarity with plan

        self.is_choppable = True
        self.resource_yield = {"log": 1} # Default yield, matches item key "log"
        self.chopped_char = ord('t')
        self.chopped_color = (139, 69, 19) # Brown for stump
        self.original_name = self.name # Store original name

    def chop(self):
        if self.is_choppable:
            self.is_choppable = False
            self.char = self.chopped_char
            self.color = self.chopped_color
            self.name = f"Chopped {self.original_name}" # More descriptive than just "Stump"
            # self.passable = True # A stump could be passable
            # self.blocks_sight = False # A stump might not block sight (Tile class doesn't have this)

            # Return a copy of the yield dictionary
            return dict(self.resource_yield)
        return {}

class OakTree(Tree):
    def __init__(self, x, y):
        super().__init__(x, y, "oak")
        self.char = ord('O')
        self.color = (0, 100, 0) # Darker green for oak
        self.resource_yield = {"log": 3, "acorn": 1} # Oak yields more logs and acorns

class AppleTree(Tree):
    def __init__(self, x, y):
        super().__init__(x, y, "apple")
        self.char = ord('A')
        self.color = (0, 150, 0) # Lighter green for apple tree
        self.resource_yield = {"log": 2, "apple": 2} # Apple tree yields some logs and apples

class PearTree(Tree):
    def __init__(self, x, y):
        super().__init__(x, y, "pear")
        self.char = ord('P')
        self.color = (0, 120, 0) # Medium green for pear tree
        self.resource_yield = {"log": 2, "pear": 2} # Pear tree
