"""
This module defines the base classes for all entities in the game world,
including NPCs and specialized creature types.
"""
import random
from config import DEFAULT_SPEECH_VOLUME, DEFAULT_HEARING_RADIUS
from data.items import ITEM_DEFINITIONS

class NPC:
    """
    The base class for all non-player characters in the game.
    """
    def __init__(self, x, y, name="NPC", dialogue=None, personality="normal",
                 family_ties="none", attitude_to_player="indifferent", player_id=None):
        self.x = x
        self.y = y
        self.name = name
        self.char = ord('N')
        self.color = (0, 255, 0)
        self.speed = 1
        self.dialogue = dialogue if dialogue is not None else ["Hello!"]
        self.personality = personality
        self.family_ties = family_ties
        self.player_id = player_id
        self.last_speech_time = 0
        self.age = random.randint(18, 65)
        self.relationships = {}
        self.grudges: dict[int, list[str]] = {}
        if self.player_id:
            initial_score = 50
            if attitude_to_player == "friendly":
                initial_score = 75
            elif attitude_to_player == "hostile":
                initial_score = 25
            self.relationships[self.player_id] = initial_score

        self.knowledge = []
        self.known_events: dict[str, 'Event'] = {}
        self.reacted_to_event_ids: set[str] = set()
        self.last_global_event_index_checked: int = -1
        self.help_needed = None

        self.home_building_id = None
        self.work_building_id = None
        self.current_destination_coords = None
        self.current_path = []
        self.current_task = "idle"
        self.previous_task = "idle"
        self.game_time_last_updated = 0
        self.last_paid_day = 0

        self.wealth_level = "average"
        if self.wealth_level == "poor":
            self.money = random.randint(5, 20)
        elif self.wealth_level == "average":
            self.money = random.randint(20, 100)
        elif self.wealth_level == "wealthy":
            self.money = random.randint(100, 500)
        else:
            self.money = random.randint(10, 50)
        self.profession = "unemployed"
        self.original_char_before_sleep = self.char
        self.npc_inventory = {}

        self.hunger: int = 0
        self.max_hunger: int = 100
        self.thirst: int = 0
        self.max_thirst: int = 100

        self.max_hp = 20
        self.hp = self.max_hp
        self.toughness = "average"
        self.is_hostile_to_player = False
        self.is_dead = False
        self.id = id(self)

        self.combat_behavior = "defensive"
        self.base_attack_name = "fists"
        self.base_attack_damage_dice = "1d3"
        self.attack_range = 1
        self.target_entity_id = None

        self.speech_volume: int = DEFAULT_SPEECH_VOLUME

        self.equipped_weapon: str | None = None
        self.equipped_armor_body: str | None = None
        self.equipped_armor_head: str | None = None

        self.perceived_item_tiles: list[tuple[int,int]] = []
        self.task_target_item_details: dict | None = None

        self.current_sub_task: str | None = None
        self.sub_task_target_coords: tuple[int, int] | None = None
        self.sub_task_timer: int = 0
        self.task_timer: int = 0
        self.sub_task_zone_target: str | None = None
        self.current_sub_task_sequence_index: int = 0

        self.hearing_radius: int = DEFAULT_HEARING_RADIUS

        self.woodcutter_search_radius: int = 15

        self.task_target_entity_id: int | None = None
        self.task_context: str | None = None
        self.leisure_timer = 0

        self.temperature: float = 37.0
        self.base_temperature_resistance: float = 2.0
        self.clothing_insulation: float = 0.0
        self.status_effects: list[str] = []

        self.den_location: tuple[int, int] | None = None
        self.desire_for_furniture: int = 0
        self.is_frightened: bool = False
        self.threat_source_ids: list[int] = []

        self.fame: int = 0
        self.infamy: int = 0
        self.title: str = ""

    @property
    def attitude_to_player(self) -> str:
        """
        Dynamically determines the NPC's attitude towards the player based on relationship score.
        """
        if not self.player_id:
            return "neutral"
        score = self.relationships.get(self.player_id, 50)
        if score < 30:
            return "hostile"
        if score < 45:
            return "unfriendly"
        if score < 55:
            return "neutral"
        if score < 75:
            return "friendly"
        return "warm"

    def add_grudge(self, target_id: int, reason: str):
        """
        Adds a grudge against a target entity, significantly lowering the relationship score.
        """
        if target_id not in self.grudges:
            self.grudges[target_id] = []
        self.grudges[target_id].append(reason)
        self.relationships[target_id] = self.relationships.get(target_id, 50) - 40
        self.relationships[target_id] = max(0, self.relationships[target_id])

    def get_dialogue(self):
        """Returns the NPC's dialogue options."""
        return self.dialogue

    def recalculate_stats(self):
        """Recalculates NPC stats based on equipped items."""
        self.clothing_insulation = 0.0
        self.defense_bonus = 0
        if self.equipped_armor_body:
            item_def = ITEM_DEFINITIONS.get(self.equipped_armor_body)
            if item_def and "properties" in item_def:
                self.clothing_insulation += item_def["properties"].get("insulation", 0.0)
                self.defense_bonus += item_def["properties"].get("defense_bonus", 0)
        if self.equipped_armor_head:
            item_def = ITEM_DEFINITIONS.get(self.equipped_armor_head)
            if item_def and "properties" in item_def:
                self.clothing_insulation += item_def["properties"].get("insulation", 0.0)
                self.defense_bonus += item_def["properties"].get("defense_bonus", 0)


    def add_item(self, item_key: str, quantity: int = 1):
        """Adds an item to the NPC's inventory."""
        self.npc_inventory[item_key] = self.npc_inventory.get(item_key, 0) + quantity

    def has_item(self, item_key: str, quantity: int = 1) -> bool:
        """Checks if the NPC has a sufficient quantity of an item."""
        return self.npc_inventory.get(item_key, 0) >= quantity

    def remove_item(self, item_key_to_remove: str, quantity: int = 1) -> bool:
        """Removes an item from the NPC's inventory. Returns True if successful."""
        if self.npc_inventory.get(item_key_to_remove, 0) >= quantity:
            self.npc_inventory[item_key_to_remove] -= quantity
            if self.npc_inventory[item_key_to_remove] <= 0:
                del self.npc_inventory[item_key_to_remove]
            return True
        return False

    def take_damage(self, amount: int, world) -> bool:
        """
        Applies damage to the NPC, accounting for armor, and handles death.
        Returns True if the NPC was killed, False otherwise.
        """
        if self.is_dead:
            return False

        total_defense_bonus = 0
        if self.equipped_armor_body and self.equipped_armor_body in ITEM_DEFINITIONS:
            armor_def = ITEM_DEFINITIONS[self.equipped_armor_body]
            total_defense_bonus += armor_def.get("properties", {}).get("defense_bonus", 0)

        if self.equipped_armor_head and self.equipped_armor_head in ITEM_DEFINITIONS:
            armor_def = ITEM_DEFINITIONS[self.equipped_armor_head]
            total_defense_bonus += armor_def.get("properties", {}).get("defense_bonus", 0)

        effective_damage = max(0, amount - total_defense_bonus)
        self.hp -= effective_damage

        if self.hp <= 0:
            self.hp = 0
            self.is_dead = True
            return True
        if not self.is_hostile_to_player:
            self.is_hostile_to_player = True
            if self.profession != "Creature":
                world.add_message_to_chat_log(f"{self.name} becomes hostile!")
        return False

class DireWolf(NPC):
    """
    A specialized NPC subclass representing a Dire Wolf.
    """
    def __init__(self, x, y, name="Dire Wolf"):
        super().__init__(x, y, name=name)
        self.char = ord('w')
        self.color = (160, 160, 160)
        self.max_hp = 15
        self.hp = self.max_hp
        self.toughness = "average"
        self.is_hostile_to_player = True
        self.combat_behavior = "aggressive"
        self.base_attack_name = "bite"
        self.base_attack_damage_dice = "1d6"
        self.attack_range = 1
        self.profession = "Creature"
        self.dialogue = ["*Growl*", "*Snarl*"]
        self.speech_volume = 5
        self.hearing_radius = DEFAULT_HEARING_RADIUS + 2
