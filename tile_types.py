class Tile:
    """The Tile class now stores a character, a color tuple, and a name."""
    def __init__(self, char, color, passable, name, properties=None):
        self.char = ord(char)
        self.color = color
        self.passable = passable
        self.name = name
        self.properties = properties if properties is not None else {}

        # Environmental Awareness Properties
        self.provides_cover_value: float = float(self.properties.get("provides_cover_value", 0.0))
        self.is_hazard: bool = bool(self.properties.get("is_hazard", False))
        self.hazard_type: str | None = self.properties.get("hazard_type", None)
        self.hazard_damage: int = int(self.properties.get("hazard_damage", 0))
        self.blocks_fov: bool = bool(self.properties.get("blocks_fov", not self.passable)) # By default, non-passable tiles block FOV
