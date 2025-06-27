class Tile:
    """The Tile class now stores a character, a color tuple, and a name."""
    def __init__(self, char, color, passable, name):
        self.char = ord(char)
        self.color = color
        self.passable = passable
        self.name = name
