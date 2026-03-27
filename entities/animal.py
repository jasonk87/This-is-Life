"""
This module defines the Animal class, a specialized subclass of NPC.
"""
from data.dawnlike import get_animal_sprite
from entities.base import NPC
from config import DEFAULT_HEARING_RADIUS
from simulation.careers import set_entity_profession

class Animal(NPC):
    """
    A streamlined version of the NPC class for animal entities.
    """
    def __init__(self, x, y, name="Animal", animal_type="unknown"):
        super().__init__(x, y, name=name)
        self.animal_type = animal_type
        self.behavior = "wanders"

        self.dialogue = None
        self.social.personality = "animal"
        self.social.family_ties = {"description": "animal"}
        self.schedule.home_building_id = None
        self.schedule.work_building_id = None
        set_entity_profession(self, "Creature", reason="animal_spawn")
        self.economic.money = 0
        self.economic.npc_inventory = {}

        self.char = get_animal_sprite(animal_type)
        self.color = (255, 255, 255)

        self.combat.is_hostile_to_player = False
        self.combat.combat_behavior = "defensive"
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

        self.physical.hunger = 0
        self.physical.max_hunger = 100

        self.pack_id: str | None = None

        # Task-related attributes
        self.schedule.current_task = "idle"
        self.schedule.previous_task = "idle"
        self.task_target_entity_id: int | None = None
        self.task_target_coords: tuple[int, int] | None = None
        self.task_timer: int = 0
        self.woodcutter_search_radius: int = 5

        # Temperature-related attributes
        self.physical.temperature = 37.0
        self.physical.base_temperature_resistance = 0.0
        self.physical.clothing_insulation = 0.0
        self.physical.status_effects = []
        self.schedule.game_time_last_updated = 0


    def get_dialogue(self):
        """
        Animals do not have dialogue.
        """
        return None
