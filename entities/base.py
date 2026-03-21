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
    body_parts_hp: dict[str, int] = field(default_factory=lambda: {"head": 5, "torso": 10, "left_arm": 5, "right_arm": 5, "left_leg": 5, "right_leg": 5})
    body_parts_max_hp: dict[str, int] = field(default_factory=lambda: {"head": 5, "torso": 10, "left_arm": 5, "right_arm": 5, "left_leg": 5, "right_leg": 5})
    toughness: str = "average"

    @property
    def hp(self) -> int:
        return sum(max(0, hp) for hp in self.body_parts_hp.values())

    @hp.setter
    def hp(self, value: int):
        current = self.hp
        if current == 0 and value > 0:
            # Reviving or healing from 0
            for part in self.body_parts_hp:
                self.body_parts_hp[part] = max(1, int(self.body_parts_max_hp[part] * (value / self.max_hp)))
            return
        elif current == 0:
            return

        ratio = value / current if current > 0 else 0
        for part in self.body_parts_hp:
            self.body_parts_hp[part] = min(self.body_parts_max_hp[part], int(self.body_parts_hp[part] * ratio))

        if value >= self.max_hp:
            for part in self.body_parts_hp:
                self.body_parts_hp[part] = self.body_parts_max_hp[part]

    @property
    def max_hp(self) -> int:
        return sum(self.body_parts_max_hp.values())

    @max_hp.setter
    def max_hp(self, value: int):
        # When max_hp is updated, distribute it proportionally
        current_max = self.max_hp
        if current_max == 0:
            # Defaults
            self.body_parts_max_hp = {"head": value//6, "torso": value//3, "left_arm": value//6, "right_arm": value//6, "left_leg": value//6, "right_leg": value//6}
            return

        ratio = value / current_max
        for part in self.body_parts_max_hp:
            self.body_parts_max_hp[part] = max(1, int(self.body_parts_max_hp[part] * ratio))

        # Ensure sum matches value (give remainder to torso)
        remainder = value - sum(self.body_parts_max_hp.values())
        if remainder != 0:
            self.body_parts_max_hp["torso"] += remainder

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
    family_ties: dict = field(default_factory=lambda: {"description": "none"})
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
    job_satisfaction: int = 50
    days_unemployed: int = 0
    work_performance: int = 50 # 0-100, tracks recent job performance

@dataclass
class Schedule:
    """Stores scheduling and task-related attributes for an entity."""
    home_building_id: int | None = None
    work_building_id: int | None = None
    current_destination_coords: tuple[int, int] | None = None
    current_path: list = field(default_factory=list)
    path_blocked_turns: int = 0
    last_blocked_position: tuple[int, int] | None = None
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
    discussed_event_ids: set[str] = field(default_factory=set)
    last_global_event_index_checked: int = -1
    help_needed: str | None = None
    long_term_memory: list[str] = field(default_factory=list)
    known_locations: dict[str, tuple[int, int]] = field(default_factory=dict)
    perceived_item_tiles: list[tuple[int, int]] = field(default_factory=list)

class NPC:
    """
    The base class for all non-player characters in the game.
    """
    def __init__(self, x, y, name="NPC", dialogue=None,
                 personality="normal", family_ties="none",
                 attitude_to_player="indifferent", player_id=None,
                 wealth_level="average"):
        self.x, self.y, self.name = x, y, name
        self.render_x, self.render_y = float(x), float(y) # For smooth animation
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
        if isinstance(family_ties, str):
            self.social.family_ties = {"description": family_ties}
        else:
            self.social.family_ties = family_ties
        self.economic.wealth_level = wealth_level

        if self.player_id:
            self._initialize_relationships(attitude_to_player, self.player_id)

        self.task_target_item_details: dict | None = None
        self.current_sub_task: str | None = None
        self.sub_task_target_coords: tuple[int, int] | None = None
        self.sub_task_timer, self.task_timer, self.leisure_timer = 0, 0, 0
        self.sub_task_zone_target: str | None = None
        self.current_sub_task_sequence_index: int = 0
        self.woodcutter_search_radius: int = 15
        self.task_target_entity_id: int | None = None
        self.task_context: str | None = None
        self.task_context_data: dict | str | None = None # Generic storage for task details
        self.den_location: tuple[int, int] | None = None
        self.desire_for_furniture, self.is_frightened = 0, False
        self.threat_source_ids: list[str] = []
        self.defense_bonus = 0

    @property
    def is_dead(self) -> bool:
        return self.physical.is_dead

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

        # Distribute damage to a random body part
        if effective_damage > 0:
            import random
            available_parts = [part for part, hp in self.combat.body_parts_hp.items() if hp > 0]
            if not available_parts:
                available_parts = list(self.combat.body_parts_hp.keys())

            target_part = random.choice(available_parts)
            self.combat.body_parts_hp[target_part] -= effective_damage
            if self.combat.body_parts_hp[target_part] < 0:
                # Overflow damage to torso if not torso, else just cap at 0
                overflow = -self.combat.body_parts_hp[target_part]
                self.combat.body_parts_hp[target_part] = 0
                if target_part != "torso":
                    self.combat.body_parts_hp["torso"] -= overflow
                    if self.combat.body_parts_hp["torso"] < 0:
                        self.combat.body_parts_hp["torso"] = 0

        # Add visual effect if world is passed
        if world:
            from engine import FloatingTextEffect
            world.visual_effects.append(FloatingTextEffect(self.x, self.y, str(effective_damage), color=(255, 50, 50)))

        # Death conditions: torso <= 0 or head <= 0
        if self.combat.body_parts_hp.get("torso", 0) <= 0 or self.combat.body_parts_hp.get("head", 0) <= 0 or self.combat.hp <= 0:
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
        self.combat = CombatStats(toughness="average",
                                  is_hostile_to_player=True, combat_behavior="aggressive",
                                  base_attack_name="bite", base_attack_damage_dice="1d6",
                                  attack_range=1)
        self.combat.max_hp = 15
        self.combat.hp = 15
        self.economic.profession = "Creature"
        self.dialogue = ["*Growl*", "*Snarl*"]
        self.speech_volume = 5
        self.hearing_radius = DEFAULT_HEARING_RADIUS + 2
