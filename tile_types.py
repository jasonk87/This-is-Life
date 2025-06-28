class Tile:
    """The Tile class now stores a character, a color tuple, and a name."""
    def __init__(self, char, color, passable, name, properties=None):
        self.char = ord(char)
        self.color = color
        self.passable = passable
        self.name = name
        self.properties = properties if properties is not None else {}
