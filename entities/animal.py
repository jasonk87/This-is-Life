"""
This module defines the Animal class, a specialized subclass of NPC.
"""
from entities.base import NPC
from config import DEFAULT_HEARING_RADIUS

class Animal(NPC):
    """
    A streamlined version of the NPC class for animal entities.
    """
    def __init__(self, x, y, name="Animal", animal_type="unknown"):
        super().__init__(x, y, name=name)
        self.animal_type = animal_type
        self.behavior = "wanders"

        self.dialogue = None
        self.personality = None
        self.family_ties = None
        self.home_building_id = None
        self.work_building_id = None
        self.profession = "Creature"
        self.money = 0
        self.npc_inventory = {}

        self.char = ord('a')
        self.color = (255, 255, 255)

        self.is_hostile_to_player = False
        self.combat_behavior = "defensive"
        self.speech_volume = 3
        self.hearing_radius = DEFAULT_HEARING_RADIUS

        self.is_tame = False
        self.tameness = 0
        self.owner = None

        self.is_being_ridden: bool = False
        self.rider_id: int | None = None

        self.gender: str = "female"
        self.is_pregnant: bool = False
        self.pregnancy_timer: int = 0

        self.last_shorn_time: int = -100000

        self.hunger: int = 0
        self.max_hunger: int = 100

        self.pack_id: str | None = None

    def get_dialogue(self):
        """
        Animals do not have dialogue.
        """
        return None
