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

        # Task-related attributes
        self.current_task: str | None = "idle"
        self.previous_task: str | None = None
        self.task_target_entity_id: int | None = None
        self.task_target_coords: tuple[int, int] | None = None
        self.task_timer: int = 0
        self.woodcutter_search_radius: int = 5

        # Temperature-related attributes
        self.temperature: float = 37.0
        self.base_temperature_resistance: float = 0.0
        self.clothing_insulation: float = 0.0
        self.status_effects: list[str] = []
        self.game_time_last_updated: int = 0


    def get_dialogue(self):
        """
        Animals do not have dialogue.
        """
        return None
