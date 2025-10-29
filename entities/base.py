"""
This module defines the base classes for all entities in the game world,
including NPCs and specialized creature types.
"""
import random
from dataclasses import dataclass, field
from config import DEFAULT_SPEECH_VOLUME, DEFAULT_HEARING_RADIUS
from data.items import ITEM_DEFINITIONS

@dataclass
class CombatStats:
    """Stores combat-related attributes for an entity."""
    max_hp: int = 20
    hp: int = 20
    toughness: str = "average"
    is_hostile_to_player: bool = False
    combat_behavior: str = "defensive"
    base_attack_name: str = "fists"
    base_attack_damage_dice: str = "1d3"
    attack_range: int = 1
    target_entity_id: int | None = None

@dataclass
class PhysicalState:
    """Stores physical attributes and states for an entity."""
    hunger: int = 0
    max_hunger: int = 100
    thirst: int = 0
    max_thirst: int = 100
    temperature: float = 37.0
    base_temperature_resistance: float = 2.0
    clothing_insulation: float = 0.0
    status_effects: list[str] = field(default_factory=list)
    is_dead: bool = False

@dataclass
class SocialState:
    """Stores social and reputational attributes for an entity."""
    personality: str = "normal"
    family_ties: str = "none"
    relationships: dict = field(default_factory=dict)
    grudges: dict[int, list[str]] = field(default_factory=dict)
    fame: int = 0
    infamy: int = 0
    title: str = ""

@dataclass
class EconomicState:
    """Stores economic attributes for an entity."""
    wealth_level: str = "average"
    money: int = 0
    npc_inventory: dict = field(default_factory=dict)
    profession: str = "unemployed"

@dataclass
class Schedule:
    """Stores scheduling and task-related attributes for an entity."""
    home_building_id: int | None = None
    work_building_id: int | None = None
    current_destination_coords: tuple[int, int] | None = None
    current_path: list = field(default_factory=list)
    current_task: str = "idle"
    previous_task: str = "idle"
    game_time_last_updated: int = 0
    last_paid_day: int = 0

@dataclass
class Equipment:
    """Stores entity equipment."""
    weapon: str | None = None
    body: str | None = None
    head: str | None = None

@dataclass
class Knowledge:
    """Stores entity knowledge and questing state."""
    known_events: dict[str, 'Event'] = field(default_factory=dict)
    reacted_to_event_ids: set[str] = field(default_factory=set)
    last_global_event_index_checked: int = -1
    help_needed: str | None = None
    long_term_memory: list[str] = field(default_factory=list)

