"""
This module defines the base classes for all entities in the game world,
including NPCs and specialized creature types.
"""
import random
import re
from dataclasses import dataclass, field
from config import DEFAULT_SPEECH_VOLUME, DEFAULT_HEARING_RADIUS
from data.dawnlike import ANIMAL_SPRITES, get_human_sprite
from data.items import ITEM_DEFINITIONS
from simulation.careers import CareerState, normalize_profession, set_entity_profession

PLACEHOLDER_FAMILY_NAME_RE = re.compile(r"^(Mother|Father|Brother|Sister)\s+Family_\d+$", re.IGNORECASE)

@dataclass
class CombatStats:
    """Stores combat-related attributes for an entity."""
    body_parts_hp: dict = field(default_factory=lambda: {"head": 5, "torso": 10, "left_arm": 5, "right_arm": 5, "left_leg": 5, "right_leg": 5})
    body_parts_max_hp: dict = field(default_factory=lambda: {"head": 5, "torso": 10, "left_arm": 5, "right_arm": 5, "left_leg": 5, "right_leg": 5})
    toughness: str = "average"
    is_hostile_to_player: bool = False
    combat_behavior: str = "defensive"
    base_attack_name: str = "fists"
    base_attack_damage_dice: str = "1d3"
    attack_range: int = 1
    target_entity_id: int | None = None
    last_hit_part: str | None = None

    @property
    def max_hp(self):
        return sum(self.body_parts_max_hp.values())

    @max_hp.setter
    def max_hp(self, value):
        current_max = self.max_hp
        if current_max == 0:
            return
        ratio = value / current_max
        for part in self.body_parts_max_hp:
            self.body_parts_max_hp[part] = max(1, int(self.body_parts_max_hp[part] * ratio))
        diff = value - sum(self.body_parts_max_hp.values())
        if diff != 0:
            self.body_parts_max_hp["torso"] += diff

    @property
    def hp(self):
        return sum(self.body_parts_hp.values())

    @hp.setter
    def hp(self, value):
        current_hp = self.hp
        if value <= 0:
            for part in self.body_parts_hp:
                self.body_parts_hp[part] = 0
            return
        if value == self.max_hp:
            self.body_parts_hp = self.body_parts_max_hp.copy()
            return
        ratio = value / current_hp if current_hp > 0 else 0
        for part in self.body_parts_hp:
            self.body_parts_hp[part] = int(self.body_parts_hp[part] * ratio)
        diff = value - sum(self.body_parts_hp.values())
        if diff != 0:
            self.body_parts_hp["torso"] += diff

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
        self.age = random.randint(18, 65)
        self.gender = random.choice(["male", "female"])
        self.char = get_human_sprite(gender=self.gender, profession="Unemployed", age=self.age)
        self.color, self.speed, self.id = (0, 255, 0), 1, id(self)

        self.dialogue = dialogue if dialogue is not None else ["Hello!"]
        self.player_id = player_id
        self.last_speech_time = 0
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
        self.career = CareerState()

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
        set_entity_profession(self, self.economic.profession, reason="spawn")

    @property
    def is_dead(self) -> bool:
        return self.physical.is_dead

    def is_placeholder_family_name(self) -> bool:
        return bool(self.name and PLACEHOLDER_FAMILY_NAME_RE.match(str(self.name)))

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

    def get_relationship_to(self, viewer) -> str | None:
        """Return this entity's relationship to a viewer, if known."""
        if not viewer or getattr(viewer, "id", None) == self.id:
            return None

        ties = getattr(self.social, "family_ties", {}) or {}
        relation = str(ties.get("relation_to_player", "")).strip().lower()
        if relation:
            return relation

        viewer_social = getattr(viewer, "social", None)
        viewer_ties = getattr(viewer_social, "family_ties", {}) or {}
        viewer_id = getattr(viewer, "id", None)

        if viewer_ties.get("mother_id") == self.id:
            return "mother"
        if viewer_ties.get("father_id") == self.id:
            return "father"
        if self.id in viewer_ties.get("sibling_ids", []):
            return "sibling"
        if viewer_ties.get("partner_id") == self.id:
            return "partner"
        if ties.get("child_id") == viewer_id:
            return "parent"
        if ties.get("son_id") == viewer_id or ties.get("daughter_id") == viewer_id:
            inferred = str(self.name).split(" ", 1)[0].strip().lower()
            if inferred in {"mother", "father"}:
                return inferred
            return "parent"
        if ties.get("sibling_id") == viewer_id:
            inferred = str(self.name).split(" ", 1)[0].strip().lower()
            if inferred in {"brother", "sister"}:
                return inferred
            return "sibling"
        return None

    def get_relationship_label(self, viewer) -> str:
        relation = self.get_relationship_to(viewer)
        if not relation:
            return ""
        label_map = {
            "mother": "Mother",
            "father": "Father",
            "brother": "Brother",
            "sister": "Sister",
            "sibling": "Sibling",
            "parent": "Parent",
            "partner": "Partner",
            "child": "Child",
        }
        return label_map.get(relation, relation.replace("_", " ").title())

    def get_title_label(self) -> str:
        profession = str(getattr(getattr(self, "economic", None), "profession", "") or "").strip()
        if hasattr(self, "career"):
            if self.career.current_role != normalize_profession(profession):
                self.career.set_role(profession)
            title = self.career.display_title()
            if title:
                return title
        if not profession or profession in {"Unemployed", "Creature", "unemployed"}:
            return ""
        return profession

    def get_display_name(self, viewer=None, include_relationship: bool = False) -> str:
        """Return a player-facing display name for this entity."""
        if viewer and getattr(viewer, "id", None) == self.id:
            return "You"

        original_name = str(getattr(self, "name", "Unknown")).strip()
        raw_name = original_name.replace("_", " ").strip()
        relation_label = self.get_relationship_label(viewer)
        if self.is_placeholder_family_name() and relation_label:
            base_name = relation_label
        else:
            base_name = raw_name or "Unknown"

        title_label = self.get_title_label()
        if title_label:
            base_name = f"{base_name} ({title_label})"

        if include_relationship and relation_label and base_name != relation_label:
            return f"{base_name} [{relation_label}]"
        return base_name

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

        remaining_damage = effective_damage
        import random
        if remaining_damage > 0:
            hit_part = random.choice(list(self.combat.body_parts_hp.keys()))
            self.combat.last_hit_part = hit_part
            if self.combat.body_parts_hp[hit_part] >= remaining_damage:
                self.combat.body_parts_hp[hit_part] -= remaining_damage
                remaining_damage = 0
            else:
                remaining_damage -= self.combat.body_parts_hp[hit_part]
                self.combat.body_parts_hp[hit_part] = 0
                for part in ["torso", "head", "left_arm", "right_arm", "left_leg", "right_leg"]:
                    if remaining_damage <= 0:
                        break
                    if self.combat.body_parts_hp[part] > 0:
                        if self.combat.body_parts_hp[part] >= remaining_damage:
                            self.combat.body_parts_hp[part] -= remaining_damage
                            remaining_damage = 0
                        else:
                            remaining_damage -= self.combat.body_parts_hp[part]
                            self.combat.body_parts_hp[part] = 0

            # Check for broken legs
            if self.combat.body_parts_hp.get("left_leg", 1) <= 0 or self.combat.body_parts_hp.get("right_leg", 1) <= 0:
                if "broken_leg" not in self.physical.status_effects:
                    self.physical.status_effects.append("broken_leg")
                    if world:
                        world.add_message_to_chat_log(f"{self.name}'s leg is broken!")

        # Add visual effect if world is passed
        if world:
            from engine import FloatingTextEffect
            world.visual_effects.append(FloatingTextEffect(self.x, self.y, str(effective_damage), color=(255, 50, 50)))

        if self.combat.hp <= 0:
            self.combat.hp = 0
            self.physical.is_dead = True
            return True
        if not self.combat.is_hostile_to_player and self.economic.profession != "Creature":
            self.combat.is_hostile_to_player = True
            if world:
                world.add_message_to_chat_log(f"{self.name} becomes hostile!")
        return False

class DireWolf(NPC):
    """
    A specialized NPC subclass representing a Dire Wolf.
    """
    def __init__(self, x, y, name="Dire Wolf"):
        super().__init__(x, y, name=name)
        self.char, self.color = ANIMAL_SPRITES["dire_wolf"], (160, 160, 160)
        self.combat = CombatStats(toughness="average",
                                  is_hostile_to_player=True, combat_behavior="aggressive",
                                  base_attack_name="bite", base_attack_damage_dice="1d6",
                                  attack_range=1)
        self.combat.max_hp = 15
        self.combat.hp = 15
        set_entity_profession(self, "Creature", reason="direwolf_spawn")
        self.dialogue = ["*Growl*", "*Snarl*"]
        self.speech_volume = 5
        self.hearing_radius = DEFAULT_HEARING_RADIUS + 2
