"""Data-driven animal entity construction."""
from __future__ import annotations

import copy
import random

from config import DEFAULT_HEARING_RADIUS
from data.animals import ANIMAL_DEFINITIONS
from data.dawnlike import get_animal_sprite
from entities.base import NPC
from entities.behaviors import create_behavior
from simulation.careers import set_entity_profession


class Animal(NPC):
    """Universal animal entity built from definition data instead of subclasses."""

    def __init__(self, x, y, name="Animal", animal_type="unknown", animal_definition=None):
        definition = copy.deepcopy(animal_definition or ANIMAL_DEFINITIONS.get(animal_type, {}))
        resolved_name = name if name != "Animal" else definition.get("name", name)
        super().__init__(x, y, name=resolved_name)

        self.animal_type = animal_type
        self.animal_definition = definition
        self.behavior = definition.get("behavior", "wanders")

        self.dialogue = None
        self.social.personality = "animal"
        self.social.family_ties = {"description": "animal"}
        self.schedule.home_building_id = None
        self.schedule.work_building_id = None
        set_entity_profession(self, "Creature", reason="animal_spawn")
        self.economic.money = 0
        self.economic.npc_inventory = {}

        char_value = definition.get("char")
        if isinstance(char_value, int):
            self.char = char_value
        elif isinstance(char_value, str) and len(char_value) == 1:
            self.char = ord(char_value)
        else:
            self.char = get_animal_sprite(animal_type)
        self.color = definition.get("color", (255, 255, 255))

        self.combat.is_hostile_to_player = definition.get("hostile", False)
        self.combat.combat_behavior = definition.get("combat_behavior", "defensive")
        self.combat.base_attack_name = definition.get("base_attack_name", "fists")
        self.combat.base_attack_damage_dice = definition.get("base_attack_damage_dice", "1d3")
        self.combat.attack_range = definition.get("attack_range", self.combat.attack_range)
        if "max_hp" in definition:
            self.combat.max_hp = definition["max_hp"]
            self.combat.hp = self.combat.max_hp

        self.speech_volume = 3
        self.hearing_radius = definition.get("hearing_radius", DEFAULT_HEARING_RADIUS)
        self.speed = 2 if "prey" in definition else definition.get("speed", self.speed)

        self.is_tame = False
        self.tameness = 0
        self.owner = None

        self.is_being_ridden = False
        self.rider_id = None

        self.gender = random.choice(["male", "female"])
        self.is_pregnant = False
        self.pregnancy_timer = 0

        self.last_shorn_time = -100000
        self.pack_id = None
        self.ai_brain = create_behavior(definition)

        self.physical.hunger = 0
        self.physical.max_hunger = definition.get("max_hunger", 100)
        self.physical.temperature = definition.get("temperature", 37.0)
        self.physical.base_temperature_resistance = definition.get("base_temperature_resistance", 0.0)
        self.physical.clothing_insulation = definition.get("clothing_insulation", 0.0)
        self.physical.status_effects = []
        self.schedule.game_time_last_updated = 0

        self.schedule.current_task = "idle"
        self.schedule.previous_task = "idle"
        self.task_target_entity_id = None
        self.task_target_coords = None
        self.task_timer = 0
        self.woodcutter_search_radius = 5
        self.den_location = None

    def get_dialogue(self):
        return None