class NPC:
    """
    The base class for all non-player characters in the game.
    """
    def __init__(self, x, y, name="NPC", dialogue=None,
                 personality="normal", family_ties="none",
                 attitude_to_player="indifferent", player_id=None,
                 wealth_level="average"):
        self.x, self.y, self.name = x, y, name
        self.char, self.color, self.speed, self.id = ord('N'), (0, 255, 0), 1, id(self)

        self.dialogue = dialogue if dialogue is not None else ["Hello!"]
        self.player_id = player_id
        self.last_speech_time = 0
        self.age = random.randint(18, 65)
        self.original_char_before_sleep = self.char
        self.speech_volume: int = DEFAULT_SPEECH_VOLUME
        self.hearing_radius: int = DEFAULT_HEARING_RADIUS

        # Conversation state
        self.conversation_partner_id: int | None = None
        self.current_conversation: list[str] = []
        self.conversation_cooldown: int = 0
        self.last_conversation_time: int = 0

        self.combat, self.physical, self.social = CombatStats(), PhysicalState(), SocialState()
        self.economic, self.schedule = EconomicState(), Schedule()
        self.equipment, self.knowledge = Equipment(), Knowledge()

        self.social.personality = personality
        self.social.family_ties = family_ties
        self.economic.wealth_level = wealth_level

        if self.player_id:
            self._initialize_relationships(attitude_to_player, self.player_id)

        self.perceived_item_tiles: list[tuple[int,int]] = []
        self.task_target_item_details: dict | None = None
        self.current_sub_task: str | None = None
        self.sub_task_target_coords: tuple[int, int] | None = None
        self.sub_task_timer, self.task_timer, self.leisure_timer = 0, 0, 0
        self.sub_task_zone_target: str | None = None
        self.current_sub_task_sequence_index: int = 0
        self.woodcutter_search_radius: int = 15
        self.task_target_entity_id: int | None = None
        self.task_context: str | None = None
        self.den_location: tuple[int, int] | None = None
        self.desire_for_furniture, self.is_frightened = 0, False
        self.threat_source_ids: list[str] = []
        self.defense_bonus = 0

    def _initialize_relationships(self, attitude, player_id):
        initial_score = 50
        if attitude == "friendly":
            initial_score = 75
        elif attitude == "hostile":
            initial_score = 25
        self.social.relationships[player_id] = initial_score

    @property
    def attitude_to_player(self) -> str:
        """
        Dynamically determines the NPC's attitude towards the player based on relationship score.
        """
        if not self.player_id:
            return "neutral"
        score = self.social.relationships.get(self.player_id, 50)
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
        if target_id not in self.social.grudges:
            self.social.grudges[target_id] = []
        self.social.grudges[target_id].append(reason)
        self.social.relationships[target_id] = self.social.relationships.get(target_id, 50) - 40
        self.social.relationships[target_id] = max(0, self.social.relationships[target_id])

    def get_dialogue(self):
        """Returns the NPC's dialogue options."""
        return self.dialogue

    def recalculate_stats(self):
        """Recalculates NPC stats based on equipped items."""
        self.physical.clothing_insulation = 0.0
        self.defense_bonus = 0
        if self.equipment.body:
            item_def = ITEM_DEFINITIONS.get(self.equipment.body)
            if item_def and "properties" in item_def:
                self.physical.clothing_insulation += item_def["properties"].get("insulation", 0.0)
                self.defense_bonus += item_def["properties"].get("defense_bonus", 0)
        if self.equipment.head:
            item_def = ITEM_DEFINITIONS.get(self.equipment.head)
            if item_def and "properties" in item_def:
                self.physical.clothing_insulation += item_def["properties"].get("insulation", 0.0)
                self.defense_bonus += item_def["properties"].get("defense_bonus", 0)

    def add_item(self, item_key: str, quantity: int = 1):
        """Adds an item to the NPC's inventory."""
        current_quantity = self.economic.npc_inventory.get(item_key, 0)
        self.economic.npc_inventory[item_key] = current_quantity + quantity

    def has_item(self, item_key: str, quantity: int = 1) -> bool:
        """Checks if the NPC has a sufficient quantity of an item."""
        return self.economic.npc_inventory.get(item_key, 0) >= quantity

    def remove_item(self, item_key_to_remove: str, quantity: int = 1) -> bool:
        """Removes an item from the NPC's inventory. Returns True if successful."""
        if self.has_item(item_key_to_remove, quantity):
            self.economic.npc_inventory[item_key_to_remove] -= quantity
            if self.economic.npc_inventory[item_key_to_remove] <= 0:
                del self.economic.npc_inventory[item_key_to_remove]
            return True
        return False

    def take_damage(self, amount: int, world) -> bool:
        """
        Applies damage to the NPC, accounting for armor, and handles death.
        Returns True if the NPC was killed, False otherwise.
        """
        if self.physical.is_dead:
            return False

        total_defense_bonus = 0
        if self.equipment.body and self.equipment.body in ITEM_DEFINITIONS:
            armor_def = ITEM_DEFINITIONS[self.equipment.body]
            total_defense_bonus += armor_def.get("properties", {}).get("defense_bonus", 0)
        if self.equipment.head and self.equipment.head in ITEM_DEFINITIONS:
            armor_def = ITEM_DEFINITIONS[self.equipment.head]
            total_defense_bonus += armor_def.get("properties", {}).get("defense_bonus", 0)

        effective_damage = max(0, amount - total_defense_bonus)
        self.combat.hp -= effective_damage

        if self.combat.hp <= 0:
            self.combat.hp = 0
            self.physical.is_dead = True
            return True
        if not self.combat.is_hostile_to_player and self.economic.profession != "Creature":
            self.combat.is_hostile_to_player = True
            world.add_message_to_chat_log(f"{self.name} becomes hostile!")
        return False

class DireWolf(NPC):
    """
    A specialized NPC subclass representing a Dire Wolf.
    """
    def __init__(self, x, y, name="Dire Wolf"):
        super().__init__(x, y, name=name)
        self.char, self.color = ord('w'), (160, 160, 160)
        self.combat = CombatStats(max_hp=15, hp=15, toughness="average",
                                  is_hostile_to_player=True, combat_behavior="aggressive",
                                  base_attack_name="bite", base_attack_damage_dice="1d6",
                                  attack_range=1)
        self.economic.profession = "Creature"
        self.dialogue = ["*Growl*", "*Snarl*"]
        self.speech_volume = 5
        self.hearing_radius = DEFAULT_HEARING_RADIUS + 2
