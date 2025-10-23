from entities.base import NPC
from config import DEFAULT_HEARING_RADIUS

class Animal(NPC):
    """
    A streamlined version of the NPC class for animal entities.
    """
    def __init__(self, x, y, name="Animal", animal_type="unknown"):
        super().__init__(x, y, name=name)
        self.animal_type = animal_type
        self.behavior = "wanders" # Default behavior

        # --- Remove or simplify NPC-specific attributes ---
        self.dialogue = None
        self.personality = None
        self.family_ties = None
        self.attitude_to_player = None
        self.home_building_id = None
        self.work_building_id = None
        self.profession = "Creature" # Use "Creature" to bypass human-like scheduling
        self.money = 0
        self.npc_inventory = {}

        # --- Animal-specific attributes ---
        self.char = ord('a')
        self.color = (255, 255, 255)

        # Set default combat/AI behavior
        self.is_hostile_to_player = False
        self.combat_behavior = "defensive" # e.g., 'aggressive', 'defensive', 'cowardly'
        self.speech_volume = 3 # Animals are generally quieter than humans
        self.hearing_radius = DEFAULT_HEARING_RADIUS

        # --- Taming Attributes ---
        self.is_tame = False
        self.tameness = 0
        self.owner = None

        # --- Riding Attributes ---
        self.is_being_ridden: bool = False
        self.rider_id: int | None = None

        # --- Mating Attributes ---
        self.gender: str = "female" # Default to female for now
        self.is_pregnant: bool = False
        self.pregnancy_timer: int = 0

        # --- Shearing Attributes ---
        self.last_shorn_time: int = -100000 # Set to a long time ago initially

        # --- Hunger Attributes ---
        self.hunger: int = 0
        self.max_hunger: int = 100 # Default max hunger

    def get_dialogue(self):
        # Animals don't have dialogue in the same way NPCs do.
        return None
