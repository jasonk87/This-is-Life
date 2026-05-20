from simulation.systems.interaction import ActionIntent, InteractionResolver
from simulation.systems.task_types import TaskType
# engine.py
import math
import random
import itertools
import re
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from runtime_compat import genai, np, requests
from tcod_compat import tcod, libtcodpy
import time
import pickle
import os
import uuid
from typing import Any
from simulation.activity import (
    ensure_activity_state,
    start_activity,
)
from entities.base import (
    CombatStats,
    DireWolf,
    EconomicState,
    Equipment,
    NPC,
    PhysicalState,
    Schedule,
    SocialState,
) # Added DireWolf
from entities.animal import Animal
from entities.items import Inventory, ItemReference, roll_crafted_item_quality
from entities.social import AspirationType, KnowledgeComponent, MemoryEvent, TravelComponent
from data.animals import ANIMAL_DEFINITIONS
from entities.tree import Tree, OakTree, AppleTree, PearTree # Tree classes seem partially defined/used.
from config import (
    WORLD_WIDTH, WORLD_HEIGHT, POI_DENSITY, CHUNK_SIZE,
    NOISE_SCALE, NOISE_OCTAVES, NOISE_PERSISTENCE, NOISE_LACUNARITY,
    ELEVATION_DEEP_WATER, ELEVATION_WATER, ELEVATION_MOUNTAIN, ELEVATION_SNOW,
    # NPC Scheduling Configs
    USE_LLM_FOR_SCHEDULES, DAY_LENGTH_TICKS, NPC_SCHEDULE_UPDATE_INTERVAL,
    WORK_START_TIME_RATIO, WORK_END_TIME_RATIO,
    # Reputation Configs
    INITIAL_CRIMINAL_POINTS, INITIAL_HERO_POINTS,
    REP_CRIMINAL, REP_HERO,
    # FOV and Light Level Configs
    DAY_LENGTH_TICKS, LIGHT_LEVEL_PERIODS,
    FOV_RADIUS_DAY, FOV_RADIUS_DUSK_DAWN, FOV_RADIUS_NIGHT, FOV_RADIUS_PITCH_BLACK,
    # Auditory Perception Configs
    DEFAULT_HEARING_RADIUS, DEFAULT_SPEECH_VOLUME,
    # Abstract Simulation Configs
    ABSTRACT_SIMULATION_DISTANCE_CHUNKS,
    # Season and Temperature Configs
    DAYS_PER_SEASON,
    SEASON_TEMPERATURE_MODIFIERS,
    BIOME_TEMPERATURE_MODIFIERS,
    TIME_OF_DAY_TEMPERATURE_MODIFIERS,
    ENABLE_OLLAMA_CONNECTION,
    LLM_BACKEND, ENABLE_LLM_CONNECTION, GOOGLE_API_KEY
)

from data.tiles import TILE_DEFINITIONS, COLORS # For TILE_DEFINITIONS
from tile_types import Tile # For Tile class
from entities.tree import Tree # For isinstance check
from data.items import ITEM_DEFINITIONS # For checking yielded resources
from data.items import ITEM_DEFINITIONS
from data.decorations import DECORATION_ITEM_DEFINITIONS
from data.prompts import LLM_PROMPTS, OLLAMA_ENDPOINT
from data.professions import PROFESSIONS, get_profession_data, get_sub_task_data
from data.decorations import DECORATION_ITEM_DEFINITIONS as ALL_DECORATION_DEFS
from tile_types import Tile as BaseTileType
from data.quests import QUEST_DEFINITIONS # Import quest definitions
from data.environment import WEATHER_DEFINITIONS
from data.construction import CONSTRUCTION_RECIPES
from data.dawnlike import get_animal_sprite, get_human_sprite
from services.llm_gossip import AsyncLLMGossipService
from ui_requests import (
    UIRequest,
    close_dialogue_request,
    close_trade_request,
    open_dialogue_request,
    open_trade_request,
)
from presentation.text_formatter import WorldTextFormatter
from presentation.ambient_speech import (
    add_ambient_speech,
    add_dialogue_line_as_ambient_speech,
    ensure_ambient_speech_state,
)
from presentation.dialogue_surface import (
    build_dialogue_topic_from_fact,
    get_contextual_dialogue_lines,
    remember_dialogue_topic_spoken,
    render_history_fact_dialogue_line,
)
from simulation.systems.ambient_info import (
    choose_ambient_conversation_pair,
    choose_shareable_fact,
    mark_ambient_conversation_started,
    mark_share_cooldowns,
    share_known_fact,
)
from simulation.social_scene import (
    choose_scene_interaction_pair,
    choose_strongest_social_scene,
    create_public_event_seed_from_record,
    find_scene_for_pair,
    record_scene_topic,
    share_fact_with_scene_overhearers,
    update_social_scenes,
)
from simulation.careers import (
    CareerState,
    entity_has_any_profession,
    entity_has_capability,
    entity_has_profession,
    infer_career_level,
    get_roles_for_building,
    normalize_profession,
    resolve_profession_for_building,
    set_entity_profession,
)
from simulation.history import (
    BirthRecord,
    Book,
    CrimeRecord,
    DeathRecord,
    EmploymentRecord,
    Event,
    HistoryLedger,
    MarriageRecord,
    MigrationRecord,
)
from simulation.records import ChronicleArchive
from simulation.knowledge import KnowledgeSystem
from simulation.skills import SkillTracker
from simulation.systems.survival import (
    update_npc_environmental_tasks as update_npc_environmental_tasks_system,
    update_player_needs as update_player_needs_system,
)
from simulation.systems.medical import update_npc_medical_state
from simulation.systems.perception import update_npc_sound_perception
from simulation.systems.incidents import (
    create_harmful_incident,
    propagate_harmful_incident_gossip,
    record_incident_attribution,
    run_traveler_arrival_incident_sharing,
    tell_harmful_incident_claim,
    update_local_incident_opinion,
)
from simulation.systems.scheduling import (
    run_npc_humanoid_scheduling_flow,
    run_npc_traveling_merchant_policy,
)
from simulation.systems.social_reaction import evaluate_social_reaction_stance
from simulation.systems.conversation_foundation import (
    choose_structured_conversation_outcome,
    evaluate_conversation_foundation,
)
from simulation.systems.conversation_topics import (
    apply_conversation_topic,
    select_conversation_topic,
)
from simulation.systems.tick import run_world_tick
from simulation.ecology import EcologySystem, WILDLIFE_SPECIES
from simulation.systems.work import update_npc_work_sub_tasks
from simulation.world_model import (
    Building,
    Chunk,
    ConstructionBlueprint,
    EmploymentTask,
    LandClaim,
    PoliticalWarrant,
    PoliticsTracker,
    Stockpile,
    ReserveTarget,
    ProductionTask,
    DecisionExplanation,
    WorldDebugSnapshot,
    CampfireRuntimeState,
    WorkshopRuntimeState,
    Ruin,
    TownBoard,
    Village,
    WorldAtlas,
)
from work_subtasks import (
    CompletedWorkSubTaskCommand,
    DefaultProduceOutputSubTaskCommand,
    create_completed_work_sub_task_commands,
)
from world_generation import WorldGenerator

VILLAGE_BUILDING_PROJECTS = {
    "clinic": {
        "cost": {"raw_log": 40, "stone_chunk": 10},
        "width": 7,
        "height": 6,
        "category": "civic_workplace",
        "description": "A place for healing and treatment."
    },
    "house": {
        "cost": {"raw_log": 50},
        "width": 7,
        "height": 7,
        "category": "residential",
        "description": "A new home for villagers."
    },
    "farm": {
        "cost": {"raw_log": 30, "stone_chunk": 10},
        "width": 8,
        "height": 6,
        "category": "agricultural_workplace",
        "description": "A farm to produce food."
    },
    "warehouse": {
        "cost": {"raw_log": 35, "stone_chunk": 8},
        "width": 8,
        "height": 6,
        "category": "storage_workplace",
        "description": "Shared storage for growing towns and businesses."
    },
    "workshop": {
        "cost": {"raw_log": 25, "stone_chunk": 6, "wooden_plank": 8},
        "width": 6,
        "height": 5,
        "category": "commercial_workplace",
        "description": "A small flexible workplace for business expansion."
    }
}

import json

if GOOGLE_API_KEY and hasattr(genai, "configure"):
    genai.configure(api_key=GOOGLE_API_KEY)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("google_genai.models").setLevel(logging.WARNING)

FAMILY_LAST_NAMES = [
    "Hart", "Miller", "Bennett", "Rowan", "Turner", "Hale", "Mercer", "Wilder",
    "Graves", "Sawyer", "Fletcher", "Briar",
]
FAMILY_FIRST_NAMES = {
    "male": ["Elias", "Jonah", "Caleb", "Owen", "Silas", "Theo", "Nathan", "Micah"],
    "female": ["Elara", "Mara", "Nora", "Clara", "Tessa", "Lena", "Iris", "Ada"],
}
PLACEHOLDER_FAMILY_NAME_RE = re.compile(r"^(Mother|Father|Brother|Sister)\s+Family_\d+$", re.IGNORECASE)
BACKGROUND_LLM_PENDING = object()

class Quest:
    """A class to represent an active quest."""
    def __init__(self, quest_id: str, title: str, description: str, quest_type: str, quest_giver_id: int):
        self.id = quest_id
        self.title = title
        self.description = description
        self.type = quest_type
        self.quest_giver_id = quest_giver_id
        self.progress = 0
        # For 'fetch' quests
        self.item_key: str | None = None
        self.required_count: int = 0
        # For 'kill' quests
        self.target_name_prefix: str | None = None
        self.required_kills: int = 0

class VisualEffect:
    """Base class for engine-side visual effect state."""
    effect_type = "base"
    def update(self, dt: float) -> bool:
        """Updates the effect. Returns True if the effect is finished."""
        return True

class FloatingTextEffect(VisualEffect):
    """Floating text animation for damage, healing, etc."""
    effect_type = "floating_text"
    def __init__(self, x, y, text, color=(255, 255, 255), duration=1.0, speed=2.0):
        self.x = float(x)
        self.y = float(y)
        self.text = text
        self.color = color
        self.duration = duration
        self.speed = speed
        self.elapsed = 0.0

    def update(self, dt: float) -> bool:
        self.y -= self.speed * dt
        self.elapsed += dt
        return self.elapsed >= self.duration


def _ambient_social_float_text(scene_indicator) -> str:
    if scene_indicator is None:
        return "*murmurs*"
    if scene_indicator.kind in {"warning", "accusation"} or scene_indicator.tone in {"tense", "fearful"}:
        return "*warning*"
    if scene_indicator.kind == "funeral" or scene_indicator.tone == "grieving":
        return "*hushed*"
    if scene_indicator.kind == "celebration" or scene_indicator.tone == "celebratory":
        return "*cheers*"
    if scene_indicator.kind == "market_concern" or scene_indicator.tone == "concerned":
        return "*concern*"
    if scene_indicator.participant_count >= 4:
        return "*chatter*"
    return "*murmurs*"


class ProjectileEffect(VisualEffect):
    """A simple projectile animation."""
    effect_type = "projectile"
    def __init__(self, start_x, start_y, end_x, end_y, char='*', color=(255, 255, 0), speed=15.0):
        self.x = float(start_x)
        self.y = float(start_y)
        self.start_x = float(start_x)
        self.start_y = float(start_y)
        self.end_x = float(end_x)
        self.end_y = float(end_y)
        self.char = char
        self.color = color
        self.speed = speed
        self.total_dist = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)
        if self.total_dist == 0: self.total_dist = 0.001
        self.dx = (end_x - start_x) / self.total_dist
        self.dy = (end_y - start_y) / self.total_dist
        self.traveled = 0.0

    def update(self, dt: float) -> bool:
        dist_step = self.speed * dt
        self.x += self.dx * dist_step
        self.y += self.dy * dist_step
        self.traveled += dist_step
        return self.traveled >= self.total_dist


COMPLETED_WORK_SUB_TASK_COMMANDS: dict[str, CompletedWorkSubTaskCommand] = create_completed_work_sub_task_commands()
NPC_WORK_TOOL_TYPES = {
    "chop_trees": "axe",
    "mine_ore": "pickaxe",
    "till_soil": "hoe",
    "plant_seeds": "hoe",
    "harvest_crops": "hoe",
}

@dataclass
class PlayerState:
    is_sitting: bool = False
    is_sleeping: bool = False
    sitting_on_object_at: tuple[int, int] | None = None
    is_jailed: bool = False
    jail_cell_coords: tuple[int, int] | None = None
    jail_time_remaining: int = 0
    is_riding: bool = False
    riding_animal_id: int | None = None
    last_dx: int = 0
    last_dy: int = -1
    original_char: int = 0xE000
    current_path: list[tuple[int, int]] = field(default_factory=list)
    move_cooldown: int = 0


class Player:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.render_x = float(x)
        self.render_y = float(y)
        self.name = "Player"
        self.first_name = "Player"
        self.char = get_human_sprite(is_player=True)
        self.color = COLORS["player_fg"]
        self.id = id(self)  # Simple unique ID for player

        # Components
        self.physical = PhysicalState()
        self.combat = CombatStats()
        self.social = SocialState()
        self.economic = EconomicState()
        self.equipment = Equipment()
        self.knowledge = KnowledgeComponent()
        self.state = PlayerState()
        self.schedule = Schedule()
        self.career = CareerState()
        self.skills = SkillTracker()
        ensure_activity_state(self)

        self.state.original_char = self.char
        self.combat.hp = self.combat.max_hp
        self.social.reputation = {REP_CRIMINAL: INITIAL_CRIMINAL_POINTS, REP_HERO: INITIAL_HERO_POINTS}
        self.social.family_ties = {}
        self.economic.money = 100
        set_entity_profession(self, self.economic.profession, reason="spawn")

    @property
    def melee_skill(self) -> int:
        return self.skills.get_level("melee", default_level=5)

    @melee_skill.setter
    def melee_skill(self, value: int) -> None:
        self.skills.levels["melee"] = max(1, int(value))

    def gain_skill_experience(self, skill_name: str, amount: int, *, default_level: int = 1) -> dict:
        result = self.skills.gain_experience(skill_name, amount, default_level=default_level)
        if result.get("leveled_up") and hasattr(self, "world_ref") and self.world_ref:
            pretty_name = skill_name.replace("_", " ").title()
            self.world_ref.add_message_to_chat_log(f"Your {pretty_name} skill rises to {result['new_level']}.")
        return result

    def get_relationship_to(self, viewer) -> str | None:
        return None

    def get_relationship_label(self, viewer) -> str:
        return ""

    def get_title_label(self) -> str:
        profession = str(getattr(getattr(self, "economic", None), "profession", "") or "").strip()
        if self.career.current_role != normalize_profession(profession):
            self.career.set_role(profession)
        title = self.career.display_title()
        if title:
            return title
        if profession and profession not in {"Unemployed", "Creature", "unemployed"}:
            return profession
        return ""

    def get_display_name(self, viewer=None, include_relationship: bool = False) -> str:
        if viewer and getattr(viewer, "id", None) == self.id:
            return "You"

        base_name = str(getattr(self, "name", "Player")).replace("_", " ").strip() or "Player"
        title_label = self.get_title_label()
        if title_label:
            return f"{base_name} ({title_label})"
        return base_name

    def is_identity_concealed(self) -> bool:
        head_item_key = self.equipment.equipped_armor.get("head")
        if not head_item_key:
            return False
        return bool(ITEM_DEFINITIONS.get(head_item_key, {}).get("properties", {}).get("conceals_identity", False))


    def take_damage(self, amount: int, world=None) -> int:
        """Applies damage to the player after accounting for armor, returns actual damage dealt."""
        effective_damage = max(0, amount - self.combat.defense_bonus)

        remaining_damage = effective_damage
        if remaining_damage > 0:
            import random
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
                        world.add_message_to_chat_log("Your leg is broken!")

        world_ref = world if world else getattr(self, 'world_ref', None)

        if world_ref:
            world_ref.visual_effects.append(FloatingTextEffect(self.x, self.y, str(effective_damage), color=(255, 0, 0)))

        if self.combat.hp <= 0 and world_ref:
            world_ref.game_state = "PLAYER_DEAD"

        return effective_damage

    def equip_armor(self, item_key: str):
        item_def = ITEM_DEFINITIONS.get(item_key)
        if not item_def or "armor" not in item_def.get("item_type_tags", []):
            self.world_ref.add_message_to_chat_log("You can't equip that.")
            return

        slot = item_def.get("equip_slot")
        if not slot or slot not in self.equipment.equipped_armor:
            self.world_ref.add_message_to_chat_log("That item doesn't have a valid equip slot.")
            return

        # Unequip current item in that slot, if any
        if self.equipment.equipped_armor.get(slot):
            self.unequip_armor(slot)

        self.equipment.equipped_armor[slot] = item_key
        self.world_ref.add_message_to_chat_log(f"You equip the {item_def['name']}.")
        self.recalculate_stats()

    def unequip_armor(self, slot: str):
        if slot in self.equipment.equipped_armor and self.equipment.equipped_armor[slot]:
            item_key = self.equipment.equipped_armor[slot]
            item_def = ITEM_DEFINITIONS.get(item_key)
            self.equipment.equipped_armor[slot] = None
            self.world_ref.add_message_to_chat_log(f"You unequip the {item_def['name']}.")
            self.recalculate_stats()

    def recalculate_stats(self):
        """Recalculates player stats based on equipped items."""
        self.physical.clothing_insulation = 0.0
        self.combat.defense_bonus = 0
        for slot, item_key in self.equipment.equipped_armor.items():
            if item_key:
                item_def = ITEM_DEFINITIONS.get(item_key)
                if item_def and "properties" in item_def:
                    self.physical.clothing_insulation += item_def["properties"].get("insulation", 0.0)
                    self.combat.defense_bonus += item_def["properties"].get("defense_bonus", 0)

    def add_item(self, item_key_to_add: str, quantity: int = 1, initial_durability: int | None = None, item_reference: ItemReference | None = None):
        if item_reference is not None:
            for _ in range(max(1, quantity)):
                self.economic.inventory.add_item_reference(item_reference)
            return

        item_def = ITEM_DEFINITIONS.get(item_key_to_add, {})
        is_stackable = item_def.get("stackable", False)

        if not is_stackable and initial_durability is not None:
            for _ in range(max(1, quantity)):
                ref = ItemReference(item_key_to_add, current_durability=initial_durability)
                self.economic.inventory.add_item_reference(ref)
        else:
            self.economic.inventory.add_item(item_key_to_add, quantity)

    def remove_item(self, item_key_to_remove: str, quantity: int = 1, specific_instance_index: int | None = None) -> bool:
        if specific_instance_index is not None:
            refs = list(self.economic.inventory.iter_item_references())
            if 0 <= specific_instance_index < len(refs):
                target_ref = refs[specific_instance_index]
                if target_ref.key == item_key_to_remove:
                    self.economic.inventory.extract_item_reference(target_ref)
                    return True
        return self.economic.inventory.remove_item(item_key_to_remove, quantity)

    def has_item(self, item_key_to_check: str, quantity: int = 1) -> bool:
        return self.economic.inventory.has_item(item_key_to_check, quantity)

    def get_item_instance_indices(self, item_key_to_find: str) -> list[int]:
        """Returns a list of indices for all instances of a given non-stackable item key."""
        refs = list(self.economic.inventory.iter_item_references())
        return [i for i, ref in enumerate(refs) if ref.key == item_key_to_find]

    def get_item_by_index(self, index: int) -> dict | None:
        """DEPRECATED - returns a mock dictionary wrapper over the reference to avoid breaking old callers."""
        refs = list(self.economic.inventory.iter_item_references())
        if 0 <= index < len(refs):
            ref = refs[index]
            return {"key": ref.key, "item_reference": ref, "durability": ref.current_durability, "max_durability": ref.max_durability}
        return None

    def get_item_reference(self, item_key_to_find: str) -> ItemReference | None:
        return self.economic.inventory.get_item_reference(item_key_to_find)

    def add_item_reference(self, item_reference: ItemReference | None) -> bool:
        return self.economic.inventory.add_item_reference(item_reference)

    def pop_item_reference(self, item_key_to_find: str) -> ItemReference | None:
        return self.economic.inventory.pop_item_reference(item_key_to_find)

    def adjust_reputation(self, rep_type: str, amount: int):
        """Adjusts the player's reputation of a specific type."""
        if rep_type in self.social.reputation:
            self.social.reputation[rep_type] += amount
            # Could add clamping here if REP_MIN/MAX_VALUE were used
            # self.social.reputation[rep_type] = max(REP_MIN_VALUE, min(self.social.reputation[rep_type], REP_MAX_VALUE))
            # print(f"Player reputation updated: {rep_type} changed by {amount} to {self.social.reputation[rep_type]}") # For now, print to console
            if hasattr(self, 'world_ref') and self.world_ref: # Access world_ref if it exists
                self.world_ref.add_message_to_chat_log(f"Reputation: {rep_type} {amount:+} (Total: {self.social.reputation[rep_type]})")
        else:
            # # print(f"Warning: Tried to adjust unknown reputation type '{rep_type}'")
            if hasattr(self, 'world_ref') and self.world_ref:
                 self.world_ref.add_message_to_chat_log(f"Warning: Tried to adjust unknown reputation type '{rep_type}'")

@dataclass
class ChunkManager:
    chunk_size: int
    chunk_width: int
    chunk_height: int
    player_chunk: tuple[int, int] = (0, 0)
    active_chunks: set[tuple[int, int]] = field(default_factory=set)

    def get_chunk_coords(self, x: int, y: int) -> tuple[int, int]:
        return int(x) // self.chunk_size, int(y) // self.chunk_size

    def compute_active_chunks(self, center_chunk: tuple[int, int]) -> set[tuple[int, int]]:
        center_x, center_y = center_chunk
        chunks: set[tuple[int, int]] = set()
        for chunk_y in range(center_y - 1, center_y + 2):
            for chunk_x in range(center_x - 1, center_x + 2):
                if 0 <= chunk_x < self.chunk_width and 0 <= chunk_y < self.chunk_height:
                    chunks.add((chunk_x, chunk_y))
        return chunks

    def update_for_player(self, x: int, y: int, *, force: bool = False) -> bool:
        new_chunk = self.get_chunk_coords(x, y)
        if not force and new_chunk == self.player_chunk:
            return False
        self.player_chunk = new_chunk
        self.active_chunks = self.compute_active_chunks(new_chunk)
        return True

    def is_chunk_active(self, chunk_coords: tuple[int, int]) -> bool:
        return chunk_coords in self.active_chunks


class World:
    @property
    def all_npcs(self):
        """Returns an iterator over all NPCs (village + world)."""
        return itertools.chain(self.village_npcs, self.npcs)

    """World class now uses a generator for a more complex map."""
    def __init__(self, seed=None, player_first_name: str | None = None):
        if seed is not None:
            random.seed(seed)
        self.chat_log = [] # Stores chat messages
        self.chunk_width = WORLD_WIDTH // CHUNK_SIZE
        self.chunk_height = WORLD_HEIGHT // CHUNK_SIZE

        self.interaction_resolver = InteractionResolver()
        self.player = Player(WORLD_WIDTH // 2, WORLD_HEIGHT // 2)
        if player_first_name:
            chosen_name = player_first_name.strip()
            if chosen_name:
                self.player.first_name = chosen_name
                self.player.name = chosen_name
        self.player.world_ref = self
        self.text = WorldTextFormatter(self)
        self.generator = WorldGenerator(self.chunk_width, self.chunk_height, seed=seed)
        self.atlas = WorldAtlas()
        self.history = HistoryLedger(event_limit=200)
        self.records = ChronicleArchive(self.history)
        self.knowledge_system = KnowledgeSystem(self.records)
        self.politics = PoliticsTracker()
        self.ecology = EcologySystem()
        self.chunks = self._initialize_chunks()
        self.npcs = []
        self.village_npcs = []
        self.villages = self.atlas.villages
        self.buildings_by_id = self.atlas.buildings_by_id
        self.regions_by_id = self.atlas.regions_by_id
        self.mouse_x = 0
        self.mouse_y = 0
        self.game_state = "PLAYING"
        self.entities_by_chunk = {} # Map (chunk_x, chunk_y) -> set(npc_id)
        self.game_time = 0
        self.last_talked_to_npc = None # Store the NPC targeted by 'T'alk (may be superseded by menu target)
        self.needs_text_input = False
        self._llm_warning_issued = False
        self._background_llm_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="world-llm")
        self._background_llm_tasks = {}
        self._gossip_llm_service = AsyncLLMGossipService()
        self.chunk_manager = ChunkManager(CHUNK_SIZE, self.chunk_width, self.chunk_height)
        self.last_abstract_simulation_hour = -1
        self.last_macro_daily_day = -1

        # Season and Temperature
        self.seasons: list[str] = ["Spring", "Summer", "Autumn", "Winter"]
        self.current_season_index: int = 0
        self.current_day: int = 0
        self.ambient_temperature: float = 20.0 # Default starting temp
        self.cold_threshold: float = 8.0
        self.severe_cold_threshold: float = 0.0
        self.warmth_decay_radius: int = 6
        self.last_temperature_tick: int = 0
        self.shelter_zones_by_id: dict[str, dict] = {}
        self.cold_threshold: float = 8.0
        self.severe_cold_threshold: float = 0.0
        self.warmth_decay_radius: int = 6
        self.last_temperature_tick: int = 0
        self.weather = "clear"
        self.weather_change_timer: int = 0

        # New Interaction Context
        self.interaction_context = {
            "active": False,
            "x": 0,
            "y": 0,
            "target_entities": [],  # List of entities on the tile
            "selected_entity_index": 0,
            "available_actions": [], # Actions for the selected entity
            "selected_action_index": 0
        }

        # Build Mode State
        self.build_mode_selected_item_index: int = 0
        # Define some placeable items (keys from DECORATION_ITEM_DEFINITIONS)
        self.placeable_furniture_keys: list[str] = [
            "wooden_chair", "wooden_table", "bed_simple", "chest_wooden", "wall_shelf", "fire_pit_simple"
        ]
        self.ghost_furniture_tile: Tile | None = None # For rendering placement preview

        # Chat UI State
        self.chat_ui_active = False
        self.chat_ui_target_npc = None
        self.chat_ui_history = [] # List of tuples: (speaker_name_or_type, text_string)
        self.chat_ui_input_line = ""
        self.chat_ui_mode = "talk"
        self.chat_ui_scroll_offset = 0
        self.chat_ui_max_history = 50

        # Trade UI State
        self.trade_ui_active = False
        self.trade_ui_npc_target = None # The NPC merchant
        self.trade_ui_player_inventory_view = True # True if viewing player's items to sell, False for merchant's
        self.trade_ui_player_item_index = 0
        self.trade_ui_merchant_item_index = 0
        self.trade_ui_player_inventory_snapshot = [] # List of (item_key, quantity, price) tuples
        self.trade_ui_merchant_inventory_snapshot = [] # List of (item_key, quantity, price) tuples

        # Crafting Menu State
        self.crafting_menu_context = {
            "selected_recipe_index": 0,
            "scroll_offset": 0,
            "all_recipes": [] # This will be populated when the menu is opened
        }

        # Building Menu State
        self.building_menu_context = {
            "selected_recipe_index": 0,
            "scroll_offset": 0,
            "all_recipes": [] # This will be populated when the menu is opened
        }

        # Knowledge Menu State
        self.knowledge_menu_context = {
            "scroll_offset": 0
        }

        # Quest Menu State
        self.quest_menu_context = {
            "selected_quest_index": 0,
            "scroll_offset": 0
        }

        # Noticeboard Menu State
        self.noticeboard_menu_context = {
            "selected_task_index": 0,
            "scroll_offset": 0,
            "task_ids": [],
            "mode": "browse",
            "posting_building_id": None,
            "selected_role_index": 0,
            "selected_wage_index": 2,
            "wage_options": [10, 15, 20, 25, 30, 40, 50],
        }

        # Company Ledger Menu State
        self.company_ledger_menu_context = {
            "building_id": None,
            "selected_action_index": 0,
            "selected_amount_index": 1,
            "amount_options": [1, 10, 50, 100],
        }

        # Governance Menu State
        self.governance_menu_context = {
            "mode": "root",
            "selected_action_index": 0,
            "selected_target_index": 0,
            "scroll_offset": 0,
        }

        # Social Menu State
        self.social_menu_context = {
            "npc_id": None,
            "mode": "root",
            "selected_action_index": 0,
            "selected_option_index": 0,
            "scroll_offset": 0,
            "conversation_stance": "neutral",
            "conversation_tone": "neutral",
            "conversation_openness": 0.0,
        }

        # Book Reading UI State
        self.book_reading_context = {
            "book_id": None,
            "scroll_offset": 0
        }

        # Items on the ground
        self.items_on_map: dict[tuple[int, int], Inventory] = {} # Key: (x,y), Value: Inventory wrapper preserving item objects
        self.blueprints_by_id: dict[str, ConstructionBlueprint] = {}
        self.blueprint_positions: dict[tuple[int, int], str] = {}
        self.land_claims_by_id: dict[str, LandClaim] = {}
        self.show_land_claim_overlay = False
        self.town_board = TownBoard()
        self.stockpiles_by_id: dict[str, Stockpile] = {}
        self.reserve_targets_by_id: dict[str, ReserveTarget] = {}
        self.production_tasks_by_id: dict[str, ProductionTask] = {}
        self.decision_explanations: list[DecisionExplanation] = []
        self.workshops_by_id: dict[str, WorkshopRuntimeState] = {}
        self.campfires_by_id: dict[str, CampfireRuntimeState] = {}
        self.next_reserve_eval_tick: int = 0
        self.next_production_eval_tick: int = 0
        self.next_dependency_eval_tick: int = 0
        self.actor_suitability_cache_until_tick: int = 0
        self.scheduling_cadence_config: dict[str, int] = {"reserve_eval_interval": 5, "production_eval_interval": 2, "dependency_eval_interval": 4, "suitability_cache_interval": 2}
        self._actor_suitability_cache: dict[tuple[str, int, str], int] = {}
        self._production_score_cache: dict[str, tuple[int, int]] = {}
        self.cold_override_threshold: float = 0.7
        self.cold_recovery_threshold: float = 0.35
        self.cold_override_cooldown_ticks: int = 40

        # FOV and Light Level state
        self.current_light_level_name = "DAY" # Default
        self.current_fov_radius = FOV_RADIUS_DAY # Default

        # Initialize FOV related maps
        self.player_fov_map = np.full((WORLD_HEIGHT, WORLD_WIDTH), fill_value=False, order="F")
        self.npc_fov_maps: dict[int, np.ndarray] = {}
        self.explored_map = np.full((WORLD_HEIGHT, WORLD_WIDTH), fill_value=False, order="F")
        self.transparency_map = np.full((WORLD_HEIGHT, WORLD_WIDTH), fill_value=True, order="F")

        # Autonomy Audit
        self.show_autonomy_overlay = False
        self.autonomy_counters = {}

        # Sound events list for the current tick
        self.sound_events: list[dict] = [] # Each dict: {"x", "y", "type", "volume", "source_id"(optional)}

        # Gossip and Event System
        self.global_events = self.history.events
        self.harmful_incidents: dict[str, Any] = {}
        self.books = self.records.books

        # Visual Effects
        self.visual_effects: list[VisualEffect] = []

        # Lightweight nearby speech layer for audible NPC chatter.
        self.active_ambient_speech = []
        self.recent_speech_ids = []
        ensure_ambient_speech_state(self)

        # UI requests emitted by simulation logic and applied by the main loop.
        self.ui_requests: list[UIRequest] = []

        # Incrementally maintained occupancy map used by pathing/movement.
        self.entity_positions: dict[tuple[int, int], int] = {}
        self.entity_positions_dirty = True
        self.entity_chunks_dirty = True

        # Generate macro structure for all chunks (villages, NPCs) but defer tile generation
        for y in range(self.chunk_height):
            for x in range(self.chunk_width):
                self._generate_chunk_macro(self.chunks[y][x], x, y)

        self._spawn_traveling_merchants()
        self._generate_player_family()
        self._find_starting_position()

        # Transparency map is now updated lazily as chunks are generated/visited
        # We might want to ensure the player's starting area is generated immediately
        self.ensure_player_surroundings_generated()
        self._refresh_chunk_activity(force=True)
        self._initialize_politics()

        self._update_light_level_and_fov() # Initialize based on game time 0
        self._update_player_fov() # Initial FOV calculation for player
        update_player_needs_system(self, initial_setup=True) # Initial status update
        self._rebuild_entity_positions()

    def __getstate__(self):
        state = self.__dict__.copy()
        state.pop("_background_llm_executor", None)
        state.pop("_background_llm_tasks", None)
        state.pop("_gossip_llm_service", None)
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._background_llm_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="world-llm")
        self._background_llm_tasks = {}
        self._gossip_llm_service = AsyncLLMGossipService()
        self.chunk_manager = ChunkManager(CHUNK_SIZE, self.chunk_width, self.chunk_height)
        self.last_abstract_simulation_hour = getattr(self, "last_abstract_simulation_hour", -1)
        self.last_macro_daily_day = getattr(self, "last_macro_daily_day", -1)
        self.stockpiles_by_id = getattr(self, "stockpiles_by_id", {})
        self.reserve_targets_by_id = getattr(self, "reserve_targets_by_id", {})
        self.production_tasks_by_id = getattr(self, "production_tasks_by_id", {})
        self.decision_explanations = getattr(self, "decision_explanations", [])
        self.workshops_by_id = getattr(self, "workshops_by_id", {})
        self.campfires_by_id = getattr(self, "campfires_by_id", {})
        self.next_reserve_eval_tick = getattr(self, "next_reserve_eval_tick", 0)
        self.next_production_eval_tick = getattr(self, "next_production_eval_tick", 0)
        self.next_dependency_eval_tick = getattr(self, "next_dependency_eval_tick", 0)
        self.actor_suitability_cache_until_tick = getattr(self, "actor_suitability_cache_until_tick", 0)
        self.scheduling_cadence_config = getattr(self, "scheduling_cadence_config", {"reserve_eval_interval": 5, "production_eval_interval": 2, "dependency_eval_interval": 4, "suitability_cache_interval": 2})
        self._actor_suitability_cache = getattr(self, "_actor_suitability_cache", {})
        self._production_score_cache = getattr(self, "_production_score_cache", {})
        self.cold_threshold = getattr(self, "cold_threshold", 8.0)
        self.severe_cold_threshold = getattr(self, "severe_cold_threshold", 0.0)
        self.warmth_decay_radius = getattr(self, "warmth_decay_radius", 6)
        self.last_temperature_tick = getattr(self, "last_temperature_tick", 0)
        self.shelter_zones_by_id = getattr(self, "shelter_zones_by_id", {})
        self.cold_override_threshold = float(getattr(self, "cold_override_threshold", 0.7))
        self.cold_recovery_threshold = float(getattr(self, "cold_recovery_threshold", 0.35))
        self.cold_override_cooldown_ticks = int(getattr(self, "cold_override_cooldown_ticks", 40) or 40)
        if getattr(self, "player", None) is not None:
            self.player.world_ref = self
            self._refresh_chunk_activity(force=True)


    def request_open_dialogue(self, npc: NPC, mode: str = "talk"):
        """Queue a request for the UI layer to open dialogue with an NPC."""
        self.ui_requests.append(open_dialogue_request(npc, mode=mode))

    def request_close_dialogue(self, target_npc: NPC | None = None):
        """Queue a request for the UI layer to close dialogue."""
        self.ui_requests.append(close_dialogue_request(target_npc))

    def request_open_trade(self, npc: NPC):
        """Queue a request for the UI layer to open a trade session."""
        self.ui_requests.append(open_trade_request(npc))

    def request_close_trade(self, target_npc: NPC | None = None):
        """Queue a request for the UI layer to close trade."""
        self.ui_requests.append(close_trade_request(target_npc))

    @staticmethod
    def _is_valid_coordinate_pair(coords) -> bool:
        return (
            isinstance(coords, (tuple, list))
            and len(coords) == 2
            and all(isinstance(value, int) for value in coords)
        )

    def get_chunk_coords(self, x: int, y: int) -> tuple[int, int]:
        manager = getattr(self, "chunk_manager", None)
        if manager is not None:
            return manager.get_chunk_coords(x, y)
        return int(x) // CHUNK_SIZE, int(y) // CHUNK_SIZE

    def _get_active_chunks(self) -> set[tuple[int, int]]:
        manager = getattr(self, "chunk_manager", None)
        return set(getattr(manager, "active_chunks", set()))

    def _is_chunk_active(self, chunk_coords: tuple[int, int]) -> bool:
        manager = getattr(self, "chunk_manager", None)
        if manager is None:
            return True
        return manager.is_chunk_active(chunk_coords)

    def _get_building_chunk_coords(self, building: Building | None) -> tuple[int, int] | None:
        if building is None:
            return None
        return self.get_chunk_coords(getattr(building, "global_origin_x", 0), getattr(building, "global_origin_y", 0))

    def _is_building_active(self, building: Building | None) -> bool:
        chunk_coords = self._get_building_chunk_coords(building)
        if chunk_coords is None:
            return False
        return self._is_chunk_active(chunk_coords)

    def _is_entity_active(self, entity) -> bool:
        if entity is None or entity is self.player:
            return True
        return self._is_chunk_active(self.get_chunk_coords(getattr(entity, "x", 0), getattr(entity, "y", 0)))

    def _find_nearest_walkable_tile(self, x: int, y: int, entity=None, *, radius: int = 4) -> tuple[int, int]:
        self._ensure_entity_positions_current()
        for search_radius in range(max(0, radius) + 1):
            for candidate_y in range(y - search_radius, y + search_radius + 1):
                for candidate_x in range(x - search_radius, x + search_radius + 1):
                    if not (0 <= candidate_x < WORLD_WIDTH and 0 <= candidate_y < WORLD_HEIGHT):
                        continue
                    tile = self.get_tile_at(candidate_x, candidate_y)
                    if tile is None or not getattr(tile, "passable", False):
                        continue
                    occupant_id = self.entity_positions.get((candidate_x, candidate_y))
                    if occupant_id is not None and occupant_id != getattr(entity, "id", None):
                        continue
                    return candidate_x, candidate_y
        return max(0, min(WORLD_WIDTH - 1, x)), max(0, min(WORLD_HEIGHT - 1, y))

    def sleep_entity(self, entity) -> bool:
        if entity is None or entity is self.player or getattr(entity, "is_sleeping", False):
            return False
        entity.is_sleeping = True
        entity.macro_x = getattr(entity, "x", 0)
        entity.macro_y = getattr(entity, "y", 0)
        entity.render_disabled = True
        entity._sleeping_render_state = {
            "char": getattr(entity, "char", None),
            "color": getattr(entity, "color", None),
            "render_x": getattr(entity, "render_x", float(getattr(entity, "x", 0))),
            "render_y": getattr(entity, "render_y", float(getattr(entity, "y", 0))),
        }
        if getattr(entity, "ai_brain", None) is not None:
            entity._sleeping_ai_brain = entity.ai_brain
            entity.ai_brain = None
        if hasattr(entity, "schedule"):
            entity.schedule.current_path = []
            entity.schedule.current_destination_coords = None
        self._remove_entity_position(entity)
        self.npc_fov_maps.pop(getattr(entity, "id", None), None)
        return True

    def wake_entity(self, entity) -> bool:
        if entity is None or entity is self.player or not getattr(entity, "is_sleeping", False):
            return False
        wake_x = int(getattr(entity, "macro_x", getattr(entity, "x", 0)))
        wake_y = int(getattr(entity, "macro_y", getattr(entity, "y", 0)))
        wake_x, wake_y = self._find_nearest_walkable_tile(wake_x, wake_y, entity)
        entity.x, entity.y = wake_x, wake_y
        entity.render_x = float(wake_x)
        entity.render_y = float(wake_y)
        if getattr(entity, "_sleeping_ai_brain", None) is not None:
            entity.ai_brain = entity._sleeping_ai_brain
            entity._sleeping_ai_brain = None
        elif isinstance(entity, Animal):
            from entities.behaviors import create_behavior

            entity.ai_brain = create_behavior(getattr(entity, "animal_definition", {}))
        else:
            from entities.human_behaviors import NPCBrain

            entity.ai_brain = NPCBrain(
                profession=getattr(getattr(entity, "economic", None), "profession", "Unemployed"),
            )
        render_state = getattr(entity, "_sleeping_render_state", {}) or {}
        if render_state.get("char") is not None:
            entity.char = render_state["char"]
        if render_state.get("color") is not None:
            entity.color = render_state["color"]
        entity.render_disabled = False
        entity.is_sleeping = False
        self._ensure_entity_positions_current()
        self.entity_positions[(wake_x, wake_y)] = entity.id
        chunk_coords = self.get_chunk_coords(wake_x, wake_y)
        self.entities_by_chunk.setdefault(chunk_coords, set()).add(entity.id)
        return True

    def _refresh_chunk_activity(self, *, force: bool = False) -> None:
        manager = getattr(self, "chunk_manager", None)
        if manager is None or getattr(self, "player", None) is None:
            return
        changed = manager.update_for_player(self.player.x, self.player.y, force=force)
        if not changed:
            return
        self.ensure_player_surroundings_generated()
        for entity in list(itertools.chain(self.village_npcs, self.npcs)):
            if getattr(getattr(entity, "physical", None), "is_dead", False):
                continue
            if self._is_entity_active(entity):
                self.wake_entity(entity)
            else:
                self.sleep_entity(entity)
        self._mark_entity_positions_dirty()

    def _get_noticeboard_menu_tasks(self):
        claimed_task_ids = set(getattr(self.player.knowledge, "claimed_tasks", []))
        tasks = []
        for task in self.town_board.haul_tasks:
            blueprint = self.blueprints_by_id.get(task.blueprint_id)
            if blueprint is None:
                continue
            if task.status == "open" or task.id in claimed_task_ids:
                tasks.append(task)
        tasks.sort(key=lambda task: (task.status != "open", task.destination_y, task.destination_x, task.item_key))
        return tasks

    def _get_noticeboard_menu_entries(self):
        entries: list[tuple[str, str]] = []
        for task in self._get_noticeboard_menu_tasks():
            entries.append(("haul", task.id))
        for task in self.town_board.get_open_employment_tasks():
            entries.append(("job", task.id))
        for need in getattr(self.town_board, "economic_needs", []):
            entries.append(("need", need.id))
        return entries

    def _get_player_owned_buildings(self) -> list[Building]:
        owned_buildings = [building for building in self.buildings_by_id.values() if self._building_is_owned_by_player(building)]
        owned_buildings.sort(key=lambda building: (building.building_type, building.id))
        return owned_buildings

    def _get_job_posting_building(self) -> Building | None:
        building_id = self.noticeboard_menu_context.get("posting_building_id")
        if not building_id:
            return None
        building = self.buildings_by_id.get(building_id)
        if building is None or not self._building_is_owned_by_player(building):
            return None
        return building

    def _get_job_posting_role_options(self, building: Building | None = None) -> list[str]:
        building = building or self._get_job_posting_building()
        if building is None:
            return []
        return get_roles_for_building(building.building_type)

    def get_job_posting_wage(self) -> int:
        wage_options = self.noticeboard_menu_context.get("wage_options", [10, 15, 20, 25, 30, 40, 50])
        if not wage_options:
            return 10
        selected_index = max(0, min(len(wage_options) - 1, int(self.noticeboard_menu_context.get("selected_wage_index", 0))))
        self.noticeboard_menu_context["selected_wage_index"] = selected_index
        return max(1, int(wage_options[selected_index]))

    def open_noticeboard_menu(self):
        entries = self._get_noticeboard_menu_entries()
        self.noticeboard_menu_context["task_ids"] = [f"{entry_type}:{entry_id}" for entry_type, entry_id in entries]
        self.noticeboard_menu_context["selected_task_index"] = 0
        self.noticeboard_menu_context["scroll_offset"] = 0
        self.noticeboard_menu_context["mode"] = "browse"
        self.game_state = "NOTICEBOARD_MENU"

    def open_job_posting_menu(self, building: Building | None = None) -> bool:
        owned_buildings = self._get_player_owned_buildings()
        if not owned_buildings:
            self.add_message_to_chat_log("You need to own a building before you can post a job.")
            return False

        selected_building = building if building in owned_buildings else owned_buildings[0]
        self.noticeboard_menu_context["mode"] = "post_job"
        self.noticeboard_menu_context["posting_building_id"] = selected_building.id
        self.noticeboard_menu_context["selected_role_index"] = 0
        self.noticeboard_menu_context["scroll_offset"] = 0
        self.noticeboard_menu_context["selected_task_index"] = 0
        self.game_state = "NOTICEBOARD_MENU"
        return True

    def _get_noticeboard_task(self, task_id: str | None):
        return self.town_board.get_task(task_id)

    def claim_noticeboard_task(self, task_id: str | None) -> bool:
        need = next((n for n in self.town_board.economic_needs if n.id == task_id), None)
        if need is not None:
            if need.type == "service":
                self._set_entity_profession(self.player, need.target_key, reason="town_need")
                self.town_board.economic_needs.remove(need)
                self.add_message_to_chat_log(f"You have stepped up to become the town's {need.target_key}.")
            elif need.type == "shortage":
                self.player.knowledge.active_quests[need.id] = {
                    "title": f"Supply {need.target_key.replace('_', ' ').title()}",
                    "description": need.description,
                    "type": "fetch",
                    "item_to_fetch_key": need.target_key,
                    "item_fetch_count": 5  # Arbitrary amount to resolve it for the player
                }
                self.add_message_to_chat_log(f"You agree to help supply the town with {need.target_key}.")
            self.open_noticeboard_menu()
            return True

        task = self._get_noticeboard_task(task_id)
        if task is None:
            self.add_message_to_chat_log("That notice is no longer available.")
            return False
        if task.assigned_entity_id == self.player.id:
            self.add_message_to_chat_log("You already claimed that hauling task.")
            return False
        if not self.town_board.claim_task(task, self.player.id):
            self.add_message_to_chat_log("Someone else already claimed that hauling task.")
            return False
        claimed_tasks = getattr(self.player.knowledge, "claimed_tasks", [])
        if task.id not in claimed_tasks:
            claimed_tasks.append(task.id)
        blueprint = self.blueprints_by_id.get(task.blueprint_id)
        if blueprint:
            self.add_message_to_chat_log(
                f"You claim a hauling task: bring {task.item_key.replace('_', ' ')} to the {blueprint.target_build.replace('_', ' ')} site."
            )
        self.open_noticeboard_menu()
        return True

    def post_employment_listing(self, building: Building | None, profession_role: str, daily_wage: int, *, posting_fee: int = 5) -> EmploymentTask | None:
        if building is None:
            self.add_message_to_chat_log("Choose a building before posting a job.")
            return None
        if not self._building_is_owned_by_player(building):
            self.add_message_to_chat_log("You can only post jobs for buildings you own.")
            return None

        normalized_role = normalize_profession(profession_role)
        role_options = self._get_job_posting_role_options(building)
        if normalized_role not in role_options:
            self.add_message_to_chat_log("That role does not fit this business.")
            return None
        if posting_fee > 0 and self.player.economic.money < posting_fee:
            self.add_message_to_chat_log(f"You need {posting_fee} coins to post a job listing.")
            return None

        open_tasks = self.town_board.get_open_employment_tasks(building.id)
        for task in open_tasks:
            if task.profession_role == normalized_role:
                self.add_message_to_chat_log("That business already has an open listing for this role.")
                return None

        if posting_fee > 0:
            self.player.economic.money -= posting_fee
        task = self.town_board.post_employment(
            building.id,
            normalized_role,
            max(1, int(daily_wage)),
            poster_entity_id=self.player.id,
        )
        building_name = str(building.building_type).replace("_", " ")
        self.add_message_to_chat_log(
            f"You post a {normalized_role} opening for the {building_name} at {task.daily_wage} coins per day."
        )
        self.open_noticeboard_menu()
        return task

    def _clear_player_claimed_task(self, task_id: str | None) -> None:
        if not task_id:
            return
        claimed_tasks = getattr(self.player.knowledge, "claimed_tasks", [])
        if task_id in claimed_tasks:
            claimed_tasks.remove(task_id)

    def _building_is_owned_by_player(self, building: Building | None) -> bool:
        if building is None:
            return False
        owner_id = getattr(building, "owner_id", None)
        return owner_id == self.player.id or bool(getattr(building, "player_owned", False))

    def _set_building_owner(self, building: Building | None, owner) -> bool:
        if building is None or owner is None:
            return False
        building.owner_id = getattr(owner, "id", None)
        building.player_owned = owner is self.player
        return True

    def _get_living_family_heirs(self, npc: NPC | None) -> list[NPC]:
        """Return living close-family heirs in dynasty priority order."""
        if npc is None:
            return []

        heirs: list[NPC] = []
        seen_ids: set[int] = set()

        def add_heir(candidate_id, *, require_adult: bool = False):
            candidate = self.get_entity_by_id(candidate_id)
            if not isinstance(candidate, NPC) or candidate.physical.is_dead:
                return
            if require_adult and getattr(candidate, "age", 0) < 18:
                return
            if candidate.id == npc.id or candidate.id in seen_ids:
                return
            seen_ids.add(candidate.id)
            heirs.append(candidate)

        family_ties = getattr(getattr(npc, "social", None), "family_ties", {}) or {}
        add_heir(family_ties.get("partner_id") or family_ties.get("spouse_id"))

        child_candidates = [
            other for other in self.all_npcs
            if isinstance(other, NPC)
            and not other.physical.is_dead
            and (
                getattr(getattr(other, "social", None), "family_ties", {}).get("mother_id") == npc.id
                or getattr(getattr(other, "social", None), "family_ties", {}).get("father_id") == npc.id
            )
        ]
        child_candidates.sort(key=lambda other: (-getattr(other, "age", 0), other.id))
        for child in child_candidates:
            add_heir(child.id, require_adult=True)

        for relative_id in family_ties.get("sibling_ids", []) or []:
            add_heir(relative_id, require_adult=True)
        add_heir(family_ties.get("mother_id"), require_adult=True)
        add_heir(family_ties.get("father_id"), require_adult=True)
        return heirs

    def _transfer_building_inheritance(self, deceased: NPC) -> None:
        """Transfer a dead NPC's owned property to the nearest living heir."""
        owned_buildings = [
            building for building in self.buildings_by_id.values()
            if getattr(building, "owner_id", None) == deceased.id
        ]
        if not owned_buildings:
            return

        heirs = self._get_living_family_heirs(deceased)
        primary_heir = heirs[0] if heirs else None

        for building in owned_buildings:
            if primary_heir is None:
                building.owner_id = None
                building.player_owned = False
                continue
            self._set_building_owner(building, primary_heir)
            if getattr(primary_heir.schedule, "home_building_id", None) is None and building.category == "residential":
                primary_heir.schedule.home_building_id = building.id
            if primary_heir not in building.residents and building.category == "residential":
                building.residents.append(primary_heir)

    def _cleanup_family_ties_after_death(self, deceased: NPC) -> None:
        """Remove stale partner/sibling references that point at the deceased."""
        for npc in self.all_npcs:
            if not isinstance(npc, NPC):
                continue
            ties = getattr(getattr(npc, "social", None), "family_ties", None)
            if not isinstance(ties, dict):
                continue
            if ties.get("partner_id") == deceased.id:
                del ties["partner_id"]
                ties["widowed_from"] = deceased.id
            if ties.get("spouse_id") == deceased.id:
                del ties["spouse_id"]
                ties["widowed_from"] = deceased.id
            sibling_ids = ties.get("sibling_ids")
            if isinstance(sibling_ids, list) and deceased.id in sibling_ids:
                ties["sibling_ids"] = [sibling_id for sibling_id in sibling_ids if sibling_id != deceased.id]

    def get_property_purchase_price(self, building: Building | None) -> int:
        if building is None:
            return 0
        base_price = max(75, int(building.width * building.height * 4))
        if "workplace" in str(getattr(building, "category", "")):
            base_price += 125
        elif getattr(building, "building_type", "") == "house":
            base_price += 50
        return base_price

    def buy_property(self, building: Building | None) -> bool:
        if building is None:
            self.add_message_to_chat_log("There is no property here to buy.")
            return False
        if self._building_is_owned_by_player(building):
            self.add_message_to_chat_log("You already own this property.")
            return False
        if getattr(building, "owner_id", None) is not None:
            self.add_message_to_chat_log("This property already belongs to someone else.")
            return False

        price = self.get_property_purchase_price(building)
        if self.player.economic.money < price:
            self.add_message_to_chat_log(f"You need {price} coins to buy this property.")
            return False

        self.player.economic.money -= price
        self._set_building_owner(building, self.player)
        building_name = str(getattr(building, "building_type", "property")).replace("_", " ")
        self.add_message_to_chat_log(f"You buy the {building_name} for {price} coins.")
        return True

    def open_company_ledger_menu(self, building: Building | None) -> bool:
        if not self._building_is_owned_by_player(building):
            self.add_message_to_chat_log("You do not own this property.")
            return False
        self.company_ledger_menu_context["building_id"] = building.id
        self.company_ledger_menu_context["selected_action_index"] = 0
        if self.company_ledger_menu_context.get("selected_amount_index") is None:
            self.company_ledger_menu_context["selected_amount_index"] = 1
        self.game_state = "COMPANY_LEDGER_MENU"
        return True

    def get_company_ledger_building(self) -> Building | None:
        building_id = self.company_ledger_menu_context.get("building_id")
        if not building_id:
            return None
        building = self.buildings_by_id.get(building_id)
        if building is None or not self._building_is_owned_by_player(building):
            return None
        return building

    def get_company_ledger_amount(self) -> int:
        amount_options = self.company_ledger_menu_context.get("amount_options", [1, 10, 50, 100])
        if not amount_options:
            return 1
        selected_amount_index = max(
            0,
            min(
                len(amount_options) - 1,
                int(self.company_ledger_menu_context.get("selected_amount_index", 0)),
            ),
        )
        self.company_ledger_menu_context["selected_amount_index"] = selected_amount_index
        return max(1, int(amount_options[selected_amount_index]))

    def get_company_ledger_stock_snapshot(self, building: Building | None = None) -> list[tuple[str, int]]:
        building = building or self.get_company_ledger_building()
        if building is None:
            return []
        inventory = getattr(building, "building_inventory", {}) or {}
        stock = [
            (item_key, int(quantity))
            for item_key, quantity in inventory.items()
            if item_key != "money" and int(quantity) > 0
        ]
        stock.sort(key=lambda entry: (ITEM_DEFINITIONS.get(entry[0], {}).get("name", entry[0]), entry[0]))
        return stock

    def transfer_company_funds(self, building: Building | None, amount: int, *, withdraw: bool) -> bool:
        building = building or self.get_company_ledger_building()
        if not self._building_is_owned_by_player(building):
            self.add_message_to_chat_log("You do not own this property.")
            return False

        normalized_amount = max(1, int(amount))
        player_balance = self._get_trade_money_balance(self.player)
        building_balance = self._get_trade_money_balance(building)
        building_name = str(getattr(building, "building_type", "business")).replace("_", " ")

        if withdraw:
            moved_amount = min(normalized_amount, building_balance)
            if moved_amount <= 0:
                self.add_message_to_chat_log(f"The {building_name} ledger has no funds to withdraw.")
                return False
            self._set_trade_money_balance(building, building_balance - moved_amount)
            self._set_trade_money_balance(self.player, player_balance + moved_amount)
            self.add_message_to_chat_log(f"You withdraw {moved_amount} coins from the {building_name} ledger.")
            return True

        moved_amount = min(normalized_amount, player_balance)
        if moved_amount <= 0:
            self.add_message_to_chat_log("You have no coins available to deposit.")
            return False
        self._set_trade_money_balance(self.player, player_balance - moved_amount)
        self._set_trade_money_balance(building, building_balance + moved_amount)
        self.add_message_to_chat_log(f"You deposit {moved_amount} coins into the {building_name} ledger.")
        return True

    def get_town_hall_building(self) -> Building | None:
        building_id = getattr(self.politics, "town_hall_building_id", None)
        if building_id:
            building = self.buildings_by_id.get(building_id)
            if building is not None:
                return building
        capital_hall = next((building for building in self.buildings_by_id.values() if building.building_type == "capital_hall"), None)
        if capital_hall is not None:
            self.politics.town_hall_building_id = capital_hall.id
        return capital_hall

    def _initialize_politics(self) -> None:
        town_hall = self.get_town_hall_building()
        if town_hall is None:
            return
        if self._get_trade_money_balance(town_hall) <= 0:
            self._set_trade_money_balance(town_hall, random.randint(600, 1200))
        self.evaluate_elections(force=True)

    def get_office_holder(self, office_name: str):
        office = self.politics.get_office(office_name)
        if office is None or office.holder_id is None:
            return None
        holder = self.get_entity_by_id(office.holder_id)
        if holder is None or getattr(getattr(holder, "physical", None), "is_dead", False):
            office.holder_id = None
            return None
        return holder

    def get_office_holder_name(self, office_name: str) -> str:
        holder = self.get_office_holder(office_name)
        return getattr(holder, "name", "Vacant")

    def _get_political_support_score(self, candidate, voters: list) -> int:
        support_score = int(getattr(getattr(candidate, "social", None), "fame", 0)) * 5
        support_score -= int(getattr(getattr(candidate, "social", None), "infamy", 0)) * 3
        for voter in voters:
            if voter is candidate:
                continue
            knowledge = getattr(voter, "knowledge", None)
            if knowledge is None or not hasattr(knowledge, "get_reputation_towards"):
                continue
            support_score += knowledge.get_reputation_towards(candidate)
        return support_score

    def evaluate_elections(self, *, force: bool = False) -> None:
        current_day = self.game_time // max(1, DAY_LENGTH_TICKS)
        adult_citizens = [npc for npc in self.village_npcs if not npc.physical.is_dead and getattr(npc, "age", 0) >= 18]
        candidates = [self.player] + adult_citizens
        if not candidates:
            return

        voters = [self.player] + adult_citizens
        for office_name, office in self.politics.offices.items():
            current_holder = self.get_office_holder(office_name)
            if current_holder is not None and not force:
                continue

            best_candidate = None
            best_score = None
            for candidate in candidates:
                score = self._get_political_support_score(candidate, voters)
                if office_name == "Captain of the Guard":
                    profession = normalize_profession(getattr(getattr(candidate, "economic", None), "profession", ""))
                    if profession in {"Guard", "Sheriff", "Deputy"}:
                        score += 20
                if best_score is None or score > best_score:
                    best_candidate = candidate
                    best_score = score

            office.holder_id = getattr(best_candidate, "id", None)
            office.last_elected_day = current_day
            if best_candidate is not None:
                self.add_message_to_chat_log(f"{best_candidate.name} has been recognized as {office_name}.")

    def _broadcast_political_memory(
        self,
        *,
        event_type: str,
        subject_id: int | None,
        importance_score: int,
        headline: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        memory = self.create_memory_event(
            event_type=event_type,
            subject_id=subject_id,
            importance_score=importance_score,
            headline=headline,
            location=None,
            metadata=metadata or {},
        )
        self.record_memory_event(self.player, memory)
        for citizen in self.village_npcs:
            if not citizen.physical.is_dead and getattr(citizen, "age", 0) >= 18:
                self.record_memory_event(citizen, memory)

    def _collect_daily_city_taxes(self, town_hall: Building) -> int:
        tax_rate = max(0.0, min(0.5, float(self.politics.tax_rate)))
        total_collected = 0

        taxable_holders = []
        for building in self.buildings_by_id.values():
            if getattr(building, "owner_id", None) is not None:
                taxable_holders.append(building)
        for npc in self.village_npcs:
            if npc.physical.is_dead:
                continue
            if normalize_profession(npc.economic.profession) != "Unemployed":
                taxable_holders.append(npc)
        if normalize_profession(self.player.economic.profession) != "Unemployed":
            taxable_holders.append(self.player)

        for holder in taxable_holders:
            current_balance = self._get_trade_money_balance(holder)
            tax_due = int(current_balance * tax_rate)
            if tax_due <= 0:
                continue
            self._set_trade_money_balance(holder, current_balance - tax_due)
            self._set_trade_money_balance(town_hall, self._get_trade_money_balance(town_hall) + tax_due)
            total_collected += tax_due

        return total_collected

    def _pay_daily_civic_salaries(self, town_hall: Building) -> None:
        mayor = self.get_office_holder("Mayor")
        mayor_id = getattr(mayor, "id", None)
        for office_name, office in self.politics.offices.items():
            holder = self.get_office_holder(office_name)
            if holder is None:
                continue

            treasury_balance = self._get_trade_money_balance(town_hall)
            if treasury_balance < office.daily_salary:
                unpaid_memory = self.create_memory_event(
                    event_type="unpaid_wages",
                    subject_id=mayor_id,
                    target_id=getattr(holder, "id", None),
                    importance_score=70,
                    headline=f"{office_name} went unpaid from the city treasury.",
                    location=(town_hall.global_center_x, town_hall.global_center_y),
                    metadata={"office": office_name, "salary": office.daily_salary},
                )
                self.record_memory_event(holder, unpaid_memory)
                if mayor_id is not None and mayor_id != getattr(holder, "id", None) and hasattr(holder, "add_grudge"):
                    holder.add_grudge(mayor_id, f"Missed civic salary as {office_name}.")
                continue

            self._set_trade_money_balance(town_hall, treasury_balance - office.daily_salary)
            self._set_trade_money_balance(holder, self._get_trade_money_balance(holder) + office.daily_salary)

    def _run_daily_governance(self) -> None:
        town_hall = self.get_town_hall_building()
        if town_hall is None:
            return

        current_day = self.game_time // max(1, DAY_LENGTH_TICKS)
        if self.politics.last_governance_day >= current_day:
            return
        if self.game_time % DAY_LENGTH_TICKS != 360:
            return

        self.evaluate_elections()
        collected_total = self._collect_daily_city_taxes(town_hall)
        self._pay_daily_civic_salaries(town_hall)
        self.politics.last_governance_day = current_day
        if collected_total > 0:
            self.add_message_to_chat_log(f"The city treasury collected {collected_total} coins in taxes.")

    def player_holds_office(self, office_name: str) -> bool:
        holder = self.get_office_holder(office_name)
        return getattr(holder, "id", None) == self.player.id

    def player_has_governance_access(self) -> bool:
        return self.player_holds_office("Mayor") or self.player_holds_office("Captain of the Guard")

    def open_governance_menu(self, building: Building | None = None) -> bool:
        town_hall = self.get_town_hall_building()
        if building is not None and town_hall is not None and getattr(building, "id", None) != town_hall.id:
            self.add_message_to_chat_log("Governance powers can only be exercised at Town Hall.")
            return False
        if town_hall is None:
            self.add_message_to_chat_log("This town has no functioning hall.")
            return False
        if not self.player_has_governance_access():
            self.add_message_to_chat_log("You do not hold office in this town.")
            return False
        self.governance_menu_context["mode"] = "root"
        self.governance_menu_context["selected_action_index"] = 0
        self.governance_menu_context["selected_target_index"] = 0
        self.governance_menu_context["scroll_offset"] = 0
        self.game_state = "GOVERNANCE_MENU"
        return True

    def close_governance_menu(self) -> None:
        self.governance_menu_context["mode"] = "root"
        self.governance_menu_context["selected_target_index"] = 0
        self.governance_menu_context["scroll_offset"] = 0
        self.game_state = "PLAYING"

    def get_governance_actions(self) -> list[str]:
        actions: list[str] = []
        if self.player_holds_office("Mayor"):
            actions.append("Adjust Taxes")
        if self.player_holds_office("Captain of the Guard"):
            actions.extend(["Issue Bounty", "Issue Arrest Warrant"])
        return actions

    def adjust_city_tax_rate(self, delta: float) -> bool:
        if not self.player_holds_office("Mayor"):
            return False
        current_rate = float(self.politics.tax_rate)
        new_rate = max(0.0, min(0.5, round(current_rate + delta, 2)))
        if abs(new_rate - current_rate) < 1e-9:
            return False
        self.politics.tax_rate = new_rate
        event_type = "raised_taxes" if new_rate > current_rate else "lowered_taxes"
        action_text = "raised" if new_rate > current_rate else "lowered"
        self._broadcast_political_memory(
            event_type=event_type,
            subject_id=self.player.id,
            importance_score=65,
            headline=f"{self.player.name} {action_text} city taxes to {int(new_rate * 100)}%.",
            metadata={"tax_rate": new_rate},
        )
        self.add_message_to_chat_log(f"You set the city tax rate to {int(new_rate * 100)}%.")
        return True

    def get_governance_targets(self) -> list:
        targets = [self.player] + [npc for npc in self.village_npcs if not npc.physical.is_dead]
        unique_targets = []
        seen_ids = set()
        for entity in targets:
            entity_id = getattr(entity, "id", None)
            if entity_id is None or entity_id in seen_ids:
                continue
            seen_ids.add(entity_id)
            unique_targets.append(entity)
        return unique_targets

    def issue_political_warrant(self, warrant_kind: str, target_id: int) -> bool:
        if warrant_kind not in {"bounty", "arrest_warrant"}:
            return False
        if not self.player_holds_office("Captain of the Guard"):
            return False
        town_hall = self.get_town_hall_building()
        if town_hall is None:
            return False

        target = self.get_entity_by_id(target_id)
        if target is None:
            self.add_message_to_chat_log("That target is no longer available.")
            return False

        guard_force = [
            npc for npc in self.village_npcs
            if not npc.physical.is_dead and normalize_profession(npc.economic.profession) in {"Guard", "Sheriff", "Deputy"}
        ]
        if not guard_force:
            self.add_message_to_chat_log("There are no guards available to carry out that order.")
            return False

        total_cost = 60 if warrant_kind == "bounty" else 40
        treasury_balance = self._get_trade_money_balance(town_hall)
        if treasury_balance < total_cost:
            self.add_message_to_chat_log("The city treasury cannot afford that order.")
            return False

        stipend = total_cost // len(guard_force)
        remainder = total_cost % len(guard_force)
        self._set_trade_money_balance(town_hall, treasury_balance - total_cost)
        for index, guard in enumerate(guard_force):
            payment = stipend + (1 if index < remainder else 0)
            if payment > 0:
                self._set_trade_money_balance(guard, self._get_trade_money_balance(guard) + payment)
            guard.task_target_entity_id = target_id
            guard.schedule.current_task = "execute_political_warrant"
            if target_id == self.player.id:
                guard.combat.is_hostile_to_player = True

        self.politics.active_warrants.append(
            PoliticalWarrant(
                warrant_kind=warrant_kind,
                target_id=target_id,
                issuer_id=self.player.id,
                cost=total_cost,
                issued_day=self.game_time // max(1, DAY_LENGTH_TICKS),
            )
        )
        event_type = "issued_bounty" if warrant_kind == "bounty" else "issued_arrest_warrant"
        self._broadcast_political_memory(
            event_type=event_type,
            subject_id=self.player.id,
            importance_score=70,
            headline=f"{self.player.name} issued a {warrant_kind.replace('_', ' ')} for {getattr(target, 'name', 'Unknown')}.",
            metadata={"target_id": target_id, "cost": total_cost},
        )
        self.add_message_to_chat_log(f"You issue a {warrant_kind.replace('_', ' ')} for {getattr(target, 'name', 'Unknown')}.")
        return True

    def _update_political_warrants(self) -> None:
        if not self.politics.active_warrants:
            return

        active_warrants: list[PoliticalWarrant] = []
        for warrant in self.politics.active_warrants:
            target = self.get_entity_by_id(warrant.target_id)
            if target is None or getattr(getattr(target, "physical", None), "is_dead", False):
                continue
            active_warrants.append(warrant)

        self.politics.active_warrants = active_warrants

    def open_social_menu(self, npc: NPC | None) -> bool:
        if npc is None or isinstance(npc, Animal) or npc.physical.is_dead:
            self.add_message_to_chat_log("They are not in a state to socialize.")
            return False
        profile = self.evaluate_conversation_foundation(self.player, npc)
        if not profile.can_start:
            self.add_message_to_chat_log(f"{npc.name} seems unwilling to talk right now.")
            return False
        self.social_menu_context["npc_id"] = npc.id
        self.social_menu_context["mode"] = "root"
        self.social_menu_context["selected_action_index"] = 0
        self.social_menu_context["selected_option_index"] = 0
        self.social_menu_context["scroll_offset"] = 0
        self.social_menu_context["conversation_stance"] = profile.stance
        self.social_menu_context["conversation_tone"] = profile.tone
        self.social_menu_context["conversation_openness"] = profile.openness
        self.interaction_context["active"] = False
        self.game_state = "SOCIAL_MENU"
        return True

    def close_social_menu(self) -> None:
        self.social_menu_context["npc_id"] = None
        self.social_menu_context["mode"] = "root"
        self.social_menu_context["selected_option_index"] = 0
        self.social_menu_context["scroll_offset"] = 0
        self.social_menu_context["conversation_stance"] = "neutral"
        self.social_menu_context["conversation_tone"] = "neutral"
        self.social_menu_context["conversation_openness"] = 0.0
        self.game_state = "PLAYING"

    def get_social_menu_target(self) -> NPC | None:
        npc_id = self.social_menu_context.get("npc_id")
        npc = self.get_entity_by_id(npc_id)
        return npc if isinstance(npc, NPC) and not npc.physical.is_dead else None

    def get_social_menu_actions(self) -> list[str]:
        return ["Give Gift", "Share Gossip", "Propose"]

    def get_social_attitude_label(self, npc: NPC | None) -> tuple[str, int]:
        if npc is None:
            return "Unknown", 0
        score = npc.knowledge.get_reputation_towards(self.player)
        if score >= 80:
            return "Devoted", score
        if score >= 25:
            return "Friendly", score
        if score <= -25:
            return "Hostile", score
        return "Neutral", score

    def _describe_player_inventory_entry(self, item_entry: dict) -> str:
        item_key = item_entry.get("key", "")
        item_reference = item_entry.get("item_reference")
        if item_reference is not None:
            label = item_reference.name
            if item_reference.max_durability is not None and item_reference.current_durability is not None:
                label += f" ({item_reference.current_durability}/{item_reference.max_durability})"
            return label
        item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key.replace("_", " ").title())
        quantity = max(1, int(item_entry.get("quantity", 1)))
        return f"{item_name} x1" if quantity > 1 else item_name

    def get_social_gift_options(self) -> list[dict[str, Any]]:
        options: list[dict[str, Any]] = []
        for amount in [1, 10, 25, 50, 100]:
            if self.player.economic.money >= amount:
                options.append(
                    {
                        "type": "money",
                        "amount": amount,
                        "label": f"{amount} coins",
                        "value": amount,
                    }
                )

        index = 0
        for item_key, count in self.player.economic.inventory.items():
            if item_key == "item_references":
                continue
            item_def = ITEM_DEFINITIONS.get(item_key, {})
            is_stackable = item_def.get("stackable", False)
            if is_stackable:
                value = max(1, int(item_def.get("value", 1)))
                options.append({
                    "type": "item",
                    "item_key": item_key,
                    "label": f"{count}x {item_def.get('name', item_key)}",
                    "value": value,
                })
                index += 1
            else:
                for item_ref in self.player.economic.inventory.iter_item_references():
                    if item_ref.key == item_key:
                        value = max(1, int(item_ref.value))
                        options.append({
                            "type": "item",
                            "item_reference": item_ref,
                            "item_key": item_key,
                            "label": item_ref.name,
                            "value": value,
                        })
                        index += 1
        return options

    def get_player_gossip_options(self) -> list[MemoryEvent]:
        memories = list(getattr(self.player.knowledge, "known_memories", {}).values())
        memories.sort(key=lambda memory: (-memory.importance_score, -memory.timestamp, memory.id))
        return memories

    def _pop_player_gift_item(self, gift_option: dict[str, Any]) -> tuple[str | None, ItemReference | None, int]:
        item_key = gift_option.get("item_key")
        item_reference = gift_option.get("item_reference")
        if not item_key:
            return None, None, 0

        item_def = ITEM_DEFINITIONS.get(item_key, {})
        if item_def.get("stackable", False):
            if self.player.has_item(item_key, 1):
                self.player.remove_item(item_key, 1)
                return item_key, None, max(1, int(item_def.get("value", 1)))
            return None, None, 0

        if item_reference is not None and self.player.economic.inventory.has_item_reference(item_reference):
            removed = self.player.economic.inventory.extract_item_reference(item_reference)
            if removed:
                return item_key, removed, max(1, int(removed.value))
        return None, None, 0

    def give_gift_to_npc(self, npc: NPC | None, gift_option: dict[str, Any] | None) -> bool:
        if npc is None or gift_option is None:
            return False

        gift_value = 0
        gift_label = ""
        if gift_option.get("type") == "money":
            amount = max(1, int(gift_option.get("amount", 0)))
            if self.player.economic.money < amount:
                self.add_message_to_chat_log("You do not have enough coins for that gift.")
                return False
            self.player.economic.money -= amount
            npc.economic.money += amount
            gift_value = amount
            gift_label = f"{amount} coins"
        elif gift_option.get("type") == "item":
            item_key, item_reference, gift_value = self._pop_player_gift_item(gift_option)
            if not item_key:
                self.add_message_to_chat_log("That item is no longer available.")
                return False
            npc_inventory = self._get_trade_inventory(npc)
            if npc_inventory is None:
                return False
            if item_reference is not None and hasattr(npc_inventory, "add_item_reference"):
                npc_inventory.add_item_reference(item_reference)
                gift_label = item_reference.name
            else:
                if hasattr(npc_inventory, "add_item"):
                    npc_inventory.add_item(item_key, 1)
                else:
                    npc_inventory[item_key] = npc_inventory.get(item_key, 0) + 1
                gift_label = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key.replace("_", " ").title())
        else:
            return False

        memory = self.create_memory_event(
            event_type="received_gift",
            subject_id=self.player.id,
            target_id=npc.id,
            importance_score=min(60, 15 + max(0, int(gift_value)) // 10),
            headline=f"{self.player.name} gave {npc.name} {gift_label}.",
            location=(npc.x, npc.y),
            metadata={"gift_label": gift_label, "gift_value": gift_value},
        )
        self.record_memory_event(npc, memory)
        self.add_message_to_chat_log(f"You give {gift_label} to {npc.name}.")
        return True

    def share_player_memory_with_npc(self, npc: NPC | None, memory_event: MemoryEvent | None) -> bool:
        if npc is None or memory_event is None:
            return False
        if npc.knowledge.knows_memory(memory_event):
            self.add_message_to_chat_log(f"{npc.name} already knows about that.")
            return False
        self.record_memory_event(npc, memory_event)
        self.add_message_to_chat_log(f"You share news with {npc.name}: {memory_event.headline or memory_event.event_type}.")
        return True

    def share_harmful_incident_claim(self, speaker, listener, incident_id: str) -> bool:
        """Share a structured secondhand claim about a known harmful incident."""
        if not speaker or not listener:
            return False
        incident = self.harmful_incidents.get(incident_id)
        if incident is None:
            return False
        shared = tell_harmful_incident_claim(speaker, listener, incident)
        if shared and speaker == self.player:
            self.add_message_to_chat_log(f"You tell {listener.name} what happened.")
        return shared

    def propagate_npc_harmful_incident_gossip(self, speaker, listener, *, overhear_radius: int = 3) -> bool:
        """Let one NPC tell another about one incident, with nearby NPC overhearing."""
        return propagate_harmful_incident_gossip(self, speaker, listener, overhear_radius=overhear_radius)

    def refresh_local_incident_opinion(self, observer, target_id: int | None) -> float:
        """Recompute one observer's belief-driven local standing for a target."""
        return update_local_incident_opinion(self, observer, target_id)

    def evaluate_social_reaction_stance(self, observer, target):
        """Entity-agnostic social reaction stance evaluation."""
        return evaluate_social_reaction_stance(self, observer, target)

    def evaluate_conversation_foundation(self, speaker, listener, max_distance=2):
        """Evaluate structured conversation stance/tone/openness and start conditions."""
        return evaluate_conversation_foundation(self, speaker, listener, max_distance=max_distance)

    def select_conversation_topic(self, speaker, listener, foundation_profile, group_listeners=None):
        """Select structured conversation topic/content from simulation state."""
        return select_conversation_topic(self, speaker, listener, foundation_profile, group_listeners=group_listeners)

    def player_propose_to_npc(self, npc: NPC | None) -> bool:
        if npc is None or npc.physical.is_dead:
            return False

        player_ties = self.player.social.family_ties
        npc_ties = npc.social.family_ties
        if player_ties.get("partner_id") or player_ties.get("spouse_id"):
            self.add_message_to_chat_log("You are already married.")
            return False
        if npc_ties.get("partner_id") or npc_ties.get("spouse_id"):
            self.add_message_to_chat_log(f"{npc.name} is already married.")
            return False

        reputation_score = npc.knowledge.get_reputation_towards(self.player)
        if reputation_score < 80:
            self.add_message_to_chat_log(f"{npc.name} gently refuses your proposal.")
            return False

        player_ties["partner_id"] = npc.id
        player_ties["spouse_id"] = npc.id
        npc_ties["partner_id"] = self.player.id
        npc_ties["spouse_id"] = self.player.id

        if npc.economic.money > 0:
            self.player.economic.money += npc.economic.money
            npc.economic.money = 0

        for building in self.buildings_by_id.values():
            if getattr(building, "owner_id", None) == npc.id:
                self._set_building_owner(building, self.player)

        marriage_record = self.record_marriage_event(
            spouse_a=npc,
            spouse_b=self.player,
            description=f"{self.player.name} and {npc.name} were married.",
            location=(npc.x, npc.y),
        )
        marriage_memory = self.create_memory_event(
            event_type="marriage",
            subject_id=self.player.id,
            target_id=npc.id,
            importance_score=60,
            headline=f"{self.player.name} married {npc.name}.",
            location=(npc.x, npc.y),
            metadata={"marriage_event_id": marriage_record.id},
        )
        self.record_memory_event(self.player, marriage_memory)
        self.record_memory_event(npc, marriage_memory)
        village = self._get_village_for_npc(npc)
        if village is not None:
            for villager in self.village_npcs:
                if villager.id != npc.id and not villager.physical.is_dead and self._get_village_for_npc(villager) == village:
                    self.record_memory_event(villager, marriage_memory)

        self.add_message_to_chat_log(f"{npc.name} accepts your proposal. You are now married!")
        return True

    def _get_employment_daily_wage(self, profession_role: str, *, override_wage: int | None = None, village=None) -> int:
        if override_wage is not None:
            return max(1, int(override_wage))

        profession_data = get_profession_data(profession_role) or {}
        base_wage = max(1, int(profession_data.get("wage", 10)))

        if village is not None:
            wealth_tier = getattr(village, "wealth_tier", "middle")
            if wealth_tier == "poor":
                base_wage = max(1, int(base_wage * 0.75))
            elif wealth_tier == "rich":
                base_wage = int(base_wage * 1.5)

            # Check if this town is desperate for this role
            if hasattr(self, "town_board") and getattr(self.town_board, "economic_needs", None):
                for need in self.town_board.economic_needs:
                    if need.settlement_id == village.id and need.type == "service" and need.target_key == profession_role:
                        base_wage = int(base_wage * 1.5)
                        break

        return base_wage

    def _is_player_owned_workplace(self, building: Building | None) -> bool:
        return bool(building and "workplace" in str(getattr(building, "category", "")) and self._building_is_owned_by_player(building))

    def _find_best_employment_task_for_npc(self, npc: NPC) -> EmploymentTask | None:
        best_task = None
        best_score = None
        village = self._get_village_for_npc(npc)
        village_id = getattr(village, "id", None)
        for task in self.town_board.get_open_employment_tasks():
            building = self.buildings_by_id.get(task.target_building_id)
            if building is None:
                continue
            if village is not None and getattr(building, "settlement_id", None) not in {None, village_id}:
                continue
            if self._count_active_workers_for_building(building) >= building.max_workers:
                continue
            score = self._evaluate_job_suitability(npc, building) + task.daily_wage
            if best_score is None or score > best_score:
                best_score = score
                best_task = task
        return best_task

    def _hire_npc_from_employment_task(self, npc: NPC, employment_task: EmploymentTask) -> bool:
        building = self.buildings_by_id.get(employment_task.target_building_id)
        if building is None:
            return False
        if not self.town_board.claim_employment_task(employment_task, npc.id):
            return False
        hired = self._assign_job(
            npc,
            building,
            profession=employment_task.profession_role,
            daily_wage=employment_task.daily_wage,
            reason="player_listing_hired" if self._is_player_owned_workplace(building) else "noticeboard_listing_hired",
        )
        if not hired:
            self.town_board.release_employment_task(employment_task.id)
            return False
        self.town_board.complete_employment_task(employment_task.id)
        self.town_board.remove_employment_task(employment_task.id)
        return True

    def handle_npc_job_seeking(self, npc: NPC) -> bool:
        if npc is None or npc.physical.is_dead or normalize_profession(npc.economic.profession) != "Unemployed":
            return False
        village = self._get_village_for_npc(npc)
        village_id = getattr(village, "id", None)
        noticeboard_points = getattr(village, "interaction_points", {}).get("noticeboard", []) if village else []
        self._sync_village_employment_tasks(village)
        available_jobs = [
            task
            for task in self.town_board.get_open_employment_tasks()
            if (building := self.buildings_by_id.get(task.target_building_id)) is not None
            and (village is None or getattr(building, "settlement_id", None) in {None, village_id})
        ]

        # Check for economic needs they can fulfill
        open_service_needs = []
        if village_id:
            open_service_needs = [
                need for need in self.town_board.economic_needs
                if need.settlement_id == village_id and need.type == "service"
            ]

        if not noticeboard_points or (not available_jobs and not open_service_needs):
            return False

        board_x, board_y = noticeboard_points[0]
        if (npc.x, npc.y) == (board_x, board_y):
            # First, check if they can just take an open service role to fulfill a town need
            if open_service_needs:
                for need in open_service_needs:
                    # Very simple evaluation: take the job if we're unemployed
                    self._set_entity_profession(npc, need.target_key, reason="town_need")
                    self.town_board.economic_needs.remove(need)
                    npc.schedule.current_task = TaskType.IDLE
                    npc.schedule.current_path = []
                    npc.schedule.current_destination_coords = None
                    self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} stepped up to become a {need.target_key} for the town.")
                    return True

            task = self._find_best_employment_task_for_npc(npc)
            if task and self._hire_npc_from_employment_task(npc, task):
                npc.schedule.current_task = TaskType.IDLE
                npc.schedule.current_path = []
                npc.schedule.current_destination_coords = None
                return True
            npc.schedule.current_task = TaskType.IDLE
            npc.schedule.current_destination_coords = None
            npc.schedule.current_path = []
            return False

        if npc.schedule.current_task != "reviewing_noticeboard_jobs" or npc.schedule.current_destination_coords != (board_x, board_y):
            path = self.calculate_path(npc.x, npc.y, board_x, board_y)
            if not path:
                return False
            npc.schedule.current_task = "reviewing_noticeboard_jobs"
            npc.schedule.current_destination_coords = (board_x, board_y)
            npc.schedule.current_path = path
            return True
        return bool(npc.schedule.current_path)

    def _mark_entity_positions_dirty(self):
        """Mark the occupancy map for a deferred rebuild after bulk changes."""
        self.entity_positions_dirty = True
        self.entity_chunks_dirty = True

    def _rebuild_entity_positions(self):
        """Rebuild the spatial indices from the current living entities."""
        self.entity_positions = {}
        self.entities_by_chunk.clear()

        def add_entity(entity):
            self.entity_positions[(entity.x, entity.y)] = entity.id
            chunk_coords = (entity.x // CHUNK_SIZE, entity.y // CHUNK_SIZE)
            self.entities_by_chunk.setdefault(chunk_coords, set()).add(entity.id)

        add_entity(self.player)
        for npc in self.all_npcs:
            if npc.physical.is_dead or getattr(npc, "is_sleeping", False):
                continue
            add_entity(npc)
        self.entity_positions_dirty = False
        self.entity_chunks_dirty = False

    def _ensure_entity_positions_current(self):
        """Rebuild the spatial indices only when bulk changes have invalidated them."""
        if self.entity_positions_dirty or self.entity_chunks_dirty:
            self._rebuild_entity_positions()

    def _update_entity_position(self, entity, new_x: int, new_y: int):
        """Move an entity while keeping the spatial indices in sync."""
        if entity is not self.player and getattr(entity, "is_sleeping", False):
            entity.x, entity.y = new_x, new_y
            entity.macro_x = new_x
            entity.macro_y = new_y
            return
        self._ensure_entity_positions_current()
        old_pos = (entity.x, entity.y)
        old_chunk = (entity.x // CHUNK_SIZE, entity.y // CHUNK_SIZE)
        if self.entity_positions.get(old_pos) == entity.id:
            del self.entity_positions[old_pos]
        if old_chunk in self.entities_by_chunk:
            self.entities_by_chunk[old_chunk].discard(entity.id)
            if not self.entities_by_chunk[old_chunk]:
                del self.entities_by_chunk[old_chunk]
        entity.x, entity.y = new_x, new_y
        if entity is not self.player:
            entity.macro_x = new_x
            entity.macro_y = new_y
        self.entity_positions[(new_x, new_y)] = entity.id
        new_chunk = (new_x // CHUNK_SIZE, new_y // CHUNK_SIZE)
        self.entities_by_chunk.setdefault(new_chunk, set()).add(entity.id)
        if entity is self.player:
            self._refresh_chunk_activity()

    def _remove_entity_position(self, entity):
        """Remove an entity from the spatial indices if it is currently tracked."""
        self._ensure_entity_positions_current()
        pos = (entity.x, entity.y)
        chunk_coords = (entity.x // CHUNK_SIZE, entity.y // CHUNK_SIZE)
        if self.entity_positions.get(pos) == entity.id:
            del self.entity_positions[pos]
        if chunk_coords in self.entities_by_chunk:
            self.entities_by_chunk[chunk_coords].discard(entity.id)
            if not self.entities_by_chunk[chunk_coords]:
                del self.entities_by_chunk[chunk_coords]

    def _reset_npc_path_blocking(self, npc: NPC):
        """Clear transient path blocking state for an NPC."""
        npc.schedule.path_blocked_turns = 0
        npc.schedule.last_blocked_position = None

    def _note_npc_path_blocked(self, npc: NPC, blocked_position: tuple[int, int]) -> int:
        """Record a blocked movement attempt and return the consecutive block count."""
        if getattr(npc.schedule, "last_blocked_position", None) == blocked_position:
            npc.schedule.path_blocked_turns = getattr(npc.schedule, "path_blocked_turns", 0) + 1
        else:
            npc.schedule.last_blocked_position = blocked_position
            npc.schedule.path_blocked_turns = 1
        return npc.schedule.path_blocked_turns

    def _try_local_npc_detour(self, npc: NPC, occupied_positions: dict[tuple[int, int], int]) -> bool:
        """Attempt a one-step local detour around a temporary blockage."""
        destination = npc.schedule.current_destination_coords
        if destination is None:
            return False

        candidates = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            step_x, step_y = npc.x + dx, npc.y + dy
            if not (0 <= step_x < WORLD_WIDTH and 0 <= step_y < WORLD_HEIGHT):
                continue
            tile = self.get_tile_at(step_x, step_y)
            if not (tile and tile.passable):
                continue
            occupant_id = occupied_positions.get((step_x, step_y))
            if occupant_id is not None and occupant_id != npc.id:
                continue
            distance = abs(destination[0] - step_x) + abs(destination[1] - step_y)
            candidates.append((distance, step_x, step_y))

        if not candidates:
            return False

        _, detour_x, detour_y = min(candidates, key=lambda candidate: candidate[0])
        self._update_entity_position(npc, detour_x, detour_y)
        return True

    def update_animations(self, dt: float):
        """Updates animation states for all entities and visual effects."""
        # Update Entity Interpolation
        # Movement speed in tiles per second for animation
        ANIMATION_SPEED = 20.0
        ANIMATION_SNAP_DISTANCE = 2.0

        for entity in itertools.chain([self.player], self.all_npcs):
            if entity is not self.player and getattr(entity, "is_sleeping", False):
                continue
            if hasattr(entity, 'render_x'):
                target_x = entity.x
                target_y = entity.y

                dx = target_x - entity.render_x
                dy = target_y - entity.render_y
                dist = math.sqrt(dx*dx + dy*dy)

                if dist > ANIMATION_SNAP_DISTANCE:
                    entity.render_x = float(target_x)
                    entity.render_y = float(target_y)
                elif dist > 0.01:
                    move_dist = ANIMATION_SPEED * dt
                    if move_dist >= dist:
                        entity.render_x = float(target_x)
                        entity.render_y = float(target_y)
                    else:
                        entity.render_x += (dx / dist) * move_dist
                        entity.render_y += (dy / dist) * move_dist
                else:
                    entity.render_x = float(target_x)
                    entity.render_y = float(target_y)

        # Update Visual Effects
        active_effects = []
        for effect in self.visual_effects:
            if not effect.update(dt):
                active_effects.append(effect)
        self.visual_effects = active_effects

    def _update_season(self):
        """Updates the current season based on the number of days passed."""
        day_of_year = self.game_time // DAY_LENGTH_TICKS
        new_season_index = (day_of_year // DAYS_PER_SEASON) % len(self.seasons)

        if new_season_index != self.current_season_index:
            self.current_season_index = new_season_index
            season_name = self.seasons[self.current_season_index]
            self.add_message_to_chat_log(self.text.season_changed(season_name))

    def _check_for_shelter(self, x: int, y: int, max_dist: int = 10) -> bool:
        """
        Checks if a position is sheltered by casting rays in 8 directions.
        If all rays hit a shelter-providing tile within max_dist, it's sheltered.
        """
        directions = [
            (0, -1),  # N
            (1, -1),  # NE
            (1, 0),   # E
            (1, 1),   # SE
            (0, 1),   # S
            (-1, 1),  # SW
            (-1, 0),  # W
            (-1, -1), # NW
        ]

        for dx, dy in directions:
            found_shelter_in_direction = False
            # Calculate endpoint for the ray
            end_x, end_y = x + dx * max_dist, y + dy * max_dist

            # Get all points in the line
            line_points = tcod.los.bresenham((x, y), (end_x, end_y))

            # Start from the second point to avoid checking the entity's own tile
            for i, (px, py) in enumerate(list(line_points)[1:]):
                if not (0 <= px < WORLD_WIDTH and 0 <= py < WORLD_HEIGHT):
                    # Ray went off the map, this direction is not sheltered
                    return False # Open to the void

                tile = self.get_tile_at(px, py)
                if tile and hasattr(tile, 'properties') and tile.properties.get("provides_shelter"):
                    found_shelter_in_direction = True
                    break # This ray is blocked, check next direction

            if not found_shelter_in_direction:
                # This ray reached max_dist without hitting a shelter tile, so not enclosed.
                return False

        # If all 8 directions found a shelter tile, then we are enclosed.
        return True

    def _handle_player_light_source_burnout(self):
        """Checks and handles burnout of player's active light source."""
        if self.player.equipment.equipped_light_item_key and \
           self.player.equipment.light_source_active_until_tick != -1 and \
           self.game_time >= self.player.equipment.light_source_active_until_tick:

            burnt_item_def = ITEM_DEFINITIONS.get(self.player.equipment.equipped_light_item_key)
            item_name = burnt_item_def.get("name", "light source") if burnt_item_def else "light source"
            self.add_message_to_chat_log(f"Your {item_name} has burnt out!")

            becomes_item_key = burnt_item_def.get("properties", {}).get("on_burnout_becomes")
            if becomes_item_key:
                self.player.add_item(becomes_item_key, 1)
                # Could also remove 1 of the original item if it was stackable and not fully consumed by "lighting" it
                # For now, lighting "unlit_torch" consumes it, and burnout creates "burnt_out_torch".

            self.player.equipment.equipped_light_item_key = None
            self.player.equipment.current_personal_light_radius = 0
            self.player.equipment.light_source_active_until_tick = -1
            # No need to call self._update_player_fov() here, as _update_light_level_and_fov (which calls this)
            # is followed by _update_player_fov() in the main loop.

    @staticmethod
    def _ambient_fov_radius_for_light_level(light_level_name: str) -> int:
        if light_level_name == "DAY":
            return FOV_RADIUS_DAY
        if light_level_name in {"DAWN", "DUSK"}:
            return FOV_RADIUS_DUSK_DAWN
        if light_level_name == "NIGHT":
            return FOV_RADIUS_NIGHT
        if light_level_name == "PITCH BLACK":
            return FOV_RADIUS_PITCH_BLACK
        return FOV_RADIUS_DAY

    def _get_effective_player_fov_radius(self) -> int:
        base_ambient_fov_radius = self.current_fov_radius
        effective_player_fov_radius = base_ambient_fov_radius

        if self.player.equipment.equipped_light_item_key and self.player.equipment.current_personal_light_radius > 0:
            is_active = True
            if self.player.equipment.light_source_active_until_tick != -1 and \
               self.game_time >= self.player.equipment.light_source_active_until_tick:
                is_active = False

            if is_active:
                effective_player_fov_radius = max(base_ambient_fov_radius, self.player.equipment.current_personal_light_radius)

        return effective_player_fov_radius

    def _update_player_fov(self) -> None:
        """
        Updates the player's field of view map and explored tiles.
        """
        effective_player_fov_radius = self._get_effective_player_fov_radius()

        self.player_fov_map = tcod.map.compute_fov(
            self.transparency_map,
            (self.player.y, self.player.x),
            radius=effective_player_fov_radius,
            algorithm=libtcodpy.FOV_SYMMETRIC_SHADOWCAST
        )
        self.explored_map |= self.player_fov_map

    def _update_npc_fov(self, npc: NPC) -> None:
        """
        Updates the field of view for a single NPC.
        Optimized to skip expensive calculation if NPC is idle/far away and doesn't need strict FOV.
        """
        if npc.physical.is_dead:
            return

        distance_to_player = abs(npc.x - self.player.x) + abs(npc.y - self.player.y)
        if distance_to_player > 60:
            return

        # Optimization: Only calculate accurate FOV if NPC is in an active state,
        # near the player, or has specific professions that require it.
        needs_strict_fov = False

        # Is the NPC in combat, hunting, frightened, or investigating?
        if getattr(npc, 'is_frightened', False) or getattr(npc.combat, 'is_hostile_to_player', False):
            needs_strict_fov = True
        elif npc.schedule.current_task in ["hunting", "investigating_sound", "fleeing_from_threat", "alerting_guards"]:
            needs_strict_fov = True

        # Is the player nearby? (e.g. to react to player crimes/actions)
        if not needs_strict_fov and abs(npc.x - self.player.x) <= self.current_fov_radius and abs(npc.y - self.player.y) <= self.current_fov_radius:
            needs_strict_fov = True

        # Do they need to look for items on the ground frequently?
        if not needs_strict_fov and entity_has_any_profession(npc, ["Guard", "Sheriff"]):
            needs_strict_fov = True

        # During tests, or if we force it for fear checks
        if getattr(self, '_testing_mode', False) or getattr(npc, '_force_fov_update', False):
            needs_strict_fov = True

        npc_fov_radius = self.current_fov_radius # NPCs use global ambient light for now

        if needs_strict_fov:
            self.npc_fov_maps[npc.id] = tcod.map.compute_fov(
                self.transparency_map,
                (npc.y, npc.x),
                radius=npc_fov_radius,
                algorithm=libtcodpy.FOV_SYMMETRIC_SHADOWCAST
            )
        else:
            # Skip calculation and clear their FOV map to save memory/processing
            if npc.id in self.npc_fov_maps:
                del self.npc_fov_maps[npc.id]
            return

        # NPC Item Perception within their FOV
        npc.knowledge.perceived_item_tiles.clear()
        fov_map_for_npc = self.npc_fov_maps[npc.id]
        visible_y_coords, visible_x_coords = np.where(fov_map_for_npc)
        for i in range(len(visible_x_coords)):
            vx, vy = visible_x_coords[i], visible_y_coords[i] # numpy where returns (row, col) -> (y, x)

            if (vx,vy) in self.items_on_map and self.items_on_map[(vx,vy)]:
                npc.knowledge.perceived_item_tiles.append((vx,vy))


    def _update_light_level_and_fov(self):
        """Updates the current light level and FOV radius based on game time, handles torch burnout."""
        self._handle_player_light_source_burnout() # Check for burnout first

        time_ratio = (self.game_time % DAY_LENGTH_TICKS) / DAY_LENGTH_TICKS

        current_period = None
        # LIGHT_LEVEL_PERIODS is sorted by start_ratio. Find the current period.
        for i in range(len(LIGHT_LEVEL_PERIODS)):
            period = LIGHT_LEVEL_PERIODS[i]
            next_period_start_ratio = LIGHT_LEVEL_PERIODS[i+1]["start_ratio"] if (i+1) < len(LIGHT_LEVEL_PERIODS) else 1.0

            if period["start_ratio"] <= time_ratio < next_period_start_ratio:
                current_period = period
                break

        if not current_period: # Should always find one, default to last if somehow not.
            current_period = LIGHT_LEVEL_PERIODS[-1]
            # Or if time_ratio is 1.0, it should use the first period (midnight)
            if time_ratio == 1.0: # Exactly end of day, loop to first period
                 current_period = LIGHT_LEVEL_PERIODS[0]


        self.current_light_level_name = current_period["name"]
        self.current_fov_radius = self._ambient_fov_radius_for_light_level(self.current_light_level_name)

        # Optional: Log change for debugging
        # if self.game_time % 10 == 0: # Log less frequently
        #     print(f"Time: {self.game_time}, Ratio: {time_ratio:.2f}, Light: {self.current_light_level_name}, FOV: {self.current_fov_radius}")


    def _get_pathfinding_cost(self, old_x, old_y, new_x, new_y):
        """
        Callback for tcod.path.AStar.
        Returns movement cost from (old_x, old_y) to (new_x, new_y).
        """
        if not (0 <= new_x < WORLD_WIDTH and 0 <= new_y < WORLD_HEIGHT):
            return 0  # Impassable (out of bounds)

        tile = self.get_tile_at(new_x, new_y)
        if not tile or not tile.passable:
            return 0  # Impassable

        # Diagonal movement cost can be higher if desired, e.g., sqrt(2) or 1.414
        # For simplicity, we'll use 1 for cardinal and diagonal.
        # tcod's AStar handles cardinal/diagonal based on graph/diagnal params.
        return 1


    def calculate_path(self, start_x: int, start_y: int, end_x: int, end_y: int) -> list[tuple[int, int]]:
        """
        Calculates a path from (start_x, start_y) to (end_x, end_y) using A* on a local cost map.
        Returns a list of (x, y) tuples, or an empty list if no path is found.
        """
        start_tile = self.get_tile_at(start_x, start_y)
        if not (start_tile and start_tile.passable):
            return []

        padding = 15
        min_x = max(0, min(start_x, end_x) - padding)
        max_x = min(WORLD_WIDTH - 1, max(start_x, end_x) + padding)
        min_y = max(0, min(start_y, end_y) - padding)
        max_y = min(WORLD_HEIGHT - 1, max(start_y, end_y) + padding)

        local_width = max_x - min_x + 1
        local_height = max_y - min_y + 1

        cost = np.ones((local_height, local_width), dtype=np.float32)

        for y_local in range(local_height):
            for x_local in range(local_width):
                x_world, y_world = min_x + x_local, min_y + y_local
                tile = self.get_tile_at(x_world, y_world)

                if not tile or not tile.passable:
                    cost[y_local, x_local] = 0
                else:
                    base_cost = 1.0
                    if hasattr(tile, 'properties') and tile.properties:
                        base_cost = float(tile.properties.get("movement_cost", 1.0))

                    if tile.is_hazard:
                        hazard_cost_value = 50
                        if tile.hazard_type == "fire_trap_active": hazard_cost_value = 100
                        elif tile.hazard_type == "water_deep": hazard_cost_value = 75
                        cost[y_local, x_local] = base_cost + hazard_cost_value
                    else:
                        cost[y_local, x_local] = base_cost

        astar = tcod.path.AStar(cost=cost, diagonal=1.41)

        start_x_local, start_y_local = start_x - min_x, start_y - min_y
        end_x_local, end_y_local = end_x - min_x, end_y - min_y

        try:
            path_indices_local = astar.get_path(start_x_local, start_y_local, end_x_local, end_y_local)
            path_coords = [(min_x + int(p[1]), min_y + int(p[0])) for p in path_indices_local]
            return path_coords
        except IndexError:
            return []

    def _is_predator(self, npc):
        if not isinstance(npc, Animal):
            return False
        animal_def = ANIMAL_DEFINITIONS.get(npc.animal_type, {})
        return "prey" in animal_def

    def _get_predator_pursuit_duration(self, predator, *, committed: bool = False) -> int:
        duration = 4
        if committed:
            duration += 5
        if getattr(self, "current_light_level_name", "DAY") in {"NIGHT", "PITCH BLACK"}:
            duration += 3
        animal_def = getattr(predator, "animal_definition", {}) or {}
        if animal_def.get("fearless"):
            duration += 2
        if animal_def.get("pack_animal"):
            duration += 1
        return duration

    def _get_predator_pursuit_state(self, predator, *, create: bool = True) -> dict | None:
        task_context = getattr(predator, "task_context_data", None)
        if task_context is None:
            if not create:
                return None
            task_context = {}
            predator.task_context_data = task_context
        elif not isinstance(task_context, dict):
            if not create:
                return None
            task_context = {"legacy_context": task_context}
            predator.task_context_data = task_context

        state = task_context.get("predator_pursuit")
        if state is None and create:
            state = {}
            task_context["predator_pursuit"] = state
        return state

    def _refresh_predator_pursuit_state(self, predator, target, *, committed: bool = False) -> None:
        if predator is None or target is None:
            return
        state = self._get_predator_pursuit_state(predator, create=True)
        if state is None:
            return

        duration = self._get_predator_pursuit_duration(predator, committed=committed)
        state["target_id"] = getattr(target, "id", None)
        state["last_seen"] = (getattr(target, "x", predator.x), getattr(target, "y", predator.y))
        state["last_seen_tick"] = self.game_time
        state["persist_until_tick"] = max(int(state.get("persist_until_tick", self.game_time)), self.game_time + duration)
        state["committed"] = bool(state.get("committed")) or committed

    def _clear_predator_pursuit_state(self, predator) -> None:
        task_context = getattr(predator, "task_context_data", None)
        if isinstance(task_context, dict):
            task_context.pop("predator_pursuit", None)

    def _get_predator_target(self, predator):
        if not predator.task_target_entity_id:
            return None
        return next((n for n in self.npcs if n.id == predator.task_target_entity_id), None)

    def _update_npc_movement(self):
        """Updates NPC positions based on their current path."""
        self._ensure_entity_positions_current()
        occupied_positions = self.entity_positions

        # This combines both lists for iteration
        for npc in self.all_npcs:
            if npc.physical.is_dead or getattr(npc, "is_sleeping", False):
                continue

            # --- Handle task-based path recalculation before movement ---
            # If hostile and needs to decide on a combat action that involves movement
            # This section ensures that an NPC's path is up-to-date with its target's position
            # right before it attempts to move.
            if npc.schedule.current_task == "execute_political_warrant" and npc.task_target_entity_id is not None:
                target = self.get_entity_by_id(npc.task_target_entity_id)
                if target is None or getattr(getattr(target, "physical", None), "is_dead", False):
                    npc.schedule.current_task = TaskType.IDLE
                    npc.task_target_entity_id = None
                    npc.combat.is_hostile_to_player = False
                else:
                    distance_to_target = abs(npc.x - target.x) + abs(npc.y - target.y)
                    if distance_to_target <= 1:
                        if target is self.player:
                            npc.combat.is_hostile_to_player = True
                            self.npc_attempt_attack_player(npc, self.player)
                        else:
                            self.npc_attempt_attack_npc(npc, target)
                        npc.schedule.current_path = []
                        npc.schedule.current_destination_coords = None
                        continue

                    target_x = target.x
                    target_y = target.y
                    destination = self._find_best_adjacent_tile_for_attack(target_x, target_y, npc)
                    if destination[0] is not None:
                        if npc.schedule.current_destination_coords != destination or not npc.schedule.current_path:
                            path = self.calculate_path(npc.x, npc.y, destination[0], destination[1])
                            if path:
                                npc.schedule.current_path = path
                                npc.schedule.current_destination_coords = destination
            elif npc.schedule.current_task == "following_player":
                if npc.task_target_entity_id == self.player.id:
                    # Recalculate path to player if not close enough
                    if abs(npc.x - self.player.x) > 2 or abs(npc.y - self.player.y) > 2:
                        dest_x, dest_y = self._find_best_adjacent_tile(self.player.x, self.player.y, npc)
                        if dest_x is not None and (npc.schedule.current_destination_coords != (dest_x, dest_y)):
                            path = self.calculate_path(npc.x, npc.y, dest_x, dest_y)
                            if path:
                                npc.schedule.current_path = path
                                npc.schedule.current_destination_coords = (dest_x, dest_y)
            elif npc.schedule.current_task == "combat_action_attack_player":
                # If in range, just attack, don't move. The attack itself is in this task block.
                # If not in range, switch to move_to_attack.
                player = self.player
                attack_range = getattr(npc, "attack_range", getattr(npc.combat, "attack_range", 1))
                if abs(npc.x - player.x) + abs(npc.y - player.y) <= attack_range:
                    # Attack is handled by this task, so we just need to ensure we don't move after.
                    self.npc_attempt_attack_player(npc, player)
                    npc.schedule.current_path = [] # Clear path after attack
                    npc.schedule.current_destination_coords = None
                    continue # End turn for this NPC
                else:
                    # Not in range, so must move. Change task and let move_to_attack logic below handle pathing.
                    npc.schedule.current_task = "combat_action_move_to_attack_player"
                    npc.schedule.current_path = [] # Clear old path
                    npc.schedule.current_destination_coords = None


            elif npc.schedule.current_task == "combat_action_flee_from_player":
                 # Recalculate flee path if there isn't one or it's very short (destination reached)
                if not npc.schedule.current_path or npc.schedule.current_destination_coords is None:
                    player_x, player_y = self.player.x, self.player.y
                    flee_distance = 15
                    # Vector from player to NPC
                    dx, dy = npc.x - player_x, npc.y - player_y
                    len_vec = math.sqrt(dx*dx + dy*dy)
                    if len_vec > 0:
                        flee_x = npc.x + int((dx / len_vec) * flee_distance)
                        flee_y = npc.y + int((dy / len_vec) * flee_distance)
                    else: # On same tile, flee randomly
                        flee_x, flee_y = npc.x + random.randint(-flee_distance, flee_distance), npc.y + random.randint(-flee_distance, flee_distance)

                    # Clamp to world bounds
                    flee_x = max(0, min(WORLD_WIDTH - 1, flee_x))
                    flee_y = max(0, min(WORLD_HEIGHT - 1, flee_y))

                    path = self.calculate_path(npc.x, npc.y, flee_x, flee_y)
                    if path:
                        npc.schedule.current_path = path
                        npc.schedule.current_destination_coords = (flee_x, flee_y)
                    else:
                        npc.schedule.current_task = "combat_action_hold_position" # No path, so hold.

            elif npc.schedule.current_task == "fleeing_from_player":
                # Fleeing from player due to infamy
                if not npc.schedule.current_path:
                    flee_distance = 15
                    dx, dy = npc.x - self.player.x, npc.y - self.player.y
                    len_vec = math.sqrt(dx*dx + dy*dy)
                    if len_vec > 0:
                        flee_x = npc.x + int((dx / len_vec) * flee_distance)
                        flee_y = npc.y + int((dy / len_vec) * flee_distance)
                    else:
                        flee_x, flee_y = npc.x + random.randint(-flee_distance, flee_distance), npc.y + random.randint(-flee_distance, flee_distance)

                    flee_x = max(0, min(WORLD_WIDTH - 1, flee_x))
                    flee_y = max(0, min(WORLD_HEIGHT - 1, flee_y))

                    path = self.calculate_path(npc.x, npc.y, flee_x, flee_y)
                    if path:
                        npc.schedule.current_path = path
                        npc.schedule.current_destination_coords = (flee_x, flee_y)
                    else:
                        npc.schedule.current_task = TaskType.IDLE # Can't flee, so just idle

            elif npc.schedule.current_task == "greeting_player":
                # Greeting player due to fame
                if not npc.schedule.current_path:
                    dest_x, dest_y = self._find_best_adjacent_tile(self.player.x, self.player.y, npc)
                    if dest_x is not None:
                        path = self.calculate_path(npc.x, npc.y, dest_x, dest_y)
                        if path:
                            npc.schedule.current_path = path
                            npc.schedule.current_destination_coords = (dest_x, dest_y)
                        else:
                            npc.schedule.current_task = TaskType.IDLE # Can't greet, so idle

            elif npc.schedule.current_task == "combat_action_move_to_attack_player":
                player = self.player
                attack_range = getattr(npc, "attack_range", getattr(npc.combat, "attack_range", 1))
                # Recalculate path if no path, or if destination is not adjacent to player anymore
                needs_new_path = False
                if not npc.schedule.current_path or not npc.schedule.current_destination_coords:
                    needs_new_path = True
                elif abs(npc.schedule.current_destination_coords[0] - player.x) + abs(npc.schedule.current_destination_coords[1] - player.y) > attack_range:
                     needs_new_path = True

                if needs_new_path:
                    # Find a new spot to path to, adjacent to the player
                    attack_pos_x, attack_pos_y = self._find_best_adjacent_tile_for_attack(player.x, player.y, npc)
                    if attack_pos_x is not None:
                        path = self.calculate_path(npc.x, npc.y, attack_pos_x, attack_pos_y)
                        if path:
                            npc.schedule.current_path = path
                            npc.schedule.current_destination_coords = (attack_pos_x, attack_pos_y)
                        else:
                            # Cannot find path to attack, so hold position
                            npc.schedule.current_task = "combat_action_hold_position"
                    else:
                        # No valid adjacent tile to attack from, hold position
                        npc.schedule.current_task = "combat_action_hold_position"

            # (Keep other elif blocks for path recalculation like move_to_cover, etc.)


            # --- Check for Micro-Reactions (Pause) ---
            if hasattr(npc, "task_context_data") and isinstance(npc.task_context_data, dict):
                pause_until = npc.task_context_data.get("pause_until_tick", 0)
                if pause_until > self.game_time:
                    continue # Skip movement to simulate a subtle reaction pause

            # --- Unified Path-Based Movement ---
            if npc.schedule.current_path:
                moves_made = 0
                max_moves = getattr(npc, 'speed', 1)
                while moves_made < max_moves and npc.schedule.current_path and len(npc.schedule.current_path) > 1:
                    next_x, next_y = npc.schedule.current_path[1] # Path index 0 is current pos

                    next_tile = self.get_tile_at(next_x, next_y)
                    if not (next_tile and next_tile.passable):
                        npc.schedule.current_path = []
                        npc.schedule.current_destination_coords = None
                        self._reset_npc_path_blocking(npc)
                        break

                    is_occupied = False
                    is_hunting_prey = self._is_predator(npc) and npc.schedule.current_task == "hunting"

                    occupant_id = occupied_positions.get((next_x, next_y))
                    if occupant_id is not None and occupant_id != npc.id:
                        if not (is_hunting_prey and occupant_id == npc.task_target_entity_id):
                            is_occupied = True

                    if is_occupied:
                        blocked_turns = self._note_npc_path_blocked(npc, (next_x, next_y))
                        occupant = self.get_entity_by_id(occupant_id)
                        occupant_is_likely_to_move = bool(
                            occupant and
                            hasattr(occupant, "schedule") and
                            occupant.schedule.current_path and
                            len(occupant.schedule.current_path) > 1 and
                            occupant.schedule.current_path[1] != (npc.x, npc.y)
                        )

                        if blocked_turns <= 2 or occupant_is_likely_to_move:
                            break

                        if self._try_local_npc_detour(npc, occupied_positions):
                            self._reset_npc_path_blocking(npc)
                            if npc.schedule.current_destination_coords:
                                detour_path = self.calculate_path(
                                    npc.x,
                                    npc.y,
                                    npc.schedule.current_destination_coords[0],
                                    npc.schedule.current_destination_coords[1],
                                )
                                npc.schedule.current_path = detour_path if detour_path else []
                            else:
                                npc.schedule.current_path = []
                            moves_made += 1
                            continue

                        npc.schedule.current_path = []
                        npc.schedule.current_destination_coords = None
                        self._reset_npc_path_blocking(npc)
                        break

                    # Update occupation tracker
                    self._update_entity_position(npc, next_x, next_y)
                    self._reset_npc_path_blocking(npc)
                    npc.schedule.current_path.pop(0)
                    moves_made += 1

                if not npc.schedule.current_path or len(npc.schedule.current_path) <= 1:
                    npc.schedule.current_path = []
                    self._reset_npc_path_blocking(npc)
                    # Destination reached, process arrival based on task
                    if npc.economic.profession == "Traveling Merchant" and npc.schedule.current_task == "traveling_to_village":
                        self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} has arrived at a village.")
                        npc.schedule.current_task = "lingering_in_village"
                        npc.leisure_timer = random.randint(DAY_LENGTH_TICKS // 2, DAY_LENGTH_TICKS)
                        npc.travel.is_traveling = False
                        npc.travel.origin_settlement_id = getattr(self._get_village_for_npc(npc, by_coords=True), "id", None)
                        npc.travel.destination_settlement_id = None
                        npc.travel.eta_days = 0

                        arrival_village = self._get_village_for_npc(npc, by_coords=True)
                        if arrival_village:
                            shared_memories = self.share_abstract_rumors_with_settlement(npc, arrival_village)
                            if shared_memories:
                                    self.add_message_to_chat_log(
                                        f"{self.get_entity_display_name(npc)} passed along {len(shared_memories)} rumor(s) from the road."
                                    )
                            incident_shares = run_traveler_arrival_incident_sharing(self, npc, arrival_village, max_shares=2)
                            if incident_shares:
                                self.add_message_to_chat_log(
                                    f"{self.get_entity_display_name(npc)} brings {incident_shares} harmful-incident tale(s) from another town."
                                )
                            key_npcs = [
                                other_npc for other_npc in self.village_npcs
                                if self._get_village_for_npc(other_npc) == arrival_village and
                                other_npc.economic.profession in ["Tavern Keeper", "Town Official", "Sheriff"]
                            ]
                            if key_npcs:
                                gossip_recipient = random.choice(key_npcs)
                                events_shared = self.knowledge_system.share_remote_events(
                                    npc,
                                    gossip_recipient,
                                    current_coords=(npc.x, npc.y),
                                    chunk_size=CHUNK_SIZE,
                                )
                                if events_shared > 0:
                                    self.add_message_to_chat_log(
                                        f"{self.get_entity_display_name(npc)} shared news from afar with {self.get_entity_display_name(gossip_recipient)}."
                                    )

                        # Clear old events but keep some "news" to carry
                        # Actually, better to clear all and relearn local news to carry to next village
                        self.knowledge_system.reset_known_events(npc)
                        village_center_x = (npc.x // CHUNK_SIZE) * CHUNK_SIZE + CHUNK_SIZE // 2
                        village_center_y = (npc.y // CHUNK_SIZE) * CHUNK_SIZE + CHUNK_SIZE // 2
                        self.knowledge_system.learn_local_events(
                            npc,
                            self.global_events,
                            center=(village_center_x, village_center_y),
                            radius_sq=(CHUNK_SIZE * 1.5) ** 2,
                        )
                        if npc.knowledge.known_events:
                            self.add_message_to_chat_log(f"Debug: {npc.name} learned about {len(npc.knowledge.known_events)} events in the new village.")

                    elif npc.schedule.current_task == "mobile_conversation_follow":
                        npc.schedule.current_task = TaskType.IDLE
                    elif npc.schedule.current_task == "socializing" and npc.task_target_entity_id:
                        chat_partner = next((p for p in self.village_npcs if p.id == npc.task_target_entity_id), None)
                        if chat_partner and abs(npc.x - chat_partner.x) + abs(npc.y - chat_partner.y) <= 1:
                            # Successfully met up, now exchange gossip
                            # NPC shares most interesting news with partner
                            event_to_share = self._get_most_interesting_known_event(npc)
                            if event_to_share:
                                knowledge_system = getattr(self, "knowledge_system", None)
                                if knowledge_system and hasattr(knowledge_system, "share_event"):
                                    knowledge_system.share_event(npc, chat_partner, event_to_share)
                                else:
                                    chat_partner.knowledge.known_events[event_to_share.id] = event_to_share
                                # self.add_message_to_chat_log(f"Debug: {npc.name} told {chat_partner.name} about {event_to_share.type}.")

                            # Partner shares most interesting news back
                            event_to_share_back = self._get_most_interesting_known_event(chat_partner)
                            if event_to_share_back:
                                knowledge_system = getattr(self, "knowledge_system", None)
                                if knowledge_system and hasattr(knowledge_system, "share_event"):
                                    knowledge_system.share_event(chat_partner, npc, event_to_share_back)
                                else:
                                    npc.knowledge.known_events[event_to_share_back.id] = event_to_share_back
                                # self.add_message_to_chat_log(f"Debug: {chat_partner.name} told {npc.name} about {event_to_share_back.type}.")

                            # Increase relationship
                            npc.social.relationships[chat_partner.id] = min(100, npc.social.relationships.get(chat_partner.id, 50) + 5)
                            chat_partner.social.relationships[npc.id] = min(100, chat_partner.social.relationships.get(npc.id, 50) + 5)


                        npc.schedule.current_task = TaskType.IDLE # Done socializing for now
                    elif npc.schedule.current_task == "gathering_social":
                        npc.schedule.current_task = "socializing_at_focal_point"
                        npc.schedule.current_path = []
                        npc.leisure_timer = max(npc.leisure_timer, random.randint(35, 80))
                        if random.random() < 0.2:
                            self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} joins a small gathering.")
                    elif npc.schedule.current_task == "visiting_friend" and npc.task_target_entity_id:
                        friend = next((p for p in self.village_npcs if p.id == npc.task_target_entity_id), None)
                        if friend and friend.schedule.home_building_id:
                            friend_home = self.buildings_by_id.get(friend.schedule.home_building_id)
                            if friend_home and (npc.x, npc.y) == (friend_home.global_center_x, friend_home.global_center_y):
                                # Successfully arrived at friend's house
                                npc.social.relationships[friend.id] = min(100, npc.social.relationships.get(friend.id, 50) + 10)
                                friend.social.relationships[npc.id] = min(100, friend.social.relationships.get(npc.id, 50) + 10)
                                # self.add_message_to_chat_log(f"Debug: {npc.name} is visiting {friend.name}, relationship increased.")
                        npc.schedule.current_task = TaskType.IDLE # Done visiting
                    elif npc.schedule.current_task == "applying_for_job":
                        # Arrived at potential workplace to apply
                        target_building = None
                        village = self._get_village_for_npc(npc, by_coords=True)
                        if village:
                            for b in village.buildings:
                                if (b.global_center_x, b.global_center_y) == (npc.x, npc.y):
                                    target_building = b
                                    break

                        if target_building:
                             current_workers = sum(1 for n in self.village_npcs if n.schedule.work_building_id == target_building.id and not n.physical.is_dead)
                             if current_workers < target_building.max_workers:
                                 self._assign_job(npc, target_building)
                                 npc.schedule.current_task = TaskType.AT_WORK
                                 self.add_message_to_chat_log(
                                     f"{self.get_entity_display_name(npc)} got the job at the {target_building.building_type.replace('_', ' ')} thanks to your tip!"
                                 )
                                 npc.social.relationships[self.player.id] = min(100, npc.social.relationships.get(self.player.id, 50) + 20)
                             else:
                                 self.add_message_to_chat_log(
                                     f"{self.get_entity_display_name(npc)} was told there are no vacancies at the {target_building.building_type.replace('_', ' ')}."
                                 )
                                 npc.schedule.current_task = TaskType.IDLE
                        else:
                            npc.schedule.current_task = TaskType.IDLE

                    elif npc.schedule.current_task == "greeting_player":
                        # Successfully reached the player, initiate dialogue
                        self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} says hello!")
                        self.start_npc_dialogue(npc)
                        self.request_open_dialogue(npc)
                        npc.schedule.current_task = TaskType.IDLE
                    elif npc.schedule.current_task == "approaching_player_for_help":
                        self.start_npc_dialogue(npc)
                        self.request_open_dialogue(npc)
                        npc.schedule.current_task = TaskType.IDLE
                    elif npc.schedule.current_task == "courting":
                        partner = next((p for p in self.village_npcs if p.id == npc.task_target_entity_id), None)
                        if partner:
                            # Proposal logic
                            relationship_score = npc.social.relationships.get(partner.id, 0)
                            if relationship_score > 70: # High relationship needed
                                npc.social.family_ties["partner_id"] = partner.id
                                npc.social.family_ties["spouse_id"] = partner.id
                                partner.social.family_ties["partner_id"] = npc.id
                                partner.social.family_ties["spouse_id"] = npc.id
                                self.add_message_to_chat_log(
                                    f"{self.get_entity_display_name(npc)} and {self.get_entity_display_name(partner)} are now married!"
                                )
                                self.record_marriage_event(
                                    spouse_a=npc,
                                    spouse_b=partner,
                                    description=f"{npc.name} and {partner.name} were married.",
                                    location=(npc.x, npc.y),
                                )
                                # Post-marriage changes
                                if partner.schedule.home_building_id:
                                    if npc.schedule.home_building_id:
                                        old_home = self.buildings_by_id.get(npc.schedule.home_building_id)
                                        if old_home and npc in old_home.residents:
                                            old_home.residents.remove(npc)

                                        new_home = self.buildings_by_id.get(partner.schedule.home_building_id)
                                        if new_home:
                                            new_home.residents.append(npc)
                                            npc.schedule.home_building_id = partner.schedule.home_building_id
                                            self.add_message_to_chat_log(
                                                f"{self.get_entity_display_name(npc)} has moved in with {self.get_entity_display_name(partner)}."
                                            )

                            else:
                                self.add_message_to_chat_log(
                                    f"{self.get_entity_display_name(npc)} proposed to {self.get_entity_display_name(partner)}, but was rejected."
                                )
                        npc.schedule.current_task = TaskType.IDLE
                    elif npc.schedule.current_task == TaskType.GOING_TO_WORK:
                        npc.schedule.current_task = TaskType.AT_WORK
                    elif npc.schedule.current_task == TaskType.LOOKING_FOR_WORK:
                        # Arrived at potential workplace
                        npc.schedule.current_task = TaskType.IDLE # Or "lingering" if handled elsewhere, for now idle means they stay put
                        # self.add_message_to_chat_log(f"Debug: {npc.name} is looking for work at a building.")
                    elif npc.schedule.current_task == "leaving_village":
                        # NPC has arrived at the edge of the map
                        self._remove_npc_from_world(npc, reason="emigrated")
                        continue # Stop processing this NPC
                    elif npc.schedule.current_task in [TaskType.GOING_HOME, TaskType.GOING_HOME_TO_SLEEP, TaskType.GOING_TO_BED]:
                        npc.schedule.current_task = TaskType.AT_HOME
                    else:
                        npc.schedule.current_task = TaskType.IDLE # Default state post-movement

                    npc.schedule.current_destination_coords = None

    def _get_building_global_center_coords(self, building_id: str) -> tuple[int, int] | None:
        """Gets a building's global center coordinates using the buildings_by_id lookup."""
        building = self.buildings_by_id.get(building_id)
        if building:
            return building.global_center_x, building.global_center_y
        return None

    def _get_time_of_day_str(self, game_time_tick: int, day_length: int) -> str:
        """Converts a game tick to a descriptive time of day string."""
        time_ratio = (game_time_tick % day_length) / day_length
        if 0 <= time_ratio < 0.1: return "Dead of Night"
        if 0.1 <= time_ratio < 0.25: return "Early Morning"
        if 0.25 <= time_ratio < 0.45: return "Morning"
        if 0.45 <= time_ratio < 0.60: return "Midday"
        if 0.60 <= time_ratio < 0.75: return "Afternoon"
        if 0.75 <= time_ratio < 0.90: return "Evening"
        return "Night"

    def _get_location_description(self, x: int, y: int) -> str:
        """Generates a brief description of a location based on its tile, building, or biome."""
        # 1. Check for building
        building = self.get_building_at(x, y)
        if building:
            building_name = building.building_type.replace('_', ' ')
            if building.building_type in ["house", "home"]:
                return f"in a {building_name}"
            else:
                return f"in the {building_name}"

        # 2. Check for specific outdoor features
        tile = self.get_tile_at(x, y)
        if tile:
            if tile.name == "Road":
                return "on a road"
            if tile.name == "Well":
                return "by the village well"
            if "water" in tile.name.lower():
                return "near the water"

        # 3. Fallback to biome
        chunk_x = x // CHUNK_SIZE
        chunk_y = y // CHUNK_SIZE
        if 0 <= chunk_x < self.chunk_width and 0 <= chunk_y < self.chunk_height:
            chunk = self.chunks[chunk_y][chunk_x]
            biome_name = chunk.biome.replace('_', ' ')
            return f"in the {biome_name}"

        return "in an unknown area"

    def _find_best_adjacent_tile(self, target_x: int, target_y: int, entity) -> tuple[int | None, int | None]:
        """
        Finds a passable, unoccupied, adjacent tile to the target for the entity to move to.
        Prefers tiles closer to the entity if multiple are valid.
        """
        potential_spots = []
        # Check cardinal directions first
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            adj_x, adj_y = target_x + dx, target_y + dy

            # Basic validation
            if not (0 <= adj_x < WORLD_WIDTH and 0 <= adj_y < WORLD_HEIGHT):
                continue
            tile = self.get_tile_at(adj_x, adj_y)
            if not (tile and tile.passable):
                continue

            # Check for occupancy
            occupied = False
            for npc in self.all_npcs:
                if npc.id != entity.id and npc.x == adj_x and npc.y == adj_y and not npc.physical.is_dead:
                    occupied = True
                    break
            if occupied:
                continue

            dist_sq = (entity.x - adj_x)**2 + (entity.y - adj_y)**2
            potential_spots.append({'x': adj_x, 'y': adj_y, 'dist_sq': dist_sq})

        if not potential_spots:
            return None, None

        potential_spots.sort(key=lambda s: s['dist_sq'])
        return potential_spots[0]['x'], potential_spots[0]['y']

    def _find_nearest_map_edge(self, npc: NPC) -> tuple[int, int]:
        """Finds the nearest map edge coordinate for an NPC to exit."""
        dist_to_left = npc.x
        dist_to_right = WORLD_WIDTH - 1 - npc.x
        dist_to_top = npc.y
        dist_to_bottom = WORLD_HEIGHT - 1 - npc.y

        min_dist = min(dist_to_left, dist_to_right, dist_to_top, dist_to_bottom)

        if min_dist == dist_to_left:
            return (0, npc.y)
        elif min_dist == dist_to_right:
            return (WORLD_WIDTH - 1, npc.y)
        elif min_dist == dist_to_top:
            return (npc.x, 0)
        else:
            return (npc.x, WORLD_HEIGHT - 1)

    def _find_best_adjacent_tile_for_attack(self, target_x: int, target_y: int, attacker_npc: NPC) -> tuple[int | None, int | None]:
        """
        Finds a passable, unoccupied, adjacent tile to the target for the attacker to move to.
        Prefers tiles closer to the attacker if multiple are valid.
        Returns (x, y) or (None, None) if no suitable tile is found.
        """
        potential_spots = []
        # Order of adjacent tiles to check (N, S, E, W)
        adj_offsets = [(0, -1), (0, 1), (-1, 0), (1, 0)]

        for dx, dy in adj_offsets:
            adj_x, adj_y = target_x + dx, target_y + dy

            if not (0 <= adj_x < WORLD_WIDTH and 0 <= adj_y < WORLD_HEIGHT):
                continue # Out of bounds

            tile = self.get_tile_at(adj_x, adj_y)
            if not (tile and tile.passable):
                continue # Not passable

            # Check if occupied by another NPC (excluding the attacker itself)
            occupied_by_other_npc = False
            # Iterate over all relevant NPC lists
            for npc_list_to_check in [self.village_npcs, self.npcs]:
                for other_npc in npc_list_to_check:
                    if other_npc.id != attacker_npc.id and other_npc.x == adj_x and other_npc.y == adj_y and not other_npc.physical.is_dead:
                        occupied_by_other_npc = True
                        break
                if occupied_by_other_npc:
                    break
            if occupied_by_other_npc:
                continue

            # Ensure the spot is not the attacker's current location if they are already next to target
            # This prevents pathing to their own spot if they are already adjacent.
            if adj_x == attacker_npc.x and adj_y == attacker_npc.y:
                continue

            dist_sq = (attacker_npc.x - adj_x)**2 + (attacker_npc.y - adj_y)**2
            potential_spots.append({'x': adj_x, 'y': adj_y, 'dist_sq': dist_sq})

        if not potential_spots:
            return None, None

        potential_spots.sort(key=lambda s: s['dist_sq'])

        return potential_spots[0]['x'], potential_spots[0]['y']

    def _find_best_cover_spot(self, npc: NPC, threat_x: int, threat_y: int, max_radius: int = 7) -> tuple[int | None, int | None]:
        """
        Finds a passable, unoccupied tile that offers cover from the threat.
        Cover is defined by being adjacent to a tile with provides_cover_value > 0,
        where that cover-providing tile is between the spot and the threat,
        OR the spot itself provides cover.
        Prioritizes higher cover value, then closer distance to the NPC.
        """
        candidate_spots = []

        for r_loop in range(1, max_radius + 1):  # Iterate radius from 1 up to max_radius
            perimeter_offsets_this_radius = set()
            for i_loop in range(r_loop + 1):
                j_loop = r_loop - i_loop
                if i_loop == 0 and j_loop == 0 : continue

                points_to_add_from_ij = []
                if i_loop == 0:
                    points_to_add_from_ij.extend([(0,j_loop), (0,-j_loop), (j_loop,0), (-j_loop,0)])
                elif j_loop == 0:
                     points_to_add_from_ij.extend([(i_loop,0), (-i_loop,0), (0,i_loop), (0,-i_loop)])
                else:
                    points_to_add_from_ij.extend([(i_loop,j_loop), (-i_loop,j_loop), (i_loop,-j_loop), (-i_loop,-j_loop)])
                    if i_loop != j_loop:
                         points_to_add_from_ij.extend([(j_loop,i_loop), (-j_loop,i_loop), (j_loop,-i_loop), (-j_loop,-i_loop)])

                for p_dx, p_dy in points_to_add_from_ij:
                    if abs(p_dx) + abs(p_dy) == r_loop:
                        perimeter_offsets_this_radius.add((p_dx, p_dy))

            for spot_dx, spot_dy in perimeter_offsets_this_radius:
                spot_x, spot_y = npc.x + spot_dx, npc.y + spot_dy

                if not (0 <= spot_x < WORLD_WIDTH and 0 <= spot_y < WORLD_HEIGHT):
                    continue

                spot_tile = self.get_tile_at(spot_x, spot_y)
                if not (spot_tile and spot_tile.passable):
                    continue

                occupied = False
                for other_npc_list_to_check in [self.village_npcs, self.npcs]:
                    for other_npc in other_npc_list_to_check:
                        if other_npc.id != npc.id and other_npc.x == spot_x and other_npc.y == spot_y and not other_npc.physical.is_dead:
                            occupied = True; break
                    if occupied: break
                if occupied: continue

                current_max_cover_value_for_spot = 0.0
                if spot_tile.provides_cover_value > 0:
                     current_max_cover_value_for_spot = max(current_max_cover_value_for_spot, spot_tile.provides_cover_value)

                for adj_dx_neighbor in range(-1, 2):
                    for adj_dy_neighbor in range(-1, 2):
                        if adj_dx_neighbor == 0 and adj_dy_neighbor == 0: continue

                        cover_obj_x, cover_obj_y = spot_x + adj_dx_neighbor, spot_y + adj_dy_neighbor
                        if not (0 <= cover_obj_x < WORLD_WIDTH and 0 <= cover_obj_y < WORLD_HEIGHT): continue

                        cover_obj_tile = self.get_tile_at(cover_obj_x, cover_obj_y)
                        if not cover_obj_tile: continue

                        tile_cover_value = 0
                        if hasattr(cover_obj_tile, 'provides_cover_value'):
                            tile_cover_value = cover_obj_tile.provides_cover_value

                        if tile_cover_value > 0:
                            dist_sq_threat_to_spot = (spot_x - threat_x)**2 + (spot_y - threat_y)**2
                            dist_sq_threat_to_cover_obj = (cover_obj_x - threat_x)**2 + (cover_obj_y - threat_y)**2

                            if dist_sq_threat_to_cover_obj < dist_sq_threat_to_spot:
                                current_max_cover_value_for_spot = max(current_max_cover_value_for_spot, tile_cover_value)

                if current_max_cover_value_for_spot > 0:
                    euclidean_dist_sq_to_npc = spot_dx*spot_dx + spot_dy*spot_dy
                    candidate_spots.append({
                        'x': spot_x, 'y': spot_y,
                        'cover': current_max_cover_value_for_spot,
                        'dist_sq': euclidean_dist_sq_to_npc
                    })

        if not candidate_spots:
            return None, None

        candidate_spots.sort(key=lambda s: (-s['cover'], s['dist_sq']))

        return candidate_spots[0]['x'], candidate_spots[0]['y']

    def _update_npc_relationships_dynamic(self):
        """Periodically updates NPC relationships based on interactions, personality, and random chance."""
        if self.game_time % DAY_LENGTH_TICKS != 0: # Run once a day
            return

        for npc in self.village_npcs:
            if npc.physical.is_dead: continue

            # Decay/Growth towards baseline
            for target_id in list(npc.social.relationships.keys()):
                current_score = npc.social.relationships[target_id]

                # Decay logic: Drift towards 50 (neutral) if no recent significant interaction
                # This is a slow drift.
                if current_score > 50:
                    npc.social.relationships[target_id] = max(50, current_score - 1)
                elif current_score < 50:
                    npc.social.relationships[target_id] = min(50, current_score + 1)

            # Random relationship events
            if random.random() < 0.1: # 10% chance per day for a random social event
                other_npc = random.choice(self.village_npcs)
                if other_npc.id != npc.id and not other_npc.physical.is_dead:
                    # Check compatibility (simple personality check for now)
                    compatibility = 0
                    if npc.social.personality == other_npc.social.personality:
                        compatibility = 10

                    current_rel = npc.social.relationships.get(other_npc.id, 50)

                    # "Breakup" or fallout logic
                    if current_rel > 70 and random.random() < 0.05: # 5% chance for friends to fight
                        change = -20
                        self.add_message_to_chat_log(
                            f"{self.get_entity_display_name(npc)} and {self.get_entity_display_name(other_npc)} had a falling out."
                        )
                    # "Making up" logic
                    elif current_rel < 30 and random.random() < 0.05: # 5% chance for enemies to make up
                        change = 20
                        self.add_message_to_chat_log(
                            f"{self.get_entity_display_name(npc)} and {self.get_entity_display_name(other_npc)} seem to be getting along better."
                        )
                    else:
                        # General random fluctuation based on compatibility
                        change = random.randint(-5, 5) + compatibility

                    new_rel = max(0, min(100, current_rel + change))
                    npc.social.relationships[other_npc.id] = new_rel
                    other_npc.social.relationships[npc.id] = new_rel # Assuming symmetric for simple events

                    # Check for romantic breakup
                    partner_id = npc.social.family_ties.get("partner_id") or npc.social.family_ties.get("spouse_id")
                    if partner_id == other_npc.id and new_rel < 30:
                        npc.social.family_ties.pop("partner_id", None)
                        npc.social.family_ties.pop("spouse_id", None)
                        other_npc.social.family_ties.pop("partner_id", None)
                        other_npc.social.family_ties.pop("spouse_id", None)
                        self.add_message_to_chat_log(
                            f"{self.get_entity_display_name(npc)} and {self.get_entity_display_name(other_npc)} have broken up."
                        )

                        # Move out logic (simplified: if living together, one leaves)
                        if npc.schedule.home_building_id and npc.schedule.home_building_id == other_npc.schedule.home_building_id:
                            # Remove npc from current home residents
                            old_home = self.buildings_by_id.get(npc.schedule.home_building_id)
                            if old_home and npc in old_home.residents:
                                old_home.residents.remove(npc)

                            npc.schedule.home_building_id = None # Become homeless momentarily
                            self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} has moved out.")

                            # Try to find a new vacant home
                            village = self._get_village_for_npc(npc)
                            if village:
                                vacant_homes = [b for b in village.buildings if b.category == "residential" and not b.residents]
                                if vacant_homes:
                                    new_home = random.choice(vacant_homes)
                                    npc.schedule.home_building_id = new_home.id
                                    new_home.residents.append(npc)
                                    self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} has found a new home.")

    def _update_npc_schedules(self):
        """
        Periodically updates NPC tasks based on game time and current state.
        Also handles routing to combat AI if NPC is hostile.
        """
        self._update_npc_relationships_dynamic()

        for npc in self.all_npcs:
            if npc.physical.is_dead or getattr(npc, "is_sleeping", False):
                continue

            npc_inventory = getattr(getattr(npc, "economic", None), "npc_inventory", None)
            if hasattr(npc_inventory, "process_tick"):
                npc_inventory.process_tick()

            if npc.schedule.current_task == "execute_political_warrant" and npc.task_target_entity_id is not None:
                continue

            update_npc_medical_state(self, npc)

            # --- Real-time Logic (Runs every tick or frequently) ---
            if npc.combat.is_hostile_to_player:
                if isinstance(npc, Animal) and hasattr(npc, "ai_brain"):
                    can_see_player = False
                    if npc.id in self.npc_fov_maps and 0 <= self.player.x < WORLD_WIDTH and 0 <= self.player.y < WORLD_HEIGHT:
                        can_see_player = self.npc_fov_maps[npc.id][self.player.y, self.player.x]
                    if self._is_predator(npc) and can_see_player:
                        attack_range = getattr(npc, "attack_range", getattr(npc.combat, "attack_range", 1))
                        in_attack_range = abs(npc.x - self.player.x) + abs(npc.y - self.player.y) <= attack_range
                        self._refresh_predator_pursuit_state(npc, self.player, committed=in_attack_range)
                    if not can_see_player and npc.ai_brain.take_turn(npc, self):
                        continue
                self._handle_npc_combat_turn(npc)
                # If creature is not actively pathing from combat AI (e.g. holding, or just attacked)
                # and not investigating a sound, they could wander a bit.
                if not npc.schedule.current_path and npc.schedule.current_task not in ["investigating_sound", "combat_action_attack_player"]:
                    if random.random() < 0.1: # Small chance to wander if not actively fighting/pathing
                        dx, dy = random.choice([(0,1), (0,-1), (1,0), (-1,0)])
                        potential_x, potential_y = npc.x + dx, npc.y + dy
                        target_tile = self.get_tile_at(potential_x, potential_y)
                        if target_tile and target_tile.passable:
                            npc.schedule.current_path = [(npc.x, npc.y), (potential_x, potential_y)]
                            npc.schedule.current_destination_coords = (potential_x, potential_y)
                            npc.schedule.current_task = "wandering_hostile"

            update_npc_sound_perception(self, npc)

            # --- FEAR SYSTEM (Real-time check) ---
            # Only update fear if not already hostile/combat to avoid overriding combat AI
            if not npc.combat.is_hostile_to_player:
                can_be_frightened = (npc.economic.profession != "Creature" and
                                     npc.schedule.current_task not in ["fleeing_from_threat", "alerting_guards", "combat_action_flee_from_player"])

                # Optimization: only check fear periodically or if nearby entities moved?
                # For now, we'll leave it in the main loop but rely on FOV.
                # Note: We only calculate FOV in the schedule block below, so fear might be slightly delayed or rely on old FOV.
                # If we want instant fear, we'd need to update FOV every tick for everyone, which is expensive.
                # Let's assume fear updates on the schedule tick or if forced.
                pass



            # --- SCHEDULED UPDATES (Low Frequency) ---
            if self.game_time - npc.schedule.game_time_last_updated < NPC_SCHEDULE_UPDATE_INTERVAL:
                continue

            npc.schedule.game_time_last_updated = self.game_time
            self._update_npc_fov(npc) # Update vision for AI decisions

            if self._handle_npc_hunting_task(npc):
                continue
            if self._assign_hunting_task_to_npc(npc):
                continue

            # --- FACTION COMBAT / RAIDERS ---
            if getattr(npc, "faction_id", None) and getattr(npc, "enemy_faction_id", None):
                # Raider logic
                if npc.id in self.npc_fov_maps:
                    fov_map = self.npc_fov_maps[npc.id]
                    visible_enemies = []
                    for vn in self.village_npcs + [self.player]:
                        if getattr(getattr(vn, 'physical', None), 'is_dead', False):
                            continue
                        if not (0 <= vn.x < WORLD_WIDTH and 0 <= vn.y < WORLD_HEIGHT):
                            continue
                        if not fov_map[vn.y, vn.x]:
                            continue
                        if isinstance(vn, Player):
                            visible_enemies.append(vn)
                            continue
                        # Determine if this NPC is an enemy
                        vn_village = self._get_village_for_npc(vn)
                        if vn_village and vn_village.id == npc.enemy_faction_id:
                            visible_enemies.append(vn)

                    if visible_enemies:
                        npc.combat.is_hostile_to_player = False # Explicitly tracking NPCs instead
                        nearest_enemy = min(visible_enemies, key=lambda e: (npc.x - e.x)**2 + (npc.y - e.y)**2)

                        # In the current implementation, 'is_hostile_to_player' controls combat AI for NPCs against the player.
                        # We need a way for NPCs to attack OTHER NPCs. The codebase has `npc_attempt_attack_npc`.
                        # Let's override the current task to engage the enemy.

                        distance_to_enemy = abs(npc.x - nearest_enemy.x) + abs(npc.y - nearest_enemy.y)
                        if distance_to_enemy <= 1:
                            if isinstance(nearest_enemy, Player):
                                self.npc_attempt_attack_player(npc, nearest_enemy)
                            else:
                                self.npc_attempt_attack_npc(npc, nearest_enemy)
                            npc.schedule.current_path = []
                            npc.schedule.current_destination_coords = None
                        else:
                            # Path to enemy
                            if npc.schedule.current_task != "raiding_combat" or not npc.schedule.current_path or npc.schedule.current_destination_coords != (nearest_enemy.x, nearest_enemy.y):
                                path = self.calculate_path(npc.x, npc.y, nearest_enemy.x, nearest_enemy.y)
                                if path:
                                    npc.schedule.current_path = path
                                    npc.schedule.current_destination_coords = (nearest_enemy.x, nearest_enemy.y)
                                    npc.schedule.current_task = "raiding_combat"
                        continue # Skip normal scheduling if in faction combat

            # --- VILLAGE DEFENDERS ---
            if entity_has_any_profession(npc, ["Guard", "Sheriff", "Militia"]):
                if npc.id in self.npc_fov_maps:
                    fov_map = self.npc_fov_maps[npc.id]
                    visible_raiders = [
                        r for r in self.npcs
                        if getattr(r, "enemy_faction_id", None) and not r.physical.is_dead and
                           0 <= r.x < WORLD_WIDTH and 0 <= r.y < WORLD_HEIGHT and fov_map[r.y, r.x]
                    ]
                    if visible_raiders:
                        nearest_raider = min(visible_raiders, key=lambda e: (npc.x - e.x)**2 + (npc.y - e.y)**2)
                        distance = abs(npc.x - nearest_raider.x) + abs(npc.y - nearest_raider.y)

                        if distance <= 1:
                            self.npc_attempt_attack_npc(npc, nearest_raider)
                            npc.schedule.current_path = []
                        else:
                            if npc.schedule.current_task != "defending_village":
                                self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} spots a raider and charges!")
                            path = self.calculate_path(npc.x, npc.y, nearest_raider.x, nearest_raider.y)
                            if path:
                                npc.schedule.current_path = path
                                npc.schedule.current_destination_coords = (nearest_raider.x, nearest_raider.y)
                                npc.schedule.current_task = "defending_village"
                        continue


            current_time_in_day = self.game_time % DAY_LENGTH_TICKS
            time_of_day_str = self._get_time_of_day_str(self.game_time, DAY_LENGTH_TICKS)

            # --- Mourning and Investigating Tasks ---
            if npc.schedule.current_task in ["mourning", "investigating"]:
                if npc.task_timer > 0:
                    npc.task_timer -= 1
                else:
                    npc.schedule.current_task = TaskType.IDLE
                    npc.task_target_coords = None
                continue # Skip normal scheduling

            # --- FEAR SYSTEM (Schedule-based check using updated FOV) ---
            can_be_frightened = (npc.economic.profession != "Creature" and
                                 not npc.combat.is_hostile_to_player and
                                 npc.schedule.current_task not in ["fleeing_from_threat", "alerting_guards", "combat_action_flee_from_player", "returning_to_warn"])

            if can_be_frightened and npc.id in self.npc_fov_maps:
                fov_map = self.npc_fov_maps[npc.id]
                visible_npcs = [
                    other_npc for other_npc in self.npcs + self.village_npcs
                    if other_npc.id != npc.id and not other_npc.physical.is_dead and 0 <= other_npc.x < WORLD_WIDTH and 0 <= other_npc.y < WORLD_HEIGHT and fov_map[int(other_npc.y), int(other_npc.x)]
                ]
                # Expanded threat detection for Hunters and others
                visible_threats = [
                    vn for vn in visible_npcs
                    if (isinstance(vn, Animal) and vn.animal_type in ["wolf", "dire_wolf"]) or
                       (isinstance(vn, DireWolf)) or
                       (vn.economic.profession == "Creature" and vn.combat.is_hostile_to_player)
                ]

                # Hunter specific logic
                if npc.economic.profession == "Hunter" and len(visible_threats) >= 1:
                     if not npc.is_frightened: # Using is_frightened as generic "threat state"
                        npc.is_frightened = True
                        npc.threat_source_ids = [threat.id for threat in visible_threats]
                        self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} spots a threat and prepares to warn the village!")
                        # Create event
                        threat_desc = f"{len(visible_threats)} threats" if len(visible_threats) > 1 else "a threat"
                        self.log_event("threat_detected", f"Hunter {npc.name} spotted {threat_desc} nearby.", npc.id, location=(npc.x, npc.y))
                        npc.schedule.current_path = []

                elif len(visible_threats) >= 2:
                    if not npc.is_frightened:
                        npc.is_frightened = True
                        npc.threat_source_ids = [threat.id for threat in visible_threats]
                        self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} sees threats and is terrified!")
                        npc.schedule.current_path = []

            if npc.is_frightened:
                if getattr(self, "interaction_resolver", None):
                    self.interaction_resolver.cancel_actor_interaction(npc.id, self, reason="threat_flee")
                threats_still_visible = False
                if npc.id in self.npc_fov_maps:
                    fov_map = self.npc_fov_maps[npc.id]
                    for threat_id in npc.threat_source_ids:
                        # Check both lists for the threat
                        threat = next((n for n in self.npcs if n.id == threat_id), None)
                        if not threat:
                            threat = next((n for n in self.village_npcs if n.id == threat_id), None)


                        if threat and not threat.physical.is_dead and 0 <= threat.x < WORLD_WIDTH and 0 <= threat.y < WORLD_HEIGHT and fov_map[int(threat.y), int(threat.x)]:
                            threats_still_visible = True
                            break
                if threats_still_visible:
                    if npc.economic.profession == "Hunter":
                        # Hunters return to warn instead of just alerting/fleeing
                        if npc.schedule.current_task != "returning_to_warn":
                            npc.schedule.current_task = "returning_to_warn"
                            # Find village center
                            village = self._get_village_for_npc(npc)
                            target_coords = None
                            if village and "town_square_center" in village.interaction_points:
                                target_coords = village.interaction_points["town_square_center"][0]

                            if target_coords:
                                path = self.calculate_path(npc.x, npc.y, target_coords[0], target_coords[1])
                                if path:
                                    npc.schedule.current_path = path
                                    npc.schedule.current_destination_coords = target_coords
                        elif npc.schedule.current_task == "returning_to_warn":
                            # Check arrival
                            if not npc.schedule.current_path or len(npc.schedule.current_path) <= 1:
                                # Arrived
                                threat_event = next((e for e in self.global_events if e.type == "threat_detected" and e.subject_id == npc.id), None)
                                self.broadcast_news(npc, 20, threat_event)
                                npc.is_frightened = False # Job done
                                npc.threat_source_ids = []
                                npc.schedule.current_task = TaskType.IDLE

                    elif entity_has_any_profession(npc, ["Guard", "Sheriff"]):
                        if npc.schedule.current_task == "alerting_guards" and (not npc.schedule.current_path or len(npc.schedule.current_path) <= 1):
                            self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} raises the alarm about the threat!")
                            npc.combat.is_hostile_to_player = True
                            for other_npc in self.village_npcs:
                                if other_npc.id != npc.id and entity_has_any_profession(other_npc, ["Guard", "Sheriff"]):
                                    if abs(npc.x - other_npc.x) + abs(npc.y - other_npc.y) <= 15:
                                        other_npc.combat.is_hostile_to_player = True
                                        self.add_message_to_chat_log(f"{self.get_entity_display_name(other_npc)} hears the alarm and prepares for battle!")
                        elif npc.schedule.current_task != "alerting_guards":
                            npc.schedule.current_task = "alerting_guards"
                            npc_village = self._get_village_for_npc(npc)
                            alarm_spot = npc_village.interaction_points.get("town_square_center") if npc_village else None
                            if alarm_spot:
                                dest_x, dest_y = self._find_best_adjacent_tile(alarm_spot[0], alarm_spot[1], npc)
                                if dest_x is not None:
                                    path = self.calculate_path(npc.x, npc.y, dest_x, dest_y)
                                    if path:
                                        npc.schedule.current_path = path
                                        npc.schedule.current_destination_coords = (dest_x, dest_y)
                    else:
                        if npc.schedule.current_task != "fleeing_from_threat":
                            npc.schedule.current_task = "fleeing_from_threat"
                            safe_spot = self.buildings_by_id.get(npc.schedule.home_building_id) or self._find_nearest_tavern(npc)
                            if safe_spot:
                                dest_x, dest_y = self._find_best_adjacent_tile(safe_spot.global_center_x, safe_spot.global_center_y, npc)
                                if dest_x is not None:
                                    path = self.calculate_path(npc.x, npc.y, dest_x, dest_y)
                                    if path:
                                        npc.schedule.current_path = path
                                        npc.schedule.current_destination_coords = (dest_x, dest_y)
                else:
                    npc.is_frightened = False
                    npc.threat_source_ids = []
                    npc.schedule.current_task = TaskType.IDLE
                    npc.schedule.current_path = []
                    self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} calms down as the threat is gone.")
                continue

            # --- Animal Behavior (strategy/controller driven) ---
            if isinstance(npc, Animal):
                if npc.ai_brain.take_turn(npc, self):
                    continue

            # Standard scheduling logic ONLY if NOT hostile by default (e.g. not a Creature) AND not investigating a sound
            elif hasattr(npc, "ai_brain"):
                npc.ai_brain.take_turn(npc, self)


    def _run_humanoid_schedule_logic(self, npc: NPC) -> bool:
        """Delegate humanoid daily scheduling to the NPC brain and job strategies."""
        if npc.economic.profession != "Creature" and not npc.combat.is_hostile_to_player and \
           npc.schedule.current_task not in ["attacking_player", "moving_to_attack_player", "fleeing_from_player",
                                             "holding_position_combat", "combat_action_use_healing_item",
                                             "combat_action_move_to_cover", "investigating_sound"]:

            update_npc_environmental_tasks_system(self, npc)

            current_time_in_day = self.game_time % DAY_LENGTH_TICKS
            run_npc_humanoid_scheduling_flow(self, npc, current_time_in_day)

        # --- Sheriff / Guard Hostility Check ---
        if npc.economic.profession in ["Sheriff", "Guard"] and not npc.combat.is_hostile_to_player:
            if self.player.economic.bounty >= 100: # Bounty threshold for arrest
                # Check if player is visible to the Sheriff/Guard
                if npc.id in self.npc_fov_maps and self.npc_fov_maps[npc.id][self.player.y, self.player.x]:
                    self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} spots you and moves to arrest you for your crimes!")
                    npc.combat.is_hostile_to_player = True
                    # Their combat AI will now handle moving towards the player to "attack" (which will be arrest)

        # After all task decisions and path assignments:
        # If NPC is at work, handle specific work sub-tasks or general production.
        # This is also where NPCs who have arrived at work (TaskType.AT_WORK) will start their sub-task logic.
        if npc.schedule.current_task == TaskType.AT_WORK:
            # Sub-task logic is now the primary driver of production.
            # The old _handle_npc_production is removed.
            work_behavior = getattr(getattr(npc, "ai_brain", None), "work_behavior", None)
            if work_behavior:
                work_behavior.take_turn(npc, self)
            else:
                update_npc_work_sub_tasks(self, npc)

        run_npc_traveling_merchant_policy(self, npc)


        npc.schedule.game_time_last_updated = self.game_time
        return True

    def _find_nearest_tree_for_chopping(self, npc: NPC, work_building: Building) -> tuple[int, int] | None:
        """
        Finds the nearest choppable tree for the NPC, using the NPC's dynamic search radius.
        If no tree is found, the NPC's search radius is increased.
        Returns global (x,y) coordinates or None.
        """
        search_radius = npc.woodcutter_search_radius
        center_x, center_y = work_building.global_center_x, work_building.global_center_y
        closest_tree_coords = None
        min_dist_sq = float('inf')

        # Iterate in expanding square rings around the building's center
        for r in range(search_radius + 1):
            coords_in_ring = []
            if r == 0:
                coords_in_ring.append((center_x, center_y))
            else:
                # Top and bottom edges of the square ring
                for i in range(-r, r + 1):
                    coords_in_ring.append((center_x + i, center_y + r))
                    if r != 0: # Avoid double adding center row if r=0 was part of this loop
                        coords_in_ring.append((center_x + i, center_y - r))
                # Left and right edges (excluding corners already covered)
                for i in range(-r + 1, r):
                    coords_in_ring.append((center_x + r, center_y + i))
                    if r != 0: # Avoid double adding center column
                        coords_in_ring.append((center_x - r, center_y + i))

            current_ring_closest_tree = None
            current_ring_min_dist_sq = float('inf')

            for x, y in list(set(coords_in_ring)): # Use set to remove duplicates from ring generation
                if not (0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT):
                    continue

                tile = self.get_tile_at(x, y)
                if isinstance(tile, Tree) and tile.is_choppable:
                    # Check if this tree is targeted by another NPC for chopping
                    is_targeted = False
                    for other_npc in self.village_npcs: # Check against all village NPCs
                        if other_npc.id != npc.id and \
                           other_npc.current_sub_task == "chop_trees" and \
                           other_npc.sub_task_target_coords == (x,y):
                            is_targeted = True
                            break
                    if is_targeted:
                        continue # Skip this tree as it's already targeted

                    dist_sq_from_npc = (npc.x - x)**2 + (npc.y - y)**2 # Distance from current NPC
                    if dist_sq_from_npc < current_ring_min_dist_sq:
                        current_ring_min_dist_sq = dist_sq_from_npc
                        current_ring_closest_tree = (x, y)

            if current_ring_closest_tree:
                # If we found a tree in this ring, it's the closest overall because we search radially.
                return current_ring_closest_tree

        npc.woodcutter_search_radius += 5
        return None

    def _find_nearest_corpse(self, npc: NPC) -> tuple[int, int] | None:
        """Finds the nearest animal corpse for the NPC to butcher."""
        search_radius = 20
        closest_corpse_coords = None
        min_dist_sq = float('inf')

        for y in range(npc.y - search_radius, npc.y + search_radius + 1):
            for x in range(npc.x - search_radius, npc.x + search_radius + 1):
                if 0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT:
                    tile = self.get_tile_at(x, y)
                    if tile and tile.name == "Animal Corpse":
                        # Check if another NPC is already targeting this corpse
                        is_targeted = False
                        for other_npc in self.village_npcs:
                             if other_npc.id != npc.id and \
                                other_npc.current_sub_task == "butcher_carcass" and \
                                other_npc.sub_task_target_coords == (x, y):
                                 is_targeted = True
                                 break

                        if not is_targeted:
                            dist_sq = (npc.x - x)**2 + (npc.y - y)**2
                            if dist_sq < min_dist_sq:
                                min_dist_sq = dist_sq
                                closest_corpse_coords = (x, y)
        return closest_corpse_coords


    HUNTABLE_SPECIES = {"deer", "rabbit", "turkey", "sheep", "boar", "bison"}
    HUNTING_FOOD_ITEMS = {"raw_meat", "raw_venison", "raw_mutton", "raw_fish", "processed_meat", "cooked_meat", "cooked_venison", "cooked_mutton", "cooked_fish", "bread"}
    BUTCHER_RAW_INPUTS = {"raw_venison", "raw_mutton", "raw_meat"}

    def _is_hunter_role(self, npc: NPC | None) -> bool:
        profession = str(getattr(getattr(npc, "economic", None), "profession", "") or "").strip().lower()
        return profession in {"hunter", "trapper", "ranger"}

    def _is_butcher_role(self, npc: NPC | None) -> bool:
        profession = str(getattr(getattr(npc, "economic", None), "profession", "") or "").strip().lower()
        return profession in {"butcher", "tavern keeper", "cook"}

    def _is_butcher_workplace(self, building: Building | None) -> bool:
        if building is None:
            return False
        text = f"{getattr(building, 'building_type', '')} {getattr(building, 'category', '')}".lower()
        return "butcher" in text or "tavern" in text or "food" in text

    def _get_available_food_count(self, inventory) -> int:
        if inventory is None:
            return 0
        return sum(int(inventory.get(item_key, 0)) for item_key in self.HUNTING_FOOD_ITEMS)

    def _get_village_food_supply_count(self, village: Village | None) -> int:
        if village is None:
            return 0
        supply_count = sum(int(getattr(village, "supply", {}).get(item_key, 0)) for item_key in self.HUNTING_FOOD_ITEMS)
        for building in getattr(village, "buildings", []):
            supply_count += self._get_available_food_count(getattr(building, "building_inventory", None))
        return supply_count

    def _refresh_village_food_pressure(self, village: Village | None) -> None:
        if village is None:
            return
        residents = max(1, len([npc for npc in self.village_npcs if not npc.physical.is_dead and self._get_village_for_npc(npc) == village]))
        food_supply = self._get_village_food_supply_count(village)
        if food_supply < residents:
            village.demand["food"] = max(village.demand.get("food", 0), residents - food_supply)
        elif "food" in village.demand:
            village.demand["food"] = max(0, village.demand.get("food", 0) - max(1, food_supply - residents + 1))
            if village.demand["food"] <= 0:
                del village.demand["food"]

    def _get_hunter_search_radius(self, npc: NPC) -> int:
        village = self._get_village_for_npc(npc) or self._get_village_for_npc(npc, by_coords=True)
        region_id = getattr(village, "region_id", None)
        populations = self.ecology.get_region_populations(self, region_id) if region_id else {}
        huntable_populations = [population for species, population in populations.items() if species in self.HUNTABLE_SPECIES]
        if not huntable_populations:
            return 80
        best_pressure = max((population.spawn_pressure for population in huntable_populations), default=0.0)
        return 100 if best_pressure < 0.25 else 45

    def _find_hunting_dropoff_building(self, npc: NPC) -> Building | None:
        work_building = self.buildings_by_id.get(getattr(getattr(npc, "schedule", None), "work_building_id", None))
        if work_building is not None:
            return work_building
        village = self._get_village_for_npc(npc) or self._get_village_for_npc(npc, by_coords=True)
        buildings = list(getattr(village, "buildings", [])) if village else list(self.buildings_by_id.values())
        preferred = [building for building in buildings if self._is_butcher_workplace(building)]
        if not preferred:
            preferred = [building for building in buildings if "storage" in str(getattr(building, "category", "")).lower()]
        if not preferred:
            preferred = [building for building in buildings if getattr(building, "category", "") == "residential"]
        if not preferred:
            return None
        return min(preferred, key=lambda building: abs(npc.x - building.global_center_x) + abs(npc.y - building.global_center_y))

    def _wildlife_population_for_animal(self, animal: Animal):
        region_id = getattr(animal, "wildlife_region_id", None)
        species_key = getattr(animal, "animal_type", None)
        if region_id and species_key:
            return self.ecology.get_population(self, region_id, species_key)
        region = self.get_region_for_coords(getattr(animal, "x", 0), getattr(animal, "y", 0))
        if region is None or species_key is None:
            return None
        return self.ecology.get_population(self, region.id, species_key)

    def _find_reachable_hunting_prey(self, npc: NPC, *, search_radius: int | None = None) -> Animal | None:
        search_radius = search_radius or self._get_hunter_search_radius(npc)
        candidates: list[tuple[float, Animal]] = []
        for animal in self.npcs:
            if not isinstance(animal, Animal) or animal.physical.is_dead:
                continue
            species_key = getattr(animal, "animal_type", None)
            if species_key not in self.HUNTABLE_SPECIES:
                continue
            population = self._wildlife_population_for_animal(animal)
            if population is None or population.population_count <= 0:
                continue
            distance = abs(npc.x - animal.x) + abs(npc.y - animal.y)
            if distance > search_radius:
                continue
            if (npc.x, npc.y) == (animal.x, animal.y):
                path = []
            else:
                path = self.calculate_path(npc.x, npc.y, animal.x, animal.y) or []
                if not path:
                    continue
            density_bonus = population.spawn_pressure * 10
            species_bonus = {"deer": 4, "turkey": 3, "rabbit": 2}.get(species_key, 0)
            candidates.append((distance - density_bonus - species_bonus, animal))
        if not candidates:
            return None
        candidates.sort(key=lambda entry: entry[0])
        return candidates[0][1]

    def _extract_meat_from_animal(self, animal: Animal) -> str | None:
        loot_table = getattr(animal, "animal_definition", {}).get("loot_drops", {}) or {}
        for preferred_key in ("raw_venison", "raw_mutton", "raw_meat"):
            if preferred_key in loot_table:
                return preferred_key
        for item_key in loot_table:
            tags = set(ITEM_DEFINITIONS.get(item_key, {}).get("item_type_tags", []))
            if "food_ingredient_raw" in tags or "food" in tags:
                return item_key
        return "raw_meat" if getattr(animal, "animal_type", None) in self.HUNTABLE_SPECIES else None

    def _assign_hunting_task_to_npc(self, npc: NPC) -> bool:
        if not self._is_hunter_role(npc) or getattr(npc, "task_context", None) in {"hunting", "delivery", "hauling", "construction"}:
            return False
        dropoff = self._find_hunting_dropoff_building(npc)
        if dropoff is None:
            return False
        prey = self._find_reachable_hunting_prey(npc)
        if prey is None:
            npc.current_sub_task = "Tracking prey"
            npc.schedule.current_task = "tracking_prey"
            npc.hunting_search_radius = self._get_hunter_search_radius(npc)
            return False
        npc.task_context = "hunting"
        npc.task_context_data = {
            "prey_id": prey.id,
            "dropoff_building_id": dropoff.id,
            "state": "pursuing",
        }
        npc.task_target_entity_id = prey.id
        npc.task_target_coords = (prey.x, prey.y)
        npc.schedule.current_task = "hunting_prey"
        npc.current_sub_task = f"Hunting {getattr(prey, 'animal_type', 'prey')}"
        npc.schedule.current_destination_coords = (prey.x, prey.y)
        npc.schedule.current_path = self.calculate_path(npc.x, npc.y, prey.x, prey.y) or []
        if (npc.x, npc.y) != (prey.x, prey.y) and not npc.schedule.current_path:
            self._clear_hunting_task(npc)
            return False
        return True

    def _clear_hunting_task(self, npc: NPC) -> None:
        npc.task_context = None
        npc.task_context_data = None
        npc.task_target_entity_id = None
        npc.task_target_coords = None
        npc.schedule.current_destination_coords = None
        npc.schedule.current_path = []
        npc.schedule.current_task = TaskType.IDLE
        npc.current_sub_task = None

    def _deposit_hunted_food(self, npc: NPC, building: Building) -> int:
        deposited = 0
        npc_inventory = getattr(getattr(npc, "economic", None), "npc_inventory", None)
        if not isinstance(npc_inventory, Inventory):
            npc.economic.npc_inventory = Inventory(npc_inventory or {})
            npc_inventory = npc.economic.npc_inventory
        for item_key in list(self.BUTCHER_RAW_INPUTS | {"processed_meat"}):
            qty = int(npc_inventory.get(item_key, 0))
            if qty <= 0:
                continue
            deposited += self._move_item_between_inventories(npc_inventory, building.building_inventory, item_key, qty)
        if deposited > 0:
            village = self.get_settlement_by_id(getattr(building, "settlement_id", None)) or self._get_village_for_npc(npc, by_coords=True)
            if village is not None:
                for item_key in self.HUNTING_FOOD_ITEMS:
                    if building.building_inventory.get(item_key, 0) > 0:
                        village.supply[item_key] = max(village.supply.get(item_key, 0), building.building_inventory.get(item_key, 0))
                self._refresh_village_food_pressure(village)
        return deposited

    def _process_butcher_workplace(self, building: Building | None, *, max_items: int = 1) -> int:
        if building is None or not self._is_butcher_workplace(building):
            return 0
        processed = 0
        consumed_by_key: dict[str, int] = {}
        for item_key in ("raw_venison", "raw_mutton", "raw_meat"):
            while processed < max_items and building.building_inventory.get(item_key, 0) > 0:
                if not building.building_inventory.remove_item(item_key, 1):
                    break
                building.building_inventory.add_item("processed_meat", 1)
                consumed_by_key[item_key] = consumed_by_key.get(item_key, 0) + 1
                processed += 1
            if processed >= max_items:
                break
        if processed > 0:
            village = self.get_settlement_by_id(getattr(building, "settlement_id", None))
            if village is not None:
                village.supply["processed_meat"] = village.supply.get("processed_meat", 0) + processed
                for raw_key, consumed_qty in consumed_by_key.items():
                    if village.supply.get(raw_key, 0) > 0:
                        village.supply[raw_key] = max(0, village.supply.get(raw_key, 0) - consumed_qty)
                        if village.supply[raw_key] <= 0:
                            village.supply.pop(raw_key, None)
                self._refresh_village_food_pressure(village)
        return processed

    def _handle_npc_hunting_task(self, npc: NPC) -> bool:
        if getattr(npc, "task_context", None) != "hunting":
            return False
        task_data = npc.task_context_data if isinstance(npc.task_context_data, dict) else {}
        state = task_data.get("state", "pursuing")
        dropoff = self.buildings_by_id.get(task_data.get("dropoff_building_id"))
        if dropoff is None:
            self._clear_hunting_task(npc)
            return False

        if state == "pursuing":
            prey = self.get_entity_by_id(task_data.get("prey_id"))
            if not isinstance(prey, Animal) or prey.physical.is_dead:
                self._clear_hunting_task(npc)
                return False
            distance = abs(npc.x - prey.x) + abs(npc.y - prey.y)
            if distance > 1:
                if npc.schedule.current_destination_coords != (prey.x, prey.y) or not npc.schedule.current_path:
                    npc.schedule.current_path = self.calculate_path(npc.x, npc.y, prey.x, prey.y) or []
                    npc.schedule.current_destination_coords = (prey.x, prey.y)
                if not npc.schedule.current_path:
                    self._clear_hunting_task(npc)
                    return False
                npc.schedule.current_task = "hunting_prey"
                npc.current_sub_task = f"Tracking {getattr(prey, 'animal_type', 'prey')}"
                return True

            meat_key = self._extract_meat_from_animal(prey)
            prey.physical.is_dead = True
            self.handle_npc_death(prey, killer_id=npc.id)
            if meat_key:
                npc.economic.npc_inventory.add_item(meat_key, 1)
            task_data["state"] = "returning"
            task_data["carried_item"] = meat_key
            npc.task_context_data = task_data
            npc.schedule.current_task = "returning_with_meat"
            npc.current_sub_task = f"Carrying {meat_key or 'carcass'}"
            coords = (dropoff.global_center_x, dropoff.global_center_y)
            npc.task_target_coords = coords
            npc.schedule.current_destination_coords = coords
            npc.schedule.current_path = self.calculate_path(npc.x, npc.y, coords[0], coords[1]) or []
            return True

        if state == "returning":
            coords = (dropoff.global_center_x, dropoff.global_center_y)
            if (npc.x, npc.y) != coords:
                if npc.schedule.current_destination_coords != coords or not npc.schedule.current_path:
                    npc.schedule.current_path = self.calculate_path(npc.x, npc.y, coords[0], coords[1]) or []
                    npc.schedule.current_destination_coords = coords
                if not npc.schedule.current_path:
                    self._clear_hunting_task(npc)
                    return False
                npc.schedule.current_task = "returning_with_meat"
                npc.current_sub_task = "Returning with meat"
                return True
            deposited = self._deposit_hunted_food(npc, dropoff)
            if deposited > 0:
                npc.current_sub_task = "Delivering meat"
                self._process_butcher_workplace(dropoff, max_items=deposited)
            self._clear_hunting_task(npc)
            return deposited > 0
        return False

    def _process_offscreen_hunting_for_village(self, village: Village, hunters: list[NPC] | None = None) -> int:
        hunters = hunters if hunters is not None else [npc for npc in self.village_npcs if self._is_hunter_role(npc) and self._get_village_for_npc(npc) == village]
        if not hunters:
            return 0
        region_id = getattr(village, "region_id", None)
        populations = self.ecology.get_region_populations(self, region_id) if region_id else {}
        if not populations:
            return 0
        output = 0
        for hunter in hunters:
            viable = [population for species, population in populations.items() if species in self.HUNTABLE_SPECIES and population.population_count > 0 and population.spawn_pressure > 0]
            if not viable:
                village.demand["food"] = village.demand.get("food", 0) + 1
                continue
            population = max(viable, key=lambda pop: (pop.spawn_pressure, pop.population_count))
            population.population_count = max(0, population.population_count - 1)
            population.refresh_pressure()
            meat_key = "raw_venison" if population.species_key == "deer" else "raw_meat"
            village.supply[meat_key] = village.supply.get(meat_key, 0) + 1
            output += 1
        self._refresh_village_food_pressure(village)
        return output


    def _warn_simulation_validation(self, warning_type: str, key, message: str, *, actor=None, metadata: dict | None = None, cooldown_ticks: int = 120) -> bool:
        from simulation.validation import emit_validation_warning

        return emit_validation_warning(
            self,
            warning_type,
            key,
            message,
            cooldown_ticks=cooldown_ticks,
            actor=actor,
            metadata=metadata,
        )

    def _abandon_invalid_work_sub_task(self, npc: NPC, *, reason: str, sub_task_data: dict | None = None, metadata: dict | None = None) -> None:
        details = dict(metadata or {})
        if sub_task_data:
            details.setdefault("sub_task_id", sub_task_data.get("id"))
            details.setdefault("target_zone_tag", sub_task_data.get("target_zone_tag"))
        self._warn_simulation_validation(
            "task_abandoned",
            (getattr(npc, "id", None), reason, details.get("sub_task_id")),
            f"{getattr(npc, 'name', 'NPC')} abandoned invalid work task: {reason}",
            actor=npc,
            metadata=details,
        )
        npc.clear_work_sub_task_state()
        npc.schedule.current_path = []
        npc.schedule.current_destination_coords = None
        npc.task_target_coords = None
        npc._work_validation_retry_after_tick = getattr(self, "game_time", 0) + 120

    def _find_target_coords_for_sub_task(self, npc: NPC, work_building: Building, sub_task_data: dict) -> tuple[int, int] | None:
        """Determines the global target coordinates for a given sub-task."""
        target_zone_tag = sub_task_data.get("target_zone_tag")
        if not target_zone_tag:
            self._warn_simulation_validation(
                "invalid_subtask",
                (getattr(work_building, "id", None), sub_task_data.get("id"), "missing_target_zone_tag"),
                "Work sub-task is missing target_zone_tag.",
                actor=npc,
                metadata={"building_id": getattr(work_building, "id", None), "sub_task_id": sub_task_data.get("id")},
            )
            return None

        if target_zone_tag == "corpse":
            return self._find_nearest_corpse(npc)


        if target_zone_tag == "manager_spot":
            manager_spots = work_building.work_zone_tiles.get("manager_spot", [])
            if manager_spots:
                return random.choice(manager_spots)
            else:
                return (work_building.global_center_x, work_building.global_center_y)

        if target_zone_tag == "scout_route":
            # For scouting, pick a random point in a wider radius around the village/workplace
            # to simulate patrolling the wilderness.
            center_x = work_building.global_center_x
            center_y = work_building.global_center_y
            scout_radius = 40

            for _ in range(10): # Try a few times to find a valid spot
                offset_x = random.randint(-scout_radius, scout_radius)
                offset_y = random.randint(-scout_radius, scout_radius)
                scout_x = center_x + offset_x
                scout_y = center_y + offset_y

                # Ensure bounds
                scout_x = max(0, min(WORLD_WIDTH - 1, scout_x))
                scout_y = max(0, min(WORLD_HEIGHT - 1, scout_y))

                tile = self.get_tile_at(scout_x, scout_y)
                if tile and tile.passable:
                    return (scout_x, scout_y)
            return None

        if target_zone_tag == "chopping_area":
            # For chopping, we find a dynamic tree target near the building.
            # The work_building itself is passed to help center the search.
            return self._find_nearest_tree_for_chopping(npc, work_building)
        elif target_zone_tag == "lumber_mill":
            # For fetching wood, find the nearest lumber mill
            lumber_mill = self._find_nearest_lumber_mill(npc)
            if lumber_mill:
                return (lumber_mill.global_center_x, lumber_mill.global_center_y)
            return None
        elif target_zone_tag == "farm":
            # For fetching wheat, find the nearest farm
            farm = self._find_nearest_farm(npc)
            if farm:
                return (farm.global_center_x, farm.global_center_y)
            return None
        elif target_zone_tag == "mill":
            # For fetching flour, find the nearest mill
            mill = self._find_nearest_mill(npc)
            if mill:
                return (mill.global_center_x, mill.global_center_y)
            return None
        elif target_zone_tag == "mine":
            # For fetching ore, find the nearest mine
            mine = self._find_nearest_mine(npc)
            if mine:
                return (mine.global_center_x, mine.global_center_y)
            return None
        elif npc.economic.profession == "Farmer" and target_zone_tag == "field_patch":
            field_tiles_coords = work_building.work_zone_tiles.get("field_patch", [])
            if not field_tiles_coords:
                self._warn_simulation_validation(
                    "missing_zone",
                    (getattr(work_building, "id", None), "field_patch"),
                    "Farm work task requires a field_patch zone, but none is defined.",
                    actor=npc,
                    metadata={"building_id": getattr(work_building, "id", None), "sub_task_id": sub_task_data.get("id"), "zone": "field_patch"},
                )
                return None

            target_tile_type_key = sub_task_data.get("target_tile_type_key") # e.g., "plains", "tilled_soil"
            if not target_tile_type_key:
                self._warn_simulation_validation(
                    "invalid_subtask",
                    (getattr(work_building, "id", None), sub_task_data.get("id"), "missing_target_tile_type_key"),
                    "Farmer work sub-task is missing target_tile_type_key.",
                    actor=npc,
                    metadata={"building_id": getattr(work_building, "id", None), "sub_task_id": sub_task_data.get("id"), "zone": "field_patch"},
                )
                return None

            # Specific check for "plant_seeds": ensure seeds are available BEFORE finding a tile
            if sub_task_data["id"] == "plant_seeds":
                seeds_to_consume = sub_task_data.get("consumes_item_from_workplace", {})
                seed_item_key = next(iter(seeds_to_consume), None) # Get the first seed type key
                if not seed_item_key or work_building.building_inventory.get(seed_item_key, 0) < seeds_to_consume[seed_item_key]:
                    self._warn_simulation_validation(
                        "missing_resource",
                        (getattr(work_building, "id", None), sub_task_data.get("id"), seed_item_key),
                        "Farm work task requires seeds that are not available.",
                        actor=npc,
                        metadata={"building_id": getattr(work_building, "id", None), "sub_task_id": sub_task_data.get("id"), "item_key": seed_item_key},
                    )
                    return None # Cannot plant if no seeds

            # Shuffle to vary the choice of tile a bit if multiple are suitable
            random.shuffle(field_tiles_coords)

            for tx, ty in field_tiles_coords:
                tile = self.get_tile_at(tx, ty)
                # Check if tile name matches the required type for the sub-task
                # Tile objects store their definition's key in tile.name if generated from TILE_DEFINITIONS keys
                # Or compare against the actual name string from TILE_DEFINITIONS
                expected_tile_name = TILE_DEFINITIONS.get(target_tile_type_key, {}).get("name")
                if tile and tile.name == expected_tile_name:
                    # Check if this tile is already targeted by another NPC for the same task
                    is_already_targeted = False
                    for other_npc in self.village_npcs:
                        if other_npc.id != npc.id and \
                           other_npc.current_sub_task == sub_task_data["id"] and \
                           other_npc.sub_task_target_coords == (tx, ty):
                            is_already_targeted = True
                            break

                    if not is_already_targeted:
                        return (tx, ty)
            self._warn_simulation_validation(
                "missing_tile",
                (getattr(work_building, "id", None), sub_task_data.get("id"), target_tile_type_key),
                "Work task could not find a suitable tile in its zone.",
                actor=npc,
                metadata={"building_id": getattr(work_building, "id", None), "sub_task_id": sub_task_data.get("id"), "target_tile_type_key": target_tile_type_key, "expected_tile_name": expected_tile_name},
            )
            return None
        else:
            # Check for anchor usage for these indoor work tags first
            if target_zone_tag in {"workbench", "desk_area", "writing_desk", "cooking_station", "alchemy_station", "medical_bed", "office_desk"}:
                anchor_types = ["work", "service"]

                ideal_role = "workbench"
                if target_zone_tag in {"desk_area", "writing_desk", "office_desk"}:
                    ideal_role = "desk"
                elif target_zone_tag == "medical_bed":
                    ideal_role = "bed"
                elif target_zone_tag == "cooking_station":
                    ideal_role = "fireplace"

                anchor_coords = work_building.get_anchor_coordinates(anchor_types, None, world=self, requesting_entity=npc, ideal_role=ideal_role)
                if self._is_valid_coordinate_pair(anchor_coords):
                    refined_coords = work_building.refine_anchor_coordinates(self, anchor_coords[0], anchor_coords[1], requesting_entity=npc)
                    if self._is_valid_coordinate_pair(refined_coords):
                        return tuple(refined_coords)

            # For other zones (like Woodcutter's log_pile_area), use pre-defined coordinates
            zone_coords_list = work_building.work_zone_tiles.get(target_zone_tag)
            if zone_coords_list:
                # Pick a random available coordinate from the list for now.
                # Could be smarter (e.g., closest, or one not currently targeted by another NPC).
                return random.choice(zone_coords_list)
            else:
                # Fallback to work/service anchors if no zone coordinates defined
                anchor_coords = work_building.get_anchor_coordinates(["work", "service"], None, world=self, requesting_entity=npc)
                if self._is_valid_coordinate_pair(anchor_coords):
                    refined_coords = work_building.refine_anchor_coordinates(self, anchor_coords[0], anchor_coords[1], requesting_entity=npc)
                    if self._is_valid_coordinate_pair(refined_coords):
                        return tuple(refined_coords)

                # self.add_message_to_chat_log(f"Warning: No coordinates defined for work zone '{target_zone_tag}' in building {work_building.id} for {npc.name}.")
                return None

    def _move_item_between_inventories(self, source_inventory, destination_inventory, item_key: str, quantity: int = 1) -> int:
        """Move items between inventory-like containers while preserving item objects when possible."""
        if quantity <= 0 or source_inventory is None or destination_inventory is None:
            return 0

        if hasattr(source_inventory, "transfer_item_objects"):
            return source_inventory.transfer_item_objects(destination_inventory, item_key, quantity)

        available_quantity = source_inventory.get(item_key, 0)
        moved_quantity = min(available_quantity, quantity)
        if moved_quantity <= 0:
            return 0

        source_inventory[item_key] = available_quantity - moved_quantity
        if source_inventory.get(item_key, 0) <= 0 and item_key in source_inventory:
            del source_inventory[item_key]

        if hasattr(destination_inventory, "add_item"):
            destination_inventory.add_item(item_key, moved_quantity)
        else:
            destination_inventory[item_key] = destination_inventory.get(item_key, 0) + moved_quantity
        return moved_quantity

    def _get_trade_inventory(self, holder):
        if holder is None:
            return None
        if hasattr(holder, "economic") and hasattr(holder.economic, "npc_inventory"):
            if not isinstance(holder.economic.npc_inventory, Inventory):
                holder.economic.npc_inventory = Inventory(holder.economic.npc_inventory or {})
            return holder.economic.npc_inventory
        if hasattr(holder, "building_inventory"):
            if not isinstance(holder.building_inventory, Inventory):
                holder.building_inventory = Inventory(holder.building_inventory or {})
            return holder.building_inventory
        return None

    def _get_trade_money_balance(self, holder) -> int:
        if holder is None:
            return 0
        if hasattr(holder, "economic") and hasattr(holder.economic, "money"):
            return max(0, int(holder.economic.money))
        inventory = self._get_trade_inventory(holder)
        if inventory is not None:
            return max(0, int(inventory.get("money", 0)))
        return 0

    def _set_trade_money_balance(self, holder, amount: int) -> None:
        normalized_amount = max(0, int(amount))
        if holder is None:
            return
        if hasattr(holder, "economic") and hasattr(holder.economic, "money"):
            holder.economic.money = normalized_amount
            return
        inventory = self._get_trade_inventory(holder)
        if inventory is None:
            return
        if normalized_amount <= 0:
            inventory.pop("money", None)
        else:
            inventory["money"] = normalized_amount

    def quote_item_reference_price(self, item_reference: ItemReference, village: Village | None = None) -> int:
        """Return a trade price that preserves quality scaling from the concrete item object."""
        if item_reference is None:
            return 0

        item_key = item_reference.key
        base_value = max(1, ITEM_DEFINITIONS.get(item_key, {}).get("value", 1))
        quality_scaled_value = max(1, item_reference.value)
        if village is None:
            return quality_scaled_value

        market_base_price = max(1, self.get_dynamic_price(item_key, village))
        quality_multiplier = quality_scaled_value / base_value
        return max(1, int(round(market_base_price * quality_multiplier)))

    def execute_trade(
        self,
        buyer,
        seller,
        item_reference: ItemReference,
        price: int | None = None,
        *,
        buyer_inventory=None,
        seller_inventory=None,
    ) -> bool:
        """
        Transfer a specific item object from seller to buyer while moving currency in the opposite direction.
        """
        if item_reference is None:
            return False

        buyer_inventory = buyer_inventory or self._get_trade_inventory(buyer)
        seller_inventory = seller_inventory or self._get_trade_inventory(seller)
        if buyer_inventory is None or seller_inventory is None:
            return False
        if not hasattr(seller_inventory, "transfer_item_reference") or not seller_inventory.has_item_reference(item_reference):
            return False

        final_price = max(0, int(item_reference.value if price is None else price))
        buyer_balance = self._get_trade_money_balance(buyer)
        seller_balance = self._get_trade_money_balance(seller)
        if buyer_balance < final_price:
            return False

        if not seller_inventory.transfer_item_reference(buyer_inventory, item_reference):
            return False

        self._set_trade_money_balance(buyer, buyer_balance - final_price)
        self._set_trade_money_balance(seller, seller_balance + final_price)
        if getattr(item_reference, "equip_slot", None) and hasattr(buyer, "evaluate_and_upgrade_equipment"):
            buyer.evaluate_and_upgrade_equipment()
        return True

    def _execute_item_sales(self, seller, buyer, item_key: str, quantity: int = 1, village: Village | None = None) -> int:
        seller_inventory = self._get_trade_inventory(seller)
        buyer_inventory = self._get_trade_inventory(buyer)
        if seller_inventory is None or buyer_inventory is None:
            return 0

        sold = 0
        for _ in range(max(0, int(quantity))):
            item_reference = seller_inventory.get_item_reference(item_key)
            if item_reference is None:
                break
            price = self.quote_item_reference_price(item_reference, village=village)
            if not self.execute_trade(
                buyer,
                seller,
                item_reference,
                price,
                buyer_inventory=buyer_inventory,
                seller_inventory=seller_inventory,
            ):
                break
            sold += 1
        return sold

    def _produce_sub_task_output(self, npc: NPC, work_building: Building, sub_task_data: dict, target_tile_obj: Tile | None = None) -> bool:
        """
        Handles item production or consumption for a completed sub-task.
        This now also handles transfers from NPC inventory to building inventory,
        and production based on tile properties (for harvesting).
        Returns True if all necessary consumptions were successful, False otherwise.
        """
        consumption_successful = True # Assume success unless specific consumption fails

        # 1. Consume from NPC inventory (if defined)
        consumes_from_npc_def = sub_task_data.get("consumes_item_from_npc_inventory")
        deposits_to_building_def = sub_task_data.get("deposits_item_to_workplace", {}) or {}
        transferred_to_building: dict[str, int] = {}
        if consumes_from_npc_def:
            for item_key, quantity_needed in consumes_from_npc_def.items():
                current_npc_qty = npc.economic.npc_inventory.get(item_key, 0)
                if current_npc_qty >= quantity_needed:
                    quantity_to_transfer = min(quantity_needed, deposits_to_building_def.get(item_key, 0))
                    if quantity_to_transfer > 0:
                        preferred_sale_targets = {
                            "raw_log": {"lumber_mill", "general_store"},
                            "iron_ore": {"blacksmith_shop", "general_store"},
                            "coal": {"blacksmith_shop", "general_store"},
                            "stone_chunk": {"general_store"},
                        }
                        sold_via_trade = work_building.building_type in preferred_sale_targets.get(item_key, set())
                        if sold_via_trade:
                            village = self._get_village_for_npc(npc, by_coords=True)
                            transferred_to_building[item_key] = self._execute_item_sales(
                                seller=npc,
                                buyer=work_building,
                                item_key=item_key,
                                quantity=quantity_to_transfer,
                                village=village,
                            )
                        else:
                            transferred_to_building[item_key] = self._move_item_between_inventories(
                                npc.economic.npc_inventory,
                                work_building.building_inventory,
                                item_key,
                                quantity_to_transfer,
                            )
                        if sold_via_trade and transferred_to_building.get(item_key, 0) < quantity_to_transfer:
                            consumption_successful = False
                            break

                    remaining_quantity_to_consume = quantity_needed - transferred_to_building.get(item_key, 0)
                    if remaining_quantity_to_consume > 0:
                        npc.economic.npc_inventory[item_key] = current_npc_qty - transferred_to_building.get(item_key, 0) - remaining_quantity_to_consume
                        if npc.economic.npc_inventory.get(item_key, 0) <= 0 and item_key in npc.economic.npc_inventory:
                            del npc.economic.npc_inventory[item_key]
                    # self.add_message_to_chat_log(f"Debug: {npc.name} consumed {quantity_needed} {item_key} from personal inventory.")
                else:
                    # self.add_message_to_chat_log(f"Debug: {npc.name} needed {quantity_needed} {item_key} from inventory for task, but only had {current_npc_qty}.")
                    consumption_successful = False
                    break # Stop further processing for this sub-task if NPC consumption fails
            if not consumption_successful:
                return # Early exit if NPC couldn't provide required items from its inventory

        # 2. Consume from Workplace inventory (if defined)
        # This should only happen if NPC consumption (if any) was successful
        if consumption_successful:
            consumes_from_building_def = sub_task_data.get("consumes_item_from_workplace")
            if consumes_from_building_def:
                for item_key, quantity_needed in consumes_from_building_def.items():
                    current_building_qty = work_building.building_inventory.get(item_key, 0)
                    if current_building_qty >= quantity_needed:
                        work_building.building_inventory[item_key] = current_building_qty - quantity_needed
                        if work_building.building_inventory[item_key] <= 0:
                            del work_building.building_inventory[item_key]
                        # self.add_message_to_chat_log(f"Debug: Task consumed {quantity_needed} {item_key} from {work_building.building_type}.")
                    else:
                        # self.add_message_to_chat_log(f"Debug: {work_building.building_type} needed {quantity_needed} {item_key} for task, but only had {current_building_qty}.")
                        consumption_successful = False
                        break # Stop further processing if building consumption fails
                if not consumption_successful:
                    # TODO: What if NPC items were consumed but building items were not? Rollback NPC consumption?
                    # For now, if building consumption fails, the process stops, potentially leaving NPC items consumed.
                    # This implies sub-tasks should be designed carefully (e.g., consume from NPC then deposit to building is one flow,
                    # consume from building to produce to building is another).
                    return False # Indicate consumption failed

        # 3. Deposit items to Workplace (if defined, and all consumptions were successful)
        if consumption_successful:
            if deposits_to_building_def:
                for item_key, quantity_deposited in deposits_to_building_def.items():
                    remaining_quantity_to_deposit = quantity_deposited - transferred_to_building.get(item_key, 0)
                    if remaining_quantity_to_deposit <= 0:
                        continue
                    current_building_qty = work_building.building_inventory.get(item_key, 0)
                    work_building.building_inventory[item_key] = current_building_qty + remaining_quantity_to_deposit
                    # item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
                    # self.add_message_to_chat_log(f"Debug: {npc.name} deposited {quantity_deposited} {item_name} to {work_building.building_type}.")

        # 4. Produce items at Workplace (if defined, and all consumptions were successful)
        if consumption_successful:
            # A. Check for tile-based harvest production first
            if sub_task_data.get("produces_item_at_workplace_from_tile_harvest") and target_tile_obj:
                if target_tile_obj.properties.get("is_harvestable"):
                    item_key = target_tile_obj.properties.get("harvest_yield_item_key")
                    quantity_produced = target_tile_obj.properties.get("harvest_yield_quantity", 0)
                    if item_key and quantity_produced > 0:
                        current_building_qty = work_building.building_inventory.get(item_key, 0)
                        work_building.building_inventory[item_key] = current_building_qty + quantity_produced
                        item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
                        self.visual_effects.append(FloatingTextEffect(npc.x, npc.y, f"+{quantity_produced} {item_name}", color=(50, 255, 50)))

            # B. Standard sub-task defined production (if not tile harvest or in addition to)
            # Ensure this doesn't double-produce if tile harvest already happened for same item.
            # Current design: harvest flag is specific, so this is for other direct productions.
            produces_at_building_def = sub_task_data.get("produces_item_at_workplace")
            if produces_at_building_def:
                for item_key, quantity_produced in produces_at_building_def.items():
                    current_building_qty = work_building.building_inventory.get(item_key, 0)
                    work_building.building_inventory[item_key] = current_building_qty + quantity_produced
                    item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
                    self.visual_effects.append(FloatingTextEffect(npc.x, npc.y, f"+{quantity_produced} {item_name}", color=(50, 255, 50)))

        village = self._get_village_for_npc(npc)
        if village:
            if consumption_successful:
                produces = sub_task_data.get("produces_item_at_workplace", {})
                for item_key, qty in produces.items():
                    village.supply[item_key] = village.supply.get(item_key, 0) + qty

                consumes = sub_task_data.get("consumes_item_from_workplace", {})
                for item_key, qty in consumes.items():
                    village.supply[item_key] = village.supply.get(item_key, 0) - qty
                    village.demand[item_key] = village.demand.get(item_key, 0) + qty

        return consumption_successful


    def _execute_completed_work_sub_task(self, npc: NPC, work_building: Building, sub_task_id: str, sub_task_data: dict):
        """Execute the command for a completed work sub-task."""
        command = COMPLETED_WORK_SUB_TASK_COMMANDS.get(sub_task_id, DefaultProduceOutputSubTaskCommand())
        task_completed = command.execute(self, npc, work_building, sub_task_data)
        if task_completed:
            self._degrade_npc_tool_for_sub_task(npc, sub_task_id)
            self._attempt_npc_sell_trade_goods(npc)
            self._attempt_workplace_supply_chain_actions(npc, work_building)

    def _degrade_npc_tool_for_sub_task(self, npc: NPC, sub_task_id: str):
        """Degrade an equipped NPC tool when a work sub-task uses it successfully."""
        required_tool_type = NPC_WORK_TOOL_TYPES.get(sub_task_id)
        if not required_tool_type or not npc.equipment.weapon:
            return

        weapon_key = str(npc.equipment.weapon)
        weapon_ref = npc.economic.npc_inventory.get_item_reference(weapon_key)
        if weapon_ref is None or weapon_ref.tool_type != required_tool_type:
            return

        npc.degrade_equipped_item("weapon", world=self)

    def _find_trade_buyer_for_item(self, npc: NPC, item_key: str) -> Building | None:
        preferred_building_types = {
            "raw_log": ["lumber_mill", "general_store"],
            "iron_ore": ["blacksmith_shop", "general_store"],
            "coal": ["blacksmith_shop", "general_store"],
            "stone_chunk": ["general_store"],
        }
        for building_type in preferred_building_types.get(item_key, []):
            buyer = self._find_nearest_building_of_type(npc, building_type)
            if buyer:
                return buyer
        return None

    def _attempt_npc_sell_trade_goods(self, npc: NPC) -> int:
        sold_total = 0
        sale_candidate_keys = ["raw_log", "iron_ore", "coal", "stone_chunk"]
        village = self._get_village_for_npc(npc, by_coords=True)

        for item_key in sale_candidate_keys:
            quantity_available = npc.economic.npc_inventory.get(item_key, 0)
            if quantity_available <= 0:
                continue

            buyer = self._find_trade_buyer_for_item(npc, item_key)
            if buyer is None:
                continue

            sold_total += self._execute_item_sales(
                seller=npc,
                buyer=buyer,
                item_key=item_key,
                quantity=quantity_available,
                village=village,
            )

        return sold_total

    def _get_supported_workstations_for_building(self, work_building: Building) -> set[str]:
        supported_workstations = set(getattr(work_building, "work_zone_tiles", {}).keys())
        building_type = getattr(work_building, "building_type", None)
        if not building_type:
            return supported_workstations
        building_type_defaults = {
            "manager_spot": {"manager_spot"},
            "lumber_mill": {"workbench"},
            "blacksmith_shop": {"forge", "anvil"},
            "bakery": {"fire"},
            "tavern": {"fire"},
            "mill": {"grinding_stone"},
            "carpenter_shop": {"workbench"},
        }
        supported_workstations.update(building_type_defaults.get(building_type, set()))
        return supported_workstations

    def _get_workplace_recipe_candidates(self, npc: NPC, work_building: Building) -> list[str]:
        supported_workstations = self._get_supported_workstations_for_building(work_building)
        if not supported_workstations:
            return []

        candidates: list[tuple[int, str]] = []
        for item_key, item_def in ITEM_DEFINITIONS.items():
            recipe = item_def.get("crafting_recipe") or {}
            required_workstation = item_def.get("required_workstation")
            if not recipe or not required_workstation or required_workstation not in supported_workstations:
                continue
            if any(work_building.building_inventory.get(ingredient_key, 0) < required_qty for ingredient_key, required_qty in recipe.items()):
                continue
            quoted_price = self.quote_item_reference_price(ItemReference(item_key), village=self._get_village_for_npc(npc, by_coords=True))
            candidates.append((quoted_price, item_key))

        candidates.sort(reverse=True)
        return [item_key for _, item_key in candidates]

    def _consume_inventory_recipe_item_objects(self, inventory: Inventory, recipe: dict[str, int]) -> bool:
        removed_items: list[ItemReference] = []
        for item_key, required_qty in recipe.items():
            for _ in range(max(0, int(required_qty))):
                item_reference = inventory.pop_item_reference(item_key)
                if item_reference is None:
                    for removed_item in removed_items:
                        inventory.add_item_reference(removed_item)
                    return False
                removed_items.append(item_reference)
        return True

    def _craft_recipe_at_workplace(self, npc: NPC, work_building: Building, item_key: str) -> bool:
        item_def = ITEM_DEFINITIONS.get(item_key, {})
        recipe = item_def.get("crafting_recipe") or {}
        if not recipe:
            return False
        if not self._consume_inventory_recipe_item_objects(work_building.building_inventory, recipe):
            return False

        existing_item_ids = {id(item) for item in npc.economic.npc_inventory.iter_item_references(item_key)}
        npc.craft_item(item_key, 1)
        crafted_item = next(
            (item for item in npc.economic.npc_inventory.iter_item_references(item_key) if id(item) not in existing_item_ids),
            None,
        )
        if crafted_item is None:
            return False
        return npc.economic.npc_inventory.transfer_item_reference(work_building.building_inventory, crafted_item)

    def _get_workplace_recipe_ingredient_keys(self, work_building: Building) -> set[str]:
        ingredient_keys: set[str] = set()
        supported_workstations = self._get_supported_workstations_for_building(work_building)
        for item_def in ITEM_DEFINITIONS.values():
            recipe = item_def.get("crafting_recipe") or {}
            required_workstation = item_def.get("required_workstation")
            if recipe and required_workstation in supported_workstations:
                ingredient_keys.update(recipe.keys())
        return ingredient_keys

    def _find_export_buyer_for_item(self, npc: NPC, item_reference: ItemReference, work_building: Building) -> Building | None:
        if work_building.building_type == "general_store":
            return None

        item_def = ITEM_DEFINITIONS.get(item_reference.key, {})
        tags = set(item_def.get("item_type_tags", []))
        preferred_buyer_types = ["general_store"]
        if "food" in tags or "drink" in tags:
            preferred_buyer_types = ["tavern", "general_store"]

        for building_type in preferred_buyer_types:
            buyer = self._find_nearest_building_of_type(npc, building_type)
            if buyer and buyer.id != work_building.id:
                return buyer
        return None

    def _attempt_workplace_export(self, npc: NPC, work_building: Building) -> int:
        if not getattr(work_building, "building_type", None):
            return 0
        inventory = self._get_trade_inventory(work_building)
        if inventory is None or not hasattr(inventory, "iter_item_references"):
            return 0
        ingredient_keys = self._get_workplace_recipe_ingredient_keys(work_building)
        village = self._get_village_for_npc(npc, by_coords=True)
        exported_count = 0

        for item_reference in list(inventory.iter_item_references()):
            item_key = item_reference.key
            if item_key == "money":
                continue
            item_def = ITEM_DEFINITIONS.get(item_key, {})
            tags = set(item_def.get("item_type_tags", []))
            if item_key.startswith("raw_") or "resource" in tags or item_key in ingredient_keys:
                continue

            buyer = self._find_export_buyer_for_item(npc, item_reference, work_building)
            if buyer is None:
                continue

            price = self.quote_item_reference_price(item_reference, village=village)
            if self.execute_trade(
                buyer=buyer,
                seller=work_building,
                item_reference=item_reference,
                price=price,
                buyer_inventory=buyer.building_inventory,
                seller_inventory=work_building.building_inventory,
            ):
                exported_count += 1
                break

        return exported_count

    def _attempt_workplace_supply_chain_actions(self, npc: NPC, work_building: Building) -> bool:
        if not getattr(work_building, "building_type", None):
            return False

        # 1. Check for shortages first
        supported_workstations = self._get_supported_workstations_for_building(work_building)
        if supported_workstations:
            missing_inputs = []

            # Determine what we actually want to craft based on building type defaults to prevent hoarding random junk
            target_products = []
            if work_building.building_type == "lumber_mill": target_products = ["wooden_plank"]
            elif work_building.building_type == "blacksmith_shop": target_products = ["iron_ingot", "iron_sword"]
            elif work_building.building_type == "bakery": target_products = ["bread"]
            elif work_building.building_type == "mill": target_products = ["flour"]
            else:
                # Fallback to anything they have at least 1 ingredient for or are defined to make
                pass

            for item_key, item_def in ITEM_DEFINITIONS.items():
                recipe = item_def.get("crafting_recipe") or {}
                required_workstation = item_def.get("required_workstation")
                if not recipe or required_workstation not in supported_workstations:
                    continue

                if target_products and item_key not in target_products:
                    continue

                # If we have a recipe we *want* to make but don't have ingredients for
                for ingredient_key, required_qty in recipe.items():
                    if work_building.building_inventory.get(ingredient_key, 0) < required_qty:
                        missing_inputs.append(ingredient_key)

            if missing_inputs:
                missing_item = missing_inputs[0]
                # Attempt to procure it from the general store/village storage
                village = self._get_village_for_npc(npc, by_coords=True)
                if village:
                    for b in village.buildings:
                        if b.building_type in ["general_store", "warehouse", "market"] and b.id != work_building.id:
                            if b.building_inventory.get(missing_item, 0) > 0:
                                # Buy/Transfer it
                                from entities.items import ItemReference
                                price = self.quote_item_reference_price(ItemReference(missing_item), village=village)
                                # Transfer money and item
                                if work_building.building_inventory.get("money", 0) >= price or getattr(work_building, "owner_id", None) is None:
                                    is_active = self._is_building_active(work_building) or self._is_building_active(b)

                                    if is_active:
                                        # Physical logistics mode (local/active): post a deduped task only.
                                        # The source item is not removed until an NPC reaches the source.
                                        self._recover_invalid_delivery_tasks()
                                        self.town_board.post_delivery_task(
                                            source_building_id=b.id,
                                            destination_building_id=work_building.id,
                                            item_key=missing_item,
                                            quantity=1,
                                            created_tick=self.game_time
                                        )
                                        # Show we are stalled and waiting for delivery
                                        if hasattr(self, "visual_effects") and self.game_time % 60 == 0:
                                            self.visual_effects.append(FloatingTextEffect(npc.x, npc.y, "*Awaiting delivery*", color=(200, 200, 150)))
                                        return True
                                    else:
                                        # Abstract logistics mode (offscreen fallback)
                                        if getattr(work_building, "owner_id", None) is not None:
                                            work_building.building_inventory["money"] -= price
                                            b.building_inventory["money"] = b.building_inventory.get("money", 0) + price

                                        # physically transfer 1 ref
                                        ref = b.building_inventory.pop_item_reference(missing_item)
                                        if ref:
                                            work_building.building_inventory.add_item_reference(ref)
                                            # Show hauling action
                                            if hasattr(self, "visual_effects"):
                                                # Avoid direct engine import per nitpicks, already in engine anyway
                                                self.visual_effects.append(FloatingTextEffect(npc.x, npc.y, f"*hauling {missing_item}*", color=(200, 200, 100)))
                                            return True

                # If we get here, we are truly stalled on inputs.
                if hasattr(self, "visual_effects") and self.game_time % 60 == 0:
                    self.visual_effects.append(FloatingTextEffect(npc.x, npc.y, f"*short on {missing_item}*", color=(200, 100, 100)))

        # 2. Try Crafting
        crafted_anything = False
        for recipe_item_key in self._get_workplace_recipe_candidates(npc, work_building):
            if self._craft_recipe_at_workplace(npc, work_building, recipe_item_key):
                crafted_anything = True
                break

        # 3. Try Exporting
        exported_anything = self._attempt_workplace_export(npc, work_building) > 0
        return crafted_anything or exported_anything

    def _handle_npc_combat_turn(self, npc: NPC):
        """
        Handles an NPC's decision-making process during their combat turn using rule-based AI.
        Replaces the previous LLM-based system to prevent lockups.
        """
        if not npc.combat.is_hostile_to_player or npc.physical.is_dead:
            return

        # 1. Gather Context
        player = self.player
        distance_x = abs(npc.x - player.x)
        distance_y = abs(npc.y - player.y)
        manhattan_distance = distance_x + distance_y

        # Determine effective attack range
        effective_attack_range = npc.combat.attack_range
        if npc.equipment.weapon and npc.equipment.weapon in ITEM_DEFINITIONS:
            weapon_def = ITEM_DEFINITIONS[npc.equipment.weapon]
            effective_attack_range = weapon_def.get("properties", {}).get("attack_range", npc.combat.attack_range)

        player_in_attack_range = (manhattan_distance <= effective_attack_range)

        # Determine visibility
        can_see_player = False
        if npc.id in self.npc_fov_maps and \
           0 <= player.x < WORLD_WIDTH and 0 <= player.y < WORLD_HEIGHT:
            can_see_player = self.npc_fov_maps[npc.id][player.y, player.x]

        # 2. Key Status Checks
        hp_percent = npc.combat.hp / npc.combat.max_hp
        is_low_health = hp_percent < 0.3
        is_critical_health = hp_percent < 0.15
        has_healing = npc.economic.npc_inventory.get("healing_salve", 0) > 0

        # 3. Decision Tree
        chosen_action = "hold_position" # Default
        narrative_thought = ""

        # A. Self-Preservation (High Priority)
        should_flee = False
        if is_low_health:
            if npc.combat.combat_behavior == "cowardly":
                should_flee = True
                narrative_thought = f"{npc.name} panics and looks for an escape!"
            elif npc.combat.combat_behavior == "defensive" and not has_healing:
                # Defensive NPCs flee if they can't heal
                should_flee = True
                narrative_thought = f"{npc.name} realizes they cannot win and retreats."
            elif is_critical_health and npc.combat.combat_behavior == "aggressive":
                 # Even aggressive NPCs might flee at death's door, but less likely
                 if random.random() < 0.3:
                     should_flee = True
                     narrative_thought = f"{npc.name} is broken and flees!"
        
        if should_flee:
             chosen_action = "flee_from_player"

        # B. Healing (if hurt but not fleeing)
        if not should_flee and is_low_health and has_healing:
            chosen_action = "use_healing_item"
            narrative_thought = f"{npc.name} grabs a healing salve."

        # C. Aggression (if stable)
        if chosen_action == "hold_position": # If no higher priority action taken
            if can_see_player:
                if player_in_attack_range:
                    chosen_action = "attack_player"
                else:
                    chosen_action = "move_to_attack_player"

        # 4. Execute Action Logic
        npc.combat.target_entity_id = player.id

        if len(narrative_thought) > 0:
             # Only log significant behavior changes or thoughts to avoid combat spam
             if random.random() < 0.3: # Reduce log spam further
                self.add_message_to_chat_log(f"({narrative_thought})")

        if chosen_action == "attack_player":
            npc.schedule.current_task = "combat_action_attack_player"
            # Sound emitted by npc_attempt_attack_player
        elif chosen_action == "move_to_attack_player":
            npc.schedule.current_task = "combat_action_move_to_attack_player"
        elif chosen_action == "flee_from_player":
            npc.schedule.current_task = "combat_action_flee_from_player"
            npc.add_grudge(player.id, "Forced me to flee.")
        elif chosen_action == "use_healing_item":
             npc.schedule.current_task = "combat_action_use_healing_item"
        elif chosen_action == "move_to_cover": # Not currently used in simple tree above, but supported
             cover_spot_x, cover_spot_y = self._find_best_cover_spot(npc, player.x, player.y)
             if cover_spot_x:
                 npc.schedule.current_task = "combat_action_move_to_cover"
                 npc.task_target_coords = (cover_spot_x, cover_spot_y)
             else:
                 npc.schedule.current_task = "combat_action_hold_position"
        else:
            npc.schedule.current_task = "combat_action_hold_position"

        # Clear path if switching to a non-movement action
        if chosen_action in ["attack_player", "hold_position", "use_healing_item"]:
            npc.schedule.current_path = []
            
        # Clear cover target if not moving to cover
        if chosen_action != "move_to_cover":
            npc.task_target_coords = None


    def npc_attempt_attack_player(self, npc: NPC, player: Player):
        """
        Handles an NPC's attempt to attack the player using rule-based dice mechanics.
        """
        if npc.is_dead or player.combat.hp <= 0:
            return
        if isinstance(npc, Animal) and self._is_predator(npc):
            self._refresh_predator_pursuit_state(npc, player, committed=True)

        # Add Visual Effect for Ranged Attack
        attack_range = getattr(npc, 'attack_range', 1)
        if attack_range > 1:
            self.visual_effects.append(ProjectileEffect(
                start_x=npc.x, start_y=npc.y,
                end_x=player.x, end_y=player.y,
                char='*', color=(255, 0, 0)
            ))

        # --- ARREST LOGIC ---
        if npc.economic.profession in ["Sheriff", "Guard"] and self.player.economic.bounty >= 100 and not self.player.state.is_jailed:
            self.add_message_to_chat_log(self.text.entity_apprehends_you(npc))
            self.serve_jail_time()
            npc.combat.is_hostile_to_player = False
            npc.schedule.current_task = TaskType.IDLE
            npc.schedule.current_path = []
            return

        # 1. Determine Stats
        
        # Attacker Skill
        npc_melee_skill = getattr(getattr(npc, "skills", None), "get_level", lambda *_args, **_kwargs: 5)("melee", 5)
        if npc.combat.combat_behavior == "aggressive": npc_melee_skill += 2
        if npc.economic.profession in ["Guard", "Sheriff"]: npc_melee_skill += 3
        
        # Weapon Damage
        damage_dice_str = npc.combat.base_attack_damage_dice
        damage_bonus = 0
        weapon_name = npc.combat.base_attack_name

        if npc.equipment.weapon and npc.equipment.weapon in ITEM_DEFINITIONS:
            weapon_def = ITEM_DEFINITIONS[npc.equipment.weapon]
            weapon_name = weapon_def.get("name", weapon_name)
            damage_dice_str = weapon_def.get("properties", {}).get("damage_dice", damage_dice_str)
            damage_bonus = weapon_def.get("properties", {}).get("damage_bonus", 0)

        # Player Defense
        player_ac = 10 + player.combat.defense_bonus # Base 10 + armor

        # 2. The Attack Roll
        d20_roll = random.randint(1, 20)
        attack_total = d20_roll + npc_melee_skill

        self.emit_sound(npc.x, npc.y, "combat_attack", volume=10, source_entity_id=npc.id)

        # 3. Resolve Hit
        if d20_roll == 20 or attack_total >= player_ac:
             # Hit!
             # Parse Dice (e.g. "1d6")
             try:
                 num_dice, die_type = map(int, damage_dice_str.lower().split('d'))
                 base_damage = sum(random.randint(1, die_type) for _ in range(num_dice))
             except ValueError:
                 base_damage = 1 # Fallback
             
             total_damage = max(1, base_damage + damage_bonus)
             
             # Crit check (Natural 20)
             if d20_roll == 20: 
                 total_damage *= 2
                 self.add_message_to_chat_log(f"CRITICAL HIT! {self.get_entity_display_name(npc)} strikes you perfectly with their {weapon_name}!")
             
             hp_before = player.combat.hp
             statuses_before = set(player.physical.status_effects)
             actual_damage = player.take_damage(total_damage, world=self)
             if hasattr(getattr(npc, "skills", None), "gain_experience"):
                 npc.skills.gain_experience("melee", max(1, actual_damage), default_level=5)
             new_statuses = set(player.physical.status_effects) - statuses_before
             self._broadcast_combat_memory(npc, player, weapon_name, hp_before - player.combat.hp, new_statuses)
             
             self.log_event(
                event_type="combat_attack",
                description="{subject} attacked {target}.",
                subject_id=npc.id,
                target_id=player.id,
                location=(npc.x, npc.y)
             )
             
             self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} hits you with {weapon_name} for {actual_damage} damage! (HP: {player.combat.hp}/{player.combat.max_hp})")

             if player.combat.hp <= 0:
                self.add_message_to_chat_log("You have been defeated!")
                self.game_state = "PLAYER_DEAD"
                self.log_event(
                    event_type="entity_death",
                    description="{subject} was killed by {target}.",
                    subject_id=player.id,
                    target_id=npc.id,
                    location=(player.x, player.y)
                )

        else:
            # Miss
            miss_desc = "dodged" if d20_roll > 10 else "blocked"
            self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} swings their {weapon_name} but you {miss_desc} it!")

        if npc.equipment.weapon:
            npc.degrade_equipped_item("weapon", world=self)

    def npc_attempt_attack_npc(self, attacker: NPC, target: NPC):
        """Handles an NPC's attempt to attack another NPC."""
        if attacker.physical.is_dead or target.physical.is_dead:
            return

        # Simple damage calculation for now, bypassing LLM for NPC vs NPC
        damage = random.randint(1, 4) # Example: 1d4 damage

        # Check if player can see the attack to log it
        can_player_see = self.player_fov_map[attacker.x, attacker.y] or self.player_fov_map[target.x, target.y]

        if can_player_see:
            self.add_message_to_chat_log(self.text.entity_attacks(attacker, target, damage))

        self.log_event(
            event_type="combat_attack",
            description="{subject} attacked {target}.",
            subject_id=attacker.id,
            target_id=target.id,
            location=(attacker.x, attacker.y)
        )

        hp_before = target.combat.hp
        statuses_before = set(target.physical.status_effects)
        was_killed = target.take_damage(damage, self)
        if hasattr(getattr(attacker, "skills", None), "gain_experience") and hp_before > target.combat.hp:
            attacker.skills.gain_experience("melee", max(1, hp_before - target.combat.hp), default_level=5)
        if attacker.equipment.weapon:
            attacker.degrade_equipped_item("weapon", world=self)
        new_statuses = set(target.physical.status_effects) - statuses_before
        self._broadcast_combat_memory(attacker, target, "attack", hp_before - target.combat.hp, new_statuses)

        if was_killed:
            if can_player_see:
                self.add_message_to_chat_log(f"{self.get_entity_display_name(target)} has been killed by {self.get_entity_display_name(attacker)}!")
            self.handle_npc_death(target, killer_id=attacker.id)
            if self._is_predator(attacker):
                attacker.physical.hunger = 0
                attacker.schedule.current_task = TaskType.IDLE
                attacker.task_target_entity_id = None

    def _find_nearest_food_vendor(self, npc: NPC) -> Building | None:
        """Finds the nearest building that sells food (e.g., general store, bakery)."""
        npc_village = self._get_village_for_npc(npc)
        if not npc_village:
            return None

        food_vendors = [b for b in npc_village.buildings if b.building_type in ["general_store", "bakery"]]
        if not food_vendors:
            return None

        closest_vendor = None
        min_dist_sq = float('inf')

        for building in food_vendors:
            dist_sq = (npc.x - building.global_center_x)**2 + (npc.y - building.global_center_y)**2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_vendor = building

        return closest_vendor

    def _find_nearest_lumber_mill(self, npc: NPC) -> Building | None:
        """Finds the nearest building with a 'lumber_mill' type in the NPC's village."""
        npc_village = self._get_village_for_npc(npc)
        if not npc_village:
            return None

        lumber_mills = [b for b in npc_village.buildings if b.building_type == "lumber_mill"]
        if not lumber_mills:
            return None

        closest_mill = None
        min_dist_sq = float('inf')

        for building in lumber_mills:
            dist_sq = (npc.x - building.global_center_x)**2 + (npc.y - building.global_center_y)**2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_mill = building

        return closest_mill

    def _find_nearest_mine(self, npc: NPC) -> Building | None:
        """Finds the nearest building with a 'mine' type in the NPC's village."""
        npc_village = self._get_village_for_npc(npc)
        if not npc_village:
            return None

        mines = [b for b in npc_village.buildings if b.building_type == "mine"]
        if not mines:
            return None

        closest_mine = None
        min_dist_sq = float('inf')

        for building in mines:
            dist_sq = (npc.x - building.global_center_x)**2 + (npc.y - building.global_center_y)**2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_mine = building

        return closest_mine

    def _find_nearest_farm(self, npc: NPC) -> Building | None:
        """Finds the nearest building with a 'farm' type in the NPC's village."""
        npc_village = self._get_village_for_npc(npc)
        if not npc_village:
            return None

        farms = [b for b in npc_village.buildings if b.building_type == "farm"]
        if not farms:
            return None

        closest_farm = None
        min_dist_sq = float('inf')

        for building in farms:
            dist_sq = (npc.x - building.global_center_x)**2 + (npc.y - building.global_center_y)**2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_farm = building

        return closest_farm

    def _find_nearest_mill(self, npc: NPC) -> Building | None:
        """Finds the nearest building with a 'mill' type in the NPC's village."""
        npc_village = self._get_village_for_npc(npc)
        if not npc_village:
            return None

        mills = [b for b in npc_village.buildings if b.building_type == "mill"]
        if not mills:
            return None

        closest_mill = None
        min_dist_sq = float('inf')

        for building in mills:
            dist_sq = (npc.x - building.global_center_x)**2 + (npc.y - building.global_center_y)**2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_mill = building

        return closest_mill

    def _get_village_for_npc(self, npc: NPC, by_coords: bool = False) -> Village | None:
        """
        Finds the village object an NPC is associated with.
        Can find by home building ID or by current coordinates.
        """
        if not by_coords and npc.schedule.home_building_id:
            # Find village by home building (for residents)
            for y_idx, row in enumerate(self.chunks):
                for x_idx, chk in enumerate(row):
                    if chk.village:
                        if self.buildings_by_id.get(npc.schedule.home_building_id) in chk.village.buildings:
                            return chk.village
        else:
            # Find village by current NPC coordinates (for travelers)
            chunk_x = npc.x // CHUNK_SIZE
            chunk_y = npc.y // CHUNK_SIZE
            if 0 <= chunk_x < self.chunk_width and 0 <= chunk_y < self.chunk_height:
                chunk = self.chunks[chunk_y][chunk_x]
                if chunk.village:
                    return chunk.village
        return None

    def get_settlement_by_id(self, settlement_id: str | None) -> Village | None:
        atlas = getattr(self, "atlas", None)
        if atlas is None or not hasattr(atlas, "get_village"):
            return None
        return atlas.get_village(settlement_id)

    def _get_settlement_residents(self, settlement: Village | None) -> list[NPC]:
        if settlement is None:
            return []
        return [
            npc
            for npc in self.village_npcs
            if not npc.physical.is_dead and self._get_village_for_npc(npc) == settlement
        ]

    def _get_family_migration_unit(self, npc: NPC | None) -> list[NPC]:
        if npc is None:
            return []
        family_unit: list[NPC] = [npc]
        seen_ids = {npc.id}

        partner_id = npc.social.family_ties.get("partner_id") or npc.social.family_ties.get("spouse_id")
        partner = self.get_entity_by_id(partner_id) if partner_id is not None else None
        if isinstance(partner, NPC) and not partner.physical.is_dead and partner.id not in seen_ids:
            family_unit.append(partner)
            seen_ids.add(partner.id)

        parent_ids = {npc.id}
        if partner is not None:
            parent_ids.add(partner.id)
        for candidate in self.all_npcs:
            if candidate.physical.is_dead or candidate.id in seen_ids or getattr(candidate, "age", 99) >= 18:
                continue
            ties = getattr(candidate.social, "family_ties", {})
            if ties.get("mother_id") in parent_ids or ties.get("father_id") in parent_ids:
                family_unit.append(candidate)
                seen_ids.add(candidate.id)
        return family_unit

    def _select_memories_for_abstract_sharing(self, traveler: NPC, *, maximum: int = 3) -> list[MemoryEvent]:
        knowledge = getattr(traveler, "knowledge", None)
        if knowledge is None or not hasattr(knowledge, "choose_memories_to_share"):
            return []
        return knowledge.choose_memories_to_share(maximum=maximum, minimum_importance=5)

    def share_abstract_rumors_with_settlement(self, traveler: NPC | None, settlement: Village | None) -> list[MemoryEvent]:
        if traveler is None or settlement is None:
            return []
        shared_memories = self._select_memories_for_abstract_sharing(traveler, maximum=3)
        if not shared_memories:
            return []
        local_npcs = self._get_settlement_residents(settlement)
        random.shuffle(local_npcs)
        recipients = local_npcs[: max(1, min(3, len(local_npcs)))]
        for memory in shared_memories:
            if recipients:
                for recipient in random.sample(recipients, k=min(len(recipients), random.randint(1, len(recipients)))):
                    self.record_memory_event(recipient, memory)
            settlement.noticeboard_rumors[memory.id] = memory
        return shared_memories

    def _create_job_opportunity_memory(self, task: EmploymentTask, settlement: Village | None) -> MemoryEvent | None:
        if task is None or settlement is None:
            return None
        building = self.buildings_by_id.get(task.target_building_id)
        if building is None:
            return None
        return self.create_memory_event(
            event_type="job_opportunity",
            subject_id=getattr(building, "owner_id", None),
            importance_score=min(95, 25 + int(task.daily_wage)),
            headline=f"{task.profession_role} work is available in {settlement.lore or settlement.id}.",
            location=(building.global_center_x, building.global_center_y),
            metadata={
                "settlement_id": settlement.id,
                "employment_task_id": task.id,
                "daily_wage": task.daily_wage,
                "profession_role": task.profession_role,
                "building_id": building.id,
            },
        )

    def _create_tax_memory(self, settlement: Village | None) -> MemoryEvent | None:
        if settlement is None:
            return None
        anchor_building = settlement.buildings[0] if settlement.buildings else None
        return self.create_memory_event(
            event_type="tax_climate",
            subject_id=None,
            importance_score=25,
            headline=f"{settlement.id[:6]} keeps taxes at {int(settlement.tax_rate * 100)}%.",
            location=(anchor_building.global_center_x, anchor_building.global_center_y) if anchor_building else None,
            metadata={"settlement_id": settlement.id, "tax_rate": settlement.tax_rate},
        )

    def _create_office_memory(self, settlement: Village | None, office_name: str) -> MemoryEvent | None:
        if settlement is None:
            return None
        if settlement.local_offices.get(office_name) is not None:
            return None
        anchor_building = settlement.buildings[0] if settlement.buildings else None
        return self.create_memory_event(
            event_type="office_opening",
            subject_id=None,
            importance_score=45,
            headline=f"{office_name} is vacant in settlement {settlement.id[:6]}.",
            location=(anchor_building.global_center_x, anchor_building.global_center_y) if anchor_building else None,
            metadata={"settlement_id": settlement.id, "office_name": office_name},
        )

    def _seed_settlement_macro_knowledge(self, settlement: Village | None) -> None:
        if settlement is None:
            return
        residents = self._get_settlement_residents(settlement)
        if not residents:
            return
        memories: list[MemoryEvent] = []
        for task in self.town_board.get_open_employment_tasks():
            building = self.buildings_by_id.get(task.target_building_id)
            if building is None or getattr(building, "settlement_id", None) != settlement.id:
                continue
            memory = self._create_job_opportunity_memory(task, settlement)
            if memory is not None:
                memories.append(memory)
        tax_memory = self._create_tax_memory(settlement)
        if tax_memory is not None:
            memories.append(tax_memory)
        for office_name in settlement.local_offices:
            office_memory = self._create_office_memory(settlement, office_name)
            if office_memory is not None:
                memories.append(office_memory)
        if not memories:
            return
        for resident in residents:
            for memory in memories:
                self.record_memory_event(resident, memory)
                settlement.noticeboard_rumors[memory.id] = memory

    def _find_aspiration_destination(self, npc: NPC, current_settlement: Village | None) -> tuple[Village | None, dict | None]:
        memories = list(getattr(getattr(npc, "knowledge", None), "known_memories", {}).values())
        current_settlement_id = getattr(current_settlement, "id", None)
        aspiration_type = getattr(getattr(npc, "aspiration", None), "aspiration_type", None)
        if aspiration_type == AspirationType.WEALTH:
            best_memory = None
            best_wage = max(0, int(getattr(getattr(npc, "economic", None), "daily_wage", 0)))
            for memory in memories:
                if memory.event_type != "job_opportunity":
                    continue
                destination_id = memory.metadata.get("settlement_id")
                wage = int(memory.metadata.get("daily_wage", 0))
                if destination_id == current_settlement_id or wage <= best_wage:
                    continue
                best_memory = memory
                best_wage = wage
            if best_memory is not None:
                return self.get_settlement_by_id(best_memory.metadata.get("settlement_id")), best_memory.metadata
        elif aspiration_type == AspirationType.POWER:
            office_memories = [memory for memory in memories if memory.event_type == "office_opening"]
            office_memories.sort(key=lambda memory: (-memory.importance_score, memory.timestamp, memory.id))
            if office_memories:
                return self.get_settlement_by_id(office_memories[0].metadata.get("settlement_id")), office_memories[0].metadata
        elif aspiration_type == AspirationType.PEACE:
            tax_memories = [
                memory
                for memory in memories
                if memory.event_type == "tax_climate"
                and float(memory.metadata.get("tax_rate", 1.0)) < float(getattr(current_settlement, "tax_rate", 1.0))
            ]
            tax_memories.sort(key=lambda memory: (float(memory.metadata.get("tax_rate", 1.0)), -memory.importance_score))
            if tax_memories:
                return self.get_settlement_by_id(tax_memories[0].metadata.get("settlement_id")), tax_memories[0].metadata
        return None, None

    def _remove_npc_from_settlement_membership(self, npc: NPC | None, settlement: Village | None) -> None:
        if npc is None or settlement is None:
            return
        home_building = self.buildings_by_id.get(getattr(npc.schedule, "home_building_id", None))
        if home_building and npc in home_building.residents:
            home_building.residents.remove(npc)
        work_building = self.buildings_by_id.get(getattr(npc.schedule, "work_building_id", None))
        if work_building and npc in work_building.occupants:
            work_building.occupants.remove(npc)
        npc.schedule.home_building_id = None
        npc.schedule.work_building_id = None
        for office_name, holder_id in list(settlement.local_offices.items()):
            if holder_id == npc.id:
                settlement.local_offices[office_name] = None

    def _start_family_migration(self, leader: NPC, destination: Village, metadata: dict | None = None) -> bool:
        if leader is None or destination is None:
            return False
        origin_settlement = self._get_village_for_npc(leader)
        family_unit = self._get_family_migration_unit(leader)
        if not family_unit:
            return False
        destination_coords = destination.interaction_points.get("town_square_center", [(destination.buildings[0].global_center_x, destination.buildings[0].global_center_y) if destination.buildings else (leader.x, leader.y)])[0]
        group_ids = [member.id for member in family_unit]
        distance = math.dist((leader.macro_x, leader.macro_y), destination_coords)
        eta_days = max(1, int(math.ceil(distance / max(1, CHUNK_SIZE * 2))))
        for member in family_unit:
            self._remove_npc_from_settlement_membership(member, origin_settlement)
            member.travel = TravelComponent(
                is_traveling=True,
                origin_settlement_id=getattr(origin_settlement, "id", None),
                destination_settlement_id=destination.id,
                destination_coords=destination_coords,
                eta_days=eta_days,
                group_leader_id=leader.id,
                group_member_ids=group_ids,
                target_employment_task_id=(metadata or {}).get("employment_task_id"),
            )
            member.aspiration.target_settlement_id = destination.id
            member.schedule.current_task = "traveling_between_settlements"
            member.is_sleeping = True
        self.record_migration_event(
            npc=leader,
            migration_kind="migrated",
            description=f"{{subject}} set out for another settlement.",
            location=(leader.x, leader.y),
        )
        return True

    def _complete_travel_arrival(self, leader: NPC) -> None:
        travel = getattr(leader, "travel", None)
        if travel is None or not travel.is_traveling:
            return
        destination = self.get_settlement_by_id(travel.destination_settlement_id)
        if destination is None:
            return
        group_members = [
            member
            for member in self.all_npcs
            if getattr(getattr(member, "travel", None), "group_leader_id", None) == leader.id
        ]
        if leader not in group_members:
            group_members.append(leader)
        destination_coords = travel.destination_coords or destination.interaction_points.get("town_square_center", [(leader.x, leader.y)])[0]
        for member in group_members:
            member.travel.is_traveling = False
            member.travel.eta_days = 0
            member.macro_x, member.macro_y = destination_coords
            member.x, member.y = destination_coords
            member.schedule.current_task = TaskType.IDLE
            vacant_home = next((building for building in destination.buildings if building.category == "residential" and len(building.residents) < 2), None)
            if vacant_home is not None and member not in vacant_home.residents:
                vacant_home.residents.append(member)
                member.schedule.home_building_id = vacant_home.id
            if member.id == leader.id and member.travel.target_employment_task_id:
                task = self.town_board.get_employment_task(member.travel.target_employment_task_id)
                if task is not None:
                    self._hire_npc_from_employment_task(member, task)
        self.share_abstract_rumors_with_settlement(leader, destination)

    def process_macro_daily_tick(self) -> None:
        current_day = self.game_time // max(1, DAY_LENGTH_TICKS)
        if self.game_time == 0 or self.game_time % DAY_LENGTH_TICKS != 0:
            return
        if current_day <= self.last_macro_daily_day:
            return
        self.last_macro_daily_day = current_day

        settlements = list(getattr(self, "villages", []))
        for settlement in settlements:
            self._sync_village_employment_tasks(settlement)
            self._seed_settlement_macro_knowledge(settlement)

        sleeping_npcs = [
            npc for npc in self.village_npcs
            if not npc.physical.is_dead and getattr(npc, "is_sleeping", False)
        ]

        processed_groups: set[int] = set()
        for npc in sleeping_npcs:
            travel = getattr(npc, "travel", None)
            if travel is None or not travel.is_traveling or travel.group_leader_id != npc.id:
                continue
            if npc.id in processed_groups:
                continue
            travel.eta_days = max(0, int(travel.eta_days) - 1)
            for member in self.all_npcs:
                member_travel = getattr(member, "travel", None)
                if member_travel and member_travel.group_leader_id == npc.id:
                    member_travel.eta_days = travel.eta_days
            if travel.eta_days <= 0:
                self._complete_travel_arrival(npc)
            processed_groups.add(npc.id)

        for npc in sleeping_npcs:
            if getattr(getattr(npc, "travel", None), "is_traveling", False):
                continue
            if getattr(npc, "age", 0) < 18:
                continue
            current_settlement = self._get_village_for_npc(npc)
            destination, metadata = self._find_aspiration_destination(npc, current_settlement)
            if destination is None or current_settlement is destination:
                continue
            self._start_family_migration(npc, destination, metadata)

    def _find_nearest_building_of_type(self, npc: NPC, building_type: str) -> Building | None:
        """Finds the nearest building of a specific type in the NPC's village."""
        npc_village = self._get_village_for_npc(npc)
        if not npc_village:
            # If no village, maybe search all buildings in a radius? For now, only village NPCs report.
            return None

        target_buildings = [b for b in npc_village.buildings if b.building_type == building_type]
        if not target_buildings:
            return None

        closest_building = None
        min_dist_sq = float('inf')

        for building in target_buildings:
            dist_sq = (npc.x - building.global_center_x)**2 + (npc.y - building.global_center_y)**2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_building = building

        return closest_building

    def _find_nearest_tavern(self, npc: NPC) -> Building | None:
        """Finds the nearest building with a 'tavern' type in the NPC's village."""
        return self._find_nearest_building_of_type(npc, "tavern")

    def _remember_npc_interrupted_task(self, npc: NPC) -> None:
        survival_tasks = {
            "seeking_food",
            "seeking_water",
            "going_to_buy_food",
            "wandering_hungry",
            "wandering_hungry_homeless",
            "idle_confused",
        }
        current_task = getattr(npc.schedule, "current_task", TaskType.IDLE)
        if current_task in survival_tasks:
            return
        npc.schedule.previous_task = current_task if current_task not in [TaskType.IDLE, TaskType.WANDERING] else TaskType.IDLE

    def _resume_npc_after_survival_need(self, npc: NPC) -> None:
        npc.schedule.current_task = npc.schedule.previous_task or TaskType.IDLE
        npc.schedule.previous_task = None
        npc.schedule.current_path = []
        npc.schedule.current_destination_coords = None

    def _consume_npc_inventory_item(self, npc: NPC, inventory, item_key: str) -> bool:
        if item_key not in ITEM_DEFINITIONS:
            return False

        item_def = ITEM_DEFINITIONS[item_key]
        on_use = item_def.get("on_use", {})
        if hasattr(inventory, "pop_item_reference"):
            item = inventory.pop_item_reference(item_key)
            if item is None:
                return False
        else:
            current_quantity = inventory.get(item_key, 0)
            if current_quantity <= 0:
                return False
            inventory[item_key] = current_quantity - 1
            if inventory.get(item_key, 0) <= 0 and item_key in inventory:
                del inventory[item_key]

        npc.physical.hunger = max(0, npc.physical.hunger - on_use.get("reduces_hunger", 0))
        npc.physical.thirst = max(0, npc.physical.thirst - on_use.get("reduces_thirst", 0))
        start_activity(
            npc,
            "eating" if on_use.get("reduces_hunger", 0) >= on_use.get("reduces_thirst", 0) else "drinking",
            3,
            world=self,
            location=(npc.x, npc.y),
            allows_conversation=False,
            allows_observation=True,
            allows_social_sharing=False,
            interruptible=True,
            metadata={
                "item_key": item_key,
                "reduces_hunger": on_use.get("reduces_hunger", 0),
                "reduces_thirst": on_use.get("reduces_thirst", 0),
                "needs_already_applied": True,
            },
        )
        return True

    def _npc_consume_from_inventory(self, npc: NPC, inventory, *, need_type: str, desperate: bool = False) -> tuple[bool, bool]:
        """
        Consume the best matching food/drink item from an inventory-like object.
        Returns (found_matching_item, consumed_item).
        """
        best_item_key = None
        best_score = -1
        found_matching_item = False

        for item_key, qty in inventory.items():
            if qty <= 0:
                continue

            item_def = ITEM_DEFINITIONS.get(item_key, {})
            on_use = item_def.get("on_use", {})
            tags = set(item_def.get("item_type_tags", []))
            reduces_hunger = on_use.get("reduces_hunger", 0)
            reduces_thirst = on_use.get("reduces_thirst", 0)
            relevant_reduction = reduces_hunger if need_type == "hunger" else reduces_thirst

            if relevant_reduction <= 0:
                continue

            found_matching_item = True

            is_rotten_or_trash = item_key == "rotten_food" or "trash" in tags
            if is_rotten_or_trash and not desperate:
                continue

            score = relevant_reduction
            if need_type == "thirst" and "drink" in tags:
                score += 10
            if need_type == "hunger" and "food" in tags:
                score += 10
            if not is_rotten_or_trash:
                score += 5

            if score > best_score:
                best_score = score
                best_item_key = item_key

        if best_item_key and self._consume_npc_inventory_item(npc, inventory, best_item_key):
            return found_matching_item, True

        return found_matching_item, False

    def _find_nearest_water_source(self, npc: NPC, search_radius: int = 25) -> tuple[int, int] | None:
        closest_coords = None
        closest_distance = float("inf")

        npc_village = self._get_village_for_npc(npc, by_coords=True)
        if npc_village and "well" in npc_village.interaction_points:
            for wx, wy in npc_village.interaction_points.get("well", []):
                distance = abs(npc.x - wx) + abs(npc.y - wy)
                if distance < closest_distance:
                    closest_distance = distance
                    closest_coords = (wx, wy)

        for y in range(max(0, npc.y - search_radius), min(self.chunk_height * CHUNK_SIZE, npc.y + search_radius + 1)):
            for x in range(max(0, npc.x - search_radius), min(self.chunk_width * CHUNK_SIZE, npc.x + search_radius + 1)):
                tile = self.get_tile_at(x, y)
                if not tile:
                    continue
                tile_name = str(getattr(tile, "name", "")).lower()
                if tile_name not in {"well", "water", "deep water"}:
                    continue
                distance = abs(npc.x - x) + abs(npc.y - y)
                if distance < closest_distance:
                    closest_distance = distance
                    closest_coords = (x, y)

        return closest_coords

    def _find_nearest_food_source(self, npc: NPC) -> Building | None:
        candidates = [building for building in [self._find_nearest_tavern(npc), self._find_nearest_food_vendor(npc)] if building]
        if not candidates:
            return None
        return min(candidates, key=lambda building: abs(npc.x - building.global_center_x) + abs(npc.y - building.global_center_y))

    def _path_npc_to_survival_target(self, npc: NPC, target_coords: tuple[int, int], *, task_name: str, adjacent_if_blocked: bool = False) -> bool:
        if target_coords is None:
            return False

        destination = target_coords
        tile = self.get_tile_at(target_coords[0], target_coords[1])
        if adjacent_if_blocked and tile and not tile.passable:
            dest_x, dest_y = self._find_best_adjacent_tile(target_coords[0], target_coords[1], npc)
            if dest_x is None or dest_y is None:
                return False
            destination = (dest_x, dest_y)

        if (npc.x, npc.y) == destination:
            npc.schedule.current_task = task_name
            npc.schedule.current_path = []
            npc.schedule.current_destination_coords = destination
            return True

        path = self.calculate_path(npc.x, npc.y, destination[0], destination[1])
        if not path:
            return False

        npc.schedule.current_task = task_name
        npc.schedule.current_path = path
        npc.schedule.current_destination_coords = destination
        return True

    def _record_stockpile_trace(self, trace_type: str, stockpile: Stockpile | None = None, *, actor=None, metadata: dict | None = None) -> None:
        trace_log = getattr(self, "interaction_trace_log", None)
        if trace_log is None:
            trace_log = []
            setattr(self, "interaction_trace_log", trace_log)
        payload = dict(metadata or {})
        if stockpile is not None:
            payload.setdefault("stockpile_id", stockpile.stockpile_id)
            payload.setdefault("position", stockpile.position)
        trace_log.append({
            "tick": getattr(self, "game_time", None),
            "interaction_id": None,
            "actor_id": getattr(actor, "id", None),
            "action_type": "stockpile_logistics",
            "trace_type": trace_type,
            "metadata": payload,
        })

    def create_stockpile(self, x: int, y: int, *, accepted_item_types: set[str] | list[str] | tuple[str, ...] | None = None, max_item_count: int = 100, owner_id=None, faction_id: str | None = None, village_id: str | None = None, stockpile_id: str | None = None) -> Stockpile:
        stockpile = Stockpile(
            stockpile_id=stockpile_id or str(uuid.uuid4()),
            x=int(x),
            y=int(y),
            accepted_item_types=set(accepted_item_types or set()),
            max_item_count=max(1, int(max_item_count)),
            owner_id=owner_id,
            faction_id=faction_id,
            village_id=village_id,
        )
        self.stockpiles_by_id[stockpile.stockpile_id] = stockpile
        self._record_stockpile_trace("stockpile_created", stockpile, metadata={"accepted_item_types": sorted(stockpile.accepted_item_types), "max_item_count": stockpile.max_item_count})
        return stockpile

    def find_stockpile_for_item(self, item_key: str, *, require_available: bool = False, require_capacity: bool = False, near: tuple[int, int] | None = None) -> Stockpile | None:
        candidates: list[tuple[int, str, Stockpile]] = []
        for stockpile in getattr(self, "stockpiles_by_id", {}).values():
            if not stockpile.accepts(item_key):
                continue
            if require_available and stockpile.available_quantity(item_key) <= 0:
                continue
            if require_capacity and not stockpile.has_capacity_for(1):
                continue
            origin = near or stockpile.position
            distance = abs(origin[0] - stockpile.x) + abs(origin[1] - stockpile.y)
            candidates.append((distance, stockpile.stockpile_id, stockpile))
        if not candidates:
            self._warn_simulation_validation(
                "no_available_stockpile",
                (item_key, require_available, require_capacity),
                "No valid stockpile is available for the requested item.",
                metadata={"item_key": item_key, "require_available": require_available, "require_capacity": require_capacity},
            )
            return None
        candidates.sort(key=lambda entry: (entry[0], entry[1]))
        return candidates[0][2]

    def deposit_item_reference_into_stockpile(self, stockpile_id: str, item_reference: ItemReference, *, actor=None) -> bool:
        stockpile = getattr(self, "stockpiles_by_id", {}).get(stockpile_id)
        if stockpile is None:
            self._warn_simulation_validation("invalid_stockpile", (stockpile_id, "deposit"), "Cannot deposit into a missing stockpile.", actor=actor, metadata={"stockpile_id": stockpile_id})
            return False
        if item_reference is None:
            self._warn_simulation_validation("missing_source_item", (stockpile_id, None), "Cannot deposit a missing item into a stockpile.", actor=actor, metadata={"stockpile_id": stockpile_id})
            return False
        if not stockpile.accepts(item_reference.key):
            self._warn_simulation_validation("unsupported_stockpile_item", (stockpile_id, item_reference.key), "Stockpile does not accept this item type.", actor=actor, metadata={"stockpile_id": stockpile_id, "item_key": item_reference.key})
            return False
        if not stockpile.has_capacity_for(1):
            self._warn_simulation_validation("full_stockpile", (stockpile_id, item_reference.key), "Stockpile has no capacity for this item.", actor=actor, metadata={"stockpile_id": stockpile_id, "item_key": item_reference.key})
            return False
        deposited = stockpile.deposit_item_reference(item_reference)
        if deposited:
            self._record_stockpile_trace("stockpile_deposit", stockpile, actor=actor, metadata={"item_key": item_reference.key, "quantity": 1, "stored_quantity": stockpile.quantity(item_reference.key)})
        return deposited

    def deposit_item_into_stockpile(self, stockpile_id: str, item_key: str, quantity: int = 1, *, actor=None) -> int:
        stockpile = getattr(self, "stockpiles_by_id", {}).get(stockpile_id)
        if stockpile is None:
            self._warn_simulation_validation("invalid_stockpile", (stockpile_id, "deposit"), "Cannot deposit into a missing stockpile.", actor=actor, metadata={"stockpile_id": stockpile_id, "item_key": item_key})
            return 0
        if not stockpile.accepts(item_key):
            self._warn_simulation_validation("unsupported_stockpile_item", (stockpile_id, item_key), "Stockpile does not accept this item type.", actor=actor, metadata={"stockpile_id": stockpile_id, "item_key": item_key})
            return 0
        deposited = stockpile.deposit_item(item_key, quantity)
        if deposited <= 0:
            self._warn_simulation_validation("full_stockpile", (stockpile_id, item_key), "Stockpile has no capacity for this item.", actor=actor, metadata={"stockpile_id": stockpile_id, "item_key": item_key, "quantity": quantity})
            return 0
        self._record_stockpile_trace("stockpile_deposit", stockpile, actor=actor, metadata={"item_key": item_key, "quantity": deposited, "stored_quantity": stockpile.quantity(item_key)})
        return deposited

    def _reserve_stockpile_item_for_task(self, stockpile_id: str | None, item_key: str, actor, task_id: str | None) -> str | None:
        stockpile = getattr(self, "stockpiles_by_id", {}).get(stockpile_id or "")
        if stockpile is None:
            self._warn_simulation_validation("invalid_stockpile", (stockpile_id, "reserve"), "Cannot reserve from a missing stockpile.", actor=actor, metadata={"stockpile_id": stockpile_id, "item_key": item_key, "task_id": task_id})
            return None
        reservation_id = stockpile.create_reservation(item_key, 1, actor_id=getattr(actor, "id", None), task_id=task_id, current_tick=getattr(self, "game_time", None))
        if reservation_id is None:
            self._warn_simulation_validation("missing_source_item", (stockpile_id, item_key), "Stockpile lacks unreserved source material for hauling.", actor=actor, metadata={"stockpile_id": stockpile_id, "item_key": item_key, "task_id": task_id})
            return None
        self._record_stockpile_trace("stockpile_reservation_created", stockpile, actor=actor, metadata={"item_key": item_key, "reservation_id": reservation_id, "task_id": task_id})
        return reservation_id

    def _release_stockpile_reservation(self, stockpile_id: str | None, reservation_id: str | None, *, actor=None, reason: str | None = None) -> None:
        stockpile = getattr(self, "stockpiles_by_id", {}).get(stockpile_id or "")
        if stockpile is None or not reservation_id:
            return
        if stockpile.release_reservation(reservation_id):
            self._record_stockpile_trace("stockpile_reservation_released", stockpile, actor=actor, metadata={"reservation_id": reservation_id, "reason": reason})

    def _find_nearest_haul_source(self, npc: NPC, item_key: str) -> dict | None:
        candidates: list[tuple[int, int, dict]] = []
        for stockpile in getattr(self, "stockpiles_by_id", {}).values():
            if stockpile.available_quantity(item_key) > 0:
                candidates.append((
                    0,
                    abs(npc.x - stockpile.x) + abs(npc.y - stockpile.y),
                    {"source_type": "stockpile", "coords": stockpile.position, "stockpile_id": stockpile.stockpile_id, "item_key": item_key},
                ))
        for (item_x, item_y), inventory in self.items_on_map.items():
            if inventory.get(item_key, 0) > 0:
                candidates.append((
                    1,
                    abs(npc.x - item_x) + abs(npc.y - item_y),
                    {"source_type": "ground", "coords": (item_x, item_y), "item_key": item_key},
                ))
        for building in self.buildings_by_id.values():
            inventory = getattr(building, "building_inventory", None)
            if inventory and inventory.get(item_key, 0) > 0:
                candidates.append((
                    2,
                    abs(npc.x - building.global_center_x) + abs(npc.y - building.global_center_y),
                    {
                        "source_type": "building",
                        "coords": (building.global_center_x, building.global_center_y),
                        "building_id": building.id,
                        "item_key": item_key,
                    },
                ))
        if not candidates:
            return None
        candidates.sort(key=lambda entry: (entry[0], entry[1]))
        return candidates[0][2]

    def _clear_npc_haul_task(self, npc: NPC, *, release_claim: bool = False) -> None:
        task_data = npc.task_context_data if isinstance(npc.task_context_data, dict) else {}
        if release_claim and task_data.get("haul_task_id"):
            self.town_board.release_task(task_data["haul_task_id"])
        if release_claim and task_data.get("delivery_task_id"):
            self.town_board.release_delivery_task(task_data["delivery_task_id"])
        if task_data.get("stockpile_reservation_id"):
            self._release_stockpile_reservation(
                task_data.get("source", {}).get("stockpile_id"),
                task_data.get("stockpile_reservation_id"),
                actor=npc,
                reason="clear_haul_task",
            )

        npc.schedule.current_task = TaskType.IDLE
        npc.schedule.current_path = []
        npc.schedule.current_destination_coords = None
        npc.task_target_coords = None
        npc.task_target_item_details = None
        npc.current_sub_task = None
        npc.task_context = None
        npc.task_context_data = None

    def _find_npc_by_id(self, entity_id: int | None) -> NPC | None:
        if entity_id is None:
            return None
        for candidate in getattr(self, "village_npcs", []):
            if getattr(candidate, "id", None) == entity_id:
                return candidate
        if getattr(getattr(self, "player", None), "id", None) == entity_id:
            return self.player
        return None

    def _record_component_claim_trace(self, trace_type: str, blueprint: ConstructionBlueprint, component, actor_id=None, *, reason: str | None = None) -> None:
        trace_log = getattr(self, "interaction_trace_log", None)
        if trace_log is None:
            trace_log = []
            setattr(self, "interaction_trace_log", trace_log)
        metadata = {
            "blueprint_id": getattr(blueprint, "id", None),
            "component_id": getattr(component, "id", None),
            "actor_id": actor_id,
            "reason": reason,
        }
        trace_log.append({
            "tick": getattr(self, "game_time", None),
            "interaction_id": None,
            "actor_id": actor_id,
            "action_type": "construction_claim",
            "trace_type": trace_type,
            "metadata": metadata,
        })

    def _get_blueprint_component(self, blueprint: ConstructionBlueprint | None, component_id: str | None):
        if blueprint is None or component_id is None:
            return None
        return next((comp for comp in getattr(blueprint, "components", []) if comp.id == component_id), None)

    def _expire_component_claim_if_needed(self, blueprint: ConstructionBlueprint, component) -> bool:
        actor_id = getattr(component, "claimed_by_actor_id", None)
        if actor_id is None:
            return False
        actor = self._find_npc_by_id(actor_id)
        actor_unavailable = actor is None or getattr(getattr(actor, "physical", None), "is_dead", False) or not getattr(actor, "is_alive", True)
        expired = component.expire_claim_if_needed(getattr(self, "game_time", None))
        if not expired and actor_unavailable:
            expired = component.release_claim(actor_id)
        if expired:
            self._record_component_claim_trace("component_claim_expired", blueprint, component, actor_id, reason="actor_unavailable" if actor_unavailable else "expired")
        return expired

    def _claim_construction_component(self, blueprint: ConstructionBlueprint, component, actor, *, reason: str) -> bool:
        actor_id = getattr(actor, "id", None)
        if actor_id is None or component is None:
            return False
        self._expire_component_claim_if_needed(blueprint, component)
        previous_actor_id = getattr(component, "claimed_by_actor_id", None)
        if not component.claim_for_actor(actor_id, getattr(self, "game_time", None)):
            return False
        if previous_actor_id != actor_id:
            self._record_component_claim_trace("component_claimed", blueprint, component, actor_id, reason=reason)
        return True

    def _release_construction_component_claim(self, blueprint: ConstructionBlueprint | None, component_id: str | None, actor_id=None, *, reason: str) -> None:
        component = self._get_blueprint_component(blueprint, component_id)
        if component is None:
            return
        released_actor_id = getattr(component, "claimed_by_actor_id", None)
        if component.release_claim(actor_id):
            self._record_component_claim_trace("component_claim_released", blueprint, component, released_actor_id, reason=reason)

    def _construction_component_available_for_actor(self, blueprint: ConstructionBlueprint, component, actor) -> bool:
        if component is None or component.status == "complete" or not component.has_remaining_work():
            return False
        self._expire_component_claim_if_needed(blueprint, component)
        actor_id = getattr(actor, "id", None)
        return not component.claim_is_active(getattr(self, "game_time", None)) or component.claimed_by_actor_id == actor_id

    def _is_available_delivery_laborer(self, candidate: NPC, *, excluding_id: int | None = None) -> bool:
        if getattr(candidate, "id", None) == excluding_id:
            return False
        if getattr(getattr(candidate, "physical", None), "is_dead", False):
            return False
        profession = str(getattr(getattr(candidate, "economic", None), "profession", "") or "").strip().lower()
        if profession not in {"laborer", "helper", "porter"}:
            return False
        if getattr(candidate, "task_context", None) in {"delivery", "construction", "hauling"}:
            return False
        schedule = getattr(candidate, "schedule", None)
        current_task = getattr(schedule, "current_task", "") or ""
        if current_task not in {TaskType.IDLE, TaskType.WANDERING, TaskType.AT_HOME, "idle_confused", ""}:
            return False
        if getattr(schedule, "current_path", None):
            return False
        return True

    def _delivery_laborer_can_service_task(self, candidate: NPC, task, *, excluding_id: int | None = None) -> bool:
        if not self._is_available_delivery_laborer(candidate, excluding_id=excluding_id):
            return False

        source_building = self.buildings_by_id.get(getattr(task, "source_building_id", None))
        dest_building = self.buildings_by_id.get(getattr(task, "destination_building_id", None))
        if source_building is None or dest_building is None:
            return False

        task_settlement_ids = {
            getattr(source_building, "settlement_id", None),
            getattr(dest_building, "settlement_id", None),
        }
        task_settlement_ids.discard(None)
        if task_settlement_ids:
            candidate_village = self._get_village_for_npc(candidate, by_coords=True)
            candidate_settlement_id = getattr(candidate_village, "id", None)
            candidate_work_building = self.buildings_by_id.get(getattr(getattr(candidate, "schedule", None), "work_building_id", None))
            candidate_work_settlement_id = getattr(candidate_work_building, "settlement_id", None)
            if candidate_settlement_id not in task_settlement_ids and candidate_work_settlement_id not in task_settlement_ids:
                return False

        source_coords = (source_building.global_center_x, source_building.global_center_y)
        if (candidate.x, candidate.y) == source_coords:
            return True
        return bool(self.calculate_path(candidate.x, candidate.y, source_coords[0], source_coords[1]))

    def _has_available_delivery_laborer_for_task(self, task, *, excluding_id: int | None = None) -> bool:
        return any(
            self._delivery_laborer_can_service_task(candidate, task, excluding_id=excluding_id)
            for candidate in getattr(self, "village_npcs", [])
        )

    def _recover_invalid_delivery_tasks(self) -> None:
        """Release or fail delivery tasks whose actor/buildings disappeared."""
        for task in list(self.town_board.get_active_delivery_tasks()):
            source_building = self.buildings_by_id.get(task.source_building_id)
            dest_building = self.buildings_by_id.get(task.destination_building_id)
            if source_building is None or dest_building is None:
                self.town_board.fail_delivery_task(task.id)
                actor = self._find_npc_by_id(task.assigned_entity_id)
                if actor is not None:
                    self._clear_npc_haul_task(actor, release_claim=False)
                continue
            if task.assigned_entity_id is None or task.status == "open":
                continue
            actor = self._find_npc_by_id(task.assigned_entity_id)
            if actor is None or getattr(getattr(actor, "physical", None), "is_dead", False):
                if task.status in {"claimed", "going_to_source"}:
                    self.town_board.release_delivery_task(task.id)
                else:
                    self.town_board.fail_delivery_task(task.id)

    def _assign_delivery_task_to_npc(self, npc: NPC) -> bool:
        self._recover_invalid_delivery_tasks()
        best_task = None
        best_distance = None

        profession = str(getattr(getattr(npc, "economic", None), "profession", "") or "").strip().lower()
        is_unemployed = profession == "unemployed"
        is_laborer = profession in {"laborer", "helper", "porter"}

        npc_workplace_id = getattr(getattr(npc, "schedule", None), "work_building_id", None)
        npc_is_owner = npc_workplace_id and npc.id == getattr(self.buildings_by_id.get(npc_workplace_id), "owner_id", None)

        if npc_is_owner and not (is_unemployed or is_laborer):
            workplace = self.buildings_by_id.get(npc_workplace_id)
            if workplace:
                active_workers = self._count_active_workers_for_building(workplace)
                if active_workers > 1:
                    return False

        for task in self.town_board.get_open_delivery_tasks():
            if not (is_unemployed or is_laborer):
                if task.destination_building_id != npc_workplace_id:
                    continue

            source_building = self.buildings_by_id.get(task.source_building_id)
            dest_building = self.buildings_by_id.get(task.destination_building_id)
            if not source_building or not dest_building:
                self.town_board.fail_delivery_task(task.id)
                continue

            distance = abs(npc.x - source_building.global_center_x) + abs(npc.y - source_building.global_center_y)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_task = task

        if best_task is None:
            return False

        # Laborers/helpers/porters are preferred, but deferral is scoped to the
        # selected task. A distant or unreachable idle laborer must not block this
        # worker/owner from keeping their own workplace supplied.
        if not is_laborer and self._has_available_delivery_laborer_for_task(best_task, excluding_id=getattr(npc, "id", None)):
            return False

        if not self.town_board.claim_delivery_task(best_task, npc.id, current_tick=getattr(self, "game_time", None)):
            return False
        self.town_board.update_delivery_task_status(best_task.id, "going_to_source", current_tick=getattr(self, "game_time", None))

        source_building = self.buildings_by_id[best_task.source_building_id]

        npc.schedule.current_task = "hauling_to_source"
        npc.current_sub_task = f"Restocking {best_task.item_key}"
        npc.task_context = "delivery"
        npc.task_context_data = {
            "delivery_task_id": best_task.id,
            "source_building_id": best_task.source_building_id,
            "destination_building_id": best_task.destination_building_id,
            "item_key": best_task.item_key,
            "source": {
                "source_type": "building",
                "coords": (source_building.global_center_x, source_building.global_center_y),
                "building_id": source_building.id,
                "item_key": best_task.item_key,
            }
        }
        npc.task_target_item_details = {"item_key": best_task.item_key}
        coords = (source_building.global_center_x, source_building.global_center_y)
        npc.task_target_coords = coords
        npc.schedule.current_destination_coords = coords
        npc.schedule.current_path = self.calculate_path(npc.x, npc.y, coords[0], coords[1]) or []
        if (npc.x, npc.y) != coords and not npc.schedule.current_path:
            self.town_board.release_delivery_task(best_task.id)
            self._clear_npc_haul_task(npc, release_claim=False)
            return False
        return True

    def _assign_haul_task_to_npc(self, npc: NPC) -> bool:
        best_choice = None
        best_distance = None
        for task in self.town_board.get_open_tasks():
            blueprint = self.blueprints_by_id.get(task.blueprint_id)
            if blueprint is None or not blueprint.needs_material(task.item_key):
                continue
            component = self._get_blueprint_component(blueprint, getattr(task, "component_id", None))
            if component is not None and not self._construction_component_available_for_actor(blueprint, component, npc):
                continue
            source = self._find_nearest_haul_source(npc, task.item_key)
            if source is None:
                continue
            total_distance = abs(npc.x - source["coords"][0]) + abs(npc.y - source["coords"][1])
            total_distance += abs(source["coords"][0] - task.destination_x) + abs(source["coords"][1] - task.destination_y)
            if best_distance is None or total_distance < best_distance:
                best_distance = total_distance
                best_choice = (task, source)
        if best_choice is None:
            return False

        task, source = best_choice
        blueprint = self.blueprints_by_id.get(task.blueprint_id)
        component = self._get_blueprint_component(blueprint, getattr(task, "component_id", None))
        if blueprint is not None and component is not None and not self._claim_construction_component(blueprint, component, npc, reason="hauling"):
            return False
        if not self.town_board.claim_task(task, npc.id):
            if blueprint is not None and component is not None:
                self._release_construction_component_claim(blueprint, component.id, getattr(npc, "id", None), reason="haul_task_claim_failed")
            return False

        stockpile_reservation_id = None
        if source.get("source_type") == "stockpile":
            stockpile_reservation_id = self._reserve_stockpile_item_for_task(source.get("stockpile_id"), task.item_key, npc, task.id)
            if stockpile_reservation_id is None:
                self.town_board.release_task(task.id)
                if blueprint is not None and component is not None:
                    self._release_construction_component_claim(blueprint, component.id, getattr(npc, "id", None), reason="stockpile_reservation_failed")
                self._record_stockpile_trace("haul_failed", None, actor=npc, metadata={"haul_task_id": task.id, "item_key": task.item_key, "reason": "stockpile_reservation_failed"})
                return False
            task.source_stockpile_id = source.get("stockpile_id")
            task.stockpile_reservation_id = stockpile_reservation_id

        self._record_stockpile_trace("haul_assigned", getattr(self, "stockpiles_by_id", {}).get(source.get("stockpile_id")), actor=npc, metadata={"haul_task_id": task.id, "blueprint_id": task.blueprint_id, "component_id": getattr(task, "component_id", None), "item_key": task.item_key, "source_type": source.get("source_type")})

        npc.schedule.current_task = "hauling_to_source"
        npc.current_sub_task = f"Fetching {task.item_key}"
        npc.task_context = "hauling"
        npc.task_context_data = {
            "haul_task_id": task.id,
            "blueprint_id": task.blueprint_id,
            "component_id": getattr(task, "component_id", None),
            "item_key": task.item_key,
            "source": source,
            "stockpile_reservation_id": stockpile_reservation_id,
        }
        npc.task_target_item_details = {"item_key": task.item_key}
        npc.task_target_coords = source["coords"]
        npc.schedule.current_destination_coords = source["coords"]
        npc.schedule.current_path = self.calculate_path(npc.x, npc.y, source["coords"][0], source["coords"][1]) or []
        if (npc.x, npc.y) != source["coords"] and not npc.schedule.current_path:
            self.town_board.release_task(task.id)
            self._release_stockpile_reservation(source.get("stockpile_id"), stockpile_reservation_id, actor=npc, reason="haul_path_failed")
            if blueprint is not None and component is not None:
                self._release_construction_component_claim(blueprint, component.id, getattr(npc, "id", None), reason="haul_path_failed")
            self._record_stockpile_trace("haul_failed", getattr(self, "stockpiles_by_id", {}).get(source.get("stockpile_id")), actor=npc, metadata={"haul_task_id": task.id, "item_key": task.item_key, "reason": "path_failed"})
            self._clear_npc_haul_task(npc, release_claim=False)
            return False
        return True

    def _pickup_haul_task_material(self, npc: NPC, haul_data: dict) -> bool:
        source = haul_data.get("source", {})
        item_key = haul_data.get("item_key")
        if not item_key:
            return False

        inventory = None
        if source.get("source_type") == "ground":
            inventory = self.items_on_map.get(tuple(source.get("coords", ())))
        elif source.get("source_type") == "building":
            inventory = getattr(self.buildings_by_id.get(source.get("building_id")), "building_inventory", None)
        elif source.get("source_type") == "stockpile":
            stockpile = getattr(self, "stockpiles_by_id", {}).get(source.get("stockpile_id"))
            if stockpile is None:
                self._warn_simulation_validation("invalid_stockpile", (source.get("stockpile_id"), "pickup"), "Cannot withdraw from a missing stockpile.", actor=npc, metadata={"stockpile_id": source.get("stockpile_id"), "item_key": item_key})
                return False
            item_reference = stockpile.withdraw_reserved_item_reference(haul_data.get("stockpile_reservation_id"), actor_id=getattr(npc, "id", None))
            if item_reference is None:
                self._warn_simulation_validation("missing_source_item", (source.get("stockpile_id"), item_key, haul_data.get("stockpile_reservation_id")), "Reserved stockpile item was unavailable at pickup.", actor=npc, metadata={"stockpile_id": source.get("stockpile_id"), "item_key": item_key})
                return False
            npc.economic.npc_inventory.add_item_reference(item_reference)
            haul_data["stockpile_reservation_id"] = None
            task = self.town_board.get_task(haul_data.get("haul_task_id"))
            if task is not None:
                task.stockpile_reservation_id = None
            self._record_stockpile_trace("stockpile_withdraw", stockpile, actor=npc, metadata={"item_key": item_key, "quantity": 1, "haul_task_id": haul_data.get("haul_task_id"), "stored_quantity": stockpile.quantity(item_key)})
            self._record_stockpile_trace("haul_started", stockpile, actor=npc, metadata={"item_key": item_key, "haul_task_id": haul_data.get("haul_task_id")})
            return True

        if inventory is None or not hasattr(inventory, "get_item_reference"):
            return False
        item_reference = inventory.get_item_reference(item_key)
        if item_reference is None:
            return False
        transferred = inventory.transfer_item_reference(npc.economic.npc_inventory, item_reference)
        if transferred:
            self._record_stockpile_trace("haul_started", None, actor=npc, metadata={"item_key": item_key, "haul_task_id": haul_data.get("haul_task_id"), "source_type": source.get("source_type")})
        return transferred

    def _is_construction_worker_role(self, npc: NPC) -> bool:
        profession = str(getattr(getattr(npc, "economic", None), "profession", "") or "").strip().lower()
        return profession in {"builder", "carpenter", "mason", "laborer", "helper", "porter", "unemployed"}

    def _has_available_construction_worker(self, blueprint, *, excluding_id: int | None = None) -> bool:
        for candidate in getattr(self, "village_npcs", []):
            if getattr(candidate, "id", None) == excluding_id:
                continue
            physical = getattr(candidate, "physical", None)
            if physical and getattr(physical, "is_dead", False):
                continue
            if not getattr(candidate, "is_alive", True):
                continue
            if not self._is_construction_worker_role(candidate):
                continue
            schedule = getattr(candidate, "schedule", None)
            current_task = getattr(schedule, "current_task", "") or ""
            if current_task not in {TaskType.IDLE, TaskType.WANDERING, TaskType.AT_HOME, "idle_confused", ""}:
                continue
            if getattr(schedule, "current_path", None):
                continue

            # Must be in the same settlement or reachable
            village = self._get_village_for_npc(candidate, by_coords=True)
            if village and blueprint.settlement_id != village.id:
                continue
            # Must be reachable
            if not self.calculate_path(candidate.x, candidate.y, blueprint.x, blueprint.y):
                continue
            return True
        return False

    def _get_buildable_blueprints(self) -> list[ConstructionBlueprint]:
        buildable = []
        for blueprint in list(self.blueprints_by_id.values()):
            blueprint.refresh_status()
            if blueprint.has_all_materials() and blueprint.status != "complete":
                buildable.append(blueprint)
        return buildable

    def _assign_construction_task_to_npc(self, npc: NPC) -> bool:
        profession = str(getattr(getattr(npc, "economic", None), "profession", "") or "").strip().lower()
        is_owner_or_manager = profession in {"owner", "manager", "foreman"}
        if not self._is_construction_worker_role(npc) and not is_owner_or_manager:
            return False

        best_blueprint = None
        best_distance = None
        for blueprint in self._get_buildable_blueprints():
            if is_owner_or_manager and self._has_available_construction_worker(blueprint, excluding_id=getattr(npc, "id", None)):
                continue
            if getattr(npc, "id", None) in getattr(blueprint, "assigned_workers", []):
                continue
            distance = abs(npc.x - blueprint.x) + abs(npc.y - blueprint.y)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_blueprint = blueprint

        if best_blueprint is None:
            return False

        if npc.id not in best_blueprint.assigned_workers:
            best_blueprint.assigned_workers.append(npc.id)
        task_id = f"construct:{best_blueprint.id}:{npc.id}"
        if task_id not in best_blueprint.active_tasks:
            best_blueprint.active_tasks.append(task_id)
        best_blueprint.refresh_status()
        self._refresh_blueprint_map_marker(best_blueprint)

        npc.schedule.current_task = "constructing_site"
        npc.current_sub_task = f"Building {best_blueprint.construction_stage}"
        npc.task_context = "construction"
        npc.task_context_data = {"blueprint_id": best_blueprint.id, "construction_task_id": task_id}
        coords = (best_blueprint.x, best_blueprint.y)
        npc.task_target_coords = coords
        npc.schedule.current_destination_coords = coords
        npc.schedule.current_path = self.calculate_path(npc.x, npc.y, coords[0], coords[1]) or []
        if (npc.x, npc.y) != coords and not npc.schedule.current_path:
            self._clear_npc_construction_task(npc, best_blueprint)
            return False
        return True

    def _clear_npc_construction_task(self, npc: NPC, blueprint: ConstructionBlueprint | None = None) -> None:
        task_data = npc.task_context_data if isinstance(npc.task_context_data, dict) else {}
        if blueprint is None:
            blueprint = self.blueprints_by_id.get(task_data.get("blueprint_id"))
        if blueprint is not None:
            self._release_construction_component_claim(blueprint, task_data.get("component_id"), getattr(npc, "id", None), reason="construction_task_cleared")
            if getattr(npc, "id", None) in blueprint.assigned_workers:
                blueprint.assigned_workers.remove(npc.id)
            task_id = task_data.get("construction_task_id")
            if task_id in blueprint.active_tasks:
                blueprint.active_tasks.remove(task_id)
            blueprint.refresh_status()
            self._refresh_blueprint_map_marker(blueprint)
        self._clear_npc_haul_task(npc, release_claim=False)

    def _handle_npc_construction_task(self, npc: NPC) -> bool:
        if npc.task_context != "construction":
            return False
        task_data = npc.task_context_data if isinstance(npc.task_context_data, dict) else {}
        blueprint = self.blueprints_by_id.get(task_data.get("blueprint_id"))
        if blueprint is None:
            self._clear_npc_haul_task(npc, release_claim=False)
            return False

        # Check if already in active build interaction
        active_interaction_id = getattr(npc.schedule, "active_interaction_id", None)
        if active_interaction_id and active_interaction_id in self.interaction_resolver.active_interactions:
            active_interaction = self.interaction_resolver.active_interactions[active_interaction_id]
            if getattr(active_interaction, "action_type", None) == "build" and active_interaction.blueprint_id == blueprint.id:
                # Still building, let interaction system handle it
                return True

        # Find or retain a claimed component to build. Claims keep multiple
        # workers from racing for the same piece while still expiring naturally.
        target_comp = None
        existing_component_id = task_data.get("component_id")
        existing_comp = self._get_blueprint_component(blueprint, existing_component_id)
        if (
            existing_comp is not None
            and existing_comp.status != "complete"
            and existing_comp.has_all_materials()
            and self._construction_component_available_for_actor(blueprint, existing_comp, npc)
        ):
            target_comp = existing_comp

        if target_comp is None:
            for comp in blueprint.components:
                if (
                    comp.status != "complete"
                    and comp.has_all_materials()
                    and self._construction_component_available_for_actor(blueprint, comp, npc)
                ):
                    target_comp = comp
                    break

        if target_comp is not None and not self._claim_construction_component(blueprint, target_comp, npc, reason="building"):
            target_comp = None

        if target_comp is not None:
            task_data["component_id"] = target_comp.id
            npc.task_context_data = task_data

        if not target_comp:
            # If no component is ready, maybe the whole thing is complete or stalled
            if blueprint.status == "complete" or all(c.status == "complete" for c in blueprint.components):
                self._complete_construction_blueprint(blueprint)
                self._clear_npc_haul_task(npc, release_claim=False)
                return True
            blueprint.refresh_status()
            self._clear_npc_construction_task(npc, blueprint)
            return False

        coords = (target_comp.x, target_comp.y)
        if (npc.x, npc.y) != coords:
            if not npc.schedule.current_path:
                npc.schedule.current_path = self.calculate_path(npc.x, npc.y, coords[0], coords[1]) or []
                npc.schedule.current_destination_coords = coords
            if not npc.schedule.current_path:
                blueprint.stalled_reason = "No path to worksite"
                self._clear_npc_construction_task(npc, blueprint)
                return False
            return True

        # At coordinates, push intent
        intent = ActionIntent(
            actor_id=npc.id,
            action_type="build",
            target_pos=coords,
            payload={"blueprint_id": blueprint.id, "component_id": target_comp.id}
        )

        result = self.interaction_resolver.resolve(intent, self)


        if result.success and result.started_interaction_id:
            npc.schedule.active_interaction_id = result.started_interaction_id
            npc.schedule.current_task = "active_interaction"
            npc.current_sub_task = f"Building {blueprint.construction_stage}"
            return True
        return False

    def _fail_delivery_for_npc(self, npc: NPC, task, *, drop_carried_item: bool = False) -> None:
        item_key = getattr(task, "item_key", None)
        if drop_carried_item and item_key:
            npc_inventory = getattr(getattr(npc, "economic", None), "npc_inventory", None)
            item_reference = npc_inventory.pop_item_reference(item_key) if npc_inventory is not None else None
            if item_reference is not None:
                self.drop_item_reference_on_map(item_reference, npc.x, npc.y)
        self.town_board.fail_delivery_task(task.id)
        self._clear_npc_haul_task(npc, release_claim=False)

    def _handle_npc_delivery_task(self, npc: NPC) -> bool:
        if npc.task_context != "delivery":
            return False

        if getattr(getattr(npc, "physical", None), "is_dead", False):
            return False

        haul_data = npc.task_context_data if isinstance(npc.task_context_data, dict) else {}
        task = self.town_board.get_delivery_task(haul_data.get("delivery_task_id"))
        dest_building = self.buildings_by_id.get(haul_data.get("destination_building_id"))
        source_building = self.buildings_by_id.get(haul_data.get("source_building_id"))
        item_key = haul_data.get("item_key")

        if task is None:
            self._clear_npc_haul_task(npc, release_claim=False)
            return False
        if dest_building is None or source_building is None or not item_key:
            self._fail_delivery_for_npc(npc, task, drop_carried_item=npc.schedule.current_task == "hauling_to_delivery_destination")
            return False

        if npc.schedule.current_task == "hauling_to_source":
            self.town_board.update_delivery_task_status(task.id, "going_to_source", current_tick=getattr(self, "game_time", None))
            source_coords = tuple(haul_data.get("source", {}).get("coords", ()))
            if len(source_coords) != 2:
                self._fail_delivery_for_npc(npc, task)
                return False
            if (npc.x, npc.y) != source_coords:
                if not npc.schedule.current_path:
                    npc.schedule.current_path = self.calculate_path(npc.x, npc.y, source_coords[0], source_coords[1]) or []
                    npc.schedule.current_destination_coords = source_coords
                if not npc.schedule.current_path:
                    self.town_board.release_delivery_task(task.id)
                    self._clear_npc_haul_task(npc, release_claim=False)
                    return False
                return True

            if not self._pickup_haul_task_material(npc, haul_data):
                self._fail_delivery_for_npc(npc, task)
                return False

            npc.schedule.current_task = "hauling_to_delivery_destination"
            npc.current_sub_task = f"Carrying {item_key}"
            self.town_board.update_delivery_task_status(task.id, "carrying", current_tick=getattr(self, "game_time", None))
            coords = (dest_building.global_center_x, dest_building.global_center_y)
            npc.task_target_coords = coords
            npc.schedule.current_destination_coords = coords
            npc.schedule.current_path = self.calculate_path(npc.x, npc.y, coords[0], coords[1]) or []
            if (npc.x, npc.y) != coords and not npc.schedule.current_path:
                self._fail_delivery_for_npc(npc, task, drop_carried_item=True)
                return False
            return True

        if npc.schedule.current_task == "hauling_to_delivery_destination":
            npc.current_sub_task = f"Delivering {item_key}"
            self.town_board.update_delivery_task_status(task.id, "going_to_destination", current_tick=getattr(self, "game_time", None))

            dest_coords = (dest_building.global_center_x, dest_building.global_center_y)
            if (npc.x, npc.y) != dest_coords:
                if not npc.schedule.current_path:
                    npc.schedule.current_path = self.calculate_path(npc.x, npc.y, dest_coords[0], dest_coords[1]) or []
                    npc.schedule.current_destination_coords = dest_coords
                if not npc.schedule.current_path:
                    self._fail_delivery_for_npc(npc, task, drop_carried_item=True)
                    return False
                return True

            # Reached destination, deposit item. Nothing arrives before this point.
            npc_inventory = getattr(getattr(npc, "economic", None), "npc_inventory", None)
            if npc_inventory is None or not npc_inventory.has_item(item_key, 1):
                self._fail_delivery_for_npc(npc, task)
                return False

            item_reference = npc_inventory.pop_item_reference(item_key)
            if item_reference is None:
                self._fail_delivery_for_npc(npc, task)
                return False

            village = self._get_village_for_npc(npc, by_coords=True)
            price = self.quote_item_reference_price(item_reference, village=village)
            if dest_building.building_inventory.get("money", 0) >= price or getattr(dest_building, "owner_id", None) is None:
                if getattr(dest_building, "owner_id", None) is not None:
                    dest_building.building_inventory["money"] -= price
                    source_building.building_inventory["money"] = source_building.building_inventory.get("money", 0) + price
                dest_building.building_inventory.add_item_reference(item_reference)
            else:
                self.drop_item_reference_on_map(item_reference, npc.x, npc.y)
                if hasattr(self, "visual_effects"):
                    self.visual_effects.append(FloatingTextEffect(npc.x, npc.y, "*Delivery failed: no funds*", color=(255, 100, 100)))
                self._fail_delivery_for_npc(npc, task)
                return False

            self.town_board.update_delivery_task_status(task.id, "complete", current_tick=getattr(self, "game_time", None))
            self.town_board.complete_delivery_task(task.id)
            self._clear_npc_haul_task(npc, release_claim=False)
            return True

        return False

    def _handle_npc_hauling_task(self, npc: NPC) -> bool:
        haul_data = npc.task_context_data if isinstance(npc.task_context_data, dict) else {}
        task = self.town_board.get_task(haul_data.get("haul_task_id"))
        blueprint = self.blueprints_by_id.get(haul_data.get("blueprint_id"))
        if task is None or blueprint is None or not blueprint.needs_material(haul_data.get("item_key", "")):
            if blueprint is not None:
                self._release_construction_component_claim(blueprint, haul_data.get("component_id"), getattr(npc, "id", None), reason="hauling_invalid")
            self._clear_npc_haul_task(npc, release_claim=task is not None and task.status != "complete")
            return False

        valid_haul_tasks = {"hauling_to_source", "hauling_to_blueprint"}
        if npc.schedule.current_task not in valid_haul_tasks:
            npc_inventory = getattr(getattr(npc, "economic", None), "npc_inventory", None)
            if npc_inventory is not None and npc_inventory.has_item(haul_data.get("item_key"), 1):
                npc.schedule.current_task = "hauling_to_blueprint"
            else:
                npc.schedule.current_task = "hauling_to_source"
            self._warn_simulation_validation(
                "task_recovered",
                (getattr(npc, "id", None), haul_data.get("haul_task_id"), "hauling_schedule"),
                "Recovered stale hauling schedule from task context.",
                actor=npc,
                metadata={"haul_task_id": haul_data.get("haul_task_id"), "restored_task": npc.schedule.current_task},
            )

        if npc.schedule.current_task == "hauling_to_source":
            source_coords = tuple(haul_data.get("source", {}).get("coords", ()))
            if (npc.x, npc.y) != source_coords:
                if not npc.schedule.current_path:
                    npc.schedule.current_path = self.calculate_path(npc.x, npc.y, source_coords[0], source_coords[1]) or []
                    npc.schedule.current_destination_coords = source_coords
                return bool(npc.schedule.current_path)
            if not self._pickup_haul_task_material(npc, haul_data):
                self._release_construction_component_claim(blueprint, haul_data.get("component_id"), getattr(npc, "id", None), reason="haul_pickup_failed")
                self._clear_npc_haul_task(npc, release_claim=True)
                return False
            npc.schedule.current_task = "hauling_to_blueprint"
            npc.current_sub_task = f"Delivering {haul_data.get('item_key')}"
            dest_x, dest_y = blueprint.x, blueprint.y
            component_id = getattr(task, "component_id", None)
            if component_id:
                for comp in blueprint.components:
                    if comp.id == component_id:
                        dest_x, dest_y = comp.x, comp.y
                        break
            npc.task_target_coords = (dest_x, dest_y)
            npc.schedule.current_destination_coords = (dest_x, dest_y)
            npc.schedule.current_path = self.calculate_path(npc.x, npc.y, dest_x, dest_y) or []
            return True

        if npc.schedule.current_task == "hauling_to_blueprint":
            dest_x, dest_y = blueprint.x, blueprint.y
            component_id = getattr(task, "component_id", None)
            if component_id:
                for comp in blueprint.components:
                    if comp.id == component_id:
                        dest_x, dest_y = comp.x, comp.y
                        break

            if getattr(self, "game_time", 0) % 40 == 0:
                self.visual_effects.append(FloatingTextEffect(npc.x, npc.y, "*hauling*", color=(200, 200, 150)))
            if (npc.x, npc.y) != (dest_x, dest_y):
                if not npc.schedule.current_path:
                    npc.schedule.current_path = self.calculate_path(npc.x, npc.y, dest_x, dest_y) or []
                    npc.schedule.current_destination_coords = (dest_x, dest_y)
                return bool(npc.schedule.current_path)
            deposited = self.deposit_actor_material_into_blueprint(npc, blueprint, haul_data.get("item_key"), task_id=task.id)
            self._record_stockpile_trace("haul_delivered" if deposited else "haul_failed", getattr(self, "stockpiles_by_id", {}).get(haul_data.get("source", {}).get("stockpile_id")), actor=npc, metadata={"haul_task_id": task.id, "blueprint_id": blueprint.id, "component_id": haul_data.get("component_id"), "item_key": haul_data.get("item_key"), "reason": None if deposited else "deposit_failed"})
            self._release_construction_component_claim(blueprint, haul_data.get("component_id"), getattr(npc, "id", None), reason="hauling_delivered" if deposited else "haul_deposit_failed")
            self._clear_npc_haul_task(npc, release_claim=not deposited)
            return deposited

        return False

    def _npc_buy_or_collect_food(self, npc: NPC, source_building: Building | None) -> bool:
        if not source_building:
            return False

        village = self._get_village_for_npc(npc, by_coords=True)
        source_inventory = self._get_trade_inventory(source_building)
        if source_inventory is None:
            return False
        best_item_reference = None
        best_score = -1
        for item_reference in source_inventory.iter_item_references():
            item_def = ITEM_DEFINITIONS.get(item_reference.key, {})
            on_use = item_def.get("on_use", {})
            if on_use.get("reduces_hunger", 0) <= 0:
                continue
            score = on_use.get("reduces_hunger", 0)
            if "food" in item_def.get("item_type_tags", []):
                score += 10
            if item_reference.key != "rotten_food":
                score += 5
            if score > best_score:
                best_score = score
                best_item_reference = item_reference

        if best_item_reference is None:
            return False

        price = self.quote_item_reference_price(best_item_reference, village=village)
        if npc.economic.money < price:
            return False

        return self.execute_trade(
            buyer=npc,
            seller=source_building,
            item_reference=best_item_reference,
            price=price,
            buyer_inventory=npc.economic.npc_inventory,
            seller_inventory=source_inventory,
        )

    def _handle_npc_survival_need(self, npc: NPC, *, need_type: str, urgent_threshold: int, desperate_threshold: int) -> bool:
        if getattr(self, "interaction_resolver", None):
            self.interaction_resolver.cancel_actor_interaction(npc.id, self, reason="survival_override")
        current_value = getattr(npc.physical, need_type, 0)
        seeking_task = "seeking_water" if need_type == "thirst" else "seeking_food"
        current_activity = getattr(npc, "current_activity", None)
        if current_activity and getattr(current_activity, "activity_type", None) in {"eating", "drinking"}:
            npc.schedule.current_task = seeking_task
            return True

        if current_value < urgent_threshold and npc.schedule.current_task == seeking_task:
            self._resume_npc_after_survival_need(npc)
            return False

        if current_value < urgent_threshold:
            return False

        desperate = current_value >= desperate_threshold
        if npc.schedule.current_task != seeking_task:
            self._remember_npc_interrupted_task(npc)
        inventory = npc.economic.npc_inventory
        found_supply, consumed_supply = self._npc_consume_from_inventory(
            npc,
            inventory,
            need_type=need_type,
            desperate=desperate,
        )
        if consumed_supply:
            self._resume_npc_after_survival_need(npc)
            return True

        if desperate:
            self._maybe_generate_survival_help_quest(npc, need_type=need_type)

        if need_type == "thirst":
            water_source = self._find_nearest_water_source(npc)
            if water_source is None:
                npc.schedule.current_task = "idle_confused"
                npc.schedule.current_path = []
                npc.schedule.current_destination_coords = None
                return True

            destination_tile = self.get_tile_at(water_source[0], water_source[1])
            if destination_tile and destination_tile.passable and (npc.x, npc.y) == water_source:
                npc.physical.thirst = 0
                self._resume_npc_after_survival_need(npc)
                return True

            if abs(npc.x - water_source[0]) + abs(npc.y - water_source[1]) <= 1:
                npc.physical.thirst = 0
                self._resume_npc_after_survival_need(npc)
                return True

            if self._path_npc_to_survival_target(npc, water_source, task_name=seeking_task, adjacent_if_blocked=True):
                return True

            npc.schedule.current_task = "idle_confused"
            npc.schedule.current_path = []
            npc.schedule.current_destination_coords = None
            return True

        if not found_supply and not desperate and npc.schedule.current_task != seeking_task:
            return False

        food_source = self._find_nearest_food_source(npc)
        if food_source and food_source.contains_global_coords(npc.x, npc.y):
            if self._npc_buy_or_collect_food(npc, food_source):
                _, consumed_after_purchase = self._npc_consume_from_inventory(
                    npc,
                    npc.economic.npc_inventory,
                    need_type="hunger",
                    desperate=True,
                )
                if consumed_after_purchase:
                    self._resume_npc_after_survival_need(npc)
                    return True
            npc.schedule.current_task = seeking_task
            npc.schedule.current_path = []
            npc.schedule.current_destination_coords = (food_source.global_center_x, food_source.global_center_y)
            return True

        if food_source and self._path_npc_to_survival_target(
            npc,
            (food_source.global_center_x, food_source.global_center_y),
            task_name=seeking_task,
        ):
            return True

        npc.schedule.current_task = "wandering_hungry"
        npc.schedule.current_path = []
        npc.schedule.current_destination_coords = None
        return True

    def _maybe_generate_survival_help_quest(self, npc: NPC, *, need_type: str) -> bool:
        if hasattr(npc, "active_quest") and npc.active_quest is not None:
            return False
        if random.random() >= 0.1:
            return False

        knows_food_source = "the tavern" in npc.knowledge.known_locations or "bakery" in npc.knowledge.known_locations
        knows_water_source = "the village well" in npc.knowledge.known_locations

        if need_type == "hunger":
            if knows_food_source:
                return False
            npc.knowledge.help_needed = "food"
            quest_item = "raw_fish"
            quest_count = random.randint(3, 5)
            quest_title = f"A Desperate Need for {quest_item.replace('_', ' ').title()}"
        else:
            if knows_water_source:
                return False
            npc.knowledge.help_needed = "water"
            quest_item = "water_flask"
            quest_count = 1
            quest_title = "A Desperate Need for Water Flask"

        quest_id = f"fetch_{quest_item}_{npc.id}_{self.game_time}"
        quest = Quest(
            quest_id=quest_id,
            title=quest_title,
            description=f"{npc.name} is in dire need of {quest_count} {quest_item.replace('_', ' ')}.",
            quest_type="fetch",
            quest_giver_id=npc.id,
        )
        quest.item_key = quest_item
        quest.required_count = quest_count
        setattr(npc, "active_quest", quest)

        if npc.id in self.npc_fov_maps and self.npc_fov_maps[npc.id][self.player.y, self.player.x]:
            npc.schedule.current_task = "approaching_player_for_help"
            dest_x, dest_y = self._find_best_adjacent_tile(self.player.x, self.player.y, npc)
            if dest_x is not None:
                path = self.calculate_path(npc.x, npc.y, dest_x, dest_y)
                if path:
                    npc.schedule.current_path = path
                    npc.schedule.current_destination_coords = (dest_x, dest_y)
        return True

    def _npc_eat_from_inventory(self, npc: NPC, inventory: dict, is_building_inventory: bool = False) -> tuple[bool, bool]:
        """
        Searches an inventory for food and consumes one item if found.
        Returns (found_food: bool, consumed_food: bool).
        `found_food` is True if any food item exists.
        `consumed_food` is True if a food item was successfully consumed.
        """
        return self._npc_consume_from_inventory(npc, inventory, need_type="hunger", desperate=False)

    def complete_contract_delivery(self, contract_id: str, turn_in_npc: NPC):
        """Handles player attempting to turn in a contract delivery."""
        turn_in_name = self.get_entity_display_name(turn_in_npc)
        if contract_id not in self.player.economic.active_contracts:
            self.add_message_to_chat_log("Error: Contract not found or already completed.")
            if self.chat_ui_active and self.chat_ui_target_npc == turn_in_npc:
                 self.chat_ui_history.append((turn_in_name, "Hmm, I don't recall that arrangement."))
            return

        contract = self.player.economic.active_contracts[contract_id]
        # Ensure this is the correct NPC to turn into, using npc_id stored in contract
        if contract.get("turn_in_npc_id") != turn_in_npc.id: # Check against NPC's actual ID
            self.add_message_to_chat_log("This is not the right person for this delivery.")
            if self.chat_ui_active and self.chat_ui_target_npc == turn_in_npc:
                 self.chat_ui_history.append((turn_in_name, "Are you sure you have that for me?"))
            return

        item_key = contract["item_key"]
        qty_needed = contract["quantity_needed"]

        if self.player.has_item(item_key, qty_needed):
            self.player.remove_item(item_key, qty_needed)

            self.player.economic.money += contract["reward"]
            completion_msg = f"Delivery complete! You gave {qty_needed} {item_key}(s) and received {contract['reward']} money."
            self.add_message_to_chat_log(completion_msg) # Log to main game log

            # Add to chat UI history if chat is active with this NPC
            if self.chat_ui_active and self.chat_ui_target_npc == turn_in_npc:
                self.chat_ui_history.append(("System", completion_msg))
                self.chat_ui_history.append((turn_in_name, f"Excellent work! Here's your {contract['reward']} coins."))
                if len(self.chat_ui_history) > self.chat_ui_max_history:
                    self.chat_ui_history = self.chat_ui_history[-self.chat_ui_max_history:]
                self.chat_ui_scroll_offset = 0

    def _get_interactables_at(self, x: int, y: int) -> list:
        """Returns a list of all interactable entities at a given coordinate."""
        entities = []

        # 1. Add the tile itself
        tile = self.get_tile_at(x, y)
        if tile:
            entities.append({"type": "tile", "data": tile, "name": tile.name})

        # 2. Add items on the ground
        if (x, y) in self.items_on_map:
            for item_key, quantity in self.items_on_map[(x, y)].items():
                item_def = self.get_item_definition(item_key)
                item_reference = self.items_on_map[(x, y)].get_item_reference(item_key)
                entities.append({
                    "type": "item",
                    "data": {"item_key": item_key, "quantity": quantity, "item_reference": item_reference},
                    "name": getattr(item_reference, "name", item_def.get("name", item_key))
                })

        # 3. Add construction blueprints
        blueprint = self.get_blueprint_at(x, y)
        if blueprint:
            entities.append({"type": "blueprint", "data": blueprint, "name": blueprint.name})

        # 4. Add NPCs
        for npc in self.all_npcs:
            if npc.x == x and npc.y == y and not npc.is_dead:
                entities.append({"type": "npc", "data": npc, "name": self.get_entity_display_name(npc, include_relationship=True)})

        # 5. Add Buildings
        building = self.get_building_at(x,y)
        if building:
            entities.append({"type": "building", "data": building, "name": building.building_type})

        return entities

    def get_item_definition(self, item_key: str) -> dict | None:
        """
        Gets the definition for an item. Handles dynamic book keys.
        Returns a copy of the definition to prevent modification of the original.
        """
        if item_key.startswith("book_"):
            book_id = item_key.split("_", 1)[1]
            book = next((b for b in self.books if b.id == book_id), None)
            if book:
                base_def_key = f"book_{book.book_type}"
                base_def = ITEM_DEFINITIONS.get(base_def_key)
                if base_def:
                    # Create a copy and override dynamic properties
                    dynamic_def = base_def.copy()
                    dynamic_def["name"] = book.title
                    dynamic_def["description"] = f"A book titled '{book.title}' by {book.author_name}."
                    return dynamic_def
            # Fallback if book not found, return the base chronicle definition
            return ITEM_DEFINITIONS.get("book_chronicle", {}).copy()

        return ITEM_DEFINITIONS.get(item_key, {}).copy()

    def _get_actions_for_entity(self, entity: dict) -> list[str]:
        """Returns a list of available actions for a given entity dictionary."""
        actions = []
        entity_type = entity["type"]
        entity_data = entity["data"]

        if entity_type == "npc":
            if isinstance(entity_data, Animal):
                animal_def = ANIMAL_DEFINITIONS.get(entity_data.animal_type, {})
                if animal_def.get("rideable") and entity_data.is_tame and entity_data.owner == self.player:
                    if self.player.state.is_riding and self.player.state.riding_animal_id == entity_data.id:
                        actions.append("Dismount")
                    else:
                        actions.append("Ride")
                actions.append("Feed")
                actions.append("Attack")
            else: # It's a humanoid NPC
                actions.extend(["Talk", "Attack"])
                if entity_has_capability(entity_data, "trade"):
                    actions.append("Trade")

                # Check if this NPC is an official in a warring village
                village = self._get_village_for_npc(entity_data)
                if village and village.at_war_with and entity_has_any_profession(entity_data, ["Mayor", "Sheriff", "Guard"]):
                    actions.append("Offer Mercenary Services")

        elif entity_type == "item":
            actions.append("Pick up")
            item_ref = entity_data.get("item_reference")
            if entity_data["item_key"].startswith("book_") or getattr(item_ref, "written_text", ""):
                actions.append("Read")

        elif entity_type == "tile":
            interaction_hint = entity_data.properties.get("interaction_hint")
            if isinstance(entity_data, Tree) and entity_data.is_choppable:
                actions.append("Chop")
            elif entity_data.properties.get("is_door"):
                actions.append("Toggle Door")
            elif entity_data.name == "Animal Corpse":
                actions.append("Butcher")
            elif entity_data.name == "Treasure Chest":
                actions.append("Loot Chest")
            elif interaction_hint == "noticeboard":
                actions.append("Read Notices")
            elif interaction_hint == "sit":
                actions.append("Sit")
            elif interaction_hint == "sleep":
                actions.append("Sleep")
            elif interaction_hint == "forge":
                actions.append("Forge")

            elif entity_data.name == "Plains" and self.player.has_item("stone_hoe"):
                actions.append("Till Soil")
            elif entity_data.name == "Tilled Soil" and self.player.has_item("wheat_seeds"):
                actions.append("Plant Seeds")
            elif entity_data.name == "Wheat":
                actions.append("Harvest")
        elif entity_type == "building":
            if entity_data.building_type == "house" and not entity_data.player_owned and not entity_data.residents:
                actions.append("Claim House")
            elif getattr(entity_data, "owner_id", None) is None and not getattr(entity_data, "player_owned", False):
                actions.append("Buy Property")
            if self._building_is_owned_by_player(entity_data):
                actions.append("Company Ledger")
                if "workplace" in str(getattr(entity_data, "category", "")):
                    actions.append("Post Job")
            if entity_data.building_type == "capital_hall" and self.player_has_governance_access():
                actions.append("Govern")

        # Add a "Shear" action for shearable animals
        if entity_type == "npc" and isinstance(entity_data, Animal):
            animal_def = ANIMAL_DEFINITIONS.get(entity_data.animal_type, {})
            if "shearable" in animal_def:
                actions.append("Shear")

        if entity_type == "tile" and entity_data.properties.get("workstation_type") == "fire":
             # Check if player has raw food
             has_raw_food = False
             for item_key, count in list(self.player.economic.inventory.items()):
                 if item_key == "item_references":
                     continue
                 item_def = ITEM_DEFINITIONS.get(item_key, {})
                 if "food_ingredient_raw" in item_def.get("item_type_tags", []):
                     has_raw_food = True
                     break
             if has_raw_food:
                 actions.append("Cook")

        actions.append("Examine") # Universal action
        return actions

    def serve_jail_time(self):
        """Handles the process of putting the player in jail."""
        # Find the nearest sheriff's office.
        sheriff_office = None
        min_dist_sq = float('inf')
        for building in self.buildings_by_id.values():
            if building.building_type == "sheriff_office":
                dist_sq = (self.player.x - building.global_center_x)**2 + (self.player.y - building.global_center_y)**2
                if dist_sq < min_dist_sq:
                    min_dist_sq = dist_sq
                    sheriff_office = building

        if not sheriff_office:
            self.add_message_to_chat_log("The sheriff pats you down but has nowhere to hold you. You're free to go... for now.")
            self.player.economic.bounty = self.player.economic.bounty // 2 # Reduce bounty anyway
            return

        # Dynamically create a 3x3 jail cell in the top-left corner of the building's interior.
        cell_origin_x = sheriff_office.global_origin_x + 1
        cell_origin_y = sheriff_office.global_origin_y + 1
        cell_center_x = cell_origin_x + 1
        cell_center_y = cell_origin_y + 1
        door_x, door_y = cell_origin_x + 1, cell_origin_y + 2

        jail_bar_def = TILE_DEFINITIONS["jail_bars"]
        iron_door_def = DECORATION_ITEM_DEFINITIONS["iron_door_closed"]
        floor_def = TILE_DEFINITIONS["wood_floor"]

        # Carve out the cell
        for y_offset in range(3):
            for x_offset in range(3):
                is_border = x_offset == 0 or x_offset == 2 or y_offset == 0 or y_offset == 2
                tile_x, tile_y = cell_origin_x + x_offset, cell_origin_y + y_offset

                if is_border:
                    if y_offset == 2 and x_offset == 1: # Door on the bottom wall
                        self._change_map_tile((tile_x, tile_y), iron_door_def)
                    else:
                        self._change_map_tile((tile_x, tile_y), jail_bar_def)
                else: # Interior of the cell
                    self._change_map_tile((tile_x, tile_y), floor_def)


        # Move player to cell
        self._update_entity_position(self.player, cell_center_x, cell_center_y)
        self.player.state.is_jailed = True
        self.player.state.jail_cell_coords = (door_x, door_y) # Store the DOOR coordinates
        self.player.state.jail_time_remaining = 500 # Set jail time
        self.add_message_to_chat_log("You've been thrown in jail!")

        # Reduce bounty
        self.player.economic.bounty = 0
        self.add_message_to_chat_log("Your bounty has been cleared.")

        self._update_player_fov() # Update FOV from new position


        del self.player.economic.active_contracts[contract_id]

        # If chat UI was active, maybe close it or go back to general talk mode
        if self.chat_ui_active and self.chat_ui_target_npc == turn_in_npc:
                self.chat_ui_mode = "talk" # Or could close: self.chat_ui_active = False; context.stop_text_input()
                                           # For now, let's keep it open in talk mode.
                # Add a follow-up generic line from NPC after payment.
                self.chat_ui_history.append((turn_in_npc.name, "Anything else I can help you with?"))


        else:
            needed_more = qty_needed - player_has_qty
            short_msg = f"You don't have enough {item_key}s. You still need {needed_more} more."
            self.add_message_to_chat_log(short_msg) # Log to main game log
            if self.chat_ui_active and self.chat_ui_target_npc == turn_in_npc:
                self.chat_ui_history.append(("System", short_msg))
                self.chat_ui_history.append((turn_in_npc.name, f"Looks like you're still short on those. Come back when you have all {qty_needed}."))
                if len(self.chat_ui_history) > self.chat_ui_max_history:
                    self.chat_ui_history = self.chat_ui_history[-self.chat_ui_max_history:]
                self.chat_ui_scroll_offset = 0

    def _get_chunk_from_building(self, building_to_find: Building) -> tuple[Chunk | None, int, int]:
        """Finds the chunk a building belongs to and its global starting coords."""
        # This is inefficient. Ideally, Building objects would store their parent chunk's coords or reference.
        for y_idx, chunk_row in enumerate(self.chunks):
            for x_idx, chunk in enumerate(chunk_row):
                if chunk and chunk.village and building_to_find in chunk.village.buildings:
                    return chunk, x_idx * CHUNK_SIZE, y_idx * CHUNK_SIZE
        return None, 0, 0

    def _building_contains_item_with_interaction(self, building: Building, interaction_hint: str) -> bool:
        """Checks if a building contains a decoration with a specific interaction_hint."""
        if not building:
            return False

        building_chunk, chunk_start_x, chunk_start_y = self._get_chunk_from_building(building)

        if not building_chunk or not building_chunk.is_generated or not building_chunk.tiles:
            # self.add_message_to_chat_log(f"Debug: Bed check - Building chunk {building_chunk.biome if building_chunk else 'N/A'} not generated or no tiles for building {building.id[:6]}")
            return False

        # Building.x and .y are local to the chunk's tile grid.
        # Iterate through the tiles *within the building's footprint on the chunk's tile grid*.
        for y_offset in range(building.height):
            for x_offset in range(building.width):
                # Don't check border walls of the building itself as locations for items like beds
                if x_offset == 0 or x_offset == building.width -1 or y_offset == 0 or y_offset == building.height -1:
                    continue

                tile_in_chunk_x = building.x + x_offset
                tile_in_chunk_y = building.y + y_offset

                if 0 <= tile_in_chunk_x < CHUNK_SIZE and 0 <= tile_in_chunk_y < CHUNK_SIZE:
                    tile = building_chunk.tiles[tile_in_chunk_y][tile_in_chunk_x]
                    if tile and hasattr(tile, 'properties') and tile.properties.get("interaction_hint") == interaction_hint:
                        # self.add_message_to_chat_log(f"Debug: Found '{interaction_hint}' in building {building.id[:6]} at {tile_in_chunk_x},{tile_in_chunk_y} (local)")
                        return True
        # self.add_message_to_chat_log(f"Debug: No '{interaction_hint}' found in building {building.id[:6]}")
        return False

    def _change_map_tile(self, coords: tuple[int, int], new_tile_def: dict, original_tree_type: str | None = None):
        """Changes a tile on the map to a new one based on a TILE_DEFINITION."""
        x, y = coords
        chunk_x, chunk_y = x // CHUNK_SIZE, y // CHUNK_SIZE
        local_x, local_y = x % CHUNK_SIZE, y % CHUNK_SIZE

        if 0 <= chunk_x < self.chunk_width and 0 <= chunk_y < self.chunk_height:
            chunk = self.chunks[chunk_y][chunk_x]
            if chunk and chunk.tiles:
                new_tile = Tile(
                    char=new_tile_def["char"],
                    color=new_tile_def["color"],
                    passable=new_tile_def["passable"],
                    name=new_tile_def["name"],
                    properties=new_tile_def.get("properties", {})
                )
                if original_tree_type:
                    new_tile.original_tree_type = original_tree_type

                chunk.tiles[local_y][local_x] = new_tile
                # Update transparency map
                self.transparency_map[y, x] = not new_tile.blocks_fov

    def _get_loaded_tile_at(self, x: int, y: int):
        """Return a tile from an already-loaded chunk without triggering generation."""
        if not (0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT):
            return None
        chunk_x, chunk_y = x // CHUNK_SIZE, y // CHUNK_SIZE
        local_x, local_y = x % CHUNK_SIZE, y % CHUNK_SIZE
        if not (0 <= chunk_x < self.chunk_width and 0 <= chunk_y < self.chunk_height):
            return None
        chunk = self.chunks[chunk_y][chunk_x]
        if chunk is None or chunk.tiles is None:
            return None
        return chunk.tiles[local_y][local_x]

    def _building_requires_entrance_integrity(self, building: Building) -> bool:
        return building.width >= 3 and building.height >= 3

    def _get_building_entrance_candidates(self, building: Building) -> list[dict[str, tuple[int, int]]]:
        center_x = building.global_origin_x + building.width // 2
        center_y = building.global_origin_y + building.height // 2
        return [
            {
                "door": (center_x, building.global_origin_y + building.height - 1),
                "inside": (center_x, building.global_origin_y + building.height - 2),
                "outside": (center_x, building.global_origin_y + building.height),
            },
            {
                "door": (center_x, building.global_origin_y),
                "inside": (center_x, building.global_origin_y + 1),
                "outside": (center_x, building.global_origin_y - 1),
            },
            {
                "door": (building.global_origin_x, center_y),
                "inside": (building.global_origin_x + 1, center_y),
                "outside": (building.global_origin_x - 1, center_y),
            },
            {
                "door": (building.global_origin_x + building.width - 1, center_y),
                "inside": (building.global_origin_x + building.width - 2, center_y),
                "outside": (building.global_origin_x + building.width, center_y),
            },
        ]

    def _is_usable_building_entrance(self, building: Building, candidate: dict[str, tuple[int, int]]) -> bool:
        door_x, door_y = candidate["door"]
        inside_x, inside_y = candidate["inside"]
        outside_x, outside_y = candidate["outside"]
        door_tile = self._get_loaded_tile_at(door_x, door_y)
        inside_tile = self._get_loaded_tile_at(inside_x, inside_y)
        outside_tile = self._get_loaded_tile_at(outside_x, outside_y)
        if door_tile is None or inside_tile is None or outside_tile is None:
            return False
        if building.contains_global_coords(outside_x, outside_y):
            return False
        entrance_is_opening = getattr(door_tile, "passable", False) or door_tile.properties.get("is_door", False)
        return entrance_is_opening and getattr(inside_tile, "passable", False) and getattr(outside_tile, "passable", False)

    def _ensure_building_entrance_integrity(self, building: Building) -> tuple[int, int] | None:
        """Guarantee a deterministic usable entrance for enclosed enterable buildings."""
        if not self._building_requires_entrance_integrity(building):
            return None

        for candidate in self._get_building_entrance_candidates(building):
            if self._is_usable_building_entrance(building, candidate):
                building.interaction_points["entrance"] = candidate["door"]
                return candidate["door"]

        chosen_candidate = None
        for candidate in self._get_building_entrance_candidates(building):
            outside_x, outside_y = candidate["outside"]
            outside_tile = self._get_loaded_tile_at(outside_x, outside_y)
            if outside_tile and getattr(outside_tile, "passable", False) and not building.contains_global_coords(outside_x, outside_y):
                chosen_candidate = candidate
                break

        if chosen_candidate is None:
            return None

        inside_x, inside_y = chosen_candidate["inside"]
        inside_tile = self._get_loaded_tile_at(inside_x, inside_y)
        if inside_tile is None or not getattr(inside_tile, "passable", False):
            self._change_map_tile((inside_x, inside_y), TILE_DEFINITIONS["wood_floor"])

        door_x, door_y = chosen_candidate["door"]
        door_tile = self._get_loaded_tile_at(door_x, door_y)
        if door_tile is None or not door_tile.properties.get("is_door", False):
            self._change_map_tile((door_x, door_y), DECORATION_ITEM_DEFINITIONS["wooden_door_closed"])

        if self._is_usable_building_entrance(building, chosen_candidate):
            building.interaction_points["entrance"] = chosen_candidate["door"]
            return chosen_candidate["door"]
        return None

    def _building_interior_path_exists(
        self,
        building: Building,
        start: tuple[int, int],
        target: tuple[int, int],
    ) -> bool:
        if start == target:
            tile = self._get_loaded_tile_at(*start)
            return bool(tile and getattr(tile, "passable", False))
        start_tile = self._get_loaded_tile_at(*start)
        target_tile = self._get_loaded_tile_at(*target)
        if not (start_tile and target_tile and start_tile.passable and target_tile.passable):
            return False
        if not (building.contains_global_coords(*start) and building.contains_global_coords(*target)):
            return False

        queue = [start]
        visited = {start}
        index = 0
        while index < len(queue):
            current_x, current_y = queue[index]
            index += 1
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                next_x, next_y = current_x + dx, current_y + dy
                next_pos = (next_x, next_y)
                if next_pos in visited or not building.contains_global_coords(next_x, next_y):
                    continue
                next_tile = self._get_loaded_tile_at(next_x, next_y)
                if not (next_tile and getattr(next_tile, "passable", False)):
                    continue
                if next_pos == target:
                    return True
                visited.add(next_pos)
                queue.append(next_pos)
        return False

    def _get_spawn_tile_for_building(self, building: Building) -> tuple[int, int] | None:
        entrance = self._ensure_building_entrance_integrity(building)
        if entrance is None:
            return None
        entrance_candidate = next(
            (
                candidate
                for candidate in self._get_building_entrance_candidates(building)
                if candidate["door"] == entrance
            ),
            None,
        )
        if entrance_candidate is None:
            return None

        center = (building.global_center_x, building.global_center_y)
        if self._building_interior_path_exists(building, center, entrance_candidate["inside"]):
            return center
        return entrance_candidate["inside"]

    def _place_building_decoration_tile(self, building: Building, item_type: str, world_x: int, world_y: int) -> bool:
        decoration_tile_def = DECORATION_ITEM_DEFINITIONS.get(item_type)
        if decoration_tile_def is None:
            return False
        if not building.contains_global_coords(world_x, world_y):
            return False

        target_chunk_x = world_x // CHUNK_SIZE
        target_chunk_y = world_y // CHUNK_SIZE
        if not (0 <= target_chunk_x < self.chunk_width and 0 <= target_chunk_y < self.chunk_height):
            return False

        target_chunk = self.chunks[target_chunk_y][target_chunk_x]
        if target_chunk is None or target_chunk.tiles is None:
            return False

        local_x = world_x % CHUNK_SIZE
        local_y = world_y % CHUNK_SIZE
        target_chunk.tiles[local_y][local_x] = Tile(
            char=decoration_tile_def["char"],
            color=decoration_tile_def["color"],
            passable=decoration_tile_def["passable"],
            name=decoration_tile_def.get("name", item_type),
            properties=decoration_tile_def.get("properties", {}),
        )
        self.transparency_map[world_y, world_x] = not target_chunk.tiles[local_y][local_x].blocks_fov

        interaction_hint = decoration_tile_def.get("properties", {}).get("interaction_hint")
        if interaction_hint == "sleep" and "sleep_spot" not in building.interaction_points:
            building.interaction_points["sleep_spot"] = (world_x, world_y)
        return True

    def _get_default_interior_decorations(self, building: Building) -> list[dict[str, int | str]]:
        max_x = building.width - 2
        max_y = building.height - 2
        center_x = max(1, min(max_x, building.width // 2))
        center_y = max(1, min(max_y, building.height // 2))

        if max_x < 1 or max_y < 1:
            return []

        layouts_by_type = {
            "house": [
                {"type": "bed_simple", "x": 1, "y": 1},
                {"type": "wooden_table", "x": center_x, "y": 1},
                {"type": "chest_wooden", "x": max_x, "y": 1},
            ],
            "general_store": [
                {"type": "wooden_table", "x": 1, "y": 1},
                {"type": "wooden_table", "x": center_x, "y": 1},
                {"type": "chest_wooden", "x": max_x, "y": 1},
            ],
            "bakery": [
                {"type": "wooden_table", "x": 1, "y": 1},
                {"type": "wooden_table", "x": center_x, "y": 1},
                {"type": "chest_wooden", "x": max_x, "y": max_y},
            ],
            "library": [
                {"type": "wooden_table", "x": 1, "y": 1},
                {"type": "wooden_table", "x": center_x, "y": 1},
                {"type": "wall_shelf", "x": max_x, "y": 1},
            ],
            "blacksmith_shop": [
                {"type": "workbench", "x": 1, "y": 1},
                {"type": "wooden_table", "x": max_x, "y": 1},
                {"type": "chest_wooden", "x": max_x, "y": max_y},
            ],
            "mill": [
                {"type": "workbench", "x": 1, "y": 1},
                {"type": "chest_wooden", "x": max_x, "y": 1},
            ],
            "mine": [
                {"type": "workbench", "x": 1, "y": 1},
                {"type": "chest_wooden", "x": max_x, "y": max_y},
            ],
            "farm": [
                {"type": "workbench", "x": 1, "y": 1},
                {"type": "chest_wooden", "x": max_x, "y": 1},
            ],
            "capital_hall": [
                {"type": "wooden_table", "x": center_x, "y": 1},
                {"type": "chest_wooden", "x": max_x, "y": 1},
            ],
            "sheriff_office": [
                {"type": "wooden_table", "x": 1, "y": 1},
                {"type": "chest_wooden", "x": max_x, "y": 1},
            ],
            "jail": [
                {"type": "bed_simple", "x": 1, "y": 1},
            ],
        }

        default_layout = layouts_by_type.get(building.building_type)
        if default_layout is not None:
            return default_layout

        if building.category == "residential":
            return [
                {"type": "bed_simple", "x": 1, "y": 1},
                {"type": "wooden_table", "x": center_x, "y": 1},
                {"type": "chest_wooden", "x": max_x, "y": 1},
            ]
        if building.category in {"commercial", "commercial_workplace"}:
            return [
                {"type": "wooden_table", "x": 1, "y": 1},
                {"type": "wooden_table", "x": center_x, "y": 1},
            ]
        if building.category in {"industrial", "industrial_workplace", "agricultural_workplace"}:
            return [
                {"type": "workbench", "x": 1, "y": 1},
                {"type": "chest_wooden", "x": max_x, "y": 1},
            ]
        if building.category in {"civic", "civic_workplace", "medical"}:
            return [
                {"type": "wooden_table", "x": 1, "y": 1},
                {"type": "chest_wooden", "x": max_x, "y": 1},
            ]
        return []

    def get_blueprint_at(self, x: int, y: int) -> ConstructionBlueprint | None:
        blueprint_id = self.blueprint_positions.get((x, y))
        if blueprint_id is None:
            return None
        return self.blueprints_by_id.get(blueprint_id)

    def _get_blueprint_tile_def(self, blueprint: ConstructionBlueprint) -> dict:
        stage_chars = {
            "planning": blueprint.char,
            "foundation": "_",
            "framing": "#",
            "finishing": "%",
            "complete": blueprint.char,
        }
        stage = getattr(blueprint, "construction_stage", "planning")
        return {
            "char": stage_chars.get(stage, blueprint.char),
            "color": blueprint.color,
            "passable": True,
            "name": f"{blueprint.name} ({stage.replace('_', ' ').title()})",
            "properties": {
                "is_construction_site": True,
                "blueprint_id": blueprint.id,
                "construction_stage": stage,
                "construction_status": getattr(blueprint, "status", "planning"),
                "stalled_reason": getattr(blueprint, "stalled_reason", None),
            },
        }

    def _refresh_blueprint_map_marker(self, blueprint: ConstructionBlueprint) -> None:
        if blueprint.id in self.blueprints_by_id:
            self._change_map_tile((blueprint.x, blueprint.y), self._get_blueprint_tile_def(blueprint))

    def place_construction_blueprint(self, recipe_key: str, x: int, y: int, *, owner_id: int | None = None, requester_id: int | None = None, settlement_id: str | None = None) -> ConstructionBlueprint | None:
        recipe = CONSTRUCTION_RECIPES.get(recipe_key)
        if recipe is None:
            return None
        if self.get_blueprint_at(x, y) is not None:
            return self.get_blueprint_at(x, y)
        chunk_x = x // CHUNK_SIZE
        chunk_y = y // CHUNK_SIZE
        village = None
        if 0 <= chunk_x < self.chunk_width and 0 <= chunk_y < self.chunk_height:
            village = getattr(self.chunks[chunk_y][chunk_x], "village", None)
        if settlement_id is None:
            settlement_id = getattr(village, "id", None)
        if settlement_id is not None:
            self.ensure_settlement_territory(self._get_village_by_id(settlement_id) or village)
        blueprint_width = int(recipe.get("width", 1))
        blueprint_height = int(recipe.get("height", 1))
        variant_id = None
        if recipe.get("source") == "building":
            from simulation.systems.architecture import BUILDING_ARCHETYPES
            if recipe_key in BUILDING_ARCHETYPES:
                wealth_tier = self._get_owner_wealth_tier(owner_id)
                variant = BUILDING_ARCHETYPES[recipe_key].get_variant(wealth_tier)
                if variant:
                    variant_id = variant.id
                    blueprint_width = variant.width
                    blueprint_height = variant.height

        if not self._can_reserve_land_for_construction(recipe_key, x, y, settlement_id, variant_id):
            return None

        reservation = self.create_land_claim(
            "construction_reservation",
            set(),
            reserved_tiles=self._construction_footprint_tiles(recipe_key, x, y, variant_id),
            owner_type="construction",
            owner_id=None,
            settlement_id=settlement_id,
            priority=9,
            metadata={"target_build": recipe_key, "x": x, "y": y},
        )

        blueprint = ConstructionBlueprint(
            x=x,
            y=y,
            target_build=recipe_key,
            required_materials=dict(recipe.get("materials", {})),
            source=recipe.get("source", "decoration"),
            tile_def_key=recipe.get("tile_def_key"),
            width=blueprint_width,
            height=blueprint_height,
            category=recipe.get("category", "player_construction"),
            settlement_id=settlement_id,
            region_id=getattr(village, "region_id", None),
            owner_id=owner_id,
            requester_id=requester_id,
            required_work=int(recipe.get("required_work", 100)),
            territory_claim_id=getattr(reservation, "id", None),
            variant_id=variant_id,
        )
        if reservation is not None:
            reservation.owner_id = blueprint.id
            reservation.metadata["blueprint_id"] = blueprint.id
        self.blueprints_by_id[blueprint.id] = blueprint
        self.blueprint_positions[(x, y)] = blueprint.id
        self.town_board.post_blueprint(blueprint)
        self._change_map_tile((x, y), self._get_blueprint_tile_def(blueprint))
        return blueprint

    def _get_village_blueprints(self, village: Village | None) -> list[ConstructionBlueprint]:
        if village is None:
            return []
        return [
            blueprint
            for blueprint in self.blueprints_by_id.values()
            if getattr(blueprint, "settlement_id", None) == village.id
        ]

    def _count_active_workers_for_building(self, building: Building | None) -> int:
        if building is None:
            return 0
        return sum(
            1
            for villager in self.village_npcs
            if villager.schedule.work_building_id == building.id and not villager.physical.is_dead
        )

    def _seed_new_building_economy(self, building: Building | None) -> None:
        if building is None:
            return
        if getattr(building, "building_type", "") == "capital_hall":
            if self._get_trade_money_balance(building) <= 0:
                self._set_trade_money_balance(building, random.randint(600, 1200))
            self.politics.town_hall_building_id = building.id
            return
        if "workplace" in str(getattr(building, "category", "")) and self._get_trade_money_balance(building) <= 0:
            self._set_trade_money_balance(building, random.randint(80, 180))

    def _sync_building_employment_tasks(self, building: Building | None) -> None:
        if building is None or "workplace" not in str(getattr(building, "category", "")):
            return
        if getattr(building, "owner_id", None) is not None:
            return

        current_workers = self._count_active_workers_for_building(building)
        open_tasks = self.town_board.get_open_employment_tasks(building.id)
        vacancies = max(0, int(getattr(building, "max_workers", 0)) - current_workers)

        while len(open_tasks) > vacancies:
            task_to_remove = open_tasks.pop()
            self.town_board.remove_employment_task(task_to_remove.id)

        role = self._resolve_profession_for_work_building(building)
        wage = self._get_employment_daily_wage(role)
        while len(open_tasks) < vacancies:
            open_tasks.append(self.town_board.post_employment(building.id, role, wage))

    def _sync_village_employment_tasks(self, village: Village | None) -> None:
        if village is None:
            return
        for building in getattr(village, "buildings", []):
            self._sync_building_employment_tasks(building)


    def _activate_completed_building_owner(self, building: Building | None) -> None:
        if building is None or "workplace" not in str(getattr(building, "category", "")):
            return
        owner = self._find_npc_by_id(getattr(building, "owner_id", None))
        if owner is None or owner is getattr(self, "player", None) or getattr(getattr(owner, "physical", None), "is_dead", False):
            return
        if getattr(getattr(owner, "schedule", None), "work_building_id", None) == building.id:
            return
        self._assign_job(
            owner,
            building,
            profession=self._resolve_profession_for_work_building(building, exclude_entity=None),
            reason="business_owner",
        )

    def _complete_construction_blueprint(self, blueprint: ConstructionBlueprint) -> bool:
        recipe = CONSTRUCTION_RECIPES.get(blueprint.target_build)
        if recipe is None:
            return False
        blueprint.build_progress = max(blueprint.build_progress, blueprint.required_work)
        blueprint.refresh_status()
        completed_building = None

        if blueprint.source == "tile":
            target_tile_def = TILE_DEFINITIONS.get(blueprint.tile_def_key)
            if target_tile_def is None:
                return False
            self._change_map_tile((blueprint.x, blueprint.y), target_tile_def)
        elif blueprint.source == "decoration":
            target_tile_def = DECORATION_ITEM_DEFINITIONS.get(blueprint.tile_def_key)
            if target_tile_def is None:
                return False
            self._change_map_tile((blueprint.x, blueprint.y), target_tile_def)
        elif blueprint.source == "building":
            chunk_x = blueprint.x // CHUNK_SIZE
            chunk_y = blueprint.y // CHUNK_SIZE
            local_x = blueprint.x % CHUNK_SIZE
            local_y = blueprint.y % CHUNK_SIZE
            chunk = None
            new_building = Building(
                local_x,
                local_y,
                blueprint.width,
                blueprint.height,
                building_type=blueprint.target_build,
                category=blueprint.category,
                global_chunk_x_start=chunk_x * CHUNK_SIZE,
                global_chunk_y_start=chunk_y * CHUNK_SIZE,
                variant_id=getattr(blueprint, "variant_id", None)
            )
            new_building.owner_id = getattr(blueprint, "owner_id", None)
            new_building.requester_id = getattr(blueprint, "requester_id", None)
            new_building.player_owned = bool(new_building.owner_id is not None and new_building.owner_id == getattr(getattr(self, "player", None), "id", None))
            new_building.settlement_id = getattr(blueprint, "settlement_id", None)
            new_building.region_id = getattr(blueprint, "region_id", None)
            new_building.territory_claim_id = getattr(blueprint, "territory_claim_id", None)
            completed_building = new_building
            self.buildings_by_id[new_building.id] = new_building
            if 0 <= chunk_x < self.chunk_width and 0 <= chunk_y < self.chunk_height:
                chunk = self.chunks[chunk_y][chunk_x]
                if getattr(chunk, "village", None):
                    chunk.village.add_building(new_building)
                    self.atlas.register_building(new_building)
                if chunk and chunk.tiles is not None:
                    self._draw_building(chunk.tiles, new_building, "wood_wall")
                    self.decorate_building_interior(new_building, chunk)
            self._seed_new_building_economy(new_building)
            village = getattr(chunk, "village", None) if chunk is not None else None
            self._activate_completed_building_owner(new_building)
            self._sync_building_employment_tasks(new_building)
            if village is not None:
                self._sync_village_employment_tasks(village)
        else:
            return False

        self._finalize_completed_blueprint_claim(blueprint, completed_building)

        for task in list(self.town_board.haul_tasks):
            if task.blueprint_id == blueprint.id:
                self._clear_player_claimed_task(task.id)
        self.town_board.remove_blueprint_tasks(blueprint.id)
        self.blueprints_by_id.pop(blueprint.id, None)
        self.blueprint_positions.pop((blueprint.x, blueprint.y), None)
        return True


    def _finalize_completed_blueprint_claim(self, blueprint: ConstructionBlueprint, building: Building | None) -> None:
        claim = self.land_claims_by_id.get(getattr(blueprint, "territory_claim_id", None))
        if claim is None:
            return
        if building is None:
            claim.active = False
            return
        claim.owner_type = "building"
        claim.owner_id = building.id
        claim.claimed_tiles |= claim.reserved_tiles
        claim.reserved_tiles.clear()
        claim.metadata["building_id"] = building.id
        building.territory_claim_id = claim.id
        target_type = self._building_claim_type(building.building_type, building.category)
        if target_type is not None:
            claim.claim_type = target_type
            padding = {"farm": 4, "ranch": 7, "hunting": 12, "logging": 10, "business": 1}.get(target_type, 1)
            extra_tiles = self._claim_rect_tiles(building.global_origin_x, building.global_origin_y, building.width, building.height, padding=padding)
            claim.claimed_tiles |= {
                tile for tile in extra_tiles
                if not self._claim_tiles_have_conflict({tile}, target_type, building.settlement_id) or tile in claim.claimed_tiles
            }
            claim.priority = {"farm": 7, "ranch": 6, "hunting": 5, "logging": 5, "business": 8}.get(target_type, claim.priority)
        else:
            claim.claim_type = "business" if "workplace" in building.category else "settlement_core"

    def _complete_one_blueprint_task(self, blueprint: ConstructionBlueprint, item_key: str, *, task_id: str | None = None) -> None:
        if task_id:
            task = self.town_board.get_task(task_id)
            if task and task.assigned_entity_id == self.player.id:
                self._clear_player_claimed_task(task.id)
            self.town_board.complete_task(task_id)
            return
        for task in self.town_board.haul_tasks:
            if task.blueprint_id == blueprint.id and task.item_key == item_key and task.status != "complete":
                if task.assigned_entity_id == self.player.id:
                    self._clear_player_claimed_task(task.id)
                task.status = "complete"
                task.assigned_entity_id = None
                return

    def _extract_actor_item_reference(self, actor, item_key: str) -> ItemReference | None:
        npc_inventory = getattr(getattr(actor, "economic", None), "npc_inventory", None)
        if hasattr(npc_inventory, "pop_item_reference"):
            return npc_inventory.pop_item_reference(item_key)

        actor_inventory = getattr(getattr(actor, "economic", None), "inventory", None)
        if not isinstance(actor_inventory, list):
            return None
        item_def = ITEM_DEFINITIONS.get(item_key, {})
        is_stackable = item_def.get("stackable", False)
        for index, item_instance in enumerate(list(actor_inventory)):
            if item_instance.get("key") != item_key:
                continue
            if is_stackable:
                item_instance["quantity"] = item_instance.get("quantity", 0) - 1
                if item_instance.get("quantity", 0) <= 0:
                    actor_inventory.pop(index)
            else:
                actor_inventory.pop(index)
            return ItemReference(
                item_key,
                quality=item_instance.get("quality", "Normal"),
                crafter_name=item_instance.get("crafter_name"),
                current_durability=item_instance.get("durability"),
            )
        return None

    def deposit_actor_material_into_blueprint(self, actor, blueprint: ConstructionBlueprint, item_key: str | None = None, *, task_id: str | None = None) -> bool:
        if blueprint is None:
            return False
        remaining = blueprint.remaining_materials()
        candidate_keys = [item_key] if item_key else list(remaining.keys())

        # Determine component_id from task
        component_id = None
        resolved_task_id = task_id
        if resolved_task_id is None and actor is self.player:
            for claimed_task_id in list(getattr(self.player.knowledge, "claimed_tasks", [])):
                claimed_task = self.town_board.get_task(claimed_task_id)
                if claimed_task and claimed_task.blueprint_id == blueprint.id and claimed_task.item_key in candidate_keys:
                    resolved_task_id = claimed_task.id
                    break

        if resolved_task_id:
            task = self.town_board.get_task(resolved_task_id)
            if task:
                component_id = getattr(task, "component_id", None)

        for candidate_key in candidate_keys:
            if not candidate_key or not blueprint.needs_material(candidate_key):
                continue
            item_reference = self._extract_actor_item_reference(actor, candidate_key)
            if item_reference is None:
                continue
            if not blueprint.deposit_item_reference(item_reference, component_id=component_id):
                self.drop_item_reference_on_map(item_reference, getattr(actor, "x", blueprint.x), getattr(actor, "y", blueprint.y))
                continue
            item_name = ITEM_DEFINITIONS.get(item_reference.key, {}).get("name", item_reference.key)

            target_x, target_y = blueprint.x, blueprint.y
            if component_id:
                for comp in blueprint.components:
                    if comp.id == component_id:
                        target_x, target_y = comp.x, comp.y
                        break

            self.visual_effects.append(FloatingTextEffect(target_x, target_y, f"-1 {item_name}", color=(255, 100, 100)))
            self._complete_one_blueprint_task(blueprint, item_reference.key, task_id=resolved_task_id)
            blueprint.refresh_status()
            self._refresh_blueprint_map_marker(blueprint)
            return True
        return False

    def player_attempt_read_book(self, book_item):
        """Handles the player's attempt to read a book."""
        if isinstance(book_item, dict):
            item_reference = book_item.get("item_reference")
            book_item_key = book_item.get("item_key", "")
        else:
            item_reference = None
            book_item_key = str(book_item or "")

        if item_reference is None and book_item_key and hasattr(self.player, "get_item_reference"):
            item_reference = self.player.get_item_reference(book_item_key)

        if isinstance(item_reference, ItemReference) and getattr(item_reference, "written_text", ""):
            self.add_message_to_chat_log(f"{item_reference.name}: {item_reference.written_text}")
            return

        if not book_item_key.startswith("book_"):
            self.add_message_to_chat_log("That is not a book.")
            return

        book_id = book_item_key.split("_", 1)[1]
        book = self.records.get_book(book_id)

        if not book:
            self.add_message_to_chat_log("You try to open the book, but the pages are stuck (Book data missing).")
            return

        # Change state to reading UI
        self.game_state = "BOOK_READING"
        self.book_reading_context["book_id"] = book.id
        self.book_reading_context["scroll_offset"] = 0

        # Knowledge Transfer
        if hasattr(book, 'referenced_event_ids') and book.referenced_event_ids:
            learned_count = self.knowledge_system.learn_from_book(
                self.player,
                book,
                book_item_key=book_item_key,
            )
            if learned_count > 0:
                self.add_message_to_chat_log(f"You learned about {learned_count} historical events from reading this book.")


    def player_attempt_loot_chest(self, x: int, y: int):
        """Handles the player interacting with a treasure chest."""
        target_tile = self.get_tile_at(x, y)
        if not target_tile or target_tile.name != "Treasure Chest":
            self.add_message_to_chat_log("There is no chest here.")
            return

        properties = target_tile.properties
        if properties.get("is_locked"):
            self.add_message_to_chat_log("The chest is locked. You need a lockpick.")
            # Lockpicking logic could go here
            return

        loot = properties.get("loot", [])
        if not loot:
            self.add_message_to_chat_log("The chest is empty.")
            return

        if isinstance(loot, Inventory):
            loot_item_names = [ITEM_DEFINITIONS.get(k, {}).get("name", k) for k, qty in loot.items() for _ in range(qty)]
        else:
            loot_item_names = [ITEM_DEFINITIONS.get(k, {}).get("name", k) for k in loot]
        self.add_message_to_chat_log(f"You open the chest and find: {', '.join(loot_item_names)}.")

        if isinstance(loot, Inventory):
            money_found = loot.pop("money", 0)
            if money_found:
                self.player.economic.money += money_found
                self.add_message_to_chat_log("You found some gold coins.")
            for item_key, quantity in list(loot.items()):
                self.player.add_item(item_key, quantity)
                del loot[item_key]
        else:
            for item_key in loot:
                if item_key == "money":
                    self.player.economic.money += random.randint(10, 50)
                    self.add_message_to_chat_log("You found some gold coins.")
                else:
                    self.player.add_item(item_key, 1)

        # Empty the chest
        target_tile.properties["loot"] = Inventory()
        target_tile.name = "Empty Chest"

        # Trigger an event
        self.log_event(
            event_type="chest_looted",
            description="The player plundered a dungeon chest.",
            subject_id=self.player.id,
            location=(x, y)
        )

    def player_attempt_mercenary_contract(self, npc: NPC):
        """Handles the player attempting to offer mercenary services to a warring village."""
        npc_display_name = self.get_entity_display_name(npc)
        village = self._get_village_for_npc(npc)
        if not village or not village.at_war_with:
            self.add_message_to_chat_log(f"{npc_display_name} tells you they have no need for mercenaries right now.")
            return

        enemy_village_id = list(village.at_war_with)[0] # Just grab the first one for simplicity

        # Check if already on a contract
        contract_id = f"merc_contract_{enemy_village_id}"
        if contract_id in self.player.knowledge.active_quests:
            self.add_message_to_chat_log(f"{npc_display_name} says: 'You already have a contract! Go defeat our enemies!'")
            return

        self.add_message_to_chat_log(f"{npc_display_name} looks you up and down.")

        if self.player.combat.max_hp < 20 and self.player.social.fame < 50:
            self.add_message_to_chat_log(f"{npc_display_name} scoffs. 'You don't look tough enough to help us in the war.'")
            return

        self.add_message_to_chat_log(f"{npc_display_name} says: 'We are at war. If you defeat 3 raiders or enemy guards, we will pay you 100 gold.'")

        # Add dynamic quest
        self.player.knowledge.active_quests[contract_id] = {
            "title": f"Mercenary: Defend the Village",
            "description": f"{npc.name} hired you to defeat enemies from the rival village.",
            "type": "kill",
            "target_faction_id": enemy_village_id,
            "target_count": 3,
            "progress": 0,
            "reward_money": 100,
            "giver_id": npc.id
        }
        self.add_message_to_chat_log(f"Quest accepted: Mercenary: Defend the Village.")

    def player_attempt_chop_tree(self, tree_x: int, tree_y: int):
        """Handles the player's attempt to chop a tree at the given world coordinates."""
        axe_item_key = "axe_stone"
        if not self.player.has_item(axe_item_key):
            self.add_message_to_chat_log("You need an axe to chop trees.")
            return

        target_tile = self.get_tile_at(tree_x, tree_y)

    def player_attempt_butcher(self, corpse_x: int, corpse_y: int):
        """Handles the player's attempt to butcher an animal corpse."""
        # Check for required tool
        knife_item_key = "knife_stone"
        if not self.player.has_item(knife_item_key):
            self.add_message_to_chat_log("You need a knife to butcher a corpse.")
            return

        target_tile = self.get_tile_at(corpse_x, corpse_y)

        if not (target_tile and target_tile.name == "Animal Corpse"):
            self.add_message_to_chat_log("There is nothing to butcher here.")
            return

        animal_type = target_tile.properties.get("animal_type")
        if not animal_type or animal_type not in ANIMAL_DEFINITIONS:
            self.add_message_to_chat_log("This corpse is unidentifiable.")
            # Turn it into bones anyway to clear it
            self._change_map_tile((corpse_x, corpse_y), DECORATION_ITEM_DEFINITIONS["bones"])
            return

        self.add_message_to_chat_log(f"You begin butchering the {animal_type}...")

        animal_def = ANIMAL_DEFINITIONS[animal_type]
        loot_table = animal_def.get("loot_drops", {})
        items_looted_messages = []

        for item_key, loot_info in loot_table.items():
            if random.random() < loot_info.get("chance", 0):
                quantity_info = loot_info["quantity"]
                if isinstance(quantity_info, list) and len(quantity_info) == 2:
                    quantity = random.randint(quantity_info[0], quantity_info[1])
                else:
                    quantity = int(quantity_info)

                if quantity > 0:
                    self.player.add_item(item_key, quantity)
                    item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
                    items_looted_messages.append(f"{quantity}x {item_name}")

        if items_looted_messages:
            self.add_message_to_chat_log(f"You recovered: {', '.join(items_looted_messages)}.")
        else:
            self.add_message_to_chat_log("You failed to recover anything useful from the carcass.")

        # Replace corpse with bones
        self._change_map_tile((corpse_x, corpse_y), DECORATION_ITEM_DEFINITIONS["bones"])

    def player_attempt_feed_animal(self, animal_npc: Animal):
        """Handles the player's attempt to feed an animal."""
        if not isinstance(animal_npc, Animal):
            self.add_message_to_chat_log("You can't feed that.")
            return

        animal_def = ANIMAL_DEFINITIONS.get(animal_npc.animal_type)
        animal_name = self.get_entity_display_name(animal_npc)
        if not animal_def or not animal_def.get("tameable"):
            self.add_message_to_chat_log(f"{animal_name} is not interested in being fed.")
            return

        food_item_key = animal_def.get("favorite_food")
        taming_difficulty = animal_def.get("taming_difficulty", 5)
        taming_chance = 1.0 / taming_difficulty

        if not self.player.has_item(food_item_key):
            food_name = ITEM_DEFINITIONS.get(food_item_key, {}).get("name", food_item_key)
            self.add_message_to_chat_log(f"You need a {food_name} to feed {animal_name}.")
            return

        self.player.remove_item(food_item_key, 1)
        food_name = ITEM_DEFINITIONS.get(food_item_key, {}).get("name", food_item_key)
        self.add_message_to_chat_log(f"You offer a {food_name} to {animal_name}.")

        if random.random() < taming_chance:
            animal_npc.is_tame = True
            animal_npc.owner = self.player
            self.add_message_to_chat_log(f"{animal_name} seems to trust you now!")
            # Change behavior to follow owner
            animal_npc.behavior = "Follow-Owner"
        else:
            self.add_message_to_chat_log(f"{animal_name} ate the {food_name} but is still wary of you.")

    def player_attempt_ride_animal(self, animal_npc: Animal):
        """Handles the player's attempt to ride an animal."""
        if self.player.state.is_riding:
            self.add_message_to_chat_log("You are already riding something.")
            return

        animal_name = self.get_entity_display_name(animal_npc)
        animal_def = ANIMAL_DEFINITIONS.get(animal_npc.animal_type)
        if not (animal_def and animal_def.get("rideable") and animal_npc.is_tame and animal_npc.owner == self.player):
            self.add_message_to_chat_log(f"You can't ride {animal_name}.")
            return

        self.player.state.is_riding = True
        self.player.state.riding_animal_id = animal_npc.id
        animal_npc.is_being_ridden = True
        animal_npc.rider_id = self.player.id

        # Move player to the animal's location
        self._update_entity_position(self.player, animal_npc.x, animal_npc.y)
        self._update_player_fov() # Update FOV from new position

        self.add_message_to_chat_log(f"You mount {animal_name}.")
        # The animal should stop its current path when mounted
        animal_npc.schedule.current_path = []
        animal_npc.schedule.current_destination_coords = None

    def player_attempt_shear(self, animal_npc: Animal):
        """Handles the player's attempt to shear a sheep."""
        if not isinstance(animal_npc, Animal) or "shearable" not in ANIMAL_DEFINITIONS.get(animal_npc.animal_type, {}):
            self.add_message_to_chat_log("You can't shear that.")
            return

        animal_name = self.get_entity_display_name(animal_npc)
        animal_def = ANIMAL_DEFINITIONS[animal_npc.animal_type]
        shearable_def = animal_def["shearable"]
        regrowth_days = shearable_def["regrowth_days"]
        days_since_shorn = (self.game_time - animal_npc.last_shorn_time) // DAY_LENGTH_TICKS

        if days_since_shorn < regrowth_days:
            self.add_message_to_chat_log(f"{animal_name} is not woolly enough to be shorn yet.")
            return

        # Check for shears tool
        if not self.player.has_item("shears"):
            self.add_message_to_chat_log("You need shears to shear a sheep.")
            return

        quantity_info = shearable_def["quantity"]
        if isinstance(quantity_info, list) and len(quantity_info) == 2:
            quantity = random.randint(quantity_info[0], quantity_info[1])
        else:
            quantity = int(quantity_info)

        if quantity > 0:
            item_yield_key = shearable_def["item_yield"]
            self.player.add_item(item_yield_key, quantity)
            item_name = ITEM_DEFINITIONS.get(item_yield_key, {}).get("name", item_yield_key)
            self.add_message_to_chat_log(f"You shear {animal_name} and get {quantity}x {item_name}.")
            animal_npc.last_shorn_time = self.game_time
        else:
            self.add_message_to_chat_log(f"You attempt to shear {animal_name}, but get no wool.")

    def player_attempt_dismount(self, animal_npc: Animal):
        """Handles the player's attempt to dismount an animal."""
        if not self.player.state.is_riding or self.player.state.riding_animal_id != animal_npc.id:
            self.add_message_to_chat_log("You are not riding this animal.")
            return

        # Find a safe spot to dismount to (adjacent and passable)
        dismount_x, dismount_y = self._find_best_adjacent_tile(animal_npc.x, animal_npc.y, self.player)

        if dismount_x is None:
            self.add_message_to_chat_log("There is no space to dismount here.")
            return

        # Update states
        self.player.state.is_riding = False
        self.player.state.riding_animal_id = None
        animal_npc.is_being_ridden = False
        animal_npc.rider_id = None

        # Move player
        self._update_entity_position(self.player, dismount_x, dismount_y)
        self._update_player_fov()

        self.add_message_to_chat_log(f"You dismount {self.get_entity_display_name(animal_npc)}.")

        if isinstance(target_tile, Tree) and target_tile.is_choppable:
            original_tree_type = target_tile.tree_type
            yielded_resources = target_tile.chop()

            if yielded_resources:
                self.add_message_to_chat_log(f"You chopped the {target_tile.original_name}!")
                self.emit_sound(tree_x, tree_y, "tree_fall", volume=15, source_entity_id=self.player.id)
                for resource_key, quantity in yielded_resources.items():
                    if resource_key in ITEM_DEFINITIONS:
                        self.player.add_item(resource_key, quantity)
                        self.add_message_to_chat_log(f"  + {quantity} {ITEM_DEFINITIONS[resource_key]['name']}")
                    else:
                        self.add_message_to_chat_log(f"  (Received undefined resource: {resource_key} x{quantity})")

                stump_key = target_tile.becomes_on_chop_key
                stump_def = TILE_DEFINITIONS.get(stump_key)
                if stump_def:
                    self._change_map_tile((tree_x, tree_y), stump_def, original_tree_type=original_tree_type)
                    new_stump_tile = self.get_tile_at(tree_x, tree_y)
                    if new_stump_tile:
                        new_stump_tile.regrowth_timer = 100

                # Handle axe degradation/breaking
                axe_def = ITEM_DEFINITIONS.get(axe_item_key)
                if axe_def and not axe_def.get("stackable", False):
                    degrade_chance = axe_def.get("properties", {}).get("durability_chance_to_degrade", 0.05) # 5% chance
                    if random.random() < degrade_chance:
                        axe_ref = self.player.get_item_reference(axe_item_key)
                        if axe_ref:
                            broke = axe_ref.degrade(1)
                            if broke:
                                self.player.remove_item(axe_item_key, 1)
                                self.add_message_to_chat_log(f"Your {axe_def['name']} broke during use!")
                                if "broken_tool_handle" in ITEM_DEFINITIONS:
                                    self.player.add_item("broken_tool_handle", 1)
                                    self.add_message_to_chat_log("You salvaged a broken tool handle.")
                            else:
                                self.add_message_to_chat_log(f"Your {axe_def['name']} shows some wear (Durability: {axe_ref.current_durability}/{axe_ref.max_durability}).")
            else:
                self.add_message_to_chat_log("Nothing was yielded from the tree.")
        elif isinstance(target_tile, Tree) and not target_tile.is_choppable:
            self.add_message_to_chat_log(f"This {target_tile.name} has already been chopped.")
        else:
            self.add_message_to_chat_log("There's nothing to chop there.")

    def player_attempt_plant_sapling(self, target_x: int, target_y: int):
        """Handles the player's attempt to plant a sapling."""
        if not self.player.has_item("sapling"):
            self.add_message_to_chat_log("You don't have any saplings to plant.")
            return

        target_tile = self.get_tile_at(target_x, target_y)
        if target_tile and target_tile.name in ["Plains", "Tilled Soil"]:
            self.player.remove_item("sapling", 1)
            sapling_def = TILE_DEFINITIONS["sapling"]
            self._change_map_tile((target_x, target_y), sapling_def)
            self.add_message_to_chat_log("You planted a sapling.")
        else:
            self.add_message_to_chat_log("You can't plant a sapling there.")

    def add_message_to_chat_log(self, message: str):
        self.chat_log.append(message)
        # Keep chat log to a reasonable size
        if len(self.chat_log) > 100:
            self.chat_log.pop(0)

    def player_attempt_sit(self, target_x: int, target_y: int):
        """Handles the player's attempt to sit on an object."""
        if self.player.state.is_sitting:
            # If already sitting and trying to interact with the same spot, stand up.
            if self.player.state.sitting_on_object_at == (target_x, target_y):
                self.player_attempt_stand_up()
            else:
                self.add_message_to_chat_log("You are already sitting. Stand up first ('E' or move).")
            return

        target_tile = self.get_tile_at(target_x, target_y)
        if target_tile and hasattr(target_tile, 'properties'):
            interaction_hint = target_tile.properties.get("interaction_hint")
            if interaction_hint == "sit":
                self.player.state.is_sitting = True
                self.player.state.sitting_on_object_at = (target_x, target_y)
                start_activity(
                    self.player,
                    "sitting",
                    30,
                    world=self,
                    location=(self.player.x, self.player.y),
                    anchor_coords=(target_x, target_y),
                    allows_conversation=True,
                    allows_observation=True,
                    allows_social_sharing=True,
                    interruptible=True,
                    metadata={"clear_sitting_on_complete": True},
                )
                self.add_message_to_chat_log(f"You sit down on the {target_tile.name}.")
            else:
                # self.add_message_to_chat_log("You can't sit there.") # Only message if no other interaction found by 'E'
                return False # Indicate sit failed, so 'E' can try other interactions like chop
        else:
            # self.add_message_to_chat_log("There's nothing to sit on there.")
            return False # Indicate sit failed
        return True # Indicate sit succeeded or an action related to sitting was taken

    def player_attempt_stand_up(self):
        """Handles the player standing up."""
        if self.player.state.is_sitting:
            self.player.state.is_sitting = False
            self.player.current_activity = None
            self.add_message_to_chat_log("You stand up.")
            self.player.state.sitting_on_object_at = None
        # No message if not sitting, or handled by caller

    def player_attempt_sleep(self, target_x: int, target_y: int):
        """Handles the player's attempt to sleep in a bed."""
        if self.player.state.is_sitting:
            self.add_message_to_chat_log("You should stand up before trying to sleep.")
            return False

        target_tile = self.get_tile_at(target_x, target_y)
        if target_tile and hasattr(target_tile, 'properties'):
            interaction_hint = target_tile.properties.get("interaction_hint")
            if interaction_hint == "sleep":
                self.add_message_to_chat_log(f"You lie down on the {target_tile.name} to rest.")
                self.player.state.is_sleeping = True # Brief state change

                # --- Advance Game Time (Simplified) ---
                # For a more complex simulation, this would involve a loop calling NPC updates.
                # For now, a simple jump. NPCs will "catch up" on their next schedule check.
                time_to_advance = DAY_LENGTH_TICKS // 3 # Sleep for 1/3 of a day (e.g., 8 hours)
                self.game_time += time_to_advance
                self.add_message_to_chat_log(f"Several hours pass...")

                # Optional: Player benefits
                heal_amount = self.player.combat.max_hp // 4 # Heal 25% of max HP
                self.player.combat.hp = min(self.player.combat.max_hp, self.player.combat.hp + heal_amount)
                if heal_amount > 0:
                     self.add_message_to_chat_log(f"You feel somewhat rested and heal for {heal_amount} HP.")
                else:
                    self.add_message_to_chat_log("You feel somewhat rested.")

                self.player.state.is_sleeping = False # Player wakes up
                return True # Sleep action was successful
            else:
                # Not a bed
                return False
        else:
            # No interactable tile
            return False

    def attempt_persuasion(self, npc_target: NPC, player_goal_text: str):
        """Handles the player's attempt to persuade an NPC."""
        if not npc_target:
            self.add_message_to_chat_log("No one specific to persuade.")
            return

        npc_display_name = self.get_entity_display_name(npc_target)
        player_rep = self.player.social.reputation
        prompt = LLM_PROMPTS["npc_persuasion_check"].format(
            npc_name=npc_target.name,
            npc_personality=npc_target.social.personality,
            npc_attitude=npc_target.attitude_to_player,
            player_social_skill=self.player.social.social_skill,
            player_criminal_points=player_rep.get(REP_CRIMINAL, 0),
            player_hero_points=player_rep.get(REP_HERO, 0),
            player_persuasion_goal_text=player_goal_text
        )

        response_str = self._call_llm(prompt)
        if not response_str:
            self.add_message_to_chat_log(f"{npc_display_name} doesn't seem to react to your attempt.")
            return

        try:
            response_json = json.loads(response_str)
            success = response_json.get("success", False)
            reaction_dialogue = response_json.get("reaction_dialogue", "...")
            new_attitude = response_json.get("new_attitude_to_player", npc_target.attitude_to_player)

            # Add NPC's reaction dialogue to chat UI history
            self.chat_ui_history.append((npc_display_name, reaction_dialogue))

            if new_attitude != npc_target.attitude_to_player:
                attitude_msg = f"({npc_display_name}'s attitude towards you is now '{new_attitude}')"
                self.chat_ui_history.append(("System", attitude_msg))
                # Also log to main game log for now, as attitude change is significant
                self.add_message_to_chat_log(attitude_msg)
                npc_target.attitude_to_player = new_attitude

            if success:
                success_msg = "(Your persuasion attempt seems successful!)"
                self.chat_ui_history.append(("System", success_msg))
                self.add_message_to_chat_log(success_msg) # Also log globally
                # Future: Implement actual game effect of success here
            else:
                failure_msg = "(Your persuasion attempt seems to have failed.)"
                self.chat_ui_history.append(("System", failure_msg))
                self.add_message_to_chat_log(failure_msg) # Also log globally
                # Future: Implement actual game effect of failure here

            # Ensure chat history doesn't exceed max and reset scroll
            if len(self.chat_ui_history) > self.chat_ui_max_history:
                self.chat_ui_history = self.chat_ui_history[-self.chat_ui_max_history:]
            self.chat_ui_scroll_offset = 0
        except json.JSONDecodeError:
            self.add_message_to_chat_log(f"{npc_display_name} gives a non-committal grunt. (LLM Format Error)")

    def _handle_npc_conversations(self):
        conversing_npcs = [npc for npc in self.village_npcs if npc.conversation_partner_id is not None]
        for npc in conversing_npcs:
            if npc.last_conversation_time + 10 < self.game_time:
                partner = next((p for p in self.village_npcs if p.id == npc.conversation_partner_id), None)
                if partner:
                    self._continue_npc_conversation(npc, partner)
                else:
                    npc.conversation_partner_id = None


    def _handle_ambient_activity_interactions(self):
        """Emit occasional lightweight dialogue around conversational activities."""
        if getattr(self, "game_state", "PLAYING") != "PLAYING":
            return
        if getattr(self, "chat_ui_active", False):
            return

        update_social_scenes(self)
        scene = choose_strongest_social_scene(self)
        pair = choose_scene_interaction_pair(scene, self) if scene is not None else None
        if pair is None:
            pair = choose_ambient_conversation_pair(self)
            if pair is None:
                return
            scene = find_scene_for_pair(self, pair[0], pair[1])
        speaker, listener = pair
        activity = getattr(speaker, "current_activity", None)

        shared_fact = choose_shareable_fact(speaker, listener, self)
        dialogue_line = None
        line = ""
        if shared_fact is not None:
            shared_line = render_history_fact_dialogue_line(speaker, listener, self, shared_fact, scene=scene)
            topic = build_dialogue_topic_from_fact(shared_fact, self)
            if (
                shared_line is not None
                and topic is not None
                and share_known_fact(speaker, listener, shared_fact, source_type="told", current_tick=int(getattr(self, "game_time", 0)))
            ):
                dialogue_line = shared_line
                line = shared_line.text
                remember_dialogue_topic_spoken(speaker, topic, self)
                mark_share_cooldowns(speaker, listener, self)
                record_scene_topic(scene, topic, self)
                share_fact_with_scene_overhearers(self, scene, speaker, listener, shared_fact)

        if not line:
            lines = get_contextual_dialogue_lines(speaker, listener, self, limit=1, scene=scene)
            if not lines:
                return
            dialogue_line = lines[0]
            line = dialogue_line.text

        mark_ambient_conversation_started(speaker, listener, self)
        speaker.ambient_activity_next_talk_tick = int(getattr(self, "game_time", 0)) + 60
        listener.ambient_activity_next_talk_tick = int(getattr(self, "game_time", 0)) + 30
        speaker.conversation_cooldown = max(getattr(speaker, "conversation_cooldown", 0), 20)
        listener.conversation_cooldown = max(getattr(listener, "conversation_cooldown", 0), 20)
        publish_dialogue = getattr(self, "_publish_ambient_dialogue_line", None)
        if callable(publish_dialogue):
            publish_dialogue(speaker, listener, dialogue_line, scene=scene, activity=activity)
        else:
            World._publish_ambient_dialogue_line(self, speaker, listener, dialogue_line, scene=scene, activity=activity)

    def _continue_npc_conversation(self, speaker, listener):
        group_participants = [speaker, listener]
        for p in self.village_npcs:
            if p.id in (speaker.id, listener.id) or p.physical.is_dead:
                continue

            if getattr(p.combat, "is_hostile_to_player", False) or getattr(p, "is_frightened", False):
                continue
            if p.schedule.current_task in {"fleeing_from_player", "avoiding_social_threat", "combat_action_flee_from_player", "attacking_player", "going_to_report_crime", "seeking_healer", "resting_in_bed"}:
                continue

            if p.conversation_partner_id in (speaker.id, listener.id):
                group_participants.append(p)
            elif abs(p.x - speaker.x) + abs(p.y - speaker.y) <= 3:
                is_following = getattr(getattr(p, "social", None), "follow_target_id", None) in (speaker.id, listener.id)
                if is_following or (p.schedule.current_task in {TaskType.IDLE, "gathering_social", "socializing_at_focal_point"} and random.random() < 0.2):
                    group_participants.append(p)
            if len(group_participants) >= 4:
                break

        other_participants = [p for p in group_participants if p.id != speaker.id]
        scene = find_scene_for_pair(self, speaker, listener)

        profile = self.evaluate_conversation_foundation(speaker, listener, max_distance=6)
        if not profile.can_start:
            for p in group_participants:
                if p.conversation_partner_id == speaker.id or p.conversation_partner_id == listener.id or p.id in (speaker.id, listener.id):
                    p.conversation_partner_id = None
                    p.current_conversation = []
            return

        if len(speaker.current_conversation) >= 6:
            self._publish_ambient_text(speaker, listener, "We should get back to it.", scene=scene, source_type="activity")
            for p in group_participants:
                if p.conversation_partner_id == speaker.id or p.conversation_partner_id == listener.id or p.id in (speaker.id, listener.id):
                    p.conversation_partner_id = None
                    p.current_conversation = []
                    p.conversation_cooldown = random.randint(100, 200)
            return

        shared_fact = choose_shareable_fact(speaker, listener, self)
        if shared_fact is not None:
            shared_line = render_history_fact_dialogue_line(speaker, listener, self, shared_fact, scene=scene)
            topic = build_dialogue_topic_from_fact(shared_fact, self)
            if (
                shared_line is not None
                and topic is not None
                and share_known_fact(speaker, listener, shared_fact, source_type="told", current_tick=int(getattr(self, "game_time", 0)))
            ):
                spoken_line = shared_line.text
                remember_dialogue_topic_spoken(speaker, topic, self)
                mark_share_cooldowns(speaker, listener, self)
                record_scene_topic(scene, topic, self)
                self._publish_ambient_dialogue_line(speaker, listener, shared_line, scene=scene)
                line_formatted = f"{speaker.name}: {spoken_line}"
                speaker.current_conversation.append(line_formatted)
                for p in other_participants:
                    p.current_conversation = list(speaker.current_conversation)
                    self.propagate_npc_harmful_incident_gossip(speaker, p)
                speaker.last_conversation_time = self.game_time
                listener.last_conversation_time = self.game_time
                return

        event_summary = "the weather"
        if speaker.knowledge.known_events:
            event = random.choice(list(speaker.knowledge.known_events.values()))
            event_summary = event.description

        history = "\n".join(speaker.current_conversation)
        task_key = ("npc_conversation", speaker.id, listener.id)
        if not self._is_npc_llm_relevant_to_player(speaker, listener):
            self._cancel_background_llm_task(task_key)
            spoken_line, goal = self._fallback_npc_social_line(speaker, listener, group_listeners=other_participants, max_distance=6)

            self._publish_ambient_text(
                speaker,
                listener,
                spoken_line,
                scene=scene,
                source_type="small_talk",
            )
            line_formatted = f"{speaker.name}: {spoken_line}"
            speaker.current_conversation.append(line_formatted)
            for p in other_participants:
                p.current_conversation = list(speaker.current_conversation)
                self.propagate_npc_harmful_incident_gossip(speaker, p)

            self._handle_npc_social_goal(speaker, listener, goal)

            speaker.last_conversation_time = self.game_time
            if other_participants:
                speaker.conversation_partner_id = random.choice(other_participants).id
            else:
                speaker.conversation_partner_id = listener.id

            for p in other_participants:
                p.last_conversation_time = self.game_time
                possible_targets = [g for g in group_participants if g.id != p.id]
                if possible_targets and random.random() < 0.5:
                    p.conversation_partner_id = random.choice(possible_targets).id
                else:
                    p.conversation_partner_id = speaker.id
            return

        dialogue = self._poll_background_llm_task(task_key)
        if dialogue is BACKGROUND_LLM_PENDING:
            return
        if dialogue is not None:
            spoken_line = ""
            goal = "continue_conversation"
            if dialogue:
                response_json = self._parse_llm_json_object(dialogue)
                if response_json is not None:
                    spoken_line = response_json.get("response", "").strip()
                    goal = self._coerce_dialogue_goal_by_profile(profile, response_json.get("goal", "continue_conversation"))
                else:
                    spoken_line = dialogue.strip()

            if not spoken_line:
                spoken_line, goal = self._fallback_npc_social_line(speaker, listener, group_listeners=other_participants, max_distance=6)

            self._publish_ambient_text(
                speaker,
                listener,
                spoken_line,
                scene=scene,
                source_type="small_talk",
            )
            line_formatted = f"{speaker.name}: {spoken_line}"
            speaker.current_conversation.append(line_formatted)
            for p in other_participants:
                p.current_conversation = list(speaker.current_conversation)
                self.propagate_npc_harmful_incident_gossip(speaker, p)

            self._handle_npc_social_goal(speaker, listener, goal)

            speaker.last_conversation_time = self.game_time
            if other_participants:
                speaker.conversation_partner_id = random.choice(other_participants).id
            else:
                speaker.conversation_partner_id = listener.id

            for p in other_participants:
                p.last_conversation_time = self.game_time
                possible_targets = [g for g in group_participants if g.id != p.id]
                if possible_targets and random.random() < 0.5:
                    p.conversation_partner_id = random.choice(possible_targets).id
                else:
                    p.conversation_partner_id = speaker.id
            return

        prompt = LLM_PROMPTS["npc_npc_conversation"].format(
            speaker_name=speaker.name,
            speaker_personality=speaker.social.personality,
            speaker_attitude_to_listener=speaker.social.relationships.get(listener.id, 50),
            listener_name=listener.name,
            listener_personality=listener.social.personality,
            listener_relationship_to_speaker=listener.social.relationships.get(speaker.id, 50),
            speaker_current_task=speaker.schedule.current_task,
            listener_current_task=listener.schedule.current_task,
            event_summary=event_summary,
            conversation_history=history
        )
        self._submit_background_llm_task(task_key, prompt)

    def _start_npc_socialization(self, npc: NPC):
        if npc.conversation_cooldown > 0:
            npc.conversation_cooldown -= 1
            return

        potential_partners = [
            p for p in self.village_npcs
            if p.id != npc.id and not p.physical.is_dead and abs(npc.x - p.x) + abs(npc.y - p.y) < 10
               and p.conversation_partner_id is None and p.conversation_cooldown == 0
        ]
        conversation_profiles = {
            partner.id: self.evaluate_conversation_foundation(npc, partner)
            for partner in potential_partners
        }
        potential_partners = [partner for partner in potential_partners if conversation_profiles[partner.id].can_start]

        if not potential_partners:
            return

        weighted_partners = []
        for partner in potential_partners:
            profile = conversation_profiles[partner.id]
            weight = max(1, int(round(profile.openness * 4)))
            if profile.stance == "respectful":
                weight += 1
            weighted_partners.extend([partner] * weight)
        partner = random.choice(weighted_partners or potential_partners)
        npc.conversation_partner_id = partner.id
        partner.conversation_partner_id = npc.id
        npc.last_conversation_time = self.game_time
        partner.last_conversation_time = self.game_time

        partner_profile = conversation_profiles.get(partner.id) or self.evaluate_conversation_foundation(npc, partner)
        if partner_profile.stance == "respectful" and self._can_player_overhear(npc):
            self.add_message_to_chat_log(
                f"{self.get_entity_display_name(npc)} *nods respectfully* to {self.get_entity_display_name(partner)}."
            )

        if self._can_player_overhear(npc):
            self.add_message_to_chat_log(
                f"You overhear {self.get_entity_display_name(npc)} and {self.get_entity_display_name(partner)} start talking."
            )

    def player_attempt_attack(self, target_npc: NPC):
        if not target_npc:
            self.add_message_to_chat_log("No target selected for attack.")
            return

        target_name = self.get_entity_display_name(target_npc)
        if target_npc.is_dead:
            self.add_message_to_chat_log(f"{target_name} is already defeated.")
            return

        player_weapon_name = "Fists"
        if self.player.has_item("axe_stone"):
            player_weapon_name = ITEM_DEFINITIONS["axe_stone"]["name"]

        player_melee_skill = getattr(self.player, 'melee_skill', 5)

        # Determine NPC toughness description based on their defense bonus
        npc_toughness_desc = "unarmored"
        if target_npc.defense_bonus > 8:
            npc_toughness_desc = "heavily armored"
        elif target_npc.defense_bonus > 4:
            npc_toughness_desc = "armored"
        elif target_npc.defense_bonus > 0:
            npc_toughness_desc = "lightly armored"

        prompt = LLM_PROMPTS["adjudicate_player_attack"].format(
            player_weapon_name=player_weapon_name,
            player_melee_skill=player_melee_skill,
            npc_name=target_npc.name,
            npc_toughness=npc_toughness_desc
        )

        response_str = self._call_llm(prompt)
        inflicted_damage = 0
        attack_landed = False

        if not response_str:
            self.add_message_to_chat_log("Your attack seems to have no effect (LLM Comms Error).")
            if not target_npc.combat.is_hostile_to_player and not target_npc.is_dead:
                target_npc.combat.is_hostile_to_player = True
                self.add_message_to_chat_log(f"{target_name} becomes hostile due to your aggression!")
            return

        try:
            response_json = json.loads(response_str)
            hit = response_json.get("hit", False)
            damage_dealt = int(response_json.get("damage_dealt", 0))
            narrative = response_json.get("narrative_feedback", "The confrontation is tense.")

            self.add_message_to_chat_log(narrative)
            self.emit_sound(self.player.x, self.player.y, "combat_attack", volume=10, source_entity_id=self.player.id) # Emit attack sound

            if hit and damage_dealt > 0:
                attack_landed = True
                self.log_event(
                    event_type="combat_attack",
                    description="{subject} attacked {target}.",
                    subject_id=self.player.id,
                    target_id=target_npc.id,
                    location=(self.player.x, self.player.y)
                )
                hp_before = target_npc.combat.hp
                statuses_before = set(target_npc.physical.status_effects)
                target_npc.take_damage(damage_dealt, self)
                inflicted_damage = max(0, hp_before - target_npc.combat.hp)
                if hasattr(self.player, "gain_skill_experience"):
                    self.player.gain_skill_experience("melee", max(1, inflicted_damage), default_level=5)
                new_statuses = set(target_npc.physical.status_effects) - statuses_before
                self._broadcast_combat_memory(self.player, target_npc, player_weapon_name, inflicted_damage, new_statuses)
                if target_npc.is_dead:
                    self.handle_npc_death(target_npc, killer_id=self.player.id)
            elif hit and damage_dealt <= 0: # A hit that does no damage
                self.add_message_to_chat_log(f"Your attack hits but glances off {target_name} harmlessly!")

            if not target_npc.combat.is_hostile_to_player and not target_npc.is_dead:
                 target_npc.combat.is_hostile_to_player = True
                 self.add_message_to_chat_log(f"{target_name} becomes hostile!")
            if not target_npc.is_dead:
                current_day = self.game_time // DAY_LENGTH_TICKS
                target_npc.add_grudge(
                    self.player.id,
                    "attacked_me",
                    severity=85,
                    current_day=current_day,
                    decay_days=12,
                )

        except json.JSONDecodeError:
            self.add_message_to_chat_log(f"The outcome of your attack is unclear. (LLM Format Error: {response_str})")
            self.emit_sound(self.player.x, self.player.y, "combat_attack", volume=8, source_entity_id=self.player.id) # Still emit
            if not target_npc.combat.is_hostile_to_player and not target_npc.is_dead:
                target_npc.combat.is_hostile_to_player = True; self.add_message_to_chat_log(f"{target_name} is angered by your confusing actions!")
        except ValueError:
            self.add_message_to_chat_log(f"The LLM provided an invalid damage amount: {response_json.get('damage_dealt') if 'response_json' in locals() else 'Unknown'}")
            self.emit_sound(self.player.x, self.player.y, "combat_attack", volume=8, source_entity_id=self.player.id) # Still emit
            if not target_npc.combat.is_hostile_to_player and not target_npc.is_dead:
                target_npc.combat.is_hostile_to_player = True; self.add_message_to_chat_log(f"{target_name} is angered by your confusing actions!")

        # --- Witness Handling ---
        # After any attack attempt, check for witnesses to the crime of assault.
        witnesses = self._get_witnesses_to_action(target_npc.x, target_npc.y, "assault")
        non_victim_witnesses = [w for w in witnesses if w.id != target_npc.id]
        if attack_landed and inflicted_damage > 0:
            incident = create_harmful_incident(
                self,
                attacker_id=self.player.id,
                target_id=target_npc.id,
                location=(target_npc.x, target_npc.y),
                severity=inflicted_damage,
                target_survived=not target_npc.is_dead,
                witness_ids=[w.id for w in non_victim_witnesses],
            )
            record_incident_attribution(
                self.player,
                incident,
                attacker_id=self.player.id,
                confidence=1.0,
                basis="actor_self",
            )
            if not target_npc.is_dead:
                record_incident_attribution(
                    target_npc,
                    incident,
                    attacker_id=self.player.id,
                    confidence=1.0,
                    basis="victim_survived",
                )
            for witness in non_victim_witnesses:
                record_incident_attribution(
                    witness,
                    incident,
                    attacker_id=self.player.id,
                    confidence=0.95,
                    basis="direct_witness",
                )
        if witnesses:
            self.player.adjust_reputation(REP_CRIMINAL, 10) # 10 criminal points for assault
            for witness in witnesses:
                # The victim won't also be a witness in the traditional sense, their reaction is hostility.
                if witness.id != target_npc.id:
                    self._handle_witness_reaction(witness, "assault", self.player, victim=target_npc)

    def _remove_npc_from_world(self, npc: NPC, reason="departed"):
        """
        Removes an NPC from the world lists (village_npcs, npcs, buildings) without killing them.
        Used for emigration or cleanup.
        """
        if npc in self.village_npcs:
            self.village_npcs.remove(npc)
        if npc in self.npcs:
            self.npcs.remove(npc)

        for building_obj in self.buildings_by_id.values():
            if npc in building_obj.residents:
                building_obj.residents.remove(npc)
            if npc in building_obj.occupants:
                building_obj.occupants.remove(npc)

        # Clear NPC from UI states if they were targeted
        if self.interaction_context["active"] and npc in self.interaction_context["target_entities"]:
            self.interaction_context["active"] = False
        self._remove_entity_position(npc)
        if self.chat_ui_target_npc == npc:
            self.request_close_dialogue(target_npc=npc)
        if self.trade_ui_npc_target == npc:
            self.request_close_trade(target_npc=npc)
        if self.last_talked_to_npc == npc: self.last_talked_to_npc = None

        # self.add_message_to_chat_log(f"Debug: {npc.name} has {reason}.")

    def handle_npc_death(self, dead_npc: NPC, killer_id: int | None = None):
        if isinstance(dead_npc, Animal) and hasattr(self, "ecology"):
            self.ecology.note_animal_death(dead_npc)
        dead_npc_name = self.get_entity_display_name(dead_npc)
        death_message = self.text.entity_died(dead_npc) if hasattr(self, "text") else f"{dead_npc_name} died."
        self.add_message_to_chat_log(death_message)

        if killer_id == self.player.id:
            for quest_id, quest_data in self.player.knowledge.active_quests.items():
                if quest_data.get("type") == "kill" and "target_faction_id" in quest_data:
                    if getattr(dead_npc, "faction_id", getattr(dead_npc, "enemy_faction_id", None)) == quest_data["target_faction_id"]:
                        quest_data["progress"] += 1
                        self.add_message_to_chat_log(f"Quest Progress: Defeated target ({quest_data['progress']}/{quest_data['target_count']})")


        death_event = self.record_death_event(
            deceased=dead_npc,
            description="{subject} was killed by {target}.",
            killer_id=killer_id,
            location=(dead_npc.x, dead_npc.y),
            cause_of_death="killed",
        )

        if killer_id is not None and not isinstance(dead_npc, Animal):
            killer = self.get_entity_by_id(killer_id)
            if killer is not None:
                killer_memory = self.create_memory_event(
                    event_type="murder",
                    subject_id=killer.id,
                    target_id=dead_npc.id,
                    importance_score=95,
                    headline=f"{getattr(killer, 'name', 'Someone')} killed {dead_npc.name}.",
                    location=(dead_npc.x, dead_npc.y),
                    metadata={"death_event_id": death_event.id},
                )
                self.record_memory_event(killer, killer_memory)

            victim_memory = self.create_memory_event(
                event_type="murder",
                subject_id=self.resolve_visible_subject_id(dead_npc, killer),
                target_id=dead_npc.id,
                importance_score=95,
                headline=f"{self.get_visible_entity_name(dead_npc, killer, unknown_name='Someone')} killed {dead_npc.name}.",
                location=(dead_npc.x, dead_npc.y),
                metadata={"death_event_id": death_event.id},
            )
            self.record_memory_event(dead_npc, victim_memory)

            for witness in self._get_witnesses_to_action(dead_npc.x, dead_npc.y, "murder"):
                if witness.id not in {killer_id, dead_npc.id}:
                    witness_memory = self.create_memory_event(
                        event_type="murder",
                        subject_id=self.resolve_visible_subject_id(witness, killer),
                        target_id=dead_npc.id,
                        importance_score=95,
                        headline=f"{self.get_visible_entity_name(witness, killer, unknown_name='Someone')} killed {dead_npc.name}.",
                        location=(dead_npc.x, dead_npc.y),
                        metadata={"death_event_id": death_event.id},
                    )
                    self.record_memory_event(witness, witness_memory)

            if getattr(self.player, "id", None) not in {killer_id, dead_npc.id}:
                player_saw_death = False
                if 0 <= dead_npc.x < WORLD_WIDTH and 0 <= dead_npc.y < WORLD_HEIGHT:
                    try:
                        player_saw_death = bool(self.player_fov_map[dead_npc.y, dead_npc.x])
                    except Exception:
                        player_saw_death = False
                if player_saw_death:
                    player_memory = self.create_memory_event(
                        event_type="murder",
                        subject_id=self.resolve_visible_subject_id(self.player, killer),
                        target_id=dead_npc.id,
                        importance_score=95,
                        headline=f"{self.get_visible_entity_name(self.player, killer, unknown_name='Someone')} killed {dead_npc.name}.",
                        location=(dead_npc.x, dead_npc.y),
                        metadata={"death_event_id": death_event.id},
                    )
                    self.record_memory_event(self.player, player_memory)

        # Handle Reputation impact if the death was witnessed (public knowledge)
        if death_event.public_knowledge and killer_id:
            killer = self.get_entity_by_id(killer_id)
            if killer:
                # Fame for killing monsters
                if isinstance(dead_npc, DireWolf) or (isinstance(dead_npc, Animal) and dead_npc.animal_type == "dire_wolf"):
                    killer.social.fame += 20
                    if isinstance(killer, Player):
                        self.add_message_to_chat_log(f"You gain fame for slaying a dangerous beast!")
                    else:
                        self.add_message_to_chat_log(f"{self.get_entity_display_name(killer)} gains fame for slaying a beast!")

                # Infamy for murder (killing non-combatants/civilians)
                # Simplified check: if victim was not a creature/monster and not hostile
                elif not isinstance(dead_npc, Animal) and dead_npc.economic.profession != "Creature":
                     # For player killer, check if victim was hostile
                     is_murder = True
                     if killer.id == self.player.id and dead_npc.combat.is_hostile_to_player:
                         is_murder = False # Self defense / combat

                     if is_murder:
                         killer.social.infamy += 20
                         if isinstance(killer, Player):
                             self.add_message_to_chat_log("Your infamy increases for this public act of violence.")
                         else:
                             self.add_message_to_chat_log(f"{self.get_entity_display_name(killer)}'s infamy increases.")

        npc_chunk_x, npc_chunk_y = dead_npc.x // CHUNK_SIZE, dead_npc.y // CHUNK_SIZE
        npc_local_x, npc_local_y = dead_npc.x % CHUNK_SIZE, dead_npc.y % CHUNK_SIZE

        corpse_placed_on_map = False
        if 0 <= npc_chunk_x < self.chunk_width and 0 <= npc_chunk_y < self.chunk_height:
            chunk = self.chunks[npc_chunk_y][npc_chunk_x]
            if chunk and chunk.tiles:
                corpse_key = "corpse_animal" if isinstance(dead_npc, Animal) else "corpse_humanoid"
                corpse_def = DECORATION_ITEM_DEFINITIONS.get(corpse_key)
                if corpse_def:
                    # Create a copy of the properties to avoid modifying the template
                    new_properties = corpse_def.get("properties", {}).copy()

                    # If it's an animal, store its type in the corpse's properties
                    if isinstance(dead_npc, Animal) and hasattr(dead_npc, 'animal_type'):
                        new_properties['animal_type'] = dead_npc.animal_type

                    chunk.tiles[npc_local_y][npc_local_x] = Tile(
                        char=corpse_def["char"], color=corpse_def["color"],
                        passable=corpse_def["passable"], name=corpse_def["name"],
                        properties=new_properties
                    )
                    corpse_placed_on_map = True

        if not corpse_placed_on_map: self.add_message_to_chat_log(f"(Could not place corpse for {dead_npc_name} on map)")

        self._transfer_building_inheritance(dead_npc)
        self._cleanup_family_ties_after_death(dead_npc)
        self._remove_npc_from_world(dead_npc, reason="died")

        # --- Item Drops ---
        items_dropped_messages = []
        # Animal loot is now handled by butchering, so we only handle humanoid drops here.
        if not isinstance(dead_npc, Animal):
            # Drop items from inventory
            for item_key, quantity in list(dead_npc.economic.npc_inventory.items()):
                if item_key == "money": continue
                if quantity > 0:
                    moved_quantity = self._move_item_between_inventories(
                        dead_npc.economic.npc_inventory,
                        self.items_on_map.setdefault((dead_npc.x, dead_npc.y), Inventory()),
                        item_key,
                        quantity,
                    )
                    item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
                    items_dropped_messages.append(f"{moved_quantity}x {item_name}")

            # Chance to drop equipped items
            equipped_to_check = [
                ("weapon", dead_npc.get_equipped_item_reference("weapon")),
                ("body", dead_npc.get_equipped_item_reference("body")),
                ("head", dead_npc.get_equipped_item_reference("head")),
            ]
            for slot_name, equipped_item in equipped_to_check:
                if equipped_item:
                    item_def = ITEM_DEFINITIONS.get(equipped_item.key, {})
                    base_drop_chance = 0.75
                    value = item_def.get("value", 0)
                    # Reduce drop chance for more valuable items
                    if value > 50:
                        drop_chance = base_drop_chance - 0.25
                    elif value > 25:
                        drop_chance = base_drop_chance - 0.1
                    else:
                        drop_chance = base_drop_chance

                    if random.random() < drop_chance:
                        if dead_npc.unequip_item(slot_name):
                            dead_npc.economic.npc_inventory.transfer_item_reference(
                                self.items_on_map.setdefault((dead_npc.x, dead_npc.y), Inventory()),
                                equipped_item,
                            )
                        elif dead_npc.economic.npc_inventory.has_item_reference(equipped_item):
                            dead_npc.economic.npc_inventory.transfer_item_reference(
                                self.items_on_map.setdefault((dead_npc.x, dead_npc.y), Inventory()),
                                equipped_item,
                            )
                        item_name = item_def.get("name", equipped_item.key)
                        items_dropped_messages.append(f"1x {item_name} (equipped)")

            if items_dropped_messages:
                self.add_message_to_chat_log(f"{dead_npc_name} dropped: {', '.join(items_dropped_messages)}.")
            else:
                self.add_message_to_chat_log(f"{dead_npc_name} dropped nothing of note.")

        # After death, emit a sound if appropriate (e.g. a shout or thud)
        # For now, let's assume death itself is not a loud sound unless it's a dramatic one.
        # self.emit_sound(dead_npc.x, dead_npc.y, "npc_death_cry", volume=8, source_entity_id=dead_npc.id)


    def player_attempt_pick_lock(self, target_x: int, target_y: int) -> bool:
        """Handles player's attempt to pick a lock."""
        if not self.player.has_item("lockpick"):
            self.add_message_to_chat_log("You don't have any lockpicks.")
            return False

        target_tile = self.get_tile_at(target_x, target_y)
        if not (target_tile and target_tile.properties.get("is_lockable")):
            self.add_message_to_chat_log("There's nothing to pick here.")
            return False

        if not target_tile.properties.get("is_locked"):
            self.add_message_to_chat_log("It's already unlocked.")
            return True # Considered "handled" as there's no lock to pick

        lock_difficulty = target_tile.properties.get("lock_difficulty", 5)

        prompt = LLM_PROMPTS["action_lockpick_check"].format(
            player_lockpicking_skill=self.player.knowledge.lockpicking_skill,
            lock_difficulty=lock_difficulty
        )
        response_str = self._call_llm(prompt)

        if not response_str:
            self.add_message_to_chat_log("You try the lock, but nothing happens. (LLM Error)")
            return True # Attempt was made

        try:
            response_json = json.loads(response_str)
            success = response_json.get("success", False)
            narrative = response_json.get("narrative_feedback", "You try the lock...")
            pick_broken = response_json.get("lockpick_broken", False)

            self.add_message_to_chat_log(narrative)

            if pick_broken:
                self.player.remove_item("lockpick", 1)
                self.add_message_to_chat_log("Your lockpick broke!")
                if not self.player.has_item("lockpick"):
                    self.add_message_to_chat_log("That was your last lockpick.")

            if success:
                target_tile.properties["is_locked"] = False

                # --- Jail Escape Logic ---
                if self.player.state.is_jailed and (target_x, target_y) == self.player.state.jail_cell_coords:
                    self.add_message_to_chat_log("With a final click, the cell door swings open. You're free!")
                    self.player.state.is_jailed = False
                    self.player.state.jail_cell_coords = None
                    # The door is now unlocked and will become passable after the toggle action.
                    return True # Escape successful


                containing_building = self._get_building_by_tile_coords(target_x, target_y)
                if containing_building and containing_building.building_inventory:
                    loot_messages = []
                    money_found = containing_building.building_inventory.pop("money", 0)
                    if money_found:
                        self.player.economic.money += money_found
                        loot_messages.append(f"{money_found} money")

                    for item_key, qty in list(containing_building.building_inventory.items()):
                        if qty <= 0:
                            del containing_building.building_inventory[item_key]
                            continue
                        self.player.add_item(item_key, qty)
                        del containing_building.building_inventory[item_key]
                        item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
                        loot_messages.append(f"{qty}x {item_name}")

                    if loot_messages:
                        self.add_message_to_chat_log(f"You loot the {target_tile.name}: {', '.join(loot_messages)}.")
                    else:
                        self.add_message_to_chat_log(f"The {target_tile.name} is empty.")
                else:
                    self.add_message_to_chat_log(f"The {target_tile.name} is empty.")

            # --- Witness Handling ---
            witnesses = self._get_witnesses_to_action(target_x, target_y, "lockpicking")
            if witnesses:
                self.player.adjust_reputation(REP_CRIMINAL, 5) # 5 criminal points for lockpicking
                for witness in witnesses:
                    self._handle_witness_reaction(witness, "lockpicking", self.player)

            return True # Lockpicking attempt was made
        except json.JSONDecodeError:
            self.add_message_to_chat_log("Your attempt to pick the lock yields an odd result. (LLM Format Error)")
            return True

    def _get_building_by_tile_coords(self, world_x: int, world_y: int) -> Building | None:
        """Helper to find which building a specific world tile is part of, if any."""
        # This could be slow if called frequently.
        # For now, it iterates all known buildings.
        for building_id, building_obj in self.buildings_by_id.items():
            # Check if (world_x, world_y) is within this building's footprint
            # Building stores its origin global_origin_x/y and dimensions width/height
            if (building_obj.global_origin_x <= world_x < building_obj.global_origin_x + building_obj.width and
                building_obj.global_origin_y <= world_y < building_obj.global_origin_y + building_obj.height):
                return building_obj
        return None

    def npc_toggle_door(self, requesting_npc: NPC, door_x: int, door_y: int) -> bool:
        """Handles an NPC's attempt to open or close a door. NPCs currently only open doors."""
        target_tile = self.get_tile_at(door_x, door_y)

        if target_tile and target_tile.properties.get("is_door"):
            is_open = target_tile.properties.get("is_open", False)

            if is_open: # NPCs currently don't try to close doors they pass through
                return True # Door is already open, action considered successful for pathing

            # Door is closed, NPC tries to open it
            new_state_key = target_tile.properties.get("opens_to")
            action_message = f"{requesting_npc.name} opens the {target_tile.name}."

            if new_state_key and new_state_key in DECORATION_ITEM_DEFINITIONS:
                new_door_def = DECORATION_ITEM_DEFINITIONS[new_state_key]

                chunk_x, chunk_y = door_x // CHUNK_SIZE, door_y // CHUNK_SIZE
                local_x, local_y = door_x % CHUNK_SIZE, door_y % CHUNK_SIZE

                self.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = Tile(
                    char=new_door_def["char"],
                    color=new_door_def["color"],
                    passable=new_door_def["passable"],
                    name=new_door_def["name"],
                    properties=new_door_def["properties"]
                )
                self.transparency_map[door_y, door_x] = not self.chunks[chunk_y][chunk_x].tiles[local_y][local_x].blocks_fov
                # self.add_message_to_chat_log(action_message) # Can be spammy
                return True
            else:
                # self.add_message_to_chat_log(f"The {target_tile.name} seems stuck for {requesting_npc.name}.")
                return False
        return False # Not a door

    def initialize_trade_session(self):
        """Populates snapshots of player and merchant inventories for the trade UI."""
        if not self.trade_ui_active or not self.trade_ui_npc_target:
            return

        merchant_npc = self.trade_ui_npc_target
        merchant_reputation = merchant_npc.knowledge.get_reputation_towards(self.player)
        merchant_distrust = merchant_npc.get_distrust_towards(self.player)
        merchant_local_opinion = self.refresh_local_incident_opinion(merchant_npc, self.player.id)
        merchant_stance = self.evaluate_social_reaction_stance(merchant_npc, self.player).stance
        should_refuse_trade = (
            merchant_reputation <= -80
            or merchant_distrust >= 70
            or merchant_local_opinion <= -45
            or merchant_stance in {"fearful", "hostile"}
        ) and merchant_local_opinion < 30
        if should_refuse_trade:
            self.add_message_to_chat_log(f"{self.get_entity_display_name(merchant_npc)} refuses to trade with you.")
            self.trade_ui_active = False
            self.trade_ui_npc_target = None
            self.game_state = "PLAYING"
            return

        self.trade_ui_player_inventory_snapshot = []
        self.trade_ui_merchant_inventory_snapshot = []
        self.trade_ui_player_item_index = 0
        self.trade_ui_merchant_item_index = 0
        self.trade_ui_player_selling = True # Default to player selling view

        merchant_village = self._get_village_for_npc(merchant_npc)

        # Player inventory snapshot: (item_key, quantity, price_to_sell_at)
        for item_key, count in list(self.player.economic.inventory.items()):
            if item_key == "item_references":
                continue
            item_def = ITEM_DEFINITIONS.get(item_key)
            if item_def:
                price = self.get_dynamic_price(item_key, merchant_village, merchant=merchant_npc)
                self.trade_ui_player_inventory_snapshot.append((item_key, count, price))

        # Merchant inventory snapshot: (item_key, quantity, price_to_buy_at)
        # Merchant inventory is likely in their work building
        merchant_inventory_source = {}
        merchant_building = self.buildings_by_id.get(merchant_npc.schedule.work_building_id)
        if merchant_building and merchant_building.building_type in ["general_store", "mill"]:
            merchant_inventory_source = merchant_building.building_inventory
        else: # Fallback to NPC's personal inventory if no store or not a store
            merchant_inventory_source = self.trade_ui_npc_target.economic.npc_inventory

        for item_key, quantity in merchant_inventory_source.items():
            if item_key == "money": continue # Don't list merchant's money as a sellable item
            item_def = ITEM_DEFINITIONS.get(item_key)
            if item_def:
                price = self.get_dynamic_price(item_key, merchant_village, merchant=merchant_npc)
                self.trade_ui_merchant_inventory_snapshot.append((item_key, quantity, price))

        # Sort by name for consistent display
        self.trade_ui_player_inventory_snapshot.sort(key=lambda x: ITEM_DEFINITIONS.get(x[0], {}).get("name", x[0]))
        self.trade_ui_merchant_inventory_snapshot.sort(key=lambda x: ITEM_DEFINITIONS.get(x[0], {}).get("name", x[0]))

    def handle_trade_action(self):
        """Processes a buy or sell action from the trade UI."""
        if not self.trade_ui_active or not self.trade_ui_npc_target:
            return

        merchant_npc = self.trade_ui_npc_target
        merchant_building = self.buildings_by_id.get(merchant_npc.schedule.work_building_id)
        merchant_village = self._get_village_for_npc(merchant_npc)

        # Determine merchant's actual inventory (store or personal)
        merchant_true_inventory = {}
        if merchant_building and merchant_building.building_type in ["general_store", "mill"]:
            merchant_true_inventory = merchant_building.building_inventory
        else:
            merchant_true_inventory = merchant_npc.economic.npc_inventory

        merchant_money = merchant_true_inventory.get("money", 0)

        if self.trade_ui_player_selling: # Player is selling
            if not self.trade_ui_player_inventory_snapshot: return
            item_key, _, price = self.trade_ui_player_inventory_snapshot[self.trade_ui_player_item_index]

            if self.player.has_item(item_key):
                if merchant_money >= price:
                    item_reference = self.player.pop_item_reference(item_key)
                    removed_item = item_reference is not None or self.player.remove_item(item_key, 1)
                    if removed_item:
                        self.player.economic.money += price
                        if item_reference is not None and hasattr(merchant_true_inventory, "add_item_reference"):
                            merchant_true_inventory.add_item_reference(item_reference)
                        else:
                            merchant_true_inventory[item_key] = merchant_true_inventory.get(item_key, 0) + 1
                        merchant_true_inventory["money"] = merchant_money - price
                        self.add_message_to_chat_log(f"You sold 1 {ITEM_DEFINITIONS[item_key]['name']} for {price} money.")
                        if merchant_village:
                            merchant_village.supply[item_key] = merchant_village.supply.get(item_key, 0) + 1
                    else:
                        self.add_message_to_chat_log("Error: Could not remove item from inventory.")
                else:
                    self.add_message_to_chat_log(f"{self.get_entity_display_name(merchant_npc)} doesn't have enough money to buy that.")
            else:
                self.add_message_to_chat_log("Error: You don't have that item to sell (inventory mismatch).")

        else: # Player is buying (viewing merchant's items)
            if not self.trade_ui_merchant_inventory_snapshot: return
            item_key, _, price = self.trade_ui_merchant_inventory_snapshot[self.trade_ui_merchant_item_index]

            if merchant_true_inventory.get(item_key, 0) > 0:
                if self.player.economic.money >= price:
                    item_reference = merchant_true_inventory.pop_item_reference(item_key) if hasattr(merchant_true_inventory, "pop_item_reference") else None
                    if item_reference is None:
                        merchant_true_inventory[item_key] -= 1
                        if merchant_true_inventory[item_key] <= 0:
                            del merchant_true_inventory[item_key]
                    merchant_true_inventory["money"] = merchant_money + price

                    if item_reference is not None:
                        self.player.add_item_reference(item_reference)
                    else:
                        self.player.add_item(item_key, 1)
                    self.player.economic.money -= price
                    self.add_message_to_chat_log(f"You bought 1 {ITEM_DEFINITIONS[item_key]['name']} for {price} money.")
                    if merchant_village:
                        merchant_village.supply[item_key] = merchant_village.supply.get(item_key, 0) - 1
                else:
                    self.add_message_to_chat_log("You don't have enough money for that.")
            else:
                self.add_message_to_chat_log(f"Error: {self.get_entity_display_name(merchant_npc)} doesn't have that item in stock (inventory mismatch).")


    def player_attempt_toggle_door(self, target_x: int, target_y: int) -> bool:
        """Handles the player's attempt to open or close a door."""
        target_tile = self.get_tile_at(target_x, target_y)

        if target_tile and target_tile.properties.get("is_door"):
            is_open = target_tile.properties.get("is_open", False)
            new_state_key = None
            action_message = ""

            if is_open: # Door is open, try to close it
                new_state_key = target_tile.properties.get("closes_to")
                action_message = f"You close the {target_tile.name}."
            else: # Door is closed, try to open it
                new_state_key = target_tile.properties.get("opens_to")
                action_message = f"You open the {target_tile.name}."

            if new_state_key and new_state_key in DECORATION_ITEM_DEFINITIONS:
                new_door_def = DECORATION_ITEM_DEFINITIONS[new_state_key]

                # Get chunk and local coords to update the tile in the chunk's grid
                chunk_x, chunk_y = target_x // CHUNK_SIZE, target_y // CHUNK_SIZE
                local_x, local_y = target_x % CHUNK_SIZE, target_y % CHUNK_SIZE

                self.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = Tile(
                    char=new_door_def["char"],
                    color=new_door_def["color"],
                    passable=new_door_def["passable"],
                    name=new_door_def["name"],
                    properties=new_door_def["properties"]
                )
                self.transparency_map[target_y, target_x] = not self.chunks[chunk_y][chunk_x].tiles[local_y][local_x].blocks_fov
                self.add_message_to_chat_log(action_message)
                return True # Action taken
            else:
                self.add_message_to_chat_log(f"The {target_tile.name} seems stuck or improperly defined.")
                return False # Action failed
        return False # Not a door or no tile

    def start_npc_dialogue(self, npc_target: NPC):
        """Initiates dialogue with an NPC, getting their first line."""
        if not npc_target:
            return
        profile = evaluate_conversation_foundation(self, self.player, npc_target, max_distance=9999)
        if not profile.can_start:
            self.chat_ui_history.clear()
            self.chat_ui_history.append((self.get_entity_display_name(npc_target), "I'd rather not talk right now."))
            return

        # Clear previous chat history for the new conversation
        self.chat_ui_history.clear()
        self.chat_ui_scroll_offset = 0
        self.chat_ui_input_line = ""

        player_rep = self.player.social.reputation

        # --- Gather Environmental and Memory Context ---
        time_of_day = self._get_time_of_day_str(self.game_time, DAY_LENGTH_TICKS)
        current_weather = self.weather
        location_description = self._get_location_description(npc_target.x, npc_target.y)
        long_term_memory_summary = "\n- ".join(npc_target.knowledge.long_term_memory[-5:]) # Last 5 memories
        if not long_term_memory_summary:
            long_term_memory_summary = "No specific memories of the player."
        # ---

        relationship_score = npc_target.social.relationships.get(self.player.id, 50)
        npc_display_name = self.get_entity_display_name(npc_target)
        relationship_context = self._describe_relationship_for_prompt(npc_target)

        prompt = LLM_PROMPTS["npc_conversation_greeting"].format(
            npc_name=npc_display_name,
            npc_personality=npc_target.social.personality,
            npc_attitude=npc_target.attitude_to_player,
            npc_relationship_to_player=relationship_context,
            relationship_score=relationship_score,
            player_fame=self.player.social.fame,
            player_infamy=self.player.social.infamy,
            player_title=self.player.social.title,
            time_of_day=time_of_day,
            current_weather=current_weather,
            location_description=location_description,
            long_term_memory=long_term_memory_summary,
            npc_help_needed=npc_target.knowledge.help_needed
        )
        greeting = self._call_llm(prompt)
        if self._llm_output_is_empty(greeting) or self._contains_placeholder_player_reference(greeting):
            greeting = self._fallback_dialogue_greeting(npc_target)

        self.chat_ui_history.append(("System", f"[tone: {profile.tone}, openness: {profile.openness:.2f}]"))
        self.chat_ui_history.append((npc_display_name, greeting.strip()))

        # If the NPC has a dynamic quest to offer, add it to the dialogue
        if hasattr(npc_target, 'active_quest') and npc_target.active_quest:
            quest = npc_target.active_quest
            offer_text = f"I'm in a bit of a bind. I desperately need {quest.required_count} {quest.item_key.replace('_', ' ')}. Can you help me? (You can 'accept quest' or 'decline quest')"
            self.chat_ui_history.append((npc_display_name, offer_text))


        if len(self.chat_ui_history) > self.chat_ui_max_history:
            self.chat_ui_history = self.chat_ui_history[-self.chat_ui_max_history:]

    def continue_npc_dialogue(self, npc_target: NPC, player_input_text: str):
        """Continues dialogue with an NPC based on player input and history."""
        if not npc_target:
            return
        profile = evaluate_conversation_foundation(self, self.player, npc_target, max_distance=9999)
        if not profile.can_start:
            self.chat_ui_history.append((self.get_entity_display_name(npc_target), "Let's end this here."))
            return

        npc_display_name = self.get_entity_display_name(npc_target)

        # --- Handle special keywords before general conversation ---
        # --- Handle special keywords before general conversation ---
        # Quest completion
        if 'complete quest' in player_input_text.lower():
            for quest_id, quest_data in self.player.knowledge.active_quests.items():
                if quest_data["quest_giver_id"] == npc_target.id:
                    self.complete_quest(quest_id, npc_target)
                    return # End dialogue turn

        # Quest acceptance/rejection
        if hasattr(npc_target, 'active_quest') and npc_target.active_quest:
            quest = npc_target.active_quest
            if 'accept' in player_input_text.lower():
                self.player.knowledge.active_quests[quest.id] = {
                    "title": quest.title,
                    "description": quest.description,
                    "type": quest.type,
                    "quest_giver_id": quest.quest_giver_id,
                    "item_to_fetch_key": quest.item_key,
                    "item_fetch_count": quest.required_count,
                    "progress": 0
                }
                self.chat_ui_history.append((npc_display_name, "Oh, thank you! Please hurry!"))
                npc_target.active_quest = None # Quest is now with the player
                return
            elif 'decline' in player_input_text.lower():
                self.chat_ui_history.append((npc_display_name, "Oh, I see. I'll have to find another way then."))
                npc_target.active_quest = None # NPC gives up offering this quest for now
                return

        # "Ask About" Logic
        ask_keywords = ["ask about", "who is", "tell me about", "know about"]
        if any(keyword in player_input_text.lower() for keyword in ask_keywords):
            found_subject = None
            relevant_events = []

            # Identify entity from input string
            input_lower = player_input_text.lower()
            # Check all NPCs + Player
            potential_subjects = list(self.all_npcs) + [self.player]

            # Sort by length descending to match longer names first (e.g. "Dire Wolf" before "Wolf")
            potential_subjects.sort(key=lambda x: len(x.name), reverse=True)

            for entity in potential_subjects:
                if entity.name.lower() in input_lower and len(entity.name) > 2:
                     found_subject = entity
                     break

            if found_subject:
                 # Gather known events involving this subject
                 for event in npc_target.knowledge.known_events.values():
                     if event.subject_id == found_subject.id or event.target_id == found_subject.id:
                         relevant_events.append(event)

                 if relevant_events:
                     summary_lines = []
                     for e in relevant_events:
                         subj = self.get_entity_by_id(e.subject_id)
                         targ = self.get_entity_by_id(e.target_id) if e.target_id else None
                         s_name = subj.name if subj else "Someone"
                         t_name = targ.name if targ else "someone"
                         summary_lines.append(f"- {e.description.format(subject=s_name, target=t_name)}")

                     summary_text = "\n".join(summary_lines)

                     prompt = LLM_PROMPTS["npc_summarize_knowledge_about_subject"].format(
                         npc_name=npc_target.name,
                         npc_personality=npc_target.social.personality,
                         relationship_score=npc_target.social.relationships.get(self.player.id, 50),
                         subject_name=found_subject.name,
                         known_events_summary=summary_text
                     )
                     response = self._call_llm(prompt)
                     if response:
                         self.chat_ui_history.append((npc_display_name, response.strip()))
                         return
            # If no subject found or no events known, fall through to general conversation

        share_keywords = ["i know where", "let me tell you about", "have you seen"]
        if any(keyword in player_input_text.lower() for keyword in share_keywords):
            shared = False
            for loc_id, coords in self.player.knowledge.known_locations.items():
                building = self.buildings_by_id.get(loc_id)
                if building and building.building_type.replace('_', ' ') in player_input_text.lower():
                    loc_name = building.building_type.replace('_', ' ')
                    if loc_name not in npc_target.knowledge.known_locations:
                        npc_target.knowledge.known_locations[loc_name] = coords
                        npc_target.social.relationships[self.player.id] = npc_target.social.relationships.get(self.player.id, 50) + 10
                        self.chat_ui_history.append((npc_display_name, f"Oh, the {loc_name}? I didn't know where that was. Thank you!"))
                        shared = True
                        break
            if not shared:
                self.chat_ui_history.append((npc_display_name, "I'm not sure what you mean."))
            return

        # Player Applying for Job Logic
        if any(word in player_input_text.lower() for word in ["hired", "job", "work", "vacancy", "hire me"]) and npc_target.economic.profession != "Unemployed":
            if self.player.economic.job_building_id:
                self.chat_ui_history.append((npc_display_name, "You already have a job. You can't work two places at once!"))
                return

            work_building = self.buildings_by_id.get(npc_target.schedule.work_building_id)
            if work_building:
                # Check for vacancies
                current_workers = sum(1 for n in self.village_npcs if n.schedule.work_building_id == work_building.id and not n.physical.is_dead)
                # Check if player is already counted (shouldn't be, but safety)
                if self.player.economic.job_building_id == work_building.id:
                    current_workers += 1

                if current_workers < work_building.max_workers:
                    # Hired!
                    self.player.economic.job_building_id = work_building.id
                    self.player.economic.days_employed = 0
                    self.player.economic.work_performance = 50
                    self.player.economic.job_satisfaction = 100

                    # Determine profession
                    new_prof = npc_target.economic.profession
                    if work_building.building_type == "sheriff_office": new_prof = "Deputy"
                    elif work_building.building_type == "lumber_mill": new_prof = "Woodcutter"
                    elif work_building.building_type == "blacksmith_shop": new_prof = "Blacksmith Apprentice"
                    elif work_building.building_type == "clinic": new_prof = "Healer's Assistant"
                    elif work_building.building_type == "tavern": new_prof = "Server"
                    elif work_building.building_type == "farm": new_prof = "Farmhand"
                    elif work_building.building_type == "general_store": new_prof = "Shop Assistant"

                    self._set_entity_profession(self.player, new_prof, reason="player_hired")

                    self.chat_ui_history.append((npc_display_name, f"You want to work here? We could use the help. You're hired as a {new_prof}!"))
                    self.add_message_to_chat_log(f"You have been hired as a {new_prof} at the {work_building.building_type.replace('_', ' ')}.")

                    # Social boost
                    npc_target.social.relationships[self.player.id] = min(100, npc_target.social.relationships.get(self.player.id, 50) + 10)
                    return
                else:
                    self.chat_ui_history.append((npc_display_name, "Sorry, we're fully staffed right now. Try somewhere else."))
                    return
            else:
                self.chat_ui_history.append((npc_display_name, "I don't have a steady workplace myself to offer you a job."))
                return

        # Job Referral Logic
        if entity_has_profession(npc_target, "Unemployed") and any(word in player_input_text.lower() for word in ["job", "work", "hiring", "vacancy"]):
            # Check if player mentioned a specific known building that has a vacancy
            referred_building = None
            for loc_id, coords in self.player.knowledge.known_locations.items():
                building = self.buildings_by_id.get(loc_id)
                if building and building.building_type.replace('_', ' ') in player_input_text.lower():
                     # Check vacancy
                     current_workers = sum(1 for n in self.village_npcs if n.schedule.work_building_id == building.id and not n.physical.is_dead)
                     if current_workers < building.max_workers:
                         referred_building = building
                         break

            if referred_building:
                self.chat_ui_history.append((npc_display_name, f"The {referred_building.building_type.replace('_', ' ')}? I'll go apply right now! Thank you!"))
                npc_target.schedule.current_task = "applying_for_job"
                npc_target.schedule.current_destination_coords = (referred_building.global_center_x, referred_building.global_center_y)
                npc_target.schedule.current_path = [] # Clear path to trigger recalculation
                return # End conversation turn to act
            else:
                # Optional: If player mentions "job" but no specific building matched, NPC could ask "Where?"
                # For now, fall through to LLM which might handle it conversationally.
                pass

        gossip_keywords = ["gossip", "rumors", "news", "hear anything"]
        if any(keyword in player_input_text.lower() for keyword in gossip_keywords):
            known_lines = get_contextual_dialogue_lines(
                npc_target,
                self.player,
                self,
                limit=1,
            )
            if known_lines and known_lines[0].topic_type != "small_talk":
                self.chat_ui_history.append((npc_display_name, known_lines[0].text))
            elif not npc_target.knowledge.known_events:
                self.chat_ui_history.append((npc_display_name, "I haven't heard anything interesting lately."))
            else:
                # Legacy generic event gossip still uses the existing prompt path.
                event_to_share = random.choice(list(npc_target.knowledge.known_events.values()))

                subject = next((n for n in self.all_npcs if n.id == event_to_share.subject_id), self.player if event_to_share.subject_id == self.player.id else None)
                target = next((n for n in self.all_npcs if n.id == event_to_share.target_id), self.player if event_to_share.target_id == self.player.id else None) if event_to_share.target_id else None

                subject_name = getattr(subject, 'name', 'Someone') if subject else 'Someone'
                target_name = getattr(target, 'name', 'someone') if target else 'someone'

                subject_title = getattr(getattr(subject, 'social', None), 'title', '') if subject else ''
                target_title = getattr(getattr(target, 'social', None), 'title', '') if target else ''

                gossip_prompt = LLM_PROMPTS["npc_share_gossip"].format(
                    npc_name=npc_target.name,
                    npc_personality=npc_target.social.personality,
                    npc_relationship_with_player=npc_target.social.relationships.get(self.player.id, 50),
                    npc_relationship_with_subject=npc_target.social.relationships.get(event_to_share.subject_id, 50),
                    npc_relationship_with_target=npc_target.social.relationships.get(event_to_share.target_id, 50) if event_to_share.target_id else 50,
                    event_description=event_to_share.description,
                    subject_name=subject_name,
                    target_name=target_name,
                    subject_title=subject_title,
                    target_title=target_title
                )
                gossip_dialogue = self._call_llm(gossip_prompt)
                if not gossip_dialogue:
                    gossip_dialogue = "I... uh... forget what I was going to say."

                self.chat_ui_history.append((npc_display_name, gossip_dialogue.strip()))
            # End the turn after sharing gossip
            return

        # Format conversation history for the prompt
        formatted_history = []
        # Take last N messages for context window (e.g., last 10 lines, 5 exchanges)
        history_context_limit = 10
        recent_history = self.chat_ui_history[-(history_context_limit-1):] if len(self.chat_ui_history) > 1 else self.chat_ui_history

        for speaker, text in recent_history:
            if speaker == "Player": # Assuming "Player" is the key for player lines
                formatted_history.append(f"Player: {text}")
            else: # NPC lines
                formatted_history.append(f"{speaker}: {text}")
        history_str = "\n".join(formatted_history)

        # --- Gather Environmental and Memory Context ---
        time_of_day = self._get_time_of_day_str(self.game_time, DAY_LENGTH_TICKS)
        current_weather = self.weather
        location_description = self._get_location_description(npc_target.x, npc_target.y)
        long_term_memory_summary = "\n- ".join(npc_target.knowledge.long_term_memory[-5:]) # Last 5 memories
        if not long_term_memory_summary:
            long_term_memory_summary = "No specific memories of the player."
        # ---

        relationship_score = npc_target.social.relationships.get(self.player.id, 50)
        relationship_context = self._describe_relationship_for_prompt(npc_target)

        prompt = LLM_PROMPTS["npc_conversation_continue"].format(
            npc_name=npc_display_name,
            npc_personality=npc_target.social.personality,
            npc_attitude=npc_target.attitude_to_player,
            npc_relationship_to_player=relationship_context,
            relationship_score=relationship_score,
            player_fame=self.player.social.fame,
            player_infamy=self.player.social.infamy,
            player_title=self.player.social.title,
            conversation_history=history_str,
            player_input=player_input_text,
            npc_current_task=npc_target.schedule.current_task,
            time_of_day=time_of_day,
            current_weather=current_weather,
            location_description=location_description,
            long_term_memory=long_term_memory_summary
        )

        response_str = self._call_llm(prompt)
        if self._llm_output_is_empty(response_str):
            fallback_response, fallback_goal = self._fallback_dialogue_continue(npc_target, player_input_text)
            self.chat_ui_history.append((npc_display_name, fallback_response))
            self._handle_npc_goal(npc_target, fallback_goal, player_input_text)
            return

        response_json = self._parse_llm_json_object(response_str)
        if response_json is not None:
            npc_response = response_json.get("response", "").strip() or self._fallback_dialogue_continue(npc_target, player_input_text)[0]
            goal = self._coerce_dialogue_goal_by_profile(profile, response_json.get("goal", "continue_conversation"))
            if self._contains_placeholder_player_reference(npc_response):
                npc_response, goal = self._fallback_dialogue_continue(npc_target, player_input_text)

            self.chat_ui_history.append((npc_display_name, npc_response.strip()))
            self._handle_npc_goal(npc_target, goal, player_input_text)
        else:
            # If the LLM fails to return valid JSON, just treat the whole response as dialogue
            fallback_response, fallback_goal = self._fallback_dialogue_continue(npc_target, player_input_text)
            dialogue_text = response_str.strip() if not self._llm_output_is_empty(response_str) else fallback_response
            if self._contains_placeholder_player_reference(dialogue_text):
                dialogue_text = fallback_response
            self.chat_ui_history.append((npc_display_name, dialogue_text))
            if dialogue_text == fallback_response:
                self._handle_npc_goal(npc_target, fallback_goal, player_input_text)

        # After NPC response, check if this NPC should offer a job
        if entity_has_profession(npc_target, "Lumber Mill Foreman") and f"lumber_delivery_{npc_target.id}" not in self.player.economic.active_contracts:
            # Check if player's response was affirmative to a previous implicit offer or just general talk
            # This is tricky without more state. For now, let's assume if they talk to Foreman, job is offered.
            # A better way: Foreman's initial greeting (start_npc_dialogue) could offer.
            # Or, if player says "work" or "job".
            # For simplicity now: if player just said something, and no active contract, Foreman offers.

            # Define contract details
            contract_id = f"lumber_delivery_{npc_target.id}"
            item_needed = "log"
            quantity_needed = 10
            reward_amount = 50 # Example reward
            item_name_plural = "logs" # For the prompt

            offer_prompt = LLM_PROMPTS["npc_job_offer_lumber"].format(
                npc_name=npc_target.name,
                npc_profession=npc_target.economic.profession,
                npc_personality=npc_target.social.personality,
                npc_attitude=npc_target.attitude_to_player,
                player_criminal_points=self.player.social.reputation.get(REP_CRIMINAL,0),
                player_hero_points=self.player.social.reputation.get(REP_HERO,0),
                quantity_needed=quantity_needed,
                item_name_plural=item_name_plural,
                reward_amount=reward_amount
            )
            job_offer_dialogue = self._call_llm(offer_prompt)
            if not job_offer_dialogue:
                job_offer_dialogue = f"I might have some work for you... if you're interested. Need {quantity_needed} {item_name_plural} for {reward_amount} coins."

            self.chat_ui_history.append((npc_display_name, job_offer_dialogue.strip()))
            # Store pending offer to be accepted on player's next input if affirmative
            self.player.economic.pending_contract_offer = {
                "contract_id": contract_id, "npc_id": npc_target.id,
                "item_key": item_needed, "quantity_needed": quantity_needed,
            "reward": reward_amount, "npc_offerer_id": npc_target.id
            }
            self.chat_ui_history.append(("System", "The Foreman has offered you a job. Type 'yes' or 'accept' to take it."))

        # --- Quest Offering Logic (Example: Sheriff offers "kill_wolves_01") ---
        # This is a simplified trigger; more robust would be keyword matching or LLM intent.
        if entity_has_profession(npc_target, "Sheriff") and "kill_wolves_01" not in self.player.knowledge.active_quests and \
           "kill_wolves_01" not in self.player.knowledge.completed_quests:

            quest_def = QUEST_DEFINITIONS.get("kill_wolves_01")
            if quest_def:
                offer_dialogue = quest_def.get("dialogue_offer", "I might have a task for you...")
                self.chat_ui_history.append((npc_display_name, offer_dialogue))
                self.add_message_to_chat_log(f"Quest Offered: {quest_def['title']}")

        if len(self.chat_ui_history) > self.chat_ui_max_history:
            self.chat_ui_history = self.chat_ui_history[-self.chat_ui_max_history:]

    def _handle_npc_goal(self, npc: NPC, goal: str, player_input: str):
        """Handles the goal set for an NPC by the LLM during conversation."""
        if goal == "follow_player":
            npc.schedule.current_task = "following_player"
            npc.task_target_entity_id = self.player.id
            npc.schedule.current_path = []  # Clear path to allow recalculation
            self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} is now following you.")
        elif goal == "go_to_location":
            # Placeholder for future implementation where the LLM might specify coordinates
            self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} wants to go to a location mentioned.")
            # Example: npc.schedule.current_task = "going_to_location"
            # npc.task_target_coords = (x, y) # (extracted from player_input or LLM response)
        elif goal == "start_trade":
            if entity_has_capability(npc, "trade"):
                self.request_open_trade(npc)
            else:
                self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} seems to want to trade, but isn't a merchant.")
        elif goal == "give_item":
            transferred_item_name = self._transfer_gift_item_from_npc(npc)
            if transferred_item_name:
                self.add_message_to_chat_log(
                    f"{self.get_entity_display_name(npc)} gave you {transferred_item_name}."
                )
            else:
                self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} has nothing to give.")
            self.request_close_dialogue()
        elif goal == "attack_target":
            npc.attitude_to_player = "hostile"
            npc.social.relationships[self.player.id] = 0
            self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} becomes incredibly hostile!")
            self.request_close_dialogue()
        elif goal == "end_conversation":
            self._summarize_and_store_conversation(npc, self.chat_ui_history)
            self.request_close_dialogue()

    def _transfer_gift_item_from_npc(self, npc: NPC) -> str | None:
        """Move a single gift item from an NPC to the player.
        """
        npc_inventory = getattr(getattr(npc, "economic", None), "npc_inventory", None)
        if not isinstance(npc_inventory, Inventory):
            return None
        for item_key, quantity in npc_inventory.items():
            if quantity <= 0:
                continue
            item_reference = npc_inventory.pop_item_reference(item_key)
            if item_reference is not None:
                self.player.add_item_reference(item_reference)
            else:
                self.player.add_item(item_key, 1)
            return ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key.replace("_", " ").title())
        return None

    def _summarize_and_store_conversation(self, npc: NPC, conversation_history: list):
        """Summarizes a conversation and stores it in the NPC's long-term memory."""
        if not conversation_history:
            return

        formatted_history = []
        for speaker, text in conversation_history:
            if speaker == "Player":
                formatted_history.append(f"Player: {text}")
            else:
                formatted_history.append(f"{speaker}: {text}")
        history_str = "\n".join(formatted_history)

        prompt = LLM_PROMPTS["summarize_conversation_for_memory"].format(
            npc_name=npc.name,
            npc_personality=npc.social.personality,
            conversation_history=history_str
        )
        summary = self._call_llm(prompt)

        if summary and len(summary) > 10: # Avoid storing short errors or empty strings
            npc.knowledge.long_term_memory.append(summary)
            # Keep memory from growing too large
            if len(npc.knowledge.long_term_memory) > 20:
                npc.knowledge.long_term_memory.pop(0)


    def _get_most_interesting_known_event(self, npc: NPC) -> Event | None:
        """Selects the most 'interesting' event from an NPC's knowledge based on type and recency."""
        if not npc.knowledge.known_events:
            return None

        scored_events = []
        for event in npc.knowledge.known_events.values():
            score = 0
            # Event Type Score
            if event.type in ["entity_death", "crime_witnessed", "threat_detected"]:
                score += 10
            elif event.type in ["quest_complete", "npc_marriage"]:
                score += 5
            elif event.type in ["npc_fired", "npc_hired"]:
                score += 2
            else:
                score += 1

            # Recency Score
            age = self.game_time - event.timestamp
            if age < DAY_LENGTH_TICKS:
                score += 5
            elif age > DAY_LENGTH_TICKS * 3:
                score -= 2

            scored_events.append((score, event))

        if not scored_events:
             return None

        scored_events.sort(key=lambda x: x[0], reverse=True)
        return scored_events[0][1]

    def _call_llm(self, prompt: str) -> str:
        """Makes a request to the configured LLM backend and returns the response."""
        if not ENABLE_LLM_CONNECTION:
            return ""

        if LLM_BACKEND == "gemini":
            return self._call_gemini(prompt)
        else:
            return self._call_ollama_backend(prompt)

    def _call_llm_for_worldgen(self, prompt: str) -> str:
        """World generation should stay fast and local; reserve LLM calls for live gameplay."""
        return ""

    def _call_llm_for_background(self, prompt: str) -> str:
        """Background simulation should not block on remote model calls during active play."""
        return ""

    def _submit_background_llm_task(self, task_key, prompt: str) -> None:
        if task_key in self._background_llm_tasks:
            return
        if len(self._background_llm_tasks) >= 4:
            return
        self._background_llm_tasks[task_key] = self._background_llm_executor.submit(self._call_llm, prompt)

    def _cancel_background_llm_task(self, task_key) -> None:
        future = self._background_llm_tasks.pop(task_key, None)
        if future is not None:
            future.cancel()

    def _poll_background_llm_task(self, task_key):
        future = self._background_llm_tasks.get(task_key)
        if future is None:
            return None
        if not future.done():
            return BACKGROUND_LLM_PENDING
        del self._background_llm_tasks[task_key]
        try:
            return future.result()
        except Exception:
            return ""

    def _call_gemini(self, prompt: str) -> str:
        if not GOOGLE_API_KEY:
            self._warn_missing_llm_once()
            return ""
        try:
            client = genai.Client(api_key=GOOGLE_API_KEY)
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )
            response_text = getattr(response, "text", "") or ""
            return response_text.strip()
        except Exception as e:
            self.add_message_to_chat_log(f"Gemini error: {e}")
            return ""

    def _call_ollama_backend(self, prompt: str) -> str:
        """Makes a request to the Ollama API and returns the response."""
        try:
            response = requests.post(
                OLLAMA_ENDPOINT + "/api/generate",
                json={
                    "model": "llama3.2:latest",
                    "prompt": prompt,
                    "stream": False
                },
                timeout=15 # 15 second timeout, increased from 5
            )
            response.raise_for_status()
            full_response = response.json()["response"]
            return full_response.strip()
        except requests.exceptions.RequestException as e:
            return ""

    def log_event(
        self,
        event_type: str,
        description: str,
        subject_id: int,
        target_id: int | None = None,
        location: tuple[int, int] | None = None,
        *,
        event: Event | None = None,
    ) -> Event:
        """Creates a history event and adds it to the world ledger."""
        new_event = event or self.history.add_event(
            event_type=event_type,
            description=description,
            subject_id=subject_id,
            target_id=target_id,
            location=location,
            game_time=self.game_time
        )
        if event is not None and self.history.get_event(event.id) is None:
            self.history.add_record(event)

        # Determine if the event is public knowledge (witnessed)
        if location:
            # Check for witnesses at the location
            # Note: _get_witnesses_to_action filters by FOV.
            # We pass a generic action type to get all eyes.
            witnesses = self._get_witnesses_to_action(location[0], location[1], "general_event")

            # If the player is the subject or target, and witnesses exist, it's public.
            # If an NPC is the subject, and player or other NPCs see it, it's public.
            # We exclude the subject themselves from the "public" count (conceptually),
            # though _get_witnesses_to_action might include them if not careful.
            # _get_witnesses check: "for npc in ... if npc.id in npc_fov_maps ...".
            # It currently iterates NPCs. If the subject is an NPC, they might see themselves?
            # Let's assume seeing yourself doesn't make it "public" knowledge if no one else is there.

            valid_witnesses = [w for w in witnesses if w.id != subject_id]

            # Also check if PLAYER witnesses it (if player is not subject)
            player_saw = False
            if subject_id != self.player.id:
                if self.player_fov_map[location[1], location[0]]:
                    player_saw = True

            if valid_witnesses or player_saw:
                new_event.public_knowledge = True

        return new_event

    def create_memory_event(
        self,
        *,
        event_type: str,
        subject_id: int | None,
        target_id: int | None = None,
        importance_score: int = 10,
        headline: str = "",
        location: tuple[int, int] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEvent:
        return MemoryEvent(
            event_type=event_type,
            subject_id=subject_id,
            target_id=target_id,
            timestamp=self.game_time,
            importance_score=max(1, int(importance_score)),
            headline=headline,
            location=location,
            metadata=dict(metadata or {}),
        )

    def record_memory_event(self, holder, memory_event: MemoryEvent | None) -> bool:
        knowledge = getattr(holder, "knowledge", None)
        if knowledge is None or memory_event is None or not hasattr(knowledge, "record_event"):
            return False
        return bool(knowledge.record_event(memory_event))

    def queue_gossip_flavor_text(self, speaker, memory_event: MemoryEvent | None) -> bool:
        if speaker is None or memory_event is None:
            return False
        gossip_service = getattr(self, "_gossip_llm_service", None)
        if gossip_service is None or not hasattr(gossip_service, "submit"):
            return False

        subject = self.get_entity_by_id(memory_event.subject_id) if memory_event.subject_id is not None else None
        target = self.get_entity_by_id(memory_event.target_id) if memory_event.target_id is not None else None
        subject_name = getattr(subject, "name", "") if subject is not None else ""
        target_name = getattr(target, "name", "") if target is not None else ""
        return bool(
            gossip_service.submit(
                speaker=speaker,
                memory_event=memory_event,
                subject_name=subject_name or "Someone",
                target_name=target_name,
            )
        )

    def queue_chronicle_draft(self, scribe, memory_events: list[MemoryEvent]) -> bool:
        if scribe is None or len(memory_events) < 2:
            return False
        gossip_service = getattr(self, "_gossip_llm_service", None)
        if gossip_service is None or not hasattr(gossip_service, "submit_chronicle"):
            return False
        building_id = getattr(getattr(scribe, "schedule", None), "work_building_id", None)
        if building_id is None:
            return False
        year = self.game_time // (DAY_LENGTH_TICKS * DAYS_PER_SEASON * 4)
        title_hint = f"Year {year} Chronicle"
        submitted = gossip_service.submit_chronicle(
            scribe=scribe,
            memory_events=memory_events,
            building_id=building_id,
            title_hint=title_hint,
        )
        if not submitted:
            return False
        scribe.knowledge.chronicle_pending_memory_ids.update(memory.id for memory in memory_events)
        return True

    def try_begin_scribe_chronicle(self, scribe: NPC) -> bool:
        if scribe is None or getattr(getattr(scribe, "physical", None), "is_dead", False):
            return False
        if str(getattr(getattr(scribe, "economic", None), "profession", "") or "") != "Scribe":
            return False
        if getattr(getattr(scribe, "schedule", None), "current_task", "") not in {TaskType.AT_WORK}:
            return False

        eligible_memories = [
            memory
            for memory in scribe.knowledge.known_memories.values()
            if memory.importance_score >= 40
            and memory.id not in scribe.knowledge.chronicle_pending_memory_ids
            and memory.id not in scribe.knowledge.chronicle_written_memory_ids
        ]
        if len(eligible_memories) < 2:
            return False
        eligible_memories.sort(key=lambda memory: (-memory.importance_score, -memory.timestamp, memory.id))
        batch = eligible_memories[:4]
        queued = self.queue_chronicle_draft(scribe, batch)
        if queued:
            scribe.schedule.current_task = "Begin Drafting"
        return queued

    def _finish_chronicle_draft(self, result) -> None:
        scribe = self.get_entity_by_id(result.speaker_id)
        if scribe is None or getattr(getattr(scribe, "knowledge", None), "chronicle_pending_memory_ids", None) is None:
            return
        memory_ids = list((result.metadata or {}).get("memory_ids", []))
        work_building = self.buildings_by_id.get((result.metadata or {}).get("building_id"))
        if work_building is None or not hasattr(work_building, "building_inventory"):
            scribe.knowledge.chronicle_pending_memory_ids.difference_update(memory_ids)
            return

        if hasattr(scribe, "career") and scribe.career.current_role != normalize_profession(scribe.economic.profession):
            scribe.career.set_role(scribe.economic.profession)
        career_level = max(
            getattr(getattr(scribe, "career", None), "level", 0),
            infer_career_level(normalize_profession(scribe.economic.profession)),
            scribe.skills.get_level("crafting"),
        )
        quality = roll_crafted_item_quality(career_level=career_level, work_performance=scribe.economic.work_performance)
        chronicle = ItemReference(
            "book_chronicle",
            quality=quality,
            crafter_name=scribe.name,
            written_text=result.text,
            title=str((result.metadata or {}).get("title_hint") or "Town Chronicle"),
        )
        work_building.building_inventory.add_item_reference(chronicle)
        scribe.knowledge.chronicle_written_memory_ids.update(memory_ids)
        scribe.knowledge.chronicle_pending_memory_ids.difference_update(memory_ids)
        scribe.skills.gain_experience("crafting", max(2, len(memory_ids) * 2))
        if getattr(getattr(scribe, "schedule", None), "current_task", "") == "Begin Drafting":
            scribe.schedule.current_task = TaskType.AT_WORK
        self.add_message_to_chat_log(f"{scribe.name} completes a new town chronicle.")

    def _drain_gossip_flavor_text_queue(self) -> None:
        gossip_service = getattr(self, "_gossip_llm_service", None)
        if gossip_service is None or not hasattr(gossip_service, "poll_completed"):
            return

        for result in gossip_service.poll_completed():
            if getattr(result, "request_type", "gossip") == "chronicle":
                self._finish_chronicle_draft(result)
                continue
            speaker = self.get_entity_by_id(result.speaker_id)
            effect_x = getattr(speaker, "x", result.speaker_position[0])
            effect_y = getattr(speaker, "y", result.speaker_position[1])
            if hasattr(self, "visual_effects"):
                self.visual_effects.append(
                    FloatingTextEffect(effect_x, effect_y, result.text, color=(200, 220, 255), duration=1.6, speed=0.5)
                )

            if speaker is None:
                continue

            distance_to_player = abs(effect_x - self.player.x) + abs(effect_y - self.player.y)
            speaker_volume = getattr(speaker, "speech_volume", DEFAULT_SPEECH_VOLUME)
            can_hear = (
                distance_to_player <= self.player.physical.hearing_radius
                and distance_to_player <= speaker_volume
            )
            if can_hear:
                self.add_message_to_chat_log(f"{self.get_entity_display_name(speaker)}: {result.text}")

    def _history_scope_for_location(self, location: tuple[int, int] | None = None) -> tuple[str | None, str | None]:
        if location is None:
            return None, None
        village = self._get_village_at_coords(location[0], location[1])
        if village is None:
            return None, None
        return getattr(village, "id", None), getattr(village, "region_id", None)

    def record_birth_event(
        self,
        *,
        child: NPC,
        parent_ids: tuple[int, ...],
        description: str,
        location: tuple[int, int] | None = None,
        settlement_id: str | None = None,
        region_id: str | None = None,
    ) -> BirthRecord:
        inferred_settlement_id, inferred_region_id = self._history_scope_for_location(location)
        settlement_id = settlement_id or inferred_settlement_id
        region_id = region_id or inferred_region_id
        birth_record = self.history.record_birth(
            child_id=child.id,
            parent_ids=parent_ids,
            child_name=child.name,
            description=description,
            game_time=self.game_time,
            location=location,
            settlement_id=settlement_id,
            region_id=region_id,
        )
        self.log_event(
            birth_record.type,
            birth_record.description,
            birth_record.subject_id,
            birth_record.target_id,
            birth_record.location,
            event=birth_record,
        )
        create_public_event_seed_from_record(self, birth_record)
        return birth_record

    def record_death_event(
        self,
        *,
        deceased: NPC,
        description: str,
        killer_id: int | None = None,
        location: tuple[int, int] | None = None,
        cause_of_death: str = "",
        settlement_id: str | None = None,
        region_id: str | None = None,
    ) -> DeathRecord:
        inferred_settlement_id, inferred_region_id = self._history_scope_for_location(location)
        settlement_id = settlement_id or inferred_settlement_id
        region_id = region_id or inferred_region_id
        death_record = self.history.record_death(
            deceased_id=deceased.id,
            description=description,
            game_time=self.game_time,
            killer_id=killer_id,
            location=location,
            cause_of_death=cause_of_death,
            settlement_id=settlement_id,
            region_id=region_id,
        )
        self.log_event(
            death_record.type,
            death_record.description,
            death_record.subject_id,
            death_record.target_id,
            death_record.location,
            event=death_record,
        )
        create_public_event_seed_from_record(self, death_record)
        return death_record

    def record_marriage_event(
        self,
        *,
        spouse_a: NPC,
        spouse_b: NPC,
        description: str,
        location: tuple[int, int] | None = None,
        settlement_id: str | None = None,
        region_id: str | None = None,
    ) -> MarriageRecord:
        inferred_settlement_id, inferred_region_id = self._history_scope_for_location(location)
        settlement_id = settlement_id or inferred_settlement_id
        region_id = region_id or inferred_region_id
        marriage_record = self.history.record_marriage(
            spouse_ids=(spouse_a.id, spouse_b.id),
            description=description,
            game_time=self.game_time,
            location=location,
            settlement_id=settlement_id,
            region_id=region_id,
        )
        self.log_event(
            marriage_record.type,
            marriage_record.description,
            marriage_record.subject_id,
            marriage_record.target_id,
            marriage_record.location,
            event=marriage_record,
        )
        create_public_event_seed_from_record(self, marriage_record)
        return marriage_record

    def record_employment_event(
        self,
        *,
        npc: NPC,
        profession: str,
        employment_action: str,
        description: str,
        location: tuple[int, int] | None = None,
        building_id: str | None = None,
        settlement_id: str | None = None,
        region_id: str | None = None,
    ) -> EmploymentRecord:
        building = self.buildings_by_id.get(building_id) if building_id else None
        settlement_id = settlement_id or getattr(building, "settlement_id", None)
        region_id = region_id or getattr(building, "region_id", None)
        if settlement_id is None or region_id is None:
            inferred_settlement_id, inferred_region_id = self._history_scope_for_location(location)
            settlement_id = settlement_id or inferred_settlement_id
            region_id = region_id or inferred_region_id

        if not hasattr(self, "history") or self.history is None:
            return EmploymentRecord(
                event_type="npc_employment_changed",
                description=description,
                subject_id=npc.id,
                game_time=self.game_time,
                worker_id=npc.id,
                profession=profession,
                employment_action=employment_action,
                location=location,
                building_id=building_id,
                settlement_id=settlement_id,
                region_id=region_id,
            )

        employment_record = self.history.record_employment_change(
            worker_id=npc.id,
            profession=profession,
            employment_action=employment_action,
            description=description,
            game_time=self.game_time,
            location=location,
            building_id=building_id,
            settlement_id=settlement_id,
            region_id=region_id,
        )
        self.log_event(
            employment_record.type,
            employment_record.description,
            employment_record.subject_id,
            employment_record.target_id,
            employment_record.location,
            event=employment_record,
        )
        create_public_event_seed_from_record(self, employment_record)
        return employment_record

    def record_crime_event(
        self,
        *,
        crime_kind: str,
        suspect_id: int,
        description: str,
        victim_id: int | None = None,
        witness_ids: tuple[int, ...] = (),
        location: tuple[int, int] | None = None,
        settlement_id: str | None = None,
        region_id: str | None = None,
    ) -> CrimeRecord:
        inferred_settlement_id, inferred_region_id = self._history_scope_for_location(location)
        settlement_id = settlement_id or inferred_settlement_id
        region_id = region_id or inferred_region_id
        crime_record = self.history.record_crime(
            crime_kind=crime_kind,
            suspect_id=suspect_id,
            victim_id=victim_id,
            witness_ids=witness_ids,
            description=description,
            game_time=self.game_time,
            location=location,
            settlement_id=settlement_id,
            region_id=region_id,
            event_type="crime_witnessed",
        )
        self.log_event(
            crime_record.type,
            crime_record.description,
            crime_record.subject_id,
            crime_record.target_id,
            crime_record.location,
            event=crime_record,
        )
        create_public_event_seed_from_record(self, crime_record)
        return crime_record

    def record_migration_event(
        self,
        *,
        npc: NPC,
        migration_kind: str,
        description: str,
        location: tuple[int, int] | None = None,
        origin_label: str | None = None,
        destination_label: str | None = None,
        settlement_id: str | None = None,
        region_id: str | None = None,
    ) -> MigrationRecord:
        inferred_settlement_id, inferred_region_id = self._history_scope_for_location(location)
        settlement_id = settlement_id or inferred_settlement_id
        region_id = region_id or inferred_region_id
        migration_record = self.history.record_migration(
            traveler_id=npc.id,
            migration_kind=migration_kind,
            description=description,
            game_time=self.game_time,
            location=location,
            origin_label=origin_label,
            destination_label=destination_label,
            settlement_id=settlement_id,
            region_id=region_id,
        )
        self.log_event(
            migration_record.type,
            migration_record.description,
            migration_record.subject_id,
            migration_record.target_id,
            migration_record.location,
            event=migration_record,
        )
        create_public_event_seed_from_record(self, migration_record)
        return migration_record

    def _find_nearest_heat_source(self, npc: NPC) -> tuple[int, int] | None:
        """Finds the nearest lit heat source for an NPC."""
        closest_source_coords = None
        min_dist_sq = float('inf')

        # 1. Check a radius around the NPC
        for y in range(npc.y - 10, npc.y + 11):
            for x in range(npc.x - 10, npc.x + 11):
                if 0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT:
                    tile = self.get_tile_at(x, y)
                    if tile and hasattr(tile, 'properties') and tile.properties.get("heat_source"):
                        dist_sq = (npc.x - x)**2 + (npc.y - y)**2
                        if dist_sq < min_dist_sq:
                            min_dist_sq = dist_sq
                            closest_source_coords = (x, y)

        # 2. Check NPC's home for heat sources
        home_building = self.buildings_by_id.get(npc.schedule.home_building_id)
        if home_building:
            for y in range(home_building.global_origin_y, home_building.global_origin_y + home_building.height):
                for x in range(home_building.global_origin_x, home_building.global_origin_x + home_building.width):
                    tile = self.get_tile_at(x, y)
                    if tile and hasattr(tile, 'properties') and tile.properties.get("heat_source"):
                        dist_sq = (npc.x - x)**2 + (npc.y - y)**2
                        if dist_sq < min_dist_sq:
                            min_dist_sq = dist_sq
                            closest_source_coords = (x, y)

        # 3. Check the local tavern
        tavern = self._find_nearest_tavern(npc)
        if tavern:
            for y in range(tavern.global_origin_y, tavern.global_origin_y + tavern.height):
                for x in range(tavern.global_origin_x, tavern.global_origin_x + tavern.width):
                    tile = self.get_tile_at(x, y)
                    if tile and hasattr(tile, 'properties') and tile.properties.get("heat_source"):
                        dist_sq = (npc.x - x)**2 + (npc.y - y)**2
                        if dist_sq < min_dist_sq:
                            min_dist_sq = dist_sq
                            closest_source_coords = (x, y)

        return closest_source_coords

    def _water_crops(self):
        """Increments the growth of crops when it rains."""
        for y_chunk in range(self.chunk_height):
            for x_chunk in range(self.chunk_width):
                chunk = self.chunks[y_chunk][x_chunk]
                if not chunk.is_terrain_generated or not chunk.tiles:
                    continue

                for y_local in range(CHUNK_SIZE):
                    for x_local in range(CHUNK_SIZE):
                        tile = chunk.tiles[y_local][x_local]
                        if tile and tile.name == "Growing Wheat":
                            tile.properties["growth_progress"] += 5 # Example growth increment

    def _update_weather(self):
        """Dynamically updates weather and handles its effects."""
        self.weather_change_timer -= 1
        if self.weather_change_timer <= 0:
            current_season = self.seasons[self.current_season_index]
            possible_weathers = []
            for weather, data in WEATHER_DEFINITIONS.items():
                if current_season in data["seasons"]:
                    possible_weathers.append(weather)

            if possible_weathers:
                self.weather = random.choice(possible_weathers)
                self.add_message_to_chat_log(self.text.weather_changed(self.weather))

            self.weather_change_timer = random.randint(DAY_LENGTH_TICKS // 2, DAY_LENGTH_TICKS * 2)

        # Process weather effects periodically, not every tick
        if self.game_time % (DAY_LENGTH_TICKS // 24) == 0:
            if self.weather == "rain":
                self._water_crops()

            # Iterate through loaded chunks for environment effects
            for y_chunk in range(self.chunk_height):
                for x_chunk in range(self.chunk_width):
                    chunk = self.chunks[y_chunk][x_chunk]
                    if not chunk.is_terrain_generated or not chunk.tiles:
                        continue

                    for y_local in range(CHUNK_SIZE):
                        for x_local in range(CHUNK_SIZE):
                            tile = chunk.tiles[y_local][x_local]
                            if not tile: continue

                            world_x = x_chunk * CHUNK_SIZE + x_local
                            world_y = y_chunk * CHUNK_SIZE + y_local

                            # Rain extinguishes fires
                            if self.weather == "rain":
                                if hasattr(tile, 'properties') and "extinguishes_to" in tile.properties:
                                    if not self._check_for_shelter(world_x, world_y):
                                        extinguishes_to_key = tile.properties["extinguishes_to"]
                                        new_tile_def = TILE_DEFINITIONS.get(extinguishes_to_key) or DECORATION_ITEM_DEFINITIONS.get(extinguishes_to_key)
                                        if new_tile_def:
                                            self._change_map_tile((world_x, world_y), new_tile_def)

                            # Flooding during storms
                            if self.weather == "storm" and random.random() < 0.001:
                                if tile.name == "Plains":
                                    # Check if near water to flood
                                    is_near_water = False
                                    for dx in [-1, 0, 1]:
                                        for dy in [-1, 0, 1]:
                                            adj = self.get_tile_at(world_x + dx, world_y + dy)
                                            if adj and "water" in adj.name.lower():
                                                is_near_water = True
                                                break
                                    if is_near_water:
                                        self._change_map_tile((world_x, world_y), TILE_DEFINITIONS["water"])

                            # Drying up during heatwave
                            if self.weather == "heatwave" and random.random() < 0.001:
                                if tile.name == "Water": # Dry up shallow water
                                    self._change_map_tile((world_x, world_y), TILE_DEFINITIONS["plains"])

    def _update_world_environment(self):
        """Handles time-based environmental changes like tree regrowth."""
        for y_chunk in range(self.chunk_height):
            for x_chunk in range(self.chunk_width):
                chunk = self.chunks[y_chunk][x_chunk]
                if not chunk.is_terrain_generated or not chunk.tiles:
                    continue

                for y_local in range(CHUNK_SIZE):
                    for x_local in range(CHUNK_SIZE):
                        tile = chunk.tiles[y_local][x_local]

                        # Tree regrowth from stump
                        if hasattr(tile, 'regrowth_timer') and tile.regrowth_timer > 0:
                            tile.regrowth_timer -= 1
                            if tile.regrowth_timer <= 0:
                                if hasattr(tile, 'original_tree_type') and tile.original_tree_type:
                                    tree_type = tile.original_tree_type
                                    world_x = x_chunk * CHUNK_SIZE + x_local
                                    world_y = y_chunk * CHUNK_SIZE + y_local

                                    new_tree = None
                                    if tree_type == "oak":
                                        new_tree = OakTree(world_x, world_y)
                                    elif tree_type == "apple":
                                        new_tree = AppleTree(world_x, world_y)
                                    elif tree_type == "pear":
                                        new_tree = PearTree(world_x, world_y)

                                    if new_tree:
                                        chunk.tiles[y_local][x_local] = new_tree
                                        # Also update the global transparency map for FOV
                                        self.transparency_map[world_x, world_y] = True # Trees are not transparent


                        # Sapling growth into tree
                        elif tile.name == "Sapling" and "growth_timer" in tile.properties:
                            tile.properties["growth_timer"] -= 1
                            if tile.properties["growth_timer"] <= 0:
                                # Determine what kind of tree it becomes
                                tree_type = tile.properties.get("evolves_to", "oak") # Default to oak
                                world_x = x_chunk * CHUNK_SIZE + x_local
                                world_y = y_chunk * CHUNK_SIZE + y_local

                                new_tree = None
                                if tree_type == "oak":
                                    new_tree = OakTree(world_x, world_y)
                                elif tree_type == "apple":
                                    new_tree = AppleTree(world_x, world_y)
                                elif tree_type == "pear":
                                    new_tree = PearTree(world_x, world_y)

                                if new_tree:
                                    chunk.tiles[y_local][x_local] = new_tree
                                    self.transparency_map[world_x, world_y] = True # Update transparency map

                        # Crop growth
                        elif tile.name == "Growing Wheat":
                            # Increment growth progress over time
                            tile.properties["growth_progress"] += 1
                            if tile.properties["growth_progress"] >= tile.properties["growth_needed"]:
                                evolves_to_key = tile.properties.get("evolves_to")
                                if evolves_to_key:
                                    new_tile_def = TILE_DEFINITIONS.get(evolves_to_key)
                                    if new_tile_def:
                                        world_x = x_chunk * CHUNK_SIZE + x_local
                                        world_y = y_chunk * CHUNK_SIZE + y_local
                                        self._change_map_tile((world_x, world_y), new_tile_def)


    def _populate_npcs(self):
        """Compatibility helper for callers expecting explicit non-village NPC population."""
        if not any(getattr(getattr(npc, "economic", None), "profession", None) == "Traveling Merchant" for npc in self.npcs):
            self._spawn_traveling_merchants()

    def _initialize_economy(self, village: Village):
        """Calculates initial supply and demand for a village."""
        village.supply = {}
        village.demand = {}

        # Calculate initial supply from all building inventories in the village
        for building in village.buildings:
            for item_key, quantity in building.building_inventory.items():
                village.supply[item_key] = village.supply.get(item_key, 0) + quantity

        # Calculate baseline demand from NPC professions and basic needs
        for npc in self.village_npcs:
            if self._get_village_for_npc(npc) != village:
                continue

            # Basic needs demand (e.g., food)
            village.demand["bread"] = village.demand.get("bread", 0) + 2 # Example: each NPC creates demand for 2 bread

            # Professional needs demand
            profession_data = get_profession_data(npc.economic.profession)
            if profession_data and profession_data.get("sub_tasks"):
                for sub_task in profession_data["sub_tasks"]:
                    consumes = sub_task.get("consumes_item_from_workplace", {})
                    for item_key, qty in consumes.items():
                        village.demand[item_key] = village.demand.get(item_key, 0) + 5 # Baseline demand of 5 for each required resource

    def _populate_village_npcs(self, chunk: Chunk, village: Village, chunk_coord_x: int, chunk_coord_y: int): # Added chunk_coord_x, chunk_coord_y
        """Populates a village with NPCs, assigning them homes and potentially jobs."""
        # chunk_global_start_x and chunk_global_start_y are now implicitly handled by Building.global_center_x/y
        # No longer need to calculate chunk_global_start_x/y here from chunk_coord_x/y for NPC placement if using building centers.

        num_npcs = random.randint(max(1, len(village.buildings) // 2), len(village.buildings))
        if not village.buildings:
            num_npcs = 0

        residential_buildings = [b for b in village.buildings if b.category == "residential"]
        workplace_buildings = [b for b in village.buildings if "workplace" in b.category] # e.g., "civic_workplace", "commercial_workplace"

        available_homes = list(residential_buildings)
        available_workplaces = list(workplace_buildings)
        random.shuffle(available_homes)
        random.shuffle(available_workplaces)

        for i in range(num_npcs):
            # npc_data = {
            #     "name": f"Villager {i+1}",
            #     "dialogue": ["Greetings."],
            #     "personality": "commoner",
            #     "family_ties": "none",
            #     "attitude_to_player": "neutral",
            #     "wealth_level": random.choice(["poor", "average", "wealthy"]),
            #     "combat_behavior": "defensive",
            #     "base_attack_name": "fists"
            # }
            llm_prompt = LLM_PROMPTS["npc_personality"].format(
                player_criminal_points=self.player.social.reputation.get(REP_CRIMINAL, 0),
                player_hero_points=self.player.social.reputation.get(REP_HERO, 0),
                name_hint="",
                personality_hint="",
                family_ties_hint="",
                attitude_to_player_hint=""
            )
            llm_response = self._call_llm_for_worldgen(llm_prompt)
            try:
                npc_data = json.loads(llm_response)
                # Assign home
                if not available_homes:
                    # self.add_message_to_chat_log("Warning: No available homes for new NPC.")
                    # Create NPC without a home, or handle differently
                    home_building = None
                    npc_x = chunk_coord_x * CHUNK_SIZE + CHUNK_SIZE // 2
                    npc_y = chunk_coord_y * CHUNK_SIZE + CHUNK_SIZE // 2
                else:
                    home_building = available_homes.pop(0)
                    # Place NPC at the global center of their home building
                    npc_x = home_building.global_center_x
                    npc_y = home_building.global_center_y

                # Ensure NPC is within world bounds (still good practice)
                npc_x = max(0, min(WORLD_WIDTH - 1, npc_x))
                npc_y = max(0, min(WORLD_HEIGHT - 1, npc_y))

                # Assign workplace (optional)
                work_building = None
                if available_workplaces and random.random() < 0.7: # 70% chance to get a job if available
                    work_building = available_workplaces.pop(0) # Assign and remove

                npc = NPC(
                    x=npc_x,
                    y=npc_y,
                    name=npc_data.get("name", f"Villager {i+1}"),
                    dialogue=npc_data.get("dialogue", ["Greetings."]),
                    personality=npc_data.get("personality", "commoner"),
                    family_ties=npc_data.get("family_ties", "none"),
                    attitude_to_player=npc_data.get("attitude_to_player", "neutral"),
                    player_id=self.player.id
                )

                # Assign wealth (randomly for now) - This is now part of LLM prompt for personality
                npc.economic.wealth_level = npc_data.get("wealth_level", random.choice(["poor", "average", "wealthy"]))

                # Combat AI attributes from LLM
                npc.combat.combat_behavior = npc_data.get("combat_behavior", "defensive")
                npc.combat.base_attack_name = npc_data.get("base_attack_name", "fists")

                # Basic logic for damage dice based on attack name or behavior
                # More sophisticated logic could be added here, e.g., guards get better defaults
                if "knife" in npc.combat.base_attack_name.lower() or \
                   "dagger" in npc.combat.base_attack_name.lower() or \
                   "tool" in npc.combat.base_attack_name.lower() or \
                   "hammer" in npc.combat.base_attack_name.lower() or \
                   "claws" in npc.combat.base_attack_name.lower() or \
                   "teeth" in npc.combat.base_attack_name.lower() or \
                   "spear" in npc.combat.base_attack_name.lower():
                    npc.combat.base_attack_damage_dice = "1d4"
                elif "sword" in npc.combat.base_attack_name.lower() or \
                     "axe" in npc.combat.base_attack_name.lower() or \
                     "mace" in npc.combat.base_attack_name.lower():
                    npc.combat.base_attack_damage_dice = "1d6"
                else: # fists, kick, staff, etc.
                    npc.combat.base_attack_damage_dice = "1d3"

                if npc.combat.combat_behavior == "aggressive" and npc.combat.base_attack_damage_dice == "1d3":
                    npc.combat.base_attack_damage_dice = "1d4" # Aggressive NPCs might hit a bit harder by default

                npc.combat.attack_range = 1 # Default melee

                # Assign profession based on work building
                if work_building:
                    npc.schedule.work_building_id = work_building.id
                    work_building.occupants.append(npc) # Store NPC object for now
                    resolved_profession = self._resolve_profession_for_work_building(work_building, exclude_entity=npc)
                    self._set_entity_profession(npc, resolved_profession, reason="initial_job_assignment")
                else:
                    self._set_entity_profession(npc, "Unemployed", reason="initial_unemployed")

                # If NPC is a Merchant and assigned to a general store, pre-populate store inventory
                if npc.economic.profession == "Merchant" and work_building and work_building.building_type == "general_store":
                    # Add some starting cash for the store to buy items
                    work_building.building_inventory["money"] = random.randint(150, 500)
                    # Add some items for sale
                    work_building.building_inventory["axe_stone"] = random.randint(1, 3)
                    work_building.building_inventory["healing_salve"] = random.randint(3, 8)
                    work_building.building_inventory["wooden_plank"] = random.randint(10, 30)
                    if random.random() < 0.5: # Chance to have some logs
                        work_building.building_inventory["raw_log"] = random.randint(5, 20)
                    # self.add_message_to_chat_log(f"Stocked General Store ({work_building.id[:6]}) for Merchant {npc.name}.")
                elif work_building and work_building.building_type in {"lumber_mill", "blacksmith_shop", "tavern", "bakery", "mill"}:
                    if work_building.building_inventory.get("money", 0) <= 0:
                        work_building.building_inventory["money"] = random.randint(80, 220)

                if home_building:
                    npc.schedule.home_building_id = home_building.id
                    home_building.residents.append(npc)
                    # Seed initial knowledge of home and workplace
                    npc.knowledge.known_locations[f"my home"] = (home_building.global_center_x, home_building.global_center_y)
                if work_building:
                    npc.knowledge.known_locations[f"my workplace"] = (work_building.global_center_x, work_building.global_center_y)

                # A subset of villagers know about key public locations to bootstrap knowledge spread
                if random.random() < 0.3: # 30% of villagers have this extra knowledge
                    tavern = next((b for b in village.buildings if b.building_type == "tavern"), None)
                    if tavern:
                        npc.knowledge.known_locations["the tavern"] = (tavern.global_center_x, tavern.global_center_y)

                    general_store = next((b for b in village.buildings if b.building_type == "general_store"), None)
                    if general_store:
                        npc.knowledge.known_locations["the general store"] = (general_store.global_center_x, general_store.global_center_y)

                    if "well" in village.interaction_points and village.interaction_points["well"]:
                        well_coords = village.interaction_points["well"][0]
                        npc.knowledge.known_locations["the village well"] = well_coords

                # Chance to give NPC a healing salve
                if random.random() < 0.33: # 33% chance
                    npc.economic.npc_inventory["healing_salve"] = npc.economic.npc_inventory.get("healing_salve", 0) + 1
                    # self.add_message_to_chat_log(f"Debug: {npc.name} received a healing salve.")

                # Assign starting equipment based on role/behavior
                if npc.economic.profession in ["Sheriff", "Guard"] or npc.combat.combat_behavior == "aggressive":
                    if "rusty_sword" in ITEM_DEFINITIONS:
                        npc.economic.npc_inventory["rusty_sword"] = npc.economic.npc_inventory.get("rusty_sword", 0) + 1
                        npc.equipment.weapon = "rusty_sword"
                        # self.add_message_to_chat_log(f"Debug: {npc.name} equipped a rusty_sword.")
                    if "leather_jerkin" in ITEM_DEFINITIONS:
                        npc.economic.npc_inventory["leather_jerkin"] = npc.economic.npc_inventory.get("leather_jerkin", 0) + 1
                        npc.equipment.body = "leather_jerkin"
                        # self.add_message_to_chat_log(f"Debug: {npc.name} equipped a leather_jerkin.")
                    # Optionally, add a helmet too
                    if random.random() < 0.5 and "iron_helmet" in ITEM_DEFINITIONS: # 50% chance for guards/aggressive to also have helmet
                        npc.economic.npc_inventory["iron_helmet"] = npc.economic.npc_inventory.get("iron_helmet", 0) + 1
                        npc.equipment.head = "iron_helmet"


                self.village_npcs.append(npc)
                self._mark_entity_positions_dirty()
                self.add_message_to_chat_log(
                    f"Generated Villager: {npc.name} (Wealth: {npc.economic.wealth_level}, Prof: {npc.economic.profession}). "
                    f"Home: {home_building.building_type if home_building else 'N/A'}. "
                    f"Work: {work_building.building_type if work_building else 'N/A'}."
                )

            except json.JSONDecodeError as e:
                self.add_message_to_chat_log(f"Error parsing LLM response for Villager NPC: {e}")
                self.add_message_to_chat_log(f"LLM Response: {llm_response}")
            except IndexError: # Ran out of homes or workplaces
                self.add_message_to_chat_log(f"Could not place NPC {npc_data.get('name', 'Unknown')} due to lack of available buildings.")


    def apply_animation_cue(self, cue: str, *, interaction=None, result=None) -> None:
        if cue == "build" and hasattr(self, "visual_effects") and interaction is not None:
            target_pos = getattr(interaction, "target_pos", None)
            if target_pos is not None:
                self.visual_effects.append(FloatingTextEffect(target_pos[0], target_pos[1], "*building*", color=(180, 180, 120)))

    def advance_active_interactions(self) -> None:
        from simulation.systems.tick import advance_active_interactions

        advance_active_interactions(self)

    def on_active_interaction_finished(self, *, actor=None, interaction=None, result=None) -> None:
        if actor is not None and getattr(actor, "task_context", None) == "construction":
            self._handle_npc_construction_task(actor)
        if getattr(interaction, "action_type", None) == "workshop_transform":
            workshop_id = getattr(interaction, "workshop_id", None)
            workshop = self.workshops_by_id.get(workshop_id)
            if workshop is not None and workshop.output_buffer.get("wooden_plank", 0) > 0:
                stockpile = self.find_stockpile_for_item("wooden_plank", require_capacity=True, near=(workshop.x, workshop.y))
                while stockpile is not None and workshop.output_buffer.get("wooden_plank", 0) > 0:
                    item = workshop.output_buffer.pop_item_reference("wooden_plank")
                    if item is None or not self.deposit_item_reference_into_stockpile(stockpile.stockpile_id, item, actor=actor):
                        if item is not None:
                            workshop.output_buffer.add_item_reference(item)
                        break
            matched_task_id = getattr(interaction, "production_task_id", None)
            if matched_task_id and matched_task_id in self.production_tasks_by_id:
                task = self.production_tasks_by_id[matched_task_id]
                if task.task_type == "craft_plank" and task.status not in {"completed", "failed", "cancelled"}:
                    task.status = "completed"
                    self._record_production_task_trace("craft_task_completion_matched", task, actor=actor, metadata={"workshop_id": workshop_id, "interaction_id": getattr(interaction, "interaction_id", None)})
                    self._mark_production_task_progress(task, int(getattr(self, "game_time", 0) or 0), actor=actor, trace_type="craft_task_completed", metadata={"workshop_id": workshop_id})
            else:
                self._warn_simulation_validation("craft_task_completion_mismatch", (workshop_id, getattr(interaction, "interaction_id", None)), "Workshop interaction completed without a matching craft task link.", actor=actor, cooldown_ticks=180)


    def on_tree_resource_created(self, *, item_key: str, coords: tuple[int, int], actor_id=None) -> None:
        if item_key != "raw_log":
            return
        trace_log = getattr(self, "interaction_trace_log", None)
        if trace_log is None:
            trace_log = []
            setattr(self, "interaction_trace_log", trace_log)
        trace_log.append({
            "tick": getattr(self, "game_time", None),
            "interaction_id": None,
            "actor_id": actor_id,
            "action_type": "resource_pipeline",
            "trace_type": "raw_log_created",
            "metadata": {"item_key": item_key, "coords": coords},
        })

    def _assign_source_to_stockpile_haul_task(self, npc: NPC, *, item_key: str = "raw_log") -> bool:
        if getattr(npc, "task_context", None) in {"hauling", "delivery", "construction"}:
            return False
        source = self._find_nearest_haul_source(npc, item_key)
        if source is None:
            return False
        if source.get("source_type") == "stockpile":
            self._warn_simulation_validation("produce_logs_invalid_source_selection", (getattr(npc, "id", None), item_key), "Source->stockpile flow skipped incompatible stockpile source.", actor=npc, metadata={"item_key": item_key}, cooldown_ticks=180)
            self._record_production_task_trace("produce_logs_source_candidate_skipped", ProductionTask(task_type="produce_logs", id=str(getattr(npc, "id", 0))), actor=npc, metadata={"item_key": item_key, "reason": "stockpile_source_incompatible"})
            self._record_decision_explanation(explanation_type="source_candidate_skipped", decision="source_skipped", primary_reason="incompatible_stockpile_source_for_source_to_stockpile_flow", actor=npc, contributing_factors={"item_key": item_key})
            # fallback to nearest non-stockpile ground source
            ground_candidates: list[tuple[int, dict]] = []
            for coords, inv in getattr(self, "items_on_map", {}).items():
                if inv is None or getattr(inv, "get", lambda *_: 0)(item_key, 0) <= 0:
                    continue
                dist = abs(npc.x - coords[0]) + abs(npc.y - coords[1])
                ground_candidates.append((dist, {"source_type": "ground", "coords": coords, "item_key": item_key}))
            if not ground_candidates:
                return False
            ground_candidates.sort(key=lambda e: (e[0], e[1]["coords"]))
            source = ground_candidates[0][1]
            self._record_production_task_trace("produce_logs_source_fallback_selected", ProductionTask(task_type="produce_logs", id=str(getattr(npc, "id", 0))), actor=npc, metadata={"item_key": item_key, "coords": source.get("coords")})
            self._record_decision_explanation(explanation_type="source_fallback_selected", decision="source_selected", primary_reason="ground_source_selected_after_incompatible_stockpile_source", actor=npc, contributing_factors={"item_key": item_key, "coords": source.get("coords")})
        stockpile = self.find_stockpile_for_item(item_key, require_capacity=True, near=source.get("coords"))
        if stockpile is None:
            return False
        reservation_id = f"stockpile-dest:{getattr(npc, 'id', None)}:{item_key}:{source.get('coords')}"
        npc.schedule.current_task = "hauling_to_source"
        npc.current_sub_task = f"Stockpiling {item_key}"
        npc.task_context = "stockpile_hauling"
        npc.task_context_data = {
            "item_key": item_key,
            "source": source,
            "destination_stockpile_id": stockpile.stockpile_id,
            "stockpile_reservation_id": reservation_id,
        }
        npc.schedule.current_destination_coords = source.get("coords")
        npc.schedule.current_path = self.calculate_path(npc.x, npc.y, source["coords"][0], source["coords"][1]) or []
        self._record_stockpile_trace("haul_to_stockpile_assigned", stockpile, actor=npc, metadata={"item_key": item_key, "source": source})
        return True

    def _is_actor_adjacent_to_position(self, actor, position: tuple[int, int]) -> bool:
        return actor is not None and abs(actor.x - position[0]) <= 1 and abs(actor.y - position[1]) <= 1

    def _route_actor_toward_position(self, actor, position: tuple[int, int], *, reason: str, task_id: str | None = None) -> bool:
        if actor is None:
            return False
        path = self.calculate_path(actor.x, actor.y, position[0], position[1]) or []
        actor.schedule.current_destination_coords = position
        actor.schedule.current_path = path
        self._record_decision_explanation(explanation_type="actor_routed_to_workshop" if "workshop" in reason else "actor_routed_to_campfire", decision="routed", primary_reason=reason, actor=actor, contributing_factors={"task_id": task_id, "target": position})
        return bool(path) or self._is_actor_adjacent_to_position(actor, position)

    def _handle_npc_stockpile_haul_task(self, npc: NPC) -> bool:
        if getattr(npc, "task_context", None) != "stockpile_hauling":
            return False
        data = npc.task_context_data if isinstance(npc.task_context_data, dict) else {}
        source = data.get("source", {})
        stockpile_id = data.get("destination_stockpile_id")
        stockpile = self.stockpiles_by_id.get(stockpile_id)
        if stockpile is None:
            self._warn_simulation_validation("invalid_stockpile", (stockpile_id, "stockpile_haul"), "Stockpile haul destination is missing.", actor=npc)
            self._clear_npc_haul_task(npc, release_claim=True)
            return False
        if npc.schedule.current_task == "hauling_to_source":
            if (npc.x, npc.y) != tuple(source.get("coords", ())):
                if not npc.schedule.current_path:
                    npc.schedule.current_path = self.calculate_path(npc.x, npc.y, source["coords"][0], source["coords"][1]) or []
                return bool(npc.schedule.current_path)
            if not self._pickup_haul_task_material(npc, data):
                self._record_stockpile_trace("haul_to_stockpile_failed", stockpile, actor=npc, metadata={"item_key": data.get("item_key"), "reason": "missing_source_item"})
                self._clear_npc_haul_task(npc, release_claim=True)
                return False
            npc.schedule.current_task = "hauling_to_stockpile"
            npc.schedule.current_destination_coords = stockpile.position
            npc.schedule.current_path = self.calculate_path(npc.x, npc.y, stockpile.x, stockpile.y) or []
            self._record_stockpile_trace("haul_to_stockpile_started", stockpile, actor=npc, metadata={"item_key": data.get("item_key")})
            return True
        if npc.schedule.current_task == "hauling_to_stockpile":
            if (npc.x, npc.y) != stockpile.position:
                if not npc.schedule.current_path:
                    npc.schedule.current_path = self.calculate_path(npc.x, npc.y, stockpile.x, stockpile.y) or []
                return bool(npc.schedule.current_path)
            item_ref = npc.economic.npc_inventory.pop_item_reference(data.get("item_key"))
            if item_ref is None or not self.deposit_item_reference_into_stockpile(stockpile.stockpile_id, item_ref, actor=npc):
                if item_ref is not None:
                    npc.economic.npc_inventory.add_item_reference(item_ref)
                self._record_stockpile_trace("haul_to_stockpile_failed", stockpile, actor=npc, metadata={"item_key": data.get("item_key"), "reason": "deposit_failed"})
                self._clear_npc_haul_task(npc, release_claim=True)
                return False
            self._record_stockpile_trace("haul_to_stockpile_delivered", stockpile, actor=npc, metadata={"item_key": data.get("item_key")})
            self._clear_npc_haul_task(npc, release_claim=False)
            return True
        return False

    def create_workshop_runtime(self, x: int, y: int, *, workshop_type: str = "sawbench", workshop_id: str | None = None) -> WorkshopRuntimeState:
        wid = workshop_id or str(uuid.uuid4())
        workshop = WorkshopRuntimeState(workshop_id=wid, workshop_type=workshop_type, x=int(x), y=int(y))
        self.workshops_by_id[wid] = workshop
        trace_log = getattr(self, "interaction_trace_log", None)
        if trace_log is None:
            trace_log = []
            setattr(self, "interaction_trace_log", trace_log)
        trace_log.append({"tick": getattr(self, "game_time", None), "interaction_id": None, "actor_id": None, "action_type": "workshop", "trace_type": "workshop_reserved", "metadata": {"workshop_id": wid, "workshop_type": workshop_type, "coords": (x, y)}})
        return workshop

    def _find_operational_workshop(self, workshop_type: str = "sawbench") -> WorkshopRuntimeState | None:
        candidates = [w for w in self.workshops_by_id.values() if w.workshop_type == workshop_type and w.operational]
        if not candidates:
            return None
        candidates.sort(key=lambda w: (w.last_used_tick, w.workshop_id))
        return candidates[0]

    def _reserve_workshop_for_actor(self, workshop: WorkshopRuntimeState, actor_id: int | None) -> bool:
        now = int(getattr(self, "game_time", 0) or 0)
        if actor_id is None:
            self._warn_simulation_validation("workshop_reservation_missing_actor", (workshop.workshop_id, "none"), "Workshop reservation requires a valid actor id.", metadata={"workshop_id": workshop.workshop_id}, cooldown_ticks=180)
            self._record_decision_explanation(explanation_type="actor_skipped", decision="reservation_rejected", primary_reason="missing_actor_id_for_workshop_reservation", source_entity_id=workshop.workshop_id)
            trace_log = getattr(self, "interaction_trace_log", None)
            if isinstance(trace_log, list):
                trace_log.append({"tick": now, "interaction_id": None, "actor_id": None, "action_type": "workshop", "trace_type": "workshop_reservation_rejected", "metadata": {"workshop_id": workshop.workshop_id}})
            return False
        if workshop.occupied_by_actor_id is not None and workshop.occupied_by_actor_id != actor_id and now <= workshop.lock_expiration_tick:
            self._warn_simulation_validation("workshop_assignment_conflict", (workshop.workshop_id, actor_id), "Workshop already occupied by another actor.", metadata={"workshop_id": workshop.workshop_id, "occupied_by": workshop.occupied_by_actor_id})
            return False
        workshop.occupied_by_actor_id = actor_id
        workshop.lock_expiration_tick = now + 120
        workshop.last_used_tick = now
        return True

    def _release_workshop_lock(self, workshop: WorkshopRuntimeState, actor_id: int | None = None) -> None:
        if actor_id is not None and workshop.occupied_by_actor_id not in {None, actor_id}:
            return
        workshop.occupied_by_actor_id = None
        workshop.active_interaction_id = None
        workshop.lock_expiration_tick = 0
        workshop.reserved_input_entity_ids = []

    def _record_production_task_trace(self, trace_type: str, task: ProductionTask, *, actor=None, metadata: dict | None = None) -> None:
        trace_log = getattr(self, "interaction_trace_log", None)
        if trace_log is None:
            trace_log = []
            setattr(self, "interaction_trace_log", trace_log)
        trace_log.append({
            "tick": getattr(self, "game_time", None),
            "interaction_id": None,
            "actor_id": getattr(actor, "id", None),
            "action_type": "production_task",
            "trace_type": trace_type,
            "metadata": {"production_task_id": task.id, "task_type": task.task_type, **dict(metadata or {})},
        })

    def _record_decision_explanation(self, *, explanation_type: str, decision: str, primary_reason: str, task: ProductionTask | None = None, actor=None, source_entity_id=None, target_entity_id=None, contributing_factors: dict | None = None, score_snapshot: dict | None = None, created_from: str = "runtime") -> str:
        tick = int(getattr(self, "game_time", 0) or 0)
        explanation_id = str(uuid.uuid4())
        rec = DecisionExplanation(
            explanation_id=explanation_id,
            tick=tick,
            explanation_type=explanation_type,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            task_id=getattr(task, "id", None),
            actor_id=getattr(actor, "id", None),
            decision=decision,
            primary_reason=primary_reason,
            contributing_factors=dict(contributing_factors or {}),
            score_snapshot=dict(score_snapshot or {}),
            created_from=created_from,
        )
        store = getattr(self, "decision_explanations", None)
        if not isinstance(store, list):
            store = []
            self.decision_explanations = store
        store.append(rec)
        if len(store) > 400:
            del store[: len(store) - 400]
            self._warn_simulation_validation("decision_explanation_overflow", ("decision_explanations", len(store)), "Decision explanation history exceeded bound and was trimmed.", metadata={"max_size": 400}, cooldown_ticks=240)
        trace_log = getattr(self, "interaction_trace_log", None)
        if isinstance(trace_log, list):
            trace_log.append({"tick": tick, "interaction_id": None, "actor_id": getattr(actor, "id", None), "action_type": "decision_explanation", "trace_type": "decision_explanation_created", "metadata": {"explanation_id": explanation_id, "task_id": getattr(task, "id", None), "decision": decision, "primary_reason": primary_reason}})
        return explanation_id

    def get_task_decision_explanation(self, task_id: str) -> str:
        items = [e for e in getattr(self, "decision_explanations", []) if e.task_id == task_id]
        if not items:
            return f"No decision explanation recorded for task {task_id}."
        latest = items[-1]
        return f"Task {task_id} {latest.decision} because {latest.primary_reason}."

    def get_actor_assignment_explanation(self, actor_id: int) -> str:
        items = [e for e in getattr(self, "decision_explanations", []) if e.actor_id == actor_id and e.explanation_type in {"actor_assigned", "actor_skipped"}]
        if not items:
            return f"No assignment explanation recorded for actor {actor_id}."
        latest = items[-1]
        return f"Actor {actor_id} {latest.decision} because {latest.primary_reason}."

    def get_recent_decision_explanations(self, limit: int = 20) -> list[dict[str, object]]:
        limit = max(1, min(100, int(limit)))
        items = list(getattr(self, "decision_explanations", []) or [])[-limit:]
        return [
            {
                "explanation_id": e.explanation_id,
                "tick": e.tick,
                "type": e.explanation_type,
                "task_id": e.task_id,
                "actor_id": e.actor_id,
                "decision": e.decision,
                "reason": e.primary_reason,
            }
            for e in items
        ]

    def build_world_debug_snapshot(self, *, trace_limit: int = 20, warning_limit: int = 20, explanation_limit: int = 20) -> WorldDebugSnapshot:
        try:
            tick = int(getattr(self, "game_time", 0) or 0)
            trace_limit = max(1, min(200, int(trace_limit)))
            warning_limit = max(1, min(200, int(warning_limit)))
            explanation_limit = max(1, min(200, int(explanation_limit)))
            reserves = []
            for target in getattr(self, "reserve_targets_by_id", {}).values():
                shortage = max(0, int(target.desired_quantity) - int(target.current_quantity))
                reserves.append({
                    "reserve_target_id": target.reserve_target_id,
                    "item": target.linked_item_type,
                    "current": target.current_quantity,
                    "minimum": target.minimum_quantity,
                    "desired": target.desired_quantity,
                    "shortage": shortage,
                    "active_task_ids": list(target.active_task_ids)[:5],
                    "cooldown_until_tick": target.cooldown_until_tick,
                })
            tasks = []
            for task in getattr(self, "production_tasks_by_id", {}).values():
                if task.status in {"completed", "failed", "cancelled"}:
                    continue
                tasks.append({"task_id": task.id, "task_type": task.task_type, "status": task.status, "priority": task.priority, "urgency": task.urgency, "blocked_reason": task.blocked_reason, "assigned_actor_ids": list(task.assigned_actor_ids), "reserved_entity_ids": list(task.reserved_entity_ids), "target_entity_id": task.target_entity_id, "routing_state": {"moving_to_workshop": bool(task.metadata.get("moving_to_workshop", False)), "moving_to_campfire": bool(task.metadata.get("moving_to_campfire", False))}})
                tasks[-1]["inherited_priority"] = task.inherited_priority
                tasks[-1]["prerequisite_item_types"] = list(task.prerequisite_item_types)
                tasks[-1]["blocked_by_task_ids"] = list(task.blocked_by_task_ids)
            interactions = []
            for iid, interaction in getattr(getattr(self, "interaction_resolver", None), "active_interactions", {}).items():
                interactions.append({"interaction_id": iid, "actor_id": getattr(interaction, "actor_id", None), "action_type": getattr(interaction, "action_type", None), "target_id": getattr(interaction, "target_id", None), "remaining_work": getattr(interaction, "remaining_work", None)})
            actors = []
            for actor in getattr(self, "village_npcs", []):
                profile = getattr(actor, "actor_work_profile", {}) or {}
                actors.append({"actor_id": getattr(actor, "id", None), "current_task": getattr(getattr(actor, "schedule", None), "current_task", None), "task_context": getattr(actor, "task_context", None), "work_identity_label": profile.get("work_identity_label"), "dominant_work_tag": profile.get("dominant_work_tag"), "fatigue_state": profile.get("fatigue_state"), "recent_work_summary": profile.get("recent_work_summary"), "cold_exposure": float(getattr(actor, "cold_exposure", 0.0) or 0.0), "sheltered_state": bool(getattr(actor, "sheltered_state", False)), "current_shelter_id": getattr(actor, "current_shelter_id", None), "survival_override_active": bool(getattr(actor, "survival_override_active", False)), "survival_override_reason": getattr(actor, "survival_override_reason", None), "survival_override_target_id": getattr(actor, "survival_override_target_id", None), "survival_override_target_position": getattr(actor, "survival_override_target_position", None), "survival_override_recovery_threshold": float(getattr(actor, "survival_override_recovery_threshold", 0.0) or 0.0), "survival_override_cooldown_until_tick": int(getattr(actor, "survival_override_cooldown_until_tick", 0) or 0), "route_target": getattr(getattr(actor, "schedule", None), "current_destination_coords", None)})
            stockpiles = []
            for sp in getattr(self, "stockpiles_by_id", {}).values():
                stockpiles.append({"stockpile_id": sp.stockpile_id, "accepted_item_types": sorted(sp.accepted_item_types), "inventory": dict(sp.stored_inventory), "reservation_count": len(sp.reservations), "capacity": sp.max_item_count, "total_items": sp.total_item_count()})
            workshops = []
            for ws in getattr(self, "workshops_by_id", {}).values():
                workshops.append({"workshop_id": ws.workshop_id, "type": ws.workshop_type, "occupied_by_actor_id": ws.occupied_by_actor_id, "active_interaction_id": ws.active_interaction_id, "input_buffer": dict(ws.input_buffer), "output_buffer": dict(ws.output_buffer), "operational": ws.operational})
            campfires = []
            for cf in getattr(self, "campfires_by_id", {}).values():
                campfires.append({"campfire_id": cf.campfire_id, "position": (cf.x, cf.y), "lit": cf.lit, "operational": cf.operational, "fuel_quantity": cf.fuel_quantity, "min_fuel": cf.minimum_fuel_quantity, "max_fuel": cf.max_fuel_quantity, "linked_reserve_target_id": cf.linked_reserve_target_id, "last_burn_tick": cf.last_burn_tick, "last_refuel_tick": cf.last_refuel_tick})
            explanations = self.get_recent_decision_explanations(explanation_limit)
            warnings = list(getattr(self, "validation_warnings", []) or [])[-warning_limit:]
            traces = list(getattr(self, "interaction_trace_log", []) or [])[-trace_limit:]
            health = {"active_interaction_count": len(interactions), "active_task_count": len(tasks), "warning_count": len(getattr(self, "validation_warnings", []) or []), "decision_explanation_count": len(getattr(self, "decision_explanations", []) or []), "next_reserve_eval_tick": self.next_reserve_eval_tick, "next_production_eval_tick": self.next_production_eval_tick, "next_dependency_eval_tick": self.next_dependency_eval_tick, "score_cache_size": len(getattr(self, "_production_score_cache", {})), "suitability_cache_size": len(getattr(self, "_actor_suitability_cache", {})), "shelter_zone_count": len(getattr(self, "shelter_zones_by_id", {})), "ambient_temperature": self.ambient_temperature}
            return WorldDebugSnapshot(tick=tick, reserve_targets=reserves, production_tasks=tasks, active_interactions=interactions, actor_work_profiles=actors, stockpiles=stockpiles, workshops=workshops + campfires, recent_decision_explanations=explanations, recent_validation_warnings=warnings, recent_traces=traces, runtime_health_summary=health)
        except Exception:
            self._warn_simulation_validation("debug_snapshot_build_failed", ("world_snapshot", int(getattr(self, "game_time", 0) or 0)), "World debug snapshot build failed.", cooldown_ticks=240)
            return WorldDebugSnapshot(tick=int(getattr(self, "game_time", 0) or 0))

    def render_world_debug_snapshot(self, snapshot: WorldDebugSnapshot) -> str:
        lines = ["WORLD RUNTIME SNAPSHOT", f"Tick: {snapshot.tick}", "", "RESERVE PRESSURE"]
        for reserve in snapshot.reserve_targets[:8]:
            lines.append(f"- {reserve['reserve_target_id']}: {reserve['item']} {reserve['current']}/{reserve['minimum']}/{reserve['desired']} shortage={reserve['shortage']}")
        lines.append("")
        lines.append("PRODUCTION TASKS")
        for task in snapshot.production_tasks[:10]:
            lines.append(f"- {task['task_id']} {task['task_type']} status={task['status']} p={task['priority']} u={task['urgency']} blocked={task['blocked_reason']}")
        lines.append("")
        lines.append("ACTORS")
        for actor in snapshot.actor_work_profiles[:10]:
            lines.append(f"- {actor['actor_id']} {actor['work_identity_label']} dominant={actor['dominant_work_tag']} fatigue={actor['fatigue_state']} task={actor['current_task']}")
        lines.append("")
        lines.append("ACTIVE INTERACTIONS")
        for interaction in snapshot.active_interactions[:10]:
            lines.append(f"- {interaction['interaction_id']} {interaction['action_type']} actor={interaction['actor_id']} remaining={interaction['remaining_work']}")
        lines.append("")
        lines.append("LOGISTICS")
        for ws in snapshot.workshops[:10]:
            if "campfire_id" in ws:
                lines.append(f"- campfire {ws['campfire_id']} fuel={ws['fuel_quantity']}/{ws['max_fuel']} lit={ws['lit']}")
        lines.append("")
        lines.append("RECENT DECISIONS")
        for item in snapshot.recent_decision_explanations[:10]:
            lines.append(f"- [{item.get('type')}] task={item.get('task_id')} actor={item.get('actor_id')} decision={item.get('decision')} reason={item.get('reason')}")
        lines.append("")
        lines.append("WARNINGS")
        for warning in snapshot.recent_validation_warnings[:10]:
            lines.append(f"- {warning.get('warning_type')} key={warning.get('key')}")
        return "\n".join(lines)

    def create_production_task(self, task_type: str, *, target_entity_id=None, metadata: dict | None = None, expiration_ticks: int = 600) -> ProductionTask:
        now_tick = int(getattr(self, "game_time", 0) or 0)
        payload = dict(metadata or {})
        task = ProductionTask(
            task_type=task_type,
            target_entity_id=target_entity_id,
            created_tick=now_tick,
            expiration_tick=now_tick + max(1, int(expiration_ticks)),
            metadata=payload,
            priority=max(1, int(payload.get("priority", 1))),
            urgency=max(0, int(payload.get("urgency", 0))),
            last_progress_tick=now_tick,
        )
        self.production_tasks_by_id[task.id] = task
        self._record_production_task_trace("production_task_created", task)
        return task

    def create_reserve_target(self, *, target_type: str = "stockpile_item", target_entity_id: str | None = None, linked_item_type: str = "raw_log", desired_quantity: int = 4, minimum_quantity: int = 1, priority: int = 2) -> ReserveTarget:
        reserve_id = str(uuid.uuid4())
        target = ReserveTarget(
            reserve_target_id=reserve_id,
            target_type=target_type,
            target_entity_id=target_entity_id,
            desired_quantity=max(1, int(desired_quantity)),
            minimum_quantity=max(0, int(minimum_quantity)),
            linked_item_type=linked_item_type,
            priority=max(1, int(priority)),
        )
        self.reserve_targets_by_id[reserve_id] = target
        self._record_production_task_trace("reserve_target_created", ProductionTask(task_type="reserve_target", id=reserve_id), metadata={"reserve_target_id": reserve_id, "target_type": target_type, "item_key": linked_item_type})
        return target

    def create_campfire_runtime(self, x: int, y: int, *, fuel_item_type: str = "raw_log", fuel_quantity: int = 4, max_fuel_quantity: int = 10, minimum_fuel_quantity: int = 2, burn_rate_per_tick: int = 1) -> CampfireRuntimeState:
        campfire_id = str(uuid.uuid4())
        cf = CampfireRuntimeState(campfire_id=campfire_id, x=int(x), y=int(y), fuel_item_type=fuel_item_type, fuel_quantity=max(0, int(fuel_quantity)), max_fuel_quantity=max(1, int(max_fuel_quantity)), minimum_fuel_quantity=max(0, int(minimum_fuel_quantity)), burn_rate_per_tick=max(1, int(burn_rate_per_tick)))
        self.campfires_by_id[campfire_id] = cf
        rt = self.create_reserve_target(target_type="campfire_fuel", target_entity_id=campfire_id, linked_item_type=fuel_item_type, desired_quantity=cf.max_fuel_quantity, minimum_quantity=cf.minimum_fuel_quantity, priority=4)
        cf.linked_reserve_target_id = rt.reserve_target_id
        self._record_production_task_trace("campfire_created", ProductionTask(task_type="campfire", id=campfire_id), metadata={"campfire_id": campfire_id, "fuel": cf.fuel_quantity})
        return cf

    def create_shelter_zone(self, positions: list[tuple[int, int]], *, shelter_type: str = "basic", exposure_reduction_modifier: float = 0.6, recovery_modifier: float = 1.2) -> str:
        sid = str(uuid.uuid4())
        erm = max(0.2, min(1.0, float(exposure_reduction_modifier)))
        rm = max(1.0, min(2.0, float(recovery_modifier)))
        self.shelter_zones_by_id[sid] = {"shelter_id": sid, "positions": set((int(x), int(y)) for x, y in positions), "shelter_type": shelter_type, "exposure_reduction_modifier": erm, "recovery_modifier": rm, "active": True}
        return sid

    def get_shelter_exposure_modifier(self, position: tuple[int, int]) -> tuple[bool, float, float, str | None]:
        for sid, zone in self.shelter_zones_by_id.items():
            if zone.get("active", True) and position in zone.get("positions", set()):
                return True, float(zone.get("exposure_reduction_modifier", 0.6)), float(zone.get("recovery_modifier", 1.2)), sid
        return False, 1.0, 1.0, None

    def advance_campfires(self) -> None:
        now = int(getattr(self, "game_time", 0) or 0)
        for cf in self.campfires_by_id.values():
            if not cf.operational or not cf.lit:
                continue
            if now <= cf.last_burn_tick:
                continue
            cf.last_burn_tick = now
            cf.fuel_quantity -= cf.burn_rate_per_tick
            self._record_production_task_trace("campfire_fuel_consumed", ProductionTask(task_type="campfire", id=cf.campfire_id), metadata={"campfire_id": cf.campfire_id, "fuel_quantity": cf.fuel_quantity, "burn_rate": cf.burn_rate_per_tick})
            if cf.fuel_quantity <= cf.minimum_fuel_quantity:
                self._record_production_task_trace("campfire_fuel_low", ProductionTask(task_type="campfire", id=cf.campfire_id), metadata={"campfire_id": cf.campfire_id, "fuel_quantity": cf.fuel_quantity})
            if cf.fuel_quantity <= 0:
                cf.fuel_quantity = 0
                cf.lit = False
                self._record_production_task_trace("campfire_fuel_depleted", ProductionTask(task_type="campfire", id=cf.campfire_id), metadata={"campfire_id": cf.campfire_id})
                self._record_production_task_trace("campfire_warmth_field_lost", ProductionTask(task_type="campfire", id=cf.campfire_id), metadata={"campfire_id": cf.campfire_id})
                self._record_decision_explanation(explanation_type="campfire_extinguished_explained", decision="extinguished", primary_reason="zero_fuel", source_entity_id=cf.campfire_id)
            else:
                self._record_production_task_trace("campfire_warmth_field_active", ProductionTask(task_type="campfire", id=cf.campfire_id), metadata={"campfire_id": cf.campfire_id, "fuel_quantity": cf.fuel_quantity})

    def advance_temperature_exposure(self) -> None:
        now = int(getattr(self, "game_time", 0) or 0)
        self.last_temperature_tick = now
        for actor in [*getattr(self, "village_npcs", []), *getattr(self, "npcs", [])]:
            if getattr(getattr(actor, "physical", None), "is_dead", False):
                continue
            warmed = False
            nearest = None
            for cf in self.campfires_by_id.values():
                if not (cf.operational and cf.lit and cf.fuel_quantity > 0):
                    continue
                dist = abs(actor.x - cf.x) + abs(actor.y - cf.y)
                if dist <= getattr(cf, "warmth_radius", 4):
                    warmed = True
                    nearest = cf
                    break
            sheltered, exposure_mod, recovery_mod, shelter_id = self.get_shelter_exposure_modifier((actor.x, actor.y))
            was_sheltered = bool(getattr(actor, "sheltered_state", False))
            actor.sheltered_state = sheltered
            actor.current_shelter_id = shelter_id
            actor.shelter_exposure_modifier = exposure_mod
            if sheltered:
                actor.last_sheltered_tick = now
            if was_sheltered != sheltered:
                self._record_production_task_trace("shelter_state_changed", ProductionTask(task_type="temperature", id=str(actor.id)), actor=actor, metadata={"sheltered_state": sheltered, "shelter_id": shelter_id})
            if warmed:
                actor.cold_exposure = max(0.0, float(getattr(actor, "cold_exposure", 0.0)) - (0.1 * recovery_mod))
                actor.warmth_state = "warmed"
                actor.last_warmed_tick = now
                actor.exposure_fatigue_modifier = max(0.0, float(getattr(actor, "exposure_fatigue_modifier", 0.0)) - 0.02)
                self._record_production_task_trace("actor_warmed_by_campfire", ProductionTask(task_type="temperature", id=str(actor.id)), actor=actor, metadata={"campfire_id": getattr(nearest, "campfire_id", None), "cold_exposure": actor.cold_exposure})
                self._record_decision_explanation(explanation_type="actor_warmed_explained", decision="warmed", primary_reason="near_lit_campfire", actor=actor, source_entity_id=getattr(nearest, "campfire_id", None))
                if sheltered:
                    self._record_production_task_trace("shelter_recovery_modifier_applied", ProductionTask(task_type="temperature", id=str(actor.id)), actor=actor, metadata={"shelter_id": shelter_id, "recovery_modifier": recovery_mod})
            else:
                if self.ambient_temperature < self.cold_threshold:
                    delta = 0.05 if self.ambient_temperature >= self.severe_cold_threshold else 0.1
                    actor.cold_exposure = min(2.0, float(getattr(actor, "cold_exposure", 0.0)) + (delta * exposure_mod))
                    actor.warmth_state = "cold"
                    actor.last_cold_tick = now
                    actor.exposure_fatigue_modifier = min(0.5, float(getattr(actor, "exposure_fatigue_modifier", 0.0)) + 0.02)
                    self._record_production_task_trace("actor_cold_exposure_increased", ProductionTask(task_type="temperature", id=str(actor.id)), actor=actor, metadata={"cold_exposure": actor.cold_exposure, "ambient_temperature": self.ambient_temperature})
                    self._record_production_task_trace("shelter_exposure_evaluated", ProductionTask(task_type="temperature", id=str(actor.id)), actor=actor, metadata={"sheltered_state": sheltered, "shelter_id": shelter_id, "exposure_modifier": exposure_mod, "recovery_modifier": recovery_mod, "ambient_temperature": self.ambient_temperature, "cold_exposure": actor.cold_exposure})
                    if sheltered:
                        self._record_production_task_trace("actor_sheltered_from_cold", ProductionTask(task_type="temperature", id=str(actor.id)), actor=actor, metadata={"shelter_id": shelter_id, "cold_exposure": actor.cold_exposure})
                        self._record_decision_explanation(explanation_type="shelter_exposure_reduced", decision="mitigated", primary_reason="shelter_modifier_applied", actor=actor, source_entity_id=shelter_id, score_snapshot={"exposure_modifier": exposure_mod})
                    else:
                        self._record_production_task_trace("actor_unsheltered_exposure", ProductionTask(task_type="temperature", id=str(actor.id)), actor=actor, metadata={"cold_exposure": actor.cold_exposure})
                    if actor.cold_exposure > 1.0:
                        self._record_decision_explanation(explanation_type="cold_exposure_penalty", decision="penalized", primary_reason="cold_exposure_high", actor=actor, score_snapshot={"cold_exposure": actor.cold_exposure})


    def _is_valid_survival_target(self, target_id: str | None, position: tuple[int, int] | None) -> bool:
        if position is None:
            return False
        if target_id and target_id.startswith("campfire:"):
            cf = self.campfires_by_id.get(target_id.split(":", 1)[1])
            return bool(cf and cf.operational and cf.lit and cf.fuel_quantity > 0)
        if target_id and target_id.startswith("shelter:"):
            shelter = self.shelter_zones_by_id.get(target_id.split(":", 1)[1])
            return bool(shelter and shelter.get("active", True) and position in shelter.get("positions", set()))
        return True

    def _find_nearest_warmth_or_shelter_target(self, actor) -> tuple[str | None, tuple[int, int] | None]:
        candidates: list[tuple[int, str, tuple[int, int]]] = []
        for cf in sorted(self.campfires_by_id.values(), key=lambda c: c.campfire_id):
            if not (cf.operational and cf.lit and cf.fuel_quantity > 0):
                continue
            pos = (int(cf.x), int(cf.y))
            candidates.append((abs(actor.x - pos[0]) + abs(actor.y - pos[1]), f"campfire:{cf.campfire_id}", pos))
        for sid, zone in sorted(self.shelter_zones_by_id.items(), key=lambda item: item[0]):
            if not zone.get("active", True):
                continue
            positions = sorted(zone.get("positions", set()))
            if not positions:
                continue
            best = min(positions, key=lambda p: abs(actor.x - p[0]) + abs(actor.y - p[1]))
            candidates.append((abs(actor.x - best[0]) + abs(actor.y - best[1]), f"shelter:{sid}", best))
        if not candidates:
            return None, None
        candidates.sort(key=lambda x: (x[0], x[1]))
        return candidates[0][1], candidates[0][2]

    def advance_cold_survival_overrides(self) -> None:
        now = int(getattr(self, "game_time", 0) or 0)
        for actor in list(getattr(self, "village_npcs", [])):
            exposure = float(getattr(actor, "cold_exposure", 0.0) or 0.0)
            active = bool(getattr(actor, "survival_override_active", False))
            if active and exposure <= float(getattr(actor, "survival_override_recovery_threshold", self.cold_recovery_threshold)):
                actor.survival_override_active = False
                actor.survival_override_reason = None
                actor.survival_override_target_id = None
                actor.survival_override_target_position = None
                actor.survival_override_cooldown_until_tick = now + max(1, int(self.cold_override_cooldown_ticks))
                self._record_production_task_trace("survival_override_recovered", ProductionTask(task_type="temperature", id=str(actor.id)), actor=actor, metadata={"actor_id": actor.id, "cold_exposure": exposure})
                self._record_decision_explanation(explanation_type="cold_survival_recovered", decision="recovered", primary_reason="cold_exposure_recovered", actor=actor, score_snapshot={"cold_exposure": exposure})
                continue
            if active:
                tid = getattr(actor, "survival_override_target_id", None)
                tpos = getattr(actor, "survival_override_target_position", None)
                if not self._is_valid_survival_target(tid, tpos):
                    self._warn_simulation_validation("cold_survival_target_invalid", (actor.id, tid), "Cold survival target became invalid.", actor=actor, metadata={"target_id": tid})
                    self._record_production_task_trace("survival_override_target_lost", ProductionTask(task_type="temperature", id=str(actor.id)), actor=actor, metadata={"target_id": tid})
                    ntid, ntpos = self._find_nearest_warmth_or_shelter_target(actor)
                    actor.survival_override_target_id, actor.survival_override_target_position = ntid, ntpos
                    if ntpos is None:
                        self._warn_simulation_validation("cold_survival_no_valid_target", (actor.id, now), "No valid warmth/shelter target found for cold override.", actor=actor)
                        self._record_decision_explanation(explanation_type="cold_survival_no_target", decision="deferred", primary_reason="no_valid_warmth_or_shelter_target", actor=actor)
                        continue
                if tpos is not None:
                    if abs(actor.x - tpos[0]) <= 1 and abs(actor.y - tpos[1]) <= 1:
                        self._record_production_task_trace("survival_override_waiting_for_recovery", ProductionTask(task_type="temperature", id=str(actor.id)), actor=actor, metadata={"target_id": tid, "target_position": tpos, "cold_exposure": exposure})
                        self._record_decision_explanation(explanation_type="cold_survival_target_selected", decision="waiting", primary_reason="already_near_survival_target", actor=actor, source_entity_id=tid, contributing_factors={"target_position": tpos})
                    else:
                        routed = self._route_actor_toward_position(actor, tpos, reason="cold_survival_override_route", task_id=getattr(actor, "survival_override_previous_task_id", None))
                        if routed:
                            self._record_production_task_trace("survival_override_route_started", ProductionTask(task_type="temperature", id=str(actor.id)), actor=actor, metadata={"target_id": tid, "target_position": tpos, "cold_exposure": exposure})
                        else:
                            self._warn_simulation_validation("cold_survival_routing_failed", (actor.id, tpos), "Cold survival override could not route actor.", actor=actor, metadata={"target_position": tpos})
                continue
            if now < int(getattr(actor, "survival_override_cooldown_until_tick", 0) or 0):
                continue
            if exposure < float(getattr(self, "cold_override_threshold", 0.7)):
                continue
            actor.survival_override_active = True
            actor.survival_override_reason = "seeking_warmth"
            actor.survival_override_started_tick = now
            actor.survival_override_recovery_threshold = float(getattr(self, "cold_recovery_threshold", 0.35))
            actor.survival_override_previous_task_id = str(getattr(actor, "task_context_data", {}).get("task_id") or "") or None
            prev_task = getattr(getattr(actor, "schedule", None), "current_task", None)
            tid, tpos = self._find_nearest_warmth_or_shelter_target(actor)
            actor.survival_override_target_id, actor.survival_override_target_position = tid, tpos
            self._record_production_task_trace("survival_override_started", ProductionTask(task_type="temperature", id=str(actor.id)), actor=actor, metadata={"actor_id": actor.id, "cold_exposure": exposure, "target_id": tid, "target_position": tpos, "previous_task_id": actor.survival_override_previous_task_id, "override_reason": actor.survival_override_reason, "recovery_threshold": actor.survival_override_recovery_threshold})
            self._record_decision_explanation(explanation_type="cold_survival_override_started", decision="started", primary_reason="cold_exposure_threshold_reached", actor=actor, score_snapshot={"cold_exposure": exposure})
            if getattr(self, "interaction_resolver", None):
                result = self.interaction_resolver.cancel_actor_interaction(actor.id, self, reason="cold_survival_override")
                if getattr(result, "cancelled", False):
                    self._record_production_task_trace("cold_survival_interruption", ProductionTask(task_type="temperature", id=str(actor.id)), actor=actor, metadata={"previous_task": prev_task})
                    self._record_decision_explanation(explanation_type="cold_survival_interrupted_task", decision="interrupted", primary_reason="cold_survival_override", actor=actor, contributing_factors={"previous_task": prev_task})
            if tpos is None:
                self._warn_simulation_validation("cold_survival_no_valid_target", (actor.id, now), "No valid warmth/shelter target found for cold override start.", actor=actor)
                self._record_decision_explanation(explanation_type="cold_survival_no_target", decision="blocked", primary_reason="no_valid_warmth_or_shelter_target", actor=actor)
                continue
            self._record_production_task_trace("survival_override_target_selected", ProductionTask(task_type="temperature", id=str(actor.id)), actor=actor, metadata={"target_id": tid, "target_position": tpos, "cold_exposure": exposure})
            self._record_decision_explanation(explanation_type="cold_survival_target_selected", decision="selected", primary_reason="nearest_valid_warmth_or_shelter_target", actor=actor, source_entity_id=tid, contributing_factors={"target_position": tpos})

    def advance_reserve_targets(self) -> None:
        now = int(getattr(self, "game_time", 0) or 0)
        if now < int(getattr(self, "next_reserve_eval_tick", 0) or 0):
            return
        self.next_reserve_eval_tick = now + max(1, int(getattr(self, "scheduling_cadence_config", {}).get("reserve_eval_interval", 5)))
        for target in list(self.reserve_targets_by_id.values()):
            target.last_evaluated_tick = now
            target.active_task_ids = [task_id for task_id in target.active_task_ids if task_id in self.production_tasks_by_id and self.production_tasks_by_id[task_id].status not in {"completed", "failed", "cancelled"}]
            if now < max(0, target.cooldown_until_tick):
                continue
            quantity = 0
            if target.target_type == "stockpile_item":
                stockpile = self.stockpiles_by_id.get(target.target_entity_id or "")
                if stockpile is None:
                    self._warn_simulation_validation("reserve_task_orphaned", (target.reserve_target_id, target.target_entity_id), "Reserve target stockpile does not exist.", metadata={"reserve_target_id": target.reserve_target_id})
                    continue
                quantity = stockpile.quantity(target.linked_item_type)
            elif target.target_type == "campfire_fuel":
                cf = self.campfires_by_id.get(target.target_entity_id or "")
                if cf is None:
                    self._warn_simulation_validation("campfire_refuel_missing_target", (target.reserve_target_id, target.target_entity_id), "Campfire reserve target is missing campfire.", metadata={"reserve_target_id": target.reserve_target_id})
                    continue
                quantity = cf.fuel_quantity
            target.current_quantity = quantity
            self._record_production_task_trace("reserve_target_evaluated", ProductionTask(task_type="reserve_target", id=target.reserve_target_id), metadata={"reserve_target_id": target.reserve_target_id, "current_quantity": quantity, "minimum_quantity": target.minimum_quantity, "desired_quantity": target.desired_quantity, "item_key": target.linked_item_type})
            if quantity >= target.minimum_quantity:
                self._record_production_task_trace("reserve_target_satisfied", ProductionTask(task_type="reserve_target", id=target.reserve_target_id), metadata={"reserve_target_id": target.reserve_target_id, "quantity": quantity})
                continue
            shortage = max(0, target.desired_quantity - quantity)
            self._record_production_task_trace("reserve_shortage_detected", ProductionTask(task_type="reserve_target", id=target.reserve_target_id), metadata={"reserve_target_id": target.reserve_target_id, "shortage": shortage, "item_key": target.linked_item_type})
            if target.active_task_ids:
                continue
            if target.linked_item_type == "raw_log":
                if target.target_type == "campfire_fuel":
                    task = self.create_production_task("refill_campfire_fuel", metadata={"campfire_id": target.target_entity_id, "item_key": "raw_log", "priority": target.priority, "urgency": min(10, shortage)}, expiration_ticks=900)
                    self._record_production_task_trace("campfire_refuel_task_created", task, metadata={"campfire_id": target.target_entity_id, "shortage": shortage})
                    self._record_decision_explanation(explanation_type="campfire_refuel_task_generated", decision="generated_task", primary_reason="campfire_fuel_shortage", task=task, source_entity_id=target.target_entity_id, contributing_factors={"shortage": shortage})
                else:
                    task = self.create_production_task("produce_logs", metadata={"stockpile_id": target.target_entity_id, "target_quantity": target.desired_quantity, "item_key": "raw_log", "priority": target.priority, "urgency": min(10, shortage)}, expiration_ticks=900)
            elif target.linked_item_type == "wooden_plank":
                task = self.create_production_task("craft_plank", metadata={"priority": target.priority, "urgency": min(10, shortage)}, expiration_ticks=900)
            else:
                self._warn_simulation_validation("reserve_unreachable_supply", (target.reserve_target_id, target.linked_item_type), "No production mapping for reserve item type.", metadata={"reserve_target_id": target.reserve_target_id, "item_key": target.linked_item_type})
                target.cooldown_until_tick = now + 120
                continue
            target.active_task_ids.append(task.id)
            target.cooldown_until_tick = now + 60
            self._record_production_task_trace("reserve_task_created", task, metadata={"reserve_target_id": target.reserve_target_id, "shortage": shortage})
            self._record_decision_explanation(explanation_type="reserve_generated_task", decision="generated_task", primary_reason="reserve_shortage_detected", task=task, source_entity_id=target.reserve_target_id, contributing_factors={"shortage": shortage, "item_key": target.linked_item_type}, score_snapshot={"current_quantity": quantity, "desired_quantity": target.desired_quantity})

    def _evaluate_production_dependencies(self, now: int) -> None:
        if now < int(getattr(self, "next_dependency_eval_tick", 0) or 0):
            return
        self.next_dependency_eval_tick = now + max(1, int(getattr(self, "scheduling_cadence_config", {}).get("dependency_eval_interval", 4)))
        active = [t for t in self.production_tasks_by_id.values() if t.status not in {"completed", "failed", "cancelled"}]
        producers: dict[str, list[ProductionTask]] = {"raw_log": [t for t in active if t.task_type == "produce_logs"], "wooden_plank": [t for t in active if t.task_type == "craft_plank"]}
        for task in active:
            task.inherited_priority = 0
            task.blocked_by_task_ids = []
            task.blocking_task_ids = []
            task.dependency_reason = None
            task.last_dependency_eval_tick = now
            if task.task_type == "build_component":
                prereqs = ["wooden_plank"]
            elif task.task_type == "craft_plank":
                prereqs = ["raw_log"]
            else:
                prereqs = []
            task.prerequisite_item_types = prereqs
            if task.blocked_reason and prereqs:
                for item in prereqs:
                    prod = producers.get(item, [])
                    if not prod:
                        self._warn_simulation_validation("production_dependency_unresolved", (task.id, item), "Blocked task has unmet dependency with no producer task.", metadata={"task_id": task.id, "item": item}, cooldown_ticks=180)
                        continue
                    for p in prod:
                        boost = min(5, max(1, int(task.priority // 2)))
                        p.inherited_priority = min(10, p.inherited_priority + boost)
                        p.blocking_task_ids.append(task.id)
                        task.blocked_by_task_ids.append(p.id)
                        task.dependency_reason = f"waiting_on:{item}"
                        self._record_production_task_trace("production_priority_inherited", p, metadata={"from_task_id": task.id, "boost": boost, "item": item})
                        self._record_decision_explanation(explanation_type="priority_inherited", decision="priority_boosted", primary_reason="blocked_high_priority_dependency", task=p, source_entity_id=task.id, contributing_factors={"item": item, "boost": boost}, score_snapshot={"inherited_priority": p.inherited_priority})


    def _compute_production_task_score(self, task: ProductionTask, now: int) -> int:
        cached = getattr(self, "_production_score_cache", {}).get(task.id)
        if cached and now <= cached[1]:
            self._record_decision_explanation(explanation_type="cached_score_used", decision="used_cached_score", primary_reason="score_cache_valid", task=task, score_snapshot={"score": cached[0], "cache_until_tick": cached[1]})
            return int(cached[0])
        starvation_age = max(0, now - max(task.last_progress_tick or task.created_tick, task.created_tick))
        starvation_bonus = min(200, starvation_age // 20)
        retry_penalty = min(100, max(0, task.retry_count) * 5)
        cooldown_penalty = 1000 if now < max(0, task.cooldown_until_tick) else 0
        pressure = max(0, int(task.resource_pressure_score or 0))
        dependency_boost = min(200, int(getattr(task, "inherited_priority", 0)) * 20)
        score = (task.priority * 100) + (task.urgency * 10) + starvation_bonus + pressure + dependency_boost - retry_penalty - cooldown_penalty
        self._production_score_cache[task.id] = (score, now + 1)
        return score

    def _mark_production_task_blocked(self, task: ProductionTask, reason: str, now: int, *, cooldown: int = 30, warning_type: str = "production_task_resource_deadlock") -> None:
        task.status = "blocked"
        task.blocked_reason = reason
        task.retry_count = max(0, task.retry_count) + 1
        task.cooldown_until_tick = now + max(1, int(cooldown))
        self._record_production_task_trace("production_task_blocked", task, metadata={"reason": reason, "cooldown_until_tick": task.cooldown_until_tick, "retry_count": task.retry_count})
        self._record_decision_explanation(explanation_type="task_blocked", decision="blocked", primary_reason=reason, task=task, contributing_factors={"retry_count": task.retry_count, "cooldown_until_tick": task.cooldown_until_tick}, score_snapshot={"resource_pressure_score": task.resource_pressure_score})
        self._warn_simulation_validation(warning_type, (task.id, reason), "Production task is blocked and cooled down.", metadata={"task_id": task.id, "task_type": task.task_type, "reason": reason, "retry_count": task.retry_count})

    def _mark_production_task_progress(self, task: ProductionTask, now: int, *, actor=None, trace_type: str = "production_task_recovered", metadata: dict | None = None) -> None:
        task.last_progress_tick = now
        task.blocked_reason = None
        task.cooldown_until_tick = 0
        task.retry_count = max(0, task.retry_count - 1)
        self._record_production_task_trace(trace_type, task, actor=actor, metadata=metadata)

    def _work_tag_for_task(self, task_type: str) -> str:
        return {
            "produce_logs": "woodcutting",
            "build_component": "construction",
            "craft_plank": "crafting",
        }.get(task_type, "hauling")

    def _score_actor_suitability(self, actor, task: ProductionTask, *, work_tag: str, near: tuple[int, int] | None = None) -> int:
        now = int(getattr(self, "game_time", 0) or 0)
        key = (task.id, int(getattr(actor, "id", 0)), work_tag)
        if now <= int(getattr(self, "actor_suitability_cache_until_tick", 0) or 0):
            cached = self._actor_suitability_cache.get(key)
            if cached is not None:
                self._record_decision_explanation(explanation_type="cached_score_used", decision="used_cached_suitability", primary_reason="suitability_cache_valid", task=task, actor=actor, score_snapshot={"suitability_score": cached})
                return int(cached)
        skill = int(getattr(actor, "skill_levels", {}).get(work_tag, 1))
        preferred = 8 if work_tag in set(getattr(actor, "preferred_work_types", []) or []) else 0
        fatigue = float(getattr(actor, "fatigue_modifier", 0.0) or 0.0)
        fatigue_penalty = int(min(40.0, max(0.0, fatigue) * 20.0))
        history = list(getattr(actor, "recent_task_history", []) or [])
        repetition_penalty = 10 if history and history[-1] == task.task_type else 0
        if bool(getattr(actor, "survival_override_active", False)):
            self._record_production_task_trace("actor_skipped_survival_override", task, actor=actor, metadata={"work_tag": work_tag})
            self._record_decision_explanation(explanation_type="actor_skipped_survival_override", decision="skipped", primary_reason="active_cold_survival_override", task=task, actor=actor)
            return -9999
        busy_penalty = 30 if getattr(actor, "task_context", None) in {"hauling", "construction", "delivery", "stockpile_hauling"} else 0
        dist_penalty = 0
        if near is not None:
            dist_penalty = min(30, abs(int(getattr(actor, "x", 0)) - near[0]) + abs(int(getattr(actor, "y", 0)) - near[1]))
        score = (skill * 20) + preferred - fatigue_penalty - repetition_penalty - busy_penalty - dist_penalty
        self._record_production_task_trace("actor_task_suitability_scored", task, actor=actor, metadata={"work_tag": work_tag, "score": score, "skill": skill, "fatigue": fatigue, "distance_penalty": dist_penalty})
        self._record_decision_explanation(explanation_type="actor_scored", decision="scored", primary_reason="suitability_computed", task=task, actor=actor, contributing_factors={"work_tag": work_tag, "skill": skill, "fatigue_penalty": fatigue_penalty, "busy_penalty": busy_penalty, "distance_penalty": dist_penalty}, score_snapshot={"suitability_score": score})
        self._actor_suitability_cache[key] = score
        self.actor_suitability_cache_until_tick = now + max(1, int(getattr(self, "scheduling_cadence_config", {}).get("suitability_cache_interval", 2)))
        if fatigue > 1.5:
            self._warn_simulation_validation("actor_overwork_detected", (getattr(actor, "id", None), work_tag), "Actor fatigue is elevated during suitability scoring.", actor=actor, metadata={"fatigue": fatigue, "work_tag": work_tag}, cooldown_ticks=180)
        return score

    def _apply_actor_work_tick(self, actor, *, work_tag: str, task: ProductionTask) -> None:
        levels = getattr(actor, "skill_levels", None)
        if isinstance(levels, dict):
            levels[work_tag] = min(10, int(levels.get(work_tag, 1)) + 1 if (int(getattr(self, "game_time", 0) or 0) % 200 == 0) else int(levels.get(work_tag, 1)))
        actor.fatigue_modifier = min(2.0, float(getattr(actor, "fatigue_modifier", 0.0) or 0.0) + 0.04)
        history = list(getattr(actor, "recent_task_history", []) or [])
        history.append(task.task_type)
        actor.recent_task_history = history[-10:]
        if getattr(actor, "current_work_focus", None) != work_tag:
            actor.current_work_focus = work_tag
            self._record_production_task_trace("actor_work_focus_shifted", task, actor=actor, metadata={"work_tag": work_tag})
        self._record_production_task_trace("actor_fatigue_increased", task, actor=actor, metadata={"work_tag": work_tag, "fatigue": actor.fatigue_modifier})
        self._apply_actor_skill_experience(actor, work_tag=work_tag, progress_amount=1, task=task)

    def _apply_actor_skill_experience(self, actor, *, work_tag: str, progress_amount: int, task: ProductionTask | None = None) -> None:
        if actor is None or not work_tag:
            return
        now = int(getattr(self, "game_time", 0) or 0)
        xp_map = getattr(actor, "skill_experience_by_tag", None)
        if not isinstance(xp_map, dict):
            xp_map = {}
            actor.skill_experience_by_tag = xp_map
        pressure = getattr(actor, "specialization_pressure", None)
        if not isinstance(pressure, dict):
            pressure = {}
            actor.specialization_pressure = pressure
        usage = list(getattr(actor, "recent_skill_usage", []) or [])
        usage.append(work_tag)
        actor.recent_skill_usage = usage[-20:]
        repeat_count = actor.recent_skill_usage.count(work_tag)
        gain = max(0.01, min(0.25, 0.03 * max(1, int(progress_amount)) * (1.0 - min(0.7, xp_map.get(work_tag, 0.0) / 300.0))))
        xp_before = float(xp_map.get(work_tag, 0.0))
        xp_after = min(500.0, xp_before + gain)
        xp_map[work_tag] = xp_after
        actor.last_skill_gain_tick = now
        specialization_value = min(1.0, max(0.0, float(pressure.get(work_tag, 0.0)) * 0.98 + (repeat_count / 20.0) * 0.05))
        pressure[work_tag] = specialization_value

        level_map = getattr(actor, "skill_levels", None)
        if not isinstance(level_map, dict):
            level_map = {}
            actor.skill_levels = level_map
        old_level = int(level_map.get(work_tag, 1))
        new_level = min(10, 1 + int((xp_after ** 0.5) // 3))
        if new_level != old_level:
            level_map[work_tag] = new_level
            self._record_production_task_trace("actor_skill_level_changed", task or ProductionTask(task_type="skill_progress"), actor=actor, metadata={"work_tag": work_tag, "old_level": old_level, "new_level": new_level, "total_experience": xp_after})
        self._record_production_task_trace("actor_skill_experience_gained", task or ProductionTask(task_type="skill_progress"), actor=actor, metadata={"work_tag": work_tag, "experience_gained": gain, "total_experience": xp_after, "resulting_skill_level": int(level_map.get(work_tag, 1))})
        self._record_production_task_trace("actor_specialization_pressure_updated", task or ProductionTask(task_type="skill_progress"), actor=actor, metadata={"work_tag": work_tag, "specialization_pressure": specialization_value})
        if specialization_value > 0.9:
            self._record_production_task_trace("actor_work_identity_reinforced", task or ProductionTask(task_type="skill_progress"), actor=actor, metadata={"work_tag": work_tag, "specialization_pressure": specialization_value})
            self._warn_simulation_validation("actor_specialization_lock", (getattr(actor, "id", None), work_tag), "Actor specialization pressure is very high.", actor=actor, metadata={"work_tag": work_tag, "specialization_pressure": specialization_value}, cooldown_ticks=240)
        if xp_after >= 499.0:
            self._warn_simulation_validation("actor_skill_growth_out_of_bounds", (getattr(actor, "id", None), work_tag), "Actor skill growth reached soft cap boundary.", actor=actor, metadata={"work_tag": work_tag, "experience": xp_after}, cooldown_ticks=240)
        self._update_actor_work_profile(actor, work_tag=work_tag, task=task)

    def _update_actor_work_profile(self, actor, *, work_tag: str | None = None, task: ProductionTask | None = None) -> None:
        if actor is None:
            return
        profile = getattr(actor, "actor_work_profile", None)
        if not isinstance(profile, dict):
            self._warn_simulation_validation("actor_profile_update_failure", (getattr(actor, "id", None), "profile_missing"), "Actor profile state was missing during update.", actor=actor)
            profile = {}
            actor.actor_work_profile = profile
        totals = profile.get("lifetime_work_totals")
        if not isinstance(totals, dict):
            totals = {"woodcutting": 0, "hauling": 0, "construction": 0, "crafting": 0}
            profile["lifetime_work_totals"] = totals
        if work_tag:
            totals[work_tag] = int(totals.get(work_tag, 0)) + 1
        ranked = sorted(totals.items(), key=lambda kv: (-int(kv[1]), kv[0]))
        dominant = ranked[0][0] if ranked else "hauling"
        profile["dominant_work_tag"] = dominant
        history = list(getattr(actor, "recent_skill_usage", []) or [])
        if len(history) > 50:
            actor.recent_skill_usage = history[-50:]
            self._warn_simulation_validation("actor_work_history_overflow", (getattr(actor, "id", None), len(history)), "Actor recent skill usage history exceeded bound and was trimmed.", actor=actor, cooldown_ticks=240)
            history = actor.recent_skill_usage
        profile["work_history_snapshot"] = history[-8:]
        fatigue = float(getattr(actor, "fatigue_modifier", 0.0) or 0.0)
        fatigue_state = "overworked" if fatigue >= 1.4 else "fatigued" if fatigue >= 0.7 else "rested"
        profile["fatigue_state"] = fatigue_state
        spec = getattr(actor, "specialization_pressure", {}) or {}
        dominant_spec = float(spec.get(dominant, 0.0))
        if dominant_spec >= 0.7:
            label = f"Habitual {dominant.title()} Specialist"
            self._record_production_task_trace("actor_specialization_emerged", task or ProductionTask(task_type="work_profile"), actor=actor, metadata={"dominant_work_tag": dominant, "specialization_pressure": dominant_spec})
        elif dominant_spec >= 0.4:
            label = f"Growing {dominant.title()} Worker"
        else:
            label = "General Laborer"
        previous_label = profile.get("work_identity_label")
        profile["work_identity_label"] = label
        profile["preferred_task_bias"] = list(getattr(actor, "preferred_work_types", []) or [])
        profile["specialization_summary"] = f"{dominant.title()} pressure {dominant_spec:.2f}"
        profile["recent_work_summary"] = f"Recent focus: {', '.join(profile['work_history_snapshot'][-3:])}" if profile["work_history_snapshot"] else "No recent work recorded."
        if previous_label and previous_label != label:
            self._record_production_task_trace("actor_identity_shift_detected", task or ProductionTask(task_type="work_profile"), actor=actor, metadata={"previous_label": previous_label, "new_label": label, "dominant_work_tag": dominant})
        self._record_production_task_trace("actor_work_profile_updated", task or ProductionTask(task_type="work_profile"), actor=actor, metadata={"dominant_work_tag": dominant, "fatigue_state": fatigue_state, "work_identity_label": label, "specialization_pressure": dominant_spec})

    def get_actor_work_identity_summary(self, actor) -> str:
        if actor is None:
            return "Unknown worker identity."
        self._update_actor_work_profile(actor, work_tag=None, task=None)
        profile = getattr(actor, "actor_work_profile", {}) or {}
        summary = f"{profile.get('work_identity_label', 'General Laborer')} with {profile.get('specialization_summary', 'balanced skills')} and {profile.get('fatigue_state', 'rested')} fatigue."
        trace_log = getattr(self, "interaction_trace_log", None)
        if isinstance(trace_log, list):
            trace_log.append({"tick": getattr(self, "game_time", None), "interaction_id": None, "actor_id": getattr(actor, "id", None), "action_type": "work_profile", "trace_type": "actor_work_summary_generated", "metadata": {"summary": summary, "dominant_work_tag": profile.get("dominant_work_tag"), "work_identity_label": profile.get("work_identity_label")}})
        return summary

    def get_actor_work_efficiency(self, actor, work_tag: str) -> tuple[float, dict]:
        if actor is None:
            self._warn_simulation_validation("interaction_efficiency_missing_actor", (work_tag, "none"), "Cannot compute work efficiency without an actor.", metadata={"work_tag": work_tag})
            return 1.0, {"reason": "missing_actor"}
        if not work_tag:
            self._warn_simulation_validation("interaction_efficiency_missing_skill_tag", (getattr(actor, "id", None), "missing"), "Cannot compute work efficiency without a work tag.", actor=actor)
            return 1.0, {"reason": "missing_work_tag"}
        skill_level = int(getattr(actor, "skill_levels", {}).get(work_tag, 1))
        fatigue = float(getattr(actor, "fatigue_modifier", 0.0) or 0.0) + float(getattr(actor, "exposure_fatigue_modifier", 0.0) or 0.0)
        preferred = 0.08 if work_tag in set(getattr(actor, "preferred_work_types", []) or []) else 0.0
        repetition_penalty = 0.05 if (list(getattr(actor, "recent_task_history", []) or [])[-1:] == [work_tag]) else 0.0
        explicit_modifier = float(getattr(actor, "work_efficiency_modifiers", {}).get(work_tag, 1.0) or 1.0)
        base_multiplier = 1.0 + min(0.4, max(0.0, (skill_level - 1) * 0.05)) + preferred - min(0.5, fatigue * 0.2) - repetition_penalty
        base_multiplier += min(0.12, max(0.0, float(getattr(actor, "specialization_pressure", {}).get(work_tag, 0.0)) * 0.12))
        multiplier = max(0.5, min(1.5, base_multiplier * explicit_modifier))
        if multiplier <= 0.5 or multiplier >= 1.5:
            self._warn_simulation_validation("actor_efficiency_out_of_bounds", (getattr(actor, "id", None), work_tag), "Actor work efficiency hit bounding limits.", actor=actor, metadata={"work_tag": work_tag, "computed_multiplier": multiplier})
        meta = {"actor_id": getattr(actor, "id", None), "work_tag": work_tag, "skill_level": skill_level, "fatigue": fatigue, "preferred_bonus": preferred, "repetition_penalty": repetition_penalty, "explicit_modifier": explicit_modifier, "efficiency_multiplier": multiplier, "cold_exposure": float(getattr(actor, "cold_exposure", 0.0) or 0.0)}
        trace_log = getattr(self, "interaction_trace_log", None)
        if isinstance(trace_log, list):
            trace_log.append({"tick": getattr(self, "game_time", None), "interaction_id": None, "actor_id": getattr(actor, "id", None), "action_type": "interaction_efficiency", "trace_type": "actor_work_efficiency_computed", "metadata": meta})
        if multiplier > 1.45:
            self._warn_simulation_validation("actor_efficiency_runaway", (getattr(actor, "id", None), work_tag), "Actor efficiency is near maximum bound.", actor=actor, metadata={"work_tag": work_tag, "efficiency_multiplier": multiplier}, cooldown_ticks=240)
        return multiplier, meta

    def _advance_produce_logs_task(self, task: ProductionTask) -> None:
        stockpile = self.stockpiles_by_id.get(task.metadata.get("stockpile_id"))
        now = int(getattr(self, "game_time", 0) or 0)
        if stockpile is None:
            task.status = "failed"
            self._warn_simulation_validation("orphaned_production_task", (task.id, "stockpile_missing"), "ProduceLogsTask lost stockpile target.", metadata={"task_id": task.id})
            self._record_production_task_trace("production_task_failed", task, metadata={"reason": "stockpile_missing"})
            return
        item_key = task.metadata.get("item_key", "raw_log")
        target_qty = max(1, int(task.metadata.get("target_quantity", 1)))
        if stockpile.quantity(item_key) >= target_qty:
            task.status = "completed"
            self._mark_production_task_progress(task, now, trace_type="production_task_completed", metadata={"quantity": stockpile.quantity(item_key)})
            return
        actors = [npc for npc in self.village_npcs if not getattr(getattr(npc, "physical", None), "is_dead", False)]
        actors.sort(key=lambda a: (-self._score_actor_suitability(a, task, work_tag="woodcutting", near=stockpile.position), getattr(a, "id", 0)))
        for actor in actors:
            if getattr(actor, "task_context", None) == "stockpile_hauling":
                self._handle_npc_stockpile_haul_task(actor)
                continue
            if getattr(actor, "task_context", None) in {"hauling", "construction", "delivery"}:
                continue
            if self._assign_source_to_stockpile_haul_task(actor, item_key=item_key):
                if actor.id not in task.assigned_actor_ids:
                    task.assigned_actor_ids.append(actor.id)
                task.status = "hauling"
                self._record_decision_explanation(explanation_type="actor_assigned", decision="assigned", primary_reason="best_available_suitability_for_produce_logs", task=task, actor=actor, contributing_factors={"work_tag": "woodcutting"}, score_snapshot={"task_status": task.status})
                self._apply_actor_work_tick(actor, work_tag="woodcutting", task=task)
                self._mark_production_task_progress(task, now, actor=actor, trace_type="production_task_selected", metadata={"status": task.status})
                return
        self._mark_production_task_blocked(task, "no_available_source_or_actor", now, warning_type="production_task_starvation")


    def _advance_craft_production_task(self, task: ProductionTask) -> None:
        now = int(getattr(self, "game_time", 0) or 0)
        workshop = self.workshops_by_id.get(task.metadata.get("workshop_id"))
        if workshop is None:
            workshop = self._find_operational_workshop(task.metadata.get("workshop_type", "sawbench"))
            if workshop is None:
                self._mark_production_task_blocked(task, "workshop_deadlock", now, warning_type="workshop_deadlock")
                return
            task.metadata["workshop_id"] = workshop.workshop_id
        candidates = [npc for npc in self.village_npcs if not getattr(getattr(npc, "physical", None), "is_dead", False)]
        candidates.sort(key=lambda a: (-self._score_actor_suitability(a, task, work_tag="crafting", near=(workshop.x, workshop.y)), getattr(a, "id", 0)))
        actor = candidates[0] if candidates else None
        if actor is None:
            self._record_decision_explanation(explanation_type="actor_skipped", decision="no_assignment", primary_reason="no_available_actor", task=task, contributing_factors={"work_tag": "crafting"})
            self._mark_production_task_blocked(task, "no_available_actors", now, warning_type="production_task_assignment_conflict")
            return
        if not self._reserve_workshop_for_actor(workshop, actor.id):
            self._mark_production_task_blocked(task, "workshop_assignment_conflict", now, warning_type="workshop_assignment_conflict")
            return
        if not self._is_actor_adjacent_to_position(actor, (workshop.x, workshop.y)):
            task.metadata["moving_to_workshop"] = True
            if self._route_actor_toward_position(actor, (workshop.x, workshop.y), reason="workshop_route_started", task_id=task.id):
                self._record_production_task_trace("craft_task_moving_to_workshop", task, actor=actor, metadata={"workshop_id": workshop.workshop_id})
                self._record_decision_explanation(explanation_type="interaction_waiting_for_range", decision="deferred", primary_reason="workshop_interaction_waiting_for_actor_range", task=task, actor=actor)
                return
            self._warn_simulation_validation("workshop_route_failed", (task.id, actor.id), "Unable to route actor toward workshop.", actor=actor, metadata={"workshop_id": workshop.workshop_id}, cooldown_ticks=120)
            return
        task.metadata["moving_to_workshop"] = False

        if workshop.input_buffer.get("raw_log", 0) <= 0:
            if workshop.reserved_input_entity_ids:
                self._mark_production_task_blocked(task, "workshop_missing_inputs", now, cooldown=20, warning_type="workshop_missing_inputs")
                return
            source = None
            if self.stockpiles_by_id:
                source_sp = self.find_stockpile_for_item("raw_log", require_available=True)
                if source_sp is not None:
                    reservation = source_sp.create_reservation("raw_log", 1, task_id=task.id, current_tick=now)
                    if reservation:
                        workshop.reserved_input_entity_ids.append(f"stockpile:{source_sp.stockpile_id}:{reservation}")
                        item = source_sp.withdraw_reserved_item_reference(reservation)
                        if item is not None:
                            workshop.input_buffer.add_item_reference(item)
                            self._record_production_task_trace("workshop_inputs_delivered", task, metadata={"workshop_id": workshop.workshop_id, "item_key": "raw_log"})
            if workshop.input_buffer.get("raw_log", 0) <= 0:
                self._mark_production_task_blocked(task, "workshop_missing_inputs", now, cooldown=20, warning_type="workshop_missing_inputs")
                return

        intent = ActionIntent(actor_id=actor.id, action_type="workshop_transform", target_pos=(workshop.x, workshop.y), payload={"workshop_id": workshop.workshop_id, "recipe": "raw_log_to_plank", "production_task_id": task.id})
        result = self.interaction_resolver.resolve(intent, self)
        if not result.success:
            self._mark_production_task_blocked(task, "workshop_interaction_start_failed", now, warning_type="workshop_deadlock")
            return
        workshop.active_interaction_id = result.started_interaction_id
        task.status = "waiting_for_work"
        self._record_decision_explanation(explanation_type="actor_assigned", decision="assigned", primary_reason="best_available_suitability_for_crafting", task=task, actor=actor, contributing_factors={"work_tag": "crafting", "workshop_id": workshop.workshop_id}, score_snapshot={"interaction_id": result.started_interaction_id})
        self._apply_actor_work_tick(actor, work_tag="crafting", task=task)
        self._mark_production_task_progress(task, now, actor=actor, trace_type="workshop_interaction_started", metadata={"workshop_id": workshop.workshop_id, "interaction_id": result.started_interaction_id})

    def _advance_build_component_task(self, task: ProductionTask) -> None:
        now = int(getattr(self, "game_time", 0) or 0)
        blueprint = self.blueprints_by_id.get(task.metadata.get("blueprint_id"))
        component_id = task.metadata.get("component_id")
        if blueprint is None:
            task.status = "failed"
            self._record_production_task_trace("production_task_failed", task, metadata={"reason": "blueprint_missing"})
            return
        component = next((c for c in getattr(blueprint, "components", []) if c.id == component_id), None)
        if component is None:
            task.status = "failed"
            self._record_production_task_trace("production_task_failed", task, metadata={"reason": "component_missing"})
            return
        if component.status == "complete":
            task.status = "completed"
            self._mark_production_task_progress(task, now, trace_type="production_task_completed", metadata={"reason": "component_complete"})
            return
        for actor in self.village_npcs:
            if getattr(actor, "task_context", None) == "hauling":
                self._handle_npc_hauling_task(actor)
            elif getattr(actor, "task_context", None) == "construction":
                self._handle_npc_construction_task(actor)
            elif component.has_all_materials():
                if self._assign_construction_task_to_npc(actor):
                    self._mark_production_task_progress(task, now, actor=actor, trace_type="build_started", metadata={"component_id": component.id})
            else:
                self._assign_haul_task_to_npc(actor)
        if not component.has_all_materials():
            self._mark_production_task_blocked(task, "missing_materials", now, cooldown=15)
            task.status = "delivering"
        else:
            task.status = "waiting_for_work"

    def _advance_refill_campfire_fuel_task(self, task: ProductionTask) -> None:
        now = int(getattr(self, "game_time", 0) or 0)
        cf = self.campfires_by_id.get(task.metadata.get("campfire_id"))
        if cf is None:
            self._warn_simulation_validation("campfire_refuel_missing_target", (task.id, task.metadata.get("campfire_id")), "Refill task missing campfire target.", metadata={"task_id": task.id})
            task.status = "failed"
            return
        if cf.fuel_quantity >= cf.max_fuel_quantity:
            task.status = "completed"
            return
        actors = [npc for npc in self.village_npcs if not getattr(getattr(npc, "physical", None), "is_dead", False)]
        if not actors:
            self._mark_production_task_blocked(task, "no_available_actors", now)
            return
        actor = sorted(actors, key=lambda a: (-self._score_actor_suitability(a, task, work_tag="hauling", near=(cf.x, cf.y)), getattr(a, "id", 0)))[0]
        item_key = task.metadata.get("item_key", "raw_log")
        if actor.economic.npc_inventory.get(item_key, 0) <= 0:
            source = self.find_stockpile_for_item(item_key, require_available=True, near=(cf.x, cf.y))
            if source is None:
                self._warn_simulation_validation("campfire_refuel_missing_fuel_source", (task.id, item_key), "No fuel source available for campfire refill.", actor=actor, metadata={"task_id": task.id})
                self._record_decision_explanation(explanation_type="campfire_refuel_blocked", decision="blocked", primary_reason="missing_fuel_source", task=task, actor=actor)
                self._mark_production_task_blocked(task, "missing_fuel_source", now)
                return
            item = source.withdraw_item_reference(item_key)
            if item is None:
                self._mark_production_task_blocked(task, "missing_fuel_source", now)
                return
            actor.economic.npc_inventory.add_item_reference(item)
            self._record_production_task_trace("campfire_refuel_started", task, actor=actor, metadata={"campfire_id": cf.campfire_id, "source_stockpile_id": source.stockpile_id})
            self._record_decision_explanation(explanation_type="campfire_refuel_actor_assigned", decision="assigned", primary_reason="hauler_selected_for_refuel", task=task, actor=actor)
        if abs(actor.x - cf.x) > 1 or abs(actor.y - cf.y) > 1:
            task.metadata["moving_to_campfire"] = True
            self._record_production_task_trace("campfire_refuel_waiting_for_actor_range", task, actor=actor, metadata={"campfire_id": cf.campfire_id})
            self._record_decision_explanation(explanation_type="delivery_waiting_for_range", decision="deferred", primary_reason="campfire_refuel_delivery_delayed_until_adjacent", task=task, actor=actor)
            self._route_actor_toward_position(actor, (cf.x, cf.y), reason="campfire_refuel_route_started", task_id=task.id)
            return
        task.metadata["moving_to_campfire"] = False
        carried = actor.economic.npc_inventory.pop_item_reference(item_key)
        if carried is None:
            self._warn_simulation_validation("campfire_fuel_delivery_mismatch", (task.id, actor.id), "Actor expected to deliver fuel but had none.", actor=actor, metadata={"campfire_id": cf.campfire_id})
            return
        cf.fuel_quantity = min(cf.max_fuel_quantity, cf.fuel_quantity + 1)
        cf.lit = True
        cf.last_refuel_tick = now
        self._record_production_task_trace("campfire_refuel_delivered", task, actor=actor, metadata={"campfire_id": cf.campfire_id, "fuel_quantity": cf.fuel_quantity})
        self._record_production_task_trace("campfire_refuel_completed", task, actor=actor, metadata={"campfire_id": cf.campfire_id})
        task.status = "completed"

    def advance_production_tasks(self) -> None:
        now = int(getattr(self, "game_time", 0) or 0)
        self._evaluate_production_dependencies(now)
        if now < int(getattr(self, "next_production_eval_tick", 0) or 0):
            self._record_decision_explanation(explanation_type="scheduler_timeslice_deferred", decision="deferred", primary_reason="production_eval_timeslice", score_snapshot={"next_production_eval_tick": self.next_production_eval_tick})
            return
        self.next_production_eval_tick = now + max(1, int(getattr(self, "scheduling_cadence_config", {}).get("production_eval_interval", 2)))
        active_tasks: list[tuple[int, str, ProductionTask]] = []
        for task in list(self.production_tasks_by_id.values()):
            if task.status in {"completed", "failed", "cancelled"}:
                continue
            if task.expiration_tick is not None and now > task.expiration_tick:
                task.status = "failed"
                self._warn_simulation_validation("orphaned_production_task", (task.id, "expired"), "ProductionTask expired before completion.", metadata={"task_id": task.id, "task_type": task.task_type})
                self._record_production_task_trace("production_task_failed", task, metadata={"reason": "expired"})
                continue
            score = self._compute_production_task_score(task, now)
            self._record_production_task_trace("production_task_scored", task, metadata={"score": score, "blocked_reason": task.blocked_reason, "cooldown_until_tick": task.cooldown_until_tick})
            self._record_decision_explanation(explanation_type="task_scored", decision="scored", primary_reason="arbitration_score_computed", task=task, contributing_factors={"blocked_reason": task.blocked_reason}, score_snapshot={"score": score, "cooldown_until_tick": task.cooldown_until_tick})
            active_tasks.append((score, task.id, task))

        active_tasks.sort(key=lambda entry: (-entry[0], entry[1]))
        for index, (score, _, task) in enumerate(active_tasks):
            if now < max(0, task.cooldown_until_tick):
                self._record_production_task_trace("production_task_deferred", task, metadata={"score": score, "reason": "cooldown"})
                self._record_decision_explanation(explanation_type="task_deferred", decision="deferred", primary_reason="cooldown_active", task=task, score_snapshot={"score": score, "cooldown_until_tick": task.cooldown_until_tick})
                continue
            if index > 0 and score > active_tasks[0][0] + 200:
                self._warn_simulation_validation("production_task_priority_inversion", (task.id, score), "Lower-ranked task appears to exceed expected arbitration window.", metadata={"task_id": task.id, "score": score})
            self._record_production_task_trace("production_task_selected", task, metadata={"score": score, "rank": index})
            self._record_decision_explanation(explanation_type="task_selected", decision="selected", primary_reason="highest_ranked_runnable_task", task=task, score_snapshot={"score": score, "rank": index})
            if task.task_type == "produce_logs":
                self._advance_produce_logs_task(task)
            elif task.task_type == "build_component":
                self._advance_build_component_task(task)
            elif task.task_type == "craft_plank":
                self._advance_craft_production_task(task)
            elif task.task_type == "refill_campfire_fuel":
                self._advance_refill_campfire_fuel_task(task)
            if (now - max(task.last_progress_tick or task.created_tick, task.created_tick)) > 200:
                self._record_production_task_trace("production_task_starved", task, metadata={"score": score})
                self._warn_simulation_validation("production_task_starvation", (task.id, task.task_type), "Production task has not progressed for an extended period.", metadata={"task_id": task.id, "task_type": task.task_type})
            if task.retry_count > 8:
                self._warn_simulation_validation("production_task_excessive_retries", (task.id, task.retry_count), "Production task is retrying excessively.", metadata={"task_id": task.id, "retry_count": task.retry_count})

    def _handle_npc_speech(self):
        current_time = time.time()
        player_rep = self.player.social.reputation  # Get player rep once

        # Ensure self.npcs and self.village_npcs are initialized
        if not hasattr(self, 'npcs'):
            self.npcs = []
        if not hasattr(self, 'village_npcs'):
            self.village_npcs = []

        for npc in self.npcs + self.village_npcs:
            task_key = ("ambient_speech", npc.id)
            if task_key in self._background_llm_tasks and not self._is_npc_llm_relevant_to_player(npc):
                self._cancel_background_llm_task(task_key)
            llm_dialogue = self._poll_background_llm_task(task_key)
            if llm_dialogue is not None and llm_dialogue is not BACKGROUND_LLM_PENDING:
                if llm_dialogue:
                    distance_to_player = abs(npc.x - self.player.x) + abs(npc.y - self.player.y)
                    can_hear = (
                        distance_to_player <= self.player.physical.hearing_radius
                        and distance_to_player <= npc.speech_volume
                    )
                    if can_hear:
                        self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)}: {llm_dialogue.strip()}")
                npc.last_speech_time = current_time
                continue

            if task_key in self._background_llm_tasks:
                continue

            if current_time - npc.last_speech_time > random.randint(10, 30):
                if not self._is_npc_llm_relevant_to_player(npc):
                    self._cancel_background_llm_task(task_key)
                    npc.last_speech_time = current_time
                    continue
                # Ambient speech might be general, or react to player if nearby and reputation is notable
                prompt = (
                    f"NPC {npc.name} (Personality: {npc.social.personality}, Attitude to Player: {npc.attitude_to_player}, Family: {npc.social.family_ties}) "
                    f"is going about their day. The player's reputation is: "
                    f"Criminal Points: {player_rep.get(REP_CRIMINAL, 0)}, Hero Points: {player_rep.get(REP_HERO, 0)}. "
                    f"Generate a short, in-character ambient thought or statement from {npc.name}. "
                    f"It could be about their current (unspecified) activity, the village, a general thought, "
                    f"or a comment related to the player if their reputation is particularly high or low and the player is assumed to be generally known or nearby. "
                    f"Keep it concise."
                )
                self._submit_background_llm_task(task_key, prompt)

    def decorate_building_interior(self, building: Building, chunk: Chunk):
        from simulation.systems.architecture import BUILDING_ARCHETYPES, generate_building

        if building.interior_decorated:
            return

        # Fast path if new architecture system supports this building type
        if building.building_type in BUILDING_ARCHETYPES:
            generated = generate_building(
                building.building_type,
                building.x, building.y,
                building.width, building.height
            )
            for furn_x, furn_y, furn_role in generated.placed_furniture:
                item_type = furn_role
                if item_type == "bed": item_type = "bed_simple"
                elif item_type == "wooden_bed": item_type = "wooden_bed"
                elif item_type == "chair": item_type = "wooden_chair"
                elif item_type == "table": item_type = "wooden_table"
                elif item_type == "storage": item_type = "chest_wooden"
                elif item_type == "dresser": item_type = "chest_wooden"
                elif item_type == "counter": item_type = "wooden_table"
                elif item_type == "desk": item_type = "wooden_table"
                elif item_type == "shelf": item_type = "wall_shelf"
                elif item_type == "bookshelf": item_type = "bookshelf"
                elif item_type == "fireplace": item_type = "fire_pit_simple"
                elif item_type == "workbench": item_type = "workbench"
                elif item_type == "stone_anvil": item_type = "stone_anvil"

                decoration_tile_def = DECORATION_ITEM_DEFINITIONS.get(item_type)
                if decoration_tile_def:
                    if 0 <= furn_x < WORLD_WIDTH and 0 <= furn_y < WORLD_HEIGHT:
                        global_x = building.global_origin_x + (furn_x - building.x)
                        global_y = building.global_origin_y + (furn_y - building.y)
                        self._place_building_decoration_tile(building, item_type, global_x, global_y)

            for anchor in generated.anchors:
                global_x = building.global_origin_x + (anchor.x - building.x)
                global_y = building.global_origin_y + (anchor.y - building.y)

                # Double-check that it's within world bounds and building bounds
                if 0 <= global_x < WORLD_WIDTH and 0 <= global_y < WORLD_HEIGHT:
                    # Also ensure it doesn't block doors, but the architecture generation already handles that
                    building.anchors.append({
                        "type": anchor.type,
                        "x": global_x,
                        "y": global_y,
                        "tags": anchor.tags
                    })

            self._ensure_building_entrance_integrity(building)
            building.interior_decorated = True
            return

        decoration_data = {'decorations': []}
        # if building.building_type == 'house':
        #     decoration_data['decorations'].append({'type': 'bed_simple', 'x': 1, 'y': 1})
        #     decoration_data['decorations'].append({'type': 'wooden_table', 'x': building.width - 2, 'y': 1})
        #     decoration_data['decorations'].append({'type': 'wooden_chair', 'x': building.width - 3, 'y': 1})
        llm_response = '' # Ensure llm_response is defined # Added chunk to access village lore
        # Ensure we have the village object if the building is in a village POI
        village = None
        if chunk and chunk.poi_type == "village" and chunk.village:
            village = chunk.village

        # self.add_message_to_chat_log(f"Decorating {building.building_type} ({building.id[:6]}) in village (Lore: {'Yes' if village and village.lore else 'No'}). Residents: {len(building.residents)}")

        # --- Gather Context for LLM ---
        village_lore_summary = "This building stands alone, its story yet unwritten."
        if village and village.lore:
            # Summarize lore if too long, or use as is if short.
            # For now, using first 150 chars as a simple summary.
            village_lore_summary = village.lore[:150].strip() + "..." if len(village.lore) > 150 else village.lore.strip()
            if not village_lore_summary: village_lore_summary = "A quiet, unassuming village."


        inhabitant_details_parts = []
        if building.residents:
            for i, resident_npc in enumerate(building.residents):
                detail = (
                    f"Inhabitant {i+1}: Name: {resident_npc.name}, "
                    f"Personality: {resident_npc.social.personality}, "
                    f"Wealth: {resident_npc.economic.wealth_level}, "
                    f"Profession: {resident_npc.economic.profession}."
                )
                inhabitant_details_parts.append(detail)

        if not inhabitant_details_parts:
            inhabitant_details = "This building is currently unoccupied or its inhabitants are unknown."
            # Potentially assign a default "generic poor family" if building type implies residence but no one is assigned
            if building.category == "residential":
                 inhabitant_details = "A simple family of modest means is presumed to live here."
        else:
            inhabitant_details = "\n".join(inhabitant_details_parts)

        decoration_items_list = ", ".join(DECORATION_ITEM_DEFINITIONS.keys())

        prompt = LLM_PROMPTS["building_interior"].format(
            building_type=building.building_type,
            width=building.width,
            height=building.height,
            village_lore_summary=village_lore_summary,
            inhabitant_details=inhabitant_details,
            decoration_items=decoration_items_list
        )

        # self.add_message_to_chat_log(f"Decorating prompt for {building.id[:6]}:\n{prompt}") # For debugging the full prompt

        llm_response = self._call_llm_for_worldgen(prompt)
        try:
            # If the response is a valid JSON, use it. Otherwise, fallback to placeholder.
            decoration_data = json.loads(llm_response)
        except json.JSONDecodeError:
            self.add_message_to_chat_log(f"LLM failed to provide valid JSON for {building.building_type} interior. Using placeholder.")
            decoration_data = {"decorations": []}
            if building.building_type == "house":
                decoration_data["decorations"].append({"type": "bed_simple", "x": 1, "y": 1})
                decoration_data["decorations"].append({"type": "wooden_table", "x": building.width - 2, "y": 1})
                decoration_data["decorations"].append({"type": "wooden_chair", "x": building.width - 3, "y": 1})

        try:
            fallback_decorations = self._get_default_interior_decorations(building)
            decorations_to_place = decoration_data.get("decorations", []) or fallback_decorations
            for item in decorations_to_place:
                item_type = item.get("type")
                item_x = item.get("x")
                item_y = item.get("y")

                if item_type and item_x is not None and item_y is not None:
                    # Ensure item is within building bounds
                    if 0 < item_x < building.width -1 and 0 < item_y < building.height -1: # Ensure not on wall
                        global_x = building.global_origin_x + item_x
                        global_y = building.global_origin_y + item_y

                        decoration_tile_def = DECORATION_ITEM_DEFINITIONS.get(item_type)
                        if decoration_tile_def:
                            self._place_building_decoration_tile(building, item_type, global_x, global_y)
                        else:
                            print(f"Unknown decoration item type: {item_type}")
                    else:
                        print(f"Decoration item {item_type} out of bounds for building at ({building.x}, {building.y})")
        except Exception as e:
            print(f"Error during placeholder decoration: {e}")

        self._ensure_building_entrance_integrity(building)
        building.interior_decorated = True

    def _spawn_traveling_merchants(self):
        """Spawns a few traveling merchants in random villages."""
        all_villages = []
        for y_chunk in range(self.chunk_height):
            for x_chunk in range(self.chunk_width):
                chunk = self.chunks[y_chunk][x_chunk]
                if chunk.village:
                    all_villages.append(chunk.village)

        if not all_villages:
            return

        num_merchants = 2 # Let's spawn 2 for now
        for i in range(num_merchants):
            start_village = random.choice(all_villages)

            # Find a building in the village to place the merchant
            if not start_village.buildings:
                continue

            start_building = random.choice(start_village.buildings)
            start_x = start_building.global_center_x
            start_y = start_building.global_center_y

            prompt = LLM_PROMPTS["npc_personality"].format(
                player_criminal_points=self.player.social.reputation.get(REP_CRIMINAL, 0),
                player_hero_points=self.player.social.reputation.get(REP_HERO, 0),
                name_hint="a traveling merchant",
                personality_hint="worldly, business-savvy, friendly",
                family_ties_hint="none",
                attitude_to_player_hint="neutral"
            )
            llm_response = self._call_llm_for_worldgen(prompt)
            try:
                npc_data = json.loads(llm_response)

                merchant = NPC(
                    x=start_x,
                    y=start_y,
                    name=npc_data.get("name", f"Traveling Merchant {i+1}"),
                    dialogue=npc_data.get("dialogue", ["Looking for a deal?"]),
                    personality=npc_data.get("personality", "merchant"),
                    family_ties=npc_data.get("family_ties", "none"),
                    attitude_to_player=npc_data.get("attitude_to_player", "neutral"),
                    player_id=self.player.id
                )
                self._set_entity_profession(merchant, "Traveling Merchant", reason="spawn_trader")
                merchant.economic.money = random.randint(200, 500)
                # Give them some goods to sell
                merchant.economic.npc_inventory["healing_salve"] = random.randint(5, 15)
                merchant.economic.npc_inventory["iron_ingot"] = random.randint(3, 10)
                # merchant.npc_inventory["cloth"] = random.randint(10, 20)

                # Set their initial AI state
                merchant.schedule.current_task = "traveling_to_village"

                self.npcs.append(merchant) # Add them to the general NPC list, not a specific village
                self._mark_entity_positions_dirty()
                self.add_message_to_chat_log(f"A traveling merchant, {self.get_entity_display_name(merchant)}, has begun their journey.")

            except json.JSONDecodeError as e:
                self.add_message_to_chat_log(f"Error parsing LLM response for Traveling Merchant: {e}")

    def talk_to_npc(self):
        # Find the closest NPC and interact with them
        closest_npc = None
        min_dist = float('inf')
        for npc in self.npcs + self.village_npcs:
            dist = math.sqrt((self.player.x - npc.x)**2 + (self.player.y - npc.y)**2)
            if dist < min_dist:
                min_dist = dist
                closest_npc = npc

        if closest_npc and min_dist <= 2: # Within 2 tiles
            # Use LLM for dynamic dialogue
            player_rep = self.player.social.reputation
            prompt = (
                f"The player (Criminal Points: {player_rep.get(REP_CRIMINAL, 0)}, Hero Points: {player_rep.get(REP_HERO, 0)}) "
                f"approaches {closest_npc.name}. "
                f"{closest_npc.name} is {closest_npc.social.personality}, their family ties are '{closest_npc.social.family_ties.get('description')}', "
                f"and their current attitude towards the player is '{closest_npc.attitude_to_player}'. "
                f"Generate a short, in-character dialogue response from {closest_npc.name} to the player. "
                f"The dialogue should reflect their personality, current attitude, and potentially acknowledge the player's reputation if significant. Keep it concise."
            )
            llm_dialogue = self._call_llm_for_background(prompt)
            # self.add_message_to_chat_log(f"{closest_npc.name}: {llm_dialogue}") # Use chat log for consistency
            print(f"\n{closest_npc.name}: {llm_dialogue}") # Keep print for now as it's more direct for dialogue
            self.last_talked_to_npc = closest_npc # Store for potential follow-up actions like persuasion
        else:
            print("No one to talk to nearby.")
            self.last_talked_to_npc = None

    def _initialize_chunks(self):
        """Initializes chunk data based on the world generator's macro map."""
        chunks = [[None for _ in range(self.chunk_width)] for _ in range(self.chunk_height)]
        for y in range(self.chunk_height):
            for x in range(self.chunk_width):
                biome = self.generator.get_biome_at(x, y)
                poi_type = self.generator.get_poi_at(x, y, biome)
                region = self.atlas.get_or_create_region_for_chunk(x, y, biome)
                chunks[y][x] = Chunk(biome, poi_type, region_id=region.id)
        return chunks

    def get_region_for_chunk(self, chunk_x: int, chunk_y: int):
        """Returns the atlas-owned region for a chunk coordinate."""
        return self.atlas.get_region_for_chunk(chunk_x, chunk_y)

    def get_region_for_coords(self, world_x: int, world_y: int):
        """Returns the atlas-owned region for world coordinates."""
        return self.atlas.get_region_for_world_coords(world_x, world_y, CHUNK_SIZE)

    def get_history_event(self, event_id: str):
        """Returns a history event from the ledger."""
        return self.history.get_event(event_id)

    def get_book_record(self, book_id: str):
        """Returns a book record from the ledger."""
        return self.history.get_book(book_id)

    def _find_starting_position(self):
        """
        Finds a suitable starting tile for the player.
        Prioritizes the player's family home if it exists.
        """
        # 1. Check for family home
        family_ids = []
        if "mother_id" in self.player.social.family_ties: family_ids.append(self.player.social.family_ties["mother_id"])
        if "father_id" in self.player.social.family_ties: family_ids.append(self.player.social.family_ties["father_id"])
        if "sibling_ids" in self.player.social.family_ties: family_ids.extend(self.player.social.family_ties["sibling_ids"])

        home_building = None
        for npc_id in family_ids:
            npc = self.get_entity_by_id(npc_id)
            if npc and npc.schedule.home_building_id:
                home_building = self.buildings_by_id.get(npc.schedule.home_building_id)
                if home_building:
                    break

        if home_building:
            home_chunk_x = home_building.global_origin_x // CHUNK_SIZE
            home_chunk_y = home_building.global_origin_y // CHUNK_SIZE
            if 0 <= home_chunk_x < self.chunk_width and 0 <= home_chunk_y < self.chunk_height:
                home_chunk = self.chunks[home_chunk_y][home_chunk_x]
                if not home_chunk.is_terrain_generated:
                    self._generate_chunk_detail(home_chunk, home_chunk_x, home_chunk_y)

            spawn_tile = self._get_spawn_tile_for_building(home_building)
            if spawn_tile is not None:
                self._update_entity_position(self.player, *spawn_tile)
                return

            start_x = home_building.global_center_x
            start_y = home_building.global_center_y
            sx, sy = self._find_best_adjacent_tile(start_x, start_y, self.player)
            if sx is not None:
                self._update_entity_position(self.player, sx, sy)
                return

        # 2. Fallback to searching outwards from the center
        center_x, center_y = self.player.x, self.player.y
        margin = 15  # Keep player this many tiles away from the edge

        # Check if the initial center position is already valid and safe
        if (margin <= center_x < WORLD_WIDTH - margin and
            margin <= center_y < WORLD_HEIGHT - margin and
            self.get_tile_at(center_x, center_y) and self.get_tile_at(center_x, center_y).passable):
            return

        # Search outwards from the center
        for r in range(1, max(WORLD_WIDTH, WORLD_HEIGHT) // 2):
            # Check top and bottom rows of the expanding search box
            for x_offset in range(-r, r + 1):
                for y_sign in [-1, 1]:
                    tx, ty = center_x + x_offset, center_y + (r * y_sign)

                    # Boundary and margin check
                    if not (margin <= tx < WORLD_WIDTH - margin and margin <= ty < WORLD_HEIGHT - margin):
                        continue

                    tile = self.get_tile_at(tx, ty)
                    if tile and tile.passable and "water" not in tile.name.lower():
                        chunk = self.chunks[ty // CHUNK_SIZE][tx // CHUNK_SIZE]
                        if chunk.biome == "plains": # Prioritize plains
                            self._update_entity_position(self.player, tx, ty)
                            return

            # Check left and right columns
            for y_offset in range(-r + 1, r):
                for x_sign in [-1, 1]:
                    tx, ty = center_x + (r * x_sign), center_y + y_offset

                    # Boundary and margin check
                    if not (margin <= tx < WORLD_WIDTH - margin and margin <= ty < WORLD_HEIGHT - margin):
                        continue

                    tile = self.get_tile_at(tx, ty)
                    if tile and tile.passable and "water" not in tile.name.lower():
                        chunk = self.chunks[ty // CHUNK_SIZE][tx // CHUNK_SIZE]
                        if chunk.biome == "plains": # Prioritize plains
                            self._update_entity_position(self.player, tx, ty)
                            return

        # Fallback if no plains found, search again for any passable tile within margin
        for r in range(1, max(WORLD_WIDTH, WORLD_HEIGHT) // 2):
            for x_offset in range(-r, r + 1):
                for y_sign in [-1, 1]:
                    tx, ty = center_x + x_offset, center_y + (r * y_sign)
                    if (margin <= tx < WORLD_WIDTH - margin and margin <= ty < WORLD_HEIGHT - margin):
                        tile = self.get_tile_at(tx, ty)
                        if tile and tile.passable and "water" not in tile.name.lower():
                            self._update_entity_position(self.player, tx, ty)
                            return
            for y_offset in range(-r + 1, r):
                for x_sign in [-1, 1]:
                    tx, ty = center_x + (r * x_sign), center_y + y_offset
                    if (margin <= tx < WORLD_WIDTH - margin and margin <= ty < WORLD_HEIGHT - margin):
                        tile = self.get_tile_at(tx, ty)
                        if tile and tile.passable and "water" not in tile.name.lower():
                            self._update_entity_position(self.player, tx, ty)
                            return

        print("Warning: No passable starting tile found within the safe margin. Player may be stuck.")

    def _create_family_npc(self, role: str, last_name: str, home_building: Building, family_ties: dict):
        """Helper to create a family member NPC."""
        # Determine age and gender based on role
        if role == "Father":
            age = random.randint(35, 55)
            gender = "male"
            name_hint = "a middle-aged man"
        elif role == "Mother":
            age = random.randint(35, 55)
            gender = "female"
            name_hint = "a middle-aged woman"
        elif role == "Brother":
            age = random.randint(16, 25)
            gender = "male"
            name_hint = "a young man"
        elif role == "Sister":
            age = random.randint(16, 25)
            gender = "female"
            name_hint = "a young woman"
        else:
            age = 20
            gender = "male"
            name_hint = "a villager"

        fallback_first_name = random.choice(FAMILY_FIRST_NAMES.get(gender, FAMILY_FIRST_NAMES["male"]))
        fallback_name = f"{fallback_first_name} {last_name}"

        prompt = LLM_PROMPTS["npc_personality"].format(
            player_criminal_points=0,
            player_hero_points=0,
            name_hint=name_hint,
            personality_hint="family member, familiar",
            family_ties_hint="player's relative",
            attitude_to_player_hint="friendly"
        )

        npc_data = {}
        llm_response = self._call_llm_for_worldgen(prompt)
        try:
            npc_data = json.loads(llm_response)
        except:
            npc_data = {
                "name": fallback_name,
                "dialogue": ["Hello, dear."],
                "personality": "friendly"
            }

        family_ties = dict(family_ties)
        family_ties.setdefault("relation_to_player", role.lower())

        npc = NPC(
            x=home_building.global_center_x,
            y=home_building.global_center_y,
            name=npc_data.get("name") or fallback_name,
            dialogue=npc_data.get("dialogue", ["Welcome home."]),
            personality=npc_data.get("personality", "friendly"),
            family_ties=family_ties,
            attitude_to_player="friendly",
            player_id=self.player.id
        )
        npc.age = age
        npc.gender = gender
        npc.schedule.home_building_id = home_building.id
        home_building.residents.append(npc)

        # Assign a random job in the village if available
        village = self._get_village_for_npc(npc, by_coords=True)
        if village:
            potential_jobs = [b for b in village.buildings if "workplace" in b.category]
            vacant_jobs = []
            for b in potential_jobs:
                workers = sum(1 for n in self.village_npcs if n.schedule.work_building_id == b.id)
                if workers < b.max_workers:
                    vacant_jobs.append(b)

            if vacant_jobs and random.random() < 0.8:
                job = random.choice(vacant_jobs)
                self._assign_job(npc, job)
            else:
                self._set_entity_profession(npc, "Unemployed", reason="no_available_job")

        # Force a schedule update on their very first tick instead of idling
        npc.schedule.game_time_last_updated = self.game_time - NPC_SCHEDULE_UPDATE_INTERVAL

        self.village_npcs.append(npc)
        self._mark_entity_positions_dirty()
        return npc

    def _generate_player_family(self):
        """Generates a family for the player and assigns them a home."""
        family_name = self.player.social.family_ties.get("last_name")
        if not family_name:
            family_name = random.choice(FAMILY_LAST_NAMES)
            self.player.social.family_ties["last_name"] = family_name
        first_name = str(getattr(self.player, "first_name", "") or "Player").strip() or "Player"
        self.player.first_name = first_name
        self.player.name = f"{first_name} {family_name}"

        if not self.villages:
            return

        # 1. Pick a starting village
        start_village = random.choice(self.villages)

        # 2. Pick a home in that village
        residential_buildings = [b for b in start_village.buildings if b.category == "residential"]
        if not residential_buildings:
            return

        # Prioritize empty houses
        empty_homes = [b for b in residential_buildings if not b.residents]
        if empty_homes:
            player_home = random.choice(empty_homes)
        else:
            player_home = random.choice(residential_buildings)
            # Evict current residents to make room for family
            for occupant in list(player_home.residents):
                self._remove_npc_from_world(occupant, reason="evicted for player family")
            player_home.residents.clear()

        player_home.player_owned = True

        # 3. Determine Family Scenario
        scenarios = ["Nuclear", "Single Mother", "Single Father", "Siblings Only"]
        weights = [0.4, 0.2, 0.2, 0.2]
        scenario = random.choices(scenarios, weights=weights, k=1)[0]

        # 4. Determine Wealth
        wealth_levels = ["Poor", "Average", "Wealthy"]
        wealth_weights = [0.3, 0.5, 0.2]
        wealth = random.choices(wealth_levels, weights=wealth_weights, k=1)[0]

        self.add_message_to_chat_log(f"Story: You come from a {wealth.lower()} {scenario.lower()} family.")

        # Adjust player starting money based on wealth
        if wealth == "Poor":
            self.player.economic.money = random.randint(0, 20)
        elif wealth == "Average":
            self.player.economic.money = random.randint(50, 100)
        elif wealth == "Wealthy":
            self.player.economic.money = random.randint(200, 500)

        # 5. Create NPCs
        if "Mother" in scenario or scenario == "Nuclear":
            self._create_family_npc("Mother", family_name, player_home, {"child_id": self.player.id, "relation_to_player": "mother"})
            self.player.social.family_ties["mother_id"] = self.village_npcs[-1].id

        if "Father" in scenario or scenario == "Nuclear":
            self._create_family_npc("Father", family_name, player_home, {"child_id": self.player.id, "relation_to_player": "father"})
            self.player.social.family_ties["father_id"] = self.village_npcs[-1].id

        # Siblings
        num_siblings = random.randint(0, 3)
        for i in range(num_siblings):
            role = random.choice(["Brother", "Sister"])
            self._create_family_npc(role, family_name, player_home, {"sibling_id": self.player.id, "relation_to_player": role.lower()})
            if "sibling_ids" not in self.player.social.family_ties:
                self.player.social.family_ties["sibling_ids"] = []
            if isinstance(self.player.social.family_ties["sibling_ids"], list):
                self.player.social.family_ties["sibling_ids"].append(self.village_npcs[-1].id)

    def _generate_chunk_macro(self, chunk: Chunk, chunk_coord_x: int, chunk_coord_y: int):
        """Generates the macro structure (village, buildings, NPCs) for a chunk."""
        if chunk.is_generated: return

        region = self.atlas.get_region(chunk.region_id)
        chunk_coords = (chunk_coord_x, chunk_coord_y)
        if chunk.poi_type == "village":
            chunk.village = Village(primary_biome=chunk.biome, chunk_coords=chunk_coords, region_id=chunk.region_id)
            chunk.village.lore = "The mists of time have obscured this village's history." # Fallback
            self._generate_village_structure(chunk, chunk_coord_x, chunk_coord_y)
            self.atlas.add_village(chunk.village, chunk_coords=chunk_coords, region=region)
        elif chunk.poi_type == "ruin":
            chunk.ruin = Ruin(primary_biome=chunk.biome, chunk_coords=chunk_coords, region_id=chunk.region_id)
            chunk.ruin.lore = "The origins of this place are lost to time."
            self.atlas.add_ruin(chunk.ruin, chunk_coords=chunk_coords, region=region)
            # Ruins are simple, we can just init the object and generate details later.

        chunk.is_generated = True

    def _generate_chunk_detail(self, chunk: Chunk, chunk_x: int, chunk_y: int):
        """Generates the detailed tiles for a chunk based on its macro structure."""
        if chunk.is_terrain_generated: return

        # Generate base terrain
        biome_def = TILE_DEFINITIONS[chunk.biome]
        tiles = [[Tile(biome_def["char"], biome_def["color"], biome_def["passable"], biome_def["name"], properties={}) for _ in range(CHUNK_SIZE)] for _ in range(CHUNK_SIZE)]
        chunk.tiles = tiles # Assign initially

        # Mark as generated immediately to prevent recursion in get_tile_at calls during decoration
        chunk.is_terrain_generated = True

        # Add biome-specific details
        self._render_biome_details(chunk, chunk_x, chunk_y)

        # Render structures
        if chunk.village:
            self._render_village_tiles(chunk)
        elif chunk.ruin:
            self._generate_ruin_layout(chunk, chunk_x, chunk_y) # Renders directly to tiles

    def _render_biome_details(self, chunk, chunk_x, chunk_y):
        """Renders terrain decorations for a chunk without spawning entities."""
        tiles = chunk.tiles
        chunk.allow_wildlife_population = True

        if chunk.biome == "plains":
            for y_local in range(CHUNK_SIZE):
                for x_local in range(CHUNK_SIZE):
                    if tiles[y_local][x_local].name == "Plains":
                        if random.random() < 0.03:
                            tree_type_roll = random.random()
                            tree_x_world = chunk_x * CHUNK_SIZE + x_local
                            tree_y_world = chunk_y * CHUNK_SIZE + y_local
                            # Avoid overwriting buildings or roads (checked by name/passable later but buildings aren't drawn yet)
                            # We render biome BEFORE buildings, so buildings will overwrite trees. This is fine.
                            if tree_type_roll < 0.4:
                                tiles[y_local][x_local] = OakTree(tree_x_world, tree_y_world)
                            elif tree_type_roll < 0.7:
                                tiles[y_local][x_local] = AppleTree(tree_x_world, tree_y_world)
                            else:
                                tiles[y_local][x_local] = PearTree(tree_x_world, tree_y_world)
                            if 0 <= tree_y_world < WORLD_HEIGHT and 0 <= tree_x_world < WORLD_WIDTH:
                                self.transparency_map[tree_y_world, tree_x_world] = False
                        elif random.random() < 0.01:
                            sapling_def = TILE_DEFINITIONS["sapling"]
                            tiles[y_local][x_local] = Tile(sapling_def["char"], sapling_def["color"], sapling_def["passable"], sapling_def["name"], properties=sapling_def.get("properties", {}).copy())
                        elif random.random() < 0.15:
                            tiles[y_local][x_local] = Tile(TILE_DEFINITIONS["tall_grass"]["char"], TILE_DEFINITIONS["tall_grass"]["color"], TILE_DEFINITIONS["tall_grass"]["passable"], TILE_DEFINITIONS["tall_grass"]["name"], TILE_DEFINITIONS["tall_grass"].get("properties", {}))
                        elif random.random() < 0.01:
                            tiles[y_local][x_local] = Tile(TILE_DEFINITIONS["flower"]["char"], TILE_DEFINITIONS["flower"]["color"], TILE_DEFINITIONS["flower"]["passable"], TILE_DEFINITIONS["flower"]["name"], TILE_DEFINITIONS["flower"].get("properties", {}))

                        # Add Dens if missing (fallback logic for existing generation)
                        # (This section was already added in previous step, ensuring it remains)

                        # Den Placement Logic
                        if random.random() < 0.002: # Chance to spawn a den per tile (low chance)
                            # Determine suitable den for this biome
                            potential_dens = []
                            for den_key, item_def in DECORATION_ITEM_DEFINITIONS.items():
                                if "den" in item_def.get("item_type_tags", []):
                                    spawn_type = item_def["properties"].get("spawn_type")
                                    animal_def = ANIMAL_DEFINITIONS.get(spawn_type)
                                    if animal_def and chunk.biome in animal_def.get("spawn_biomes", []):
                                        potential_dens.append(den_key)

                            if potential_dens:
                                den_key = random.choice(potential_dens)
                                den_def = DECORATION_ITEM_DEFINITIONS[den_key]
                                world_x = chunk_x * CHUNK_SIZE + x_local
                                world_y = chunk_y * CHUNK_SIZE + y_local

                                # Place the den
                                tiles[y_local][x_local] = Tile(
                                    char=den_def["char"],
                                    color=den_def["color"],
                                    passable=den_def["passable"],
                                    name=den_def["name"],
                                    properties=den_def.get("properties", {}).copy()
                                )
                                if 0 <= world_x < WORLD_WIDTH and 0 <= world_y < WORLD_HEIGHT:
                                    self.transparency_map[world_y, world_x] = not den_def.get("blocks_fov", False)

    def _is_wildlife_spawn_tile_suitable(self, species_key: str, chunk: Chunk, world_x: int, world_y: int) -> bool:
        tile = self.get_tile_at(world_x, world_y)
        if tile is None or not getattr(tile, "passable", False):
            return False
        species_def = WILDLIFE_SPECIES.get(species_key, {})
        preferred_biomes = set(species_def.get("preferred_biomes", set()))
        if preferred_biomes and getattr(chunk, "biome", None) not in preferred_biomes:
            return False
        preferred_tiles = set(species_def.get("preferred_tiles", set()))
        if preferred_tiles and getattr(tile, "name", None) not in preferred_tiles:
            return False
        if abs(world_x - self.player.x) + abs(world_y - self.player.y) < 6:
            return False
        self._ensure_entity_positions_current()
        if self.entity_positions.get((world_x, world_y)) is not None:
            return False
        village = getattr(chunk, "village", None)
        if village is not None:
            for building in getattr(village, "buildings", []):
                if abs(world_x - building.global_center_x) + abs(world_y - building.global_center_y) <= 8:
                    return False
            for coords_list in getattr(village, "interaction_points", {}).values():
                for point_x, point_y in coords_list:
                    if abs(world_x - point_x) + abs(world_y - point_y) <= 8:
                        return False
        return True

    def _find_wildlife_spawn_tiles(self, species_key: str, chunk: Chunk, chunk_x: int, chunk_y: int, limit: int = 12) -> list[tuple[int, int]]:
        candidates: list[tuple[int, int]] = []
        if not chunk.tiles:
            return candidates
        for y_local in range(CHUNK_SIZE):
            for x_local in range(CHUNK_SIZE):
                world_x = chunk_x * CHUNK_SIZE + x_local
                world_y = chunk_y * CHUNK_SIZE + y_local
                if self._is_wildlife_spawn_tile_suitable(species_key, chunk, world_x, world_y):
                    candidates.append((world_x, world_y))
        random.shuffle(candidates)
        return candidates[:limit]

    def _manifest_wildlife_entity(self, species_key: str, x: int, y: int, region_id: str, population_id: str) -> Animal | None:
        animal_def = ANIMAL_DEFINITIONS.get(species_key)
        if not animal_def:
            return None
        animal = Animal(
            x,
            y,
            name=animal_def.get("name", species_key.title()),
            animal_type=species_key,
            animal_definition=animal_def,
        )
        animal.wildlife_region_id = region_id
        animal.wildlife_population_id = population_id
        animal.current_sub_task = "Roaming"
        self.npcs.append(animal)
        return animal

    def _populate_chunk_wildlife(self, chunk: Chunk, chunk_x: int, chunk_y: int):
        """Manifest nearby wildlife from persistent regional populations.

        Regional populations remain the source of truth. This method only creates
        a bounded number of local animal actors for active/generated chunks; it
        does not create population out of thin air or use per-tile respawn rolls.
        """
        if chunk.wildlife_generated or not chunk.tiles or not getattr(chunk, "allow_wildlife_population", False):
            return

        chunk.wildlife_generated = True
        region = self.atlas.get_region(getattr(chunk, "region_id", None))
        if region is None:
            return

        region_populations = self.ecology.get_region_populations(self, region.id)
        spawned_entities = False
        chunk_coords = (chunk_x, chunk_y)

        for species_key, population in region_populations.items():
            if population.population_count <= 0:
                continue
            target_visible = self.ecology.target_visible_count(population)
            visible_in_region = self.ecology.count_visible_wildlife(self, region.id, species_key)
            if visible_in_region >= target_visible:
                population.refresh_pressure(visible_in_region)
                continue
            species_def = WILDLIFE_SPECIES.get(species_key, {})
            max_per_chunk = int(species_def.get("max_visible_per_chunk", 3))
            visible_in_chunk = self.ecology.count_visible_wildlife(self, region.id, species_key, chunk_coords=chunk_coords)
            available_slots = min(max_per_chunk - visible_in_chunk, target_visible - visible_in_region)
            if available_slots <= 0:
                continue

            spawn_tiles = self._find_wildlife_spawn_tiles(species_key, chunk, chunk_x, chunk_y, limit=max(available_slots * 3, 6))
            if not spawn_tiles:
                continue
            group_min, group_max = species_def.get("group_size", (1, 1))
            spawn_count = min(available_slots, random.randint(int(group_min), int(group_max)), len(spawn_tiles))
            for spawn_x, spawn_y in spawn_tiles[:spawn_count]:
                animal = self._manifest_wildlife_entity(species_key, spawn_x, spawn_y, region.id, f"{region.id}:{species_key}")
                if animal is None:
                    continue
                population.visible_entity_ids.add(animal.id)
                spawned_entities = True
            population.refresh_pressure(self.ecology.count_visible_wildlife(self, region.id, species_key))

        if spawned_entities:
            self._mark_entity_positions_dirty()

    def _generate_village_structure(self, chunk: Chunk, chunk_coord_x: int, chunk_coord_y: int):
        """Generates the logical structure of a village (buildings, NPCs) without rendering tiles."""

        llm_prompt = LLM_PROMPTS["village_lore"].format(biome=chunk.biome)
        llm_response = self._call_llm_for_worldgen(llm_prompt)
        try:
            lore_data = json.loads(llm_response)
            chunk.village.lore = lore_data.get("village_lore", "The mists of time have obscured this village's history.")
        except json.JSONDecodeError:
            chunk.village.lore = "The mists of time have obscured this village's history."

        chunk_global_start_x = chunk_coord_x * CHUNK_SIZE
        chunk_global_start_y = chunk_coord_y * CHUNK_SIZE

        # Layout strategy:
        # Use a temporary layout grid to manage collision during generation
        layout_grid = [[0 for _ in range(CHUNK_SIZE)] for _ in range(CHUNK_SIZE)] # 0 = empty, 1 = occupied/road

        # Main road down the middle
        road_y = CHUNK_SIZE // 2
        for x in range(CHUNK_SIZE):
            layout_grid[road_y][x] = 1

        # Cross road
        road_x = CHUNK_SIZE // 2
        for y in range(CHUNK_SIZE):
            layout_grid[y][road_x] = 1

        # Place well at center
        global_well_x = chunk_global_start_x + road_x
        global_well_y = chunk_global_start_y + road_y
        chunk.village.interaction_points["well"] = [(global_well_x, global_well_y)]
        noticeboard_x = chunk_global_start_x + min(CHUNK_SIZE - 2, road_x + 1)
        noticeboard_y = chunk_global_start_y + road_y
        chunk.village.interaction_points["noticeboard"] = [(noticeboard_x, noticeboard_y)]

        # Helper to determine placement bias
        def _get_building_placement_bias(building_type: str, category: str, wealth_tier: str) -> str:
            if building_type in ["capital_hall", "tavern", "clinic"]:
                return "central"

            if category in ["civic", "civic_workplace", "commercial", "commercial_workplace", "medical"]:
                if wealth_tier == "poor":
                    return "mixed"
                return "central"

            if category in ["industrial", "industrial_workplace", "agricultural_workplace"]:
                return "edge"

            if category == "residential":
                if wealth_tier == "poor":
                    return "cluster_with_same"
                elif wealth_tier == "rich":
                    return "near_civic"
                return "mixed"

            return "mixed"

        # Helper to place building
        def try_place_building(b_type, category, default_width, default_height, x_hint=None, y_hint=None, max_workers=2, owner_wealth=None):
            # Extract wealth tier for bias scoring and variant selection
            from simulation.systems.architecture import BUILDING_ARCHETYPES
            wealth_tier = owner_wealth if owner_wealth else "middle"
            variant_id = None
            width = default_width
            height = default_height

            yard_size = 0
            if b_type in BUILDING_ARCHETYPES:
                archetype = BUILDING_ARCHETYPES[b_type]
                tags = archetype.tags
                if not owner_wealth:
                    if "poor" in tags: wealth_tier = "poor"
                    elif "rich" in tags: wealth_tier = "rich"

                # Query BlueprintVariant to override default dimensions
                variant = archetype.get_variant(wealth_tier)
                if variant:
                    variant_id = variant.id
                    width = variant.width
                    height = variant.height
                    yard_size = variant.fenced_yard_size

            total_w = width + yard_size * 2
            total_h = height + yard_size * 2

            # 1. Try exact hint first (existing exact behavior)
            if x_hint is not None and y_hint is not None:
                # Hint centers on the building, check layout taking yard into account
                start_x = max(1, x_hint - yard_size)
                start_y = max(1, y_hint - yard_size)

                if 0 <= start_x < CHUNK_SIZE - total_w and 0 <= start_y < CHUNK_SIZE - total_h:
                    overlap = False
                    for i in range(total_h):
                        for j in range(total_w):
                            if layout_grid[start_y + i][start_x + j] == 1:
                                overlap = True
                                break
                        if overlap: break
                    if not overlap:
                        # Mark territory and building footprint
                        for i in range(total_h):
                            for j in range(total_w):
                                layout_grid[start_y + i][start_x + j] = 1

                        # Actual building coordinates (inside the yard)
                        bx = start_x + yard_size
                        by = start_y + yard_size
                        building = Building(bx, by, width, height, building_type=b_type, category=category,
                                            global_chunk_x_start=chunk_global_start_x, global_chunk_y_start=chunk_global_start_y, variant_id=variant_id)
                        building.max_workers = max_workers
                        chunk.village.add_building(building)
                        self.atlas.register_building(building)
                        return building

            bias = _get_building_placement_bias(b_type, category, wealth_tier)

            # 3. Generate a deterministic candidate set of offsets
            # A spiral outward from the center (or hinted location) provides a good stable set
            # Default to the middle of the quadrant instead of the road if no hint,
            # so buildings have room to place instead of colliding with the road immediately.
            center_x = x_hint if x_hint is not None else (CHUNK_SIZE // 4)
            center_y = y_hint if y_hint is not None else (CHUNK_SIZE // 4)

            # Fixed offset sequence (approximate spiral: dx, dy)
            # Limit to deterministic checks, expanded to ensure we find room
            offsets = [
                (0, 0), (1, 0), (0, 1), (-1, 0), (0, -1),
                (2, 0), (0, 2), (-2, 0), (0, -2), (2, 2), (-2, -2), (2, -2), (-2, 2),
                (3, 0), (0, 3), (-3, 0), (0, -3), (3, 3), (-3, -3),
                (4, 0), (0, 4), (-4, 0), (0, -4),
                (5, 5), (-5, -5), (5, -5), (-5, 5),
                (8, 0), (0, 8), (-8, 0), (0, -8), (8, 8), (-8, -8), (8, -8), (-8, 8),
                (12, 0), (0, 12), (-12, 0), (0, -12), (12, 12), (-12, -12), (12, -12), (-12, 12),
                (16, 0), (0, 16), (-16, 0), (0, -16), (16, 16), (-16, -16), (16, -16), (-16, 16),
                (20, 0), (0, 20), (-20, 0), (0, -20), (20, 20), (-20, -20), (20, -20), (-20, 20),
                (24, 0), (0, 24), (-24, 0), (0, -24), (24, 24), (-24, -24), (24, -24), (-24, 24)
            ]

            valid_candidates = []
            for dx, dy in offsets:
                bx = center_x + dx
                by = center_y + dy

                # Check bounds
                if not (1 <= bx < CHUNK_SIZE - total_w - 1 and 1 <= by < CHUNK_SIZE - total_h - 1):
                    continue

                # Check collision
                overlap = False
                for i in range(total_h):
                    for j in range(total_w):
                        if layout_grid[by + i][bx + j] == 1:
                            overlap = True
                            break
                    if overlap: break

                if not overlap:
                    valid_candidates.append((bx, by))

            if not valid_candidates:
                # Fallback to random placement attempts if all deterministic offsets fail
                for attempt in range(20):
                    bx = random.randint(1, CHUNK_SIZE - total_w - 1)
                    by = random.randint(1, CHUNK_SIZE - total_h - 1)
                    # Check bounds
                    if not (1 <= bx < CHUNK_SIZE - total_w - 1 and 1 <= by < CHUNK_SIZE - total_h - 1):
                        continue
                    overlap = False
                    for i in range(total_h):
                        for j in range(total_w):
                            if layout_grid[by + i][bx + j] == 1:
                                overlap = True
                                break
                        if overlap: break
                    if not overlap:
                        valid_candidates.append((bx, by))
                        break

            if not valid_candidates:
                return None

            # 4. Score valid candidates based on bias
            best_score = float('-inf')
            best_candidate = valid_candidates[0]

            for bx, by in valid_candidates:
                score = 0.0

                # Distance to center
                dist_to_center = abs(bx - road_x) + abs(by - road_y)

                if bias == "central":
                    score -= dist_to_center * 0.5  # Slight preference for center
                elif bias == "edge":
                    score += dist_to_center * 0.5  # Slight preference for edges

                # Distance to same category or civic
                min_dist_same = float('inf')
                min_dist_civic = float('inf')

                for existing_b in chunk.village.buildings:
                    dist = abs(bx - existing_b.x) + abs(by - existing_b.y)
                    if existing_b.category == category:
                        min_dist_same = min(min_dist_same, dist)
                    if existing_b.category in ["civic", "civic_workplace"]:
                        min_dist_civic = min(min_dist_civic, dist)

                if bias == "cluster_with_same" and min_dist_same != float('inf'):
                    score -= min_dist_same * 0.2  # Very slight pull
                elif bias == "spread" and min_dist_same != float('inf'):
                    score += min_dist_same * 0.2  # Very slight push
                elif bias == "near_civic" and min_dist_civic != float('inf'):
                    score -= min_dist_civic * 0.2

                # Deterministic tie-breaker
                score += (bx * 0.01) + (by * 0.001)

                if score > best_score:
                    best_score = score
                    best_candidate = (bx, by)

            # 5. Place building
            final_bx, final_by = best_candidate
            for i in range(total_h):
                for j in range(total_w):
                    layout_grid[final_by + i][final_bx + j] = 1

            # Determine actual building coordinates inside the yard reservation
            actual_bx = final_bx + yard_size
            actual_by = final_by + yard_size

            building = Building(actual_bx, actual_by, width, height, building_type=b_type, category=category,
                                global_chunk_x_start=chunk_global_start_x, global_chunk_y_start=chunk_global_start_y, variant_id=variant_id)
            building.max_workers = max_workers
            chunk.village.add_building(building)
            self.atlas.register_building(building)
            return building

        # --- Generate Buildings ---

        # Capital Hall
        capital_hall = try_place_building("capital_hall", "civic", 9, 7, road_x - 11, road_y - 3, max_workers=3)
        if capital_hall and capital_hall.building_inventory.get("money", 0) <= 0:
            capital_hall.building_inventory["money"] = random.randint(600, 1200)

        # Clinic
        clinic = try_place_building("clinic", "civic_workplace", 7, 6, road_x - 10, road_y - 8, max_workers=2)
        if clinic:
            clinic.work_zone_tiles["medical_bed"] = [(clinic.global_origin_x + 1, clinic.global_origin_y + 1)]
            clinic.work_zone_tiles["alchemy_station"] = [(clinic.global_origin_x + 5, clinic.global_origin_y + 1)]

        # Jail
        jail = try_place_building("jail", "civic", 7, 5, road_x + 2, road_y - 2, max_workers=2)

        # Sheriff's Office
        if jail:
            try_place_building("sheriff_office", "civic_workplace", 7, 5, road_x + 2, jail.y + 7, max_workers=2)
        else:
            try_place_building("sheriff_office", "civic_workplace", 7, 5, road_x + 2, road_y + 5, max_workers=2)

        # General Store
        try_place_building("general_store", "commercial_workplace", 8, 6, road_x - 10, road_y + 5, max_workers=2)

        # Tavern
        try_place_building("tavern", "commercial_workplace", 9, 7, max_workers=3)

        # Lumber Mill
        lumber_mill = try_place_building("lumber_mill", "industrial_workplace", 7, 7, 1, CHUNK_SIZE - 8, max_workers=4)
        if lumber_mill:
            # Define zones (simplified logic)
            lumber_mill.work_zone_tiles["chopping_area"] = []
            # Add dummy global coords for internal zones based on offset
            lumber_mill.work_zone_tiles["log_pile_area"] = [(lumber_mill.global_origin_x + 1, lumber_mill.global_origin_y + lumber_mill.height - 3)]
            lumber_mill.work_zone_tiles["splitting_area"] = lumber_mill.work_zone_tiles["log_pile_area"]

        # Carpenter
        try_place_building("carpenter_shop", "industrial_workplace", 7, 6, max_workers=2)

        # Windmill
        windmill = try_place_building("mill", "industrial_workplace", 7, 7, CHUNK_SIZE - 8, CHUNK_SIZE - 8, max_workers=2)
        if windmill:
            windmill.work_zone_tiles["grinding_stone"] = [(windmill.global_origin_x + 3, windmill.global_origin_y + 3)]

        # Bakery
        bakery = try_place_building("bakery", "commercial_workplace", 7, 6, 1, 1, max_workers=2)
        if bakery:
            bakery.work_zone_tiles["oven"] = [(bakery.global_origin_x + 3, bakery.global_origin_y + 1)]

        # Mine
        mine = try_place_building("mine", "industrial_workplace", 8, 6, 1, 1, max_workers=5)
        if mine:
            mine.work_zone_tiles["mine_face"] = [(mine.global_origin_x + i, mine.global_origin_y + 1) for i in range(1, 7)]
            mine.work_zone_tiles["storage_area"] = [(mine.global_origin_x + 1, mine.global_origin_y + 4)]

        # Blacksmith
        blacksmith = try_place_building("blacksmith_shop", "industrial_workplace", 7, 6, road_x + 2, road_y + 2, max_workers=2)
        if blacksmith:
            blacksmith.work_zone_tiles["forge"] = [(blacksmith.global_origin_x + 1, blacksmith.global_origin_y + 1)]
            blacksmith.work_zone_tiles["anvil"] = [(blacksmith.global_origin_x + 5, blacksmith.global_origin_y + 4)]

        # Farm
        farm = try_place_building("farm", "agricultural_workplace", 8, 6, max_workers=3)
        if farm:
            # Logic for field patch
            field_width, field_height = 5, 5
            field_x = farm.x + 2
            field_y = farm.y + farm.height + 1
            # Ensure field fits in chunk
            if field_y + field_height < CHUNK_SIZE:
                farm.work_zone_tiles["field_patch"] = [
                    (chunk_global_start_x + field_x + rx, chunk_global_start_y + field_y + ry)
                    for ry in range(field_height) for rx in range(field_width)
                ]
                # Mark field in grid to prevent others
                for ry in range(field_height):
                    for rx in range(field_width):
                        if 0 <= field_y + ry < CHUNK_SIZE and 0 <= field_x + rx < CHUNK_SIZE:
                            layout_grid[field_y + ry][field_x + rx] = 1
            if "wheat_seeds" in ITEM_DEFINITIONS:
                 farm.building_inventory["wheat_seeds"] = random.randint(5, 15)

        # Fishing Hut
        # Needs water check. We don't have tiles yet.
        # We can use the pond logic: if we generate a pond, we know where it is.
        # Or we check macro elevation.
        # For simplicity, we'll assume water exists if we decide to place one,
        # but without tile map, precise placement next to water is hard.
        # Strategy: Postpone Fishing Hut placement to render time? No, need Building object for NPCs.
        # Strategy: Assume water at edges or specific spot.
        # Let's skip dynamic water placement dependency for now or assume a pond exists at fixed location.

        # Houses
        for _ in range(random.randint(3, 5)):
            try_place_building("house", "residential", random.randint(5, 9), random.randint(5, 9))

        # Library
        try_place_building("library", "civic_workplace", 8, 6, max_workers=2)

        self._populate_village_npcs(chunk, chunk.village, chunk_coord_x, chunk_coord_y)
        self._initialize_economy(chunk.village)

    def _render_village_tiles(self, chunk: Chunk):
        """Renders the buildings and roads of a village onto the chunk's tiles."""
        tiles = chunk.tiles

        # Render roads
        road_y = CHUNK_SIZE // 2
        road_x = CHUNK_SIZE // 2
        for x in range(CHUNK_SIZE):
            tiles[road_y][x] = Tile(TILE_DEFINITIONS["road"]["char"], TILE_DEFINITIONS["road"]["color"], TILE_DEFINITIONS["road"]["passable"], TILE_DEFINITIONS["road"]["name"])
        for y in range(CHUNK_SIZE):
            tiles[y][road_x] = Tile(TILE_DEFINITIONS["road"]["char"], TILE_DEFINITIONS["road"]["color"], TILE_DEFINITIONS["road"]["passable"], TILE_DEFINITIONS["road"]["name"])

        noticeboard_points = getattr(chunk.village, "interaction_points", {}).get("noticeboard", [])
        if noticeboard_points:
            board_x, board_y = noticeboard_points[0]
            local_board_x = board_x - (board_x // CHUNK_SIZE) * CHUNK_SIZE
            local_board_y = board_y - (board_y // CHUNK_SIZE) * CHUNK_SIZE
            board_def = DECORATION_ITEM_DEFINITIONS["noticeboard"]
            if 0 <= local_board_x < CHUNK_SIZE and 0 <= local_board_y < CHUNK_SIZE:
                tiles[local_board_y][local_board_x] = Tile(
                    board_def["char"],
                    board_def["color"],
                    board_def["passable"],
                    board_def["name"],
                    board_def.get("properties", {}),
                )

        # Render buildings
        from simulation.systems.architecture import BUILDING_ARCHETYPES, _get_wealth_tier
        for building in chunk.village.buildings:
            wall_type = "wood_wall"
            floor_type = "wood_floor"

            # Determine dynamic architecture from archetype tags if available
            archetype = BUILDING_ARCHETYPES.get(building.building_type)
            if archetype:
                wealth = _get_wealth_tier(archetype.tags)
                if wealth == "poor":
                    wall_type = "log_wall"
                    floor_type = "dirt_floor"
                elif wealth == "mid":
                    wall_type = "wood_wall"
                    floor_type = "wood_floor"
                elif wealth == "high":
                    wall_type = random.choice(["brick_wall", "stone_wall"])
                    floor_type = "stone_floor" if wall_type == "stone_wall" else "brick_floor"

                if archetype.category == "industrial":
                    wall_type = "plaster_wall"
                    floor_type = "dirt_floor"

            # Hardcoded overrides for specific civic structures
            if building.building_type in ["mine", "blacksmith_shop", "library", "sheriff_office", "jail", "capital_hall"]:
                wall_type = "stone_wall"
                floor_type = "stone_floor"
            if building.building_type == "jail":
                wall_type = "jail_bars"
            elif building.building_type == "sheriff_office":
                wall_type = "sheriff_office_wall"
            elif building.building_type == "capital_hall":
                wall_type = "capital_hall_wall"

            self._draw_building(tiles, building, wall_type, floor_type)
            if not building.interior_decorated:
                self.decorate_building_interior(building, chunk)

        # Render Well (if exists)
        if "well" in chunk.village.interaction_points:
            for wx, wy in chunk.village.interaction_points["well"]:
                # Convert global to local
                local_x = wx % CHUNK_SIZE
                local_y = wy % CHUNK_SIZE
                tiles[local_y][local_x] = Tile(TILE_DEFINITIONS["well"]["char"], TILE_DEFINITIONS["well"]["color"], TILE_DEFINITIONS["well"]["passable"], TILE_DEFINITIONS["well"]["name"])


    def _generate_ruin_layout(self, chunk: Chunk, global_chunk_x: int, global_chunk_y: int):
        """Generates a multi-room ruined structure within a chunk."""
        tiles = chunk.tiles if chunk.tiles else [[Tile(TILE_DEFINITIONS["plains"]["char"], TILE_DEFINITIONS["plains"]["color"], TILE_DEFINITIONS["plains"]["passable"], TILE_DEFINITIONS["plains"]["name"]) for _ in range(CHUNK_SIZE)] for _ in range(CHUNK_SIZE)]
        chunk.tiles = tiles

        wall_tile = TILE_DEFINITIONS["cracked_stone_wall"]
        floor_tile = TILE_DEFINITIONS["mossy_cobblestone"]
        rubble_decor = DECORATION_ITEM_DEFINITIONS["rubble"]

        # Simple dungeon generator (BSP-ish / Drunkard Walk combination)
        rooms = []
        num_rooms = random.randint(3, 5)

        for _ in range(num_rooms):
            rw = random.randint(5, 9)
            rh = random.randint(5, 9)
            rx = random.randint(2, CHUNK_SIZE - rw - 2)
            ry = random.randint(2, CHUNK_SIZE - rh - 2)

            # Check overlap
            overlap = False
            for (orx, ory, orw, orh) in rooms:
                if (rx < orx + orw and rx + rw > orx and ry < ory + orh and ry + rh > ory):
                    overlap = True
                    break

            if not overlap:
                rooms.append((rx, ry, rw, rh))

        if not rooms:
            return tiles

        # Draw rooms
        for (rx, ry, rw, rh) in rooms:
            for y in range(ry, ry + rh):
                for x in range(rx, rx + rw):
                    is_border = (x == rx or x == rx + rw - 1 or y == ry or y == ry + rh - 1)
                    if is_border:
                        tiles[y][x] = Tile(wall_tile["char"], wall_tile["color"], wall_tile["passable"], wall_tile["name"], wall_tile["properties"])
                    else:
                        tiles[y][x] = Tile(floor_tile["char"], floor_tile["color"], floor_tile["passable"], floor_tile["name"])

        # Draw corridors
        for i in range(len(rooms) - 1):
            r1 = rooms[i]
            r2 = rooms[i+1]
            c1 = (r1[0] + r1[2]//2, r1[1] + r1[3]//2)
            c2 = (r2[0] + r2[2]//2, r2[1] + r2[3]//2)

            # Draw L-shaped corridor
            if random.random() > 0.5:
                # Horizontal then Vertical
                for x in range(min(c1[0], c2[0]), max(c1[0], c2[0]) + 1):
                    tiles[c1[1]][x] = Tile(floor_tile["char"], floor_tile["color"], floor_tile["passable"], floor_tile["name"])
                for y in range(min(c1[1], c2[1]), max(c1[1], c2[1]) + 1):
                    tiles[y][c2[0]] = Tile(floor_tile["char"], floor_tile["color"], floor_tile["passable"], floor_tile["name"])
            else:
                # Vertical then Horizontal
                for y in range(min(c1[1], c2[1]), max(c1[1], c2[1]) + 1):
                    tiles[y][c1[0]] = Tile(floor_tile["char"], floor_tile["color"], floor_tile["passable"], floor_tile["name"])
                for x in range(min(c1[0], c2[0]), max(c1[0], c2[0]) + 1):
                    tiles[c2[1]][x] = Tile(floor_tile["char"], floor_tile["color"], floor_tile["passable"], floor_tile["name"])

        # Scatter rubble and add dungeon features
        for (rx, ry, rw, rh) in rooms:
            for _ in range(random.randint(2, 6)):
                rdx = random.randint(rx + 1, rx + rw - 2)
                rdy = random.randint(ry + 1, ry + rh - 2)
                tiles[rdy][rdx] = Tile(rubble_decor["char"], rubble_decor["color"], rubble_decor["passable"], rubble_decor["name"], rubble_decor["properties"])


            # Maybe spawn a hostile entity
            if random.random() < 0.7:
                ex, ey = random.randint(rx + 1, rx + rw - 2), random.randint(ry + 1, ry + rh - 2)
                global_x = global_chunk_x * CHUNK_SIZE + ex
                global_y = global_chunk_y * CHUNK_SIZE + ey

                # Cultists or feral beasts
                if random.random() < 0.5:
                    animal_type = random.choice(["wolf", "dire_wolf"])
                    animal_def = ANIMAL_DEFINITIONS.get(animal_type)
                    if animal_def:
                        new_entity = Animal(global_x, global_y, name=f"Dungeon {animal_def['name']}", animal_type=animal_type, animal_definition=animal_def)
                        new_entity.char = animal_def["char"] if isinstance(animal_def["char"], int) else ord(animal_def["char"])
                        new_entity.color = animal_def["color"]
                        new_entity.combat.max_hp = animal_def["max_hp"]
                        new_entity.combat.hp = new_entity.combat.max_hp
                        new_entity.combat.is_hostile_to_player = True
                        new_entity.behavior = "Aggressive"
                        self.npcs.append(new_entity)
                else:
                    new_entity = NPC(global_x, global_y, name="Cultist", dialogue=["The master awakens..."], personality="fanatic")
                    self._set_entity_profession(new_entity, "Cultist", reason="cultist_spawn")
                    new_entity.combat.is_hostile_to_player = True
                    new_entity.combat.max_hp = 30
                    new_entity.combat.hp = 30
                    new_entity.char = get_human_sprite(
                        gender=getattr(new_entity, "gender", None),
                        profession="Cultist",
                        age=getattr(new_entity, "age", None),
                    )
                    new_entity.color = (150, 0, 150) # Purple
                    self.npcs.append(new_entity)


        # Add a Treasure Chest in the last room
        last_room = rooms[-1]
        cx, cy = last_room[0] + last_room[2]//2, last_room[1] + last_room[3]//2
        chest_def = DECORATION_ITEM_DEFINITIONS["chest_wooden"].copy()

        # Add random loot to chest properties
        loot_items = Inventory()
        for _ in range(random.randint(2, 5)):
            loot_items.add_item(random.choice(["money", "healing_salve", "iron_ingot", "gemstone", "sword_iron"]), 1)

        properties = chest_def.get("properties", {}).copy()
        properties["is_dungeon_chest"] = True
        properties["loot"] = loot_items
        properties["is_locked"] = False # Unlocked for simple looting

        tiles[cy][cx] = Tile(chest_def["char"], (255, 215, 0), False, "Treasure Chest", properties)

        self._mark_entity_positions_dirty()
        return tiles


    def _draw_building(self, tiles, building, wall_tile_key, floor_tile_key="wood_floor"):
        for i in range(building.height):
            for j in range(building.width):
                is_border = i == 0 or i == building.height - 1 or j == 0 or j == building.width - 1
                is_window = (i == 1 and j == 0) or (i == 1 and j == building.width - 1) or \
                            (i == building.height - 2 and j == 0) or (i == building.height - 2 and j == building.width - 1)

                target_y = building.y + i
                target_x = building.x + j
                global_x = building.global_origin_x + j
                global_y = building.global_origin_y + i

                if is_border:
                    new_tile = Tile(TILE_DEFINITIONS[wall_tile_key]["char"], TILE_DEFINITIONS[wall_tile_key]["color"], TILE_DEFINITIONS[wall_tile_key]["passable"], TILE_DEFINITIONS[wall_tile_key]["name"])
                    tiles[target_y][target_x] = new_tile
                    if 0 <= global_x < WORLD_WIDTH and 0 <= global_y < WORLD_HEIGHT:
                         self.transparency_map[global_y, global_x] = not new_tile.blocks_fov

                elif is_window and building.building_type in ["house", "large_house", "common_house", "city_hall", "tavern", "clinic"]:
                    new_tile = Tile(TILE_DEFINITIONS["window"]["char"], TILE_DEFINITIONS["window"]["color"], TILE_DEFINITIONS["window"]["passable"], TILE_DEFINITIONS["window"]["name"])
                    tiles[target_y][target_x] = new_tile
                    if 0 <= global_x < WORLD_WIDTH and 0 <= global_y < WORLD_HEIGHT:
                         self.transparency_map[global_y, global_x] = not new_tile.blocks_fov

                else:
                    new_tile = Tile(TILE_DEFINITIONS[floor_tile_key]["char"], TILE_DEFINITIONS[floor_tile_key]["color"], TILE_DEFINITIONS[floor_tile_key]["passable"], TILE_DEFINITIONS[floor_tile_key]["name"])
                    tiles[target_y][target_x] = new_tile
                    # Floors usually don't block FOV, but update just in case
                    if 0 <= global_x < WORLD_WIDTH and 0 <= global_y < WORLD_HEIGHT:
                         self.transparency_map[global_y, global_x] = True

        self._ensure_building_entrance_integrity(building)

    def ensure_player_surroundings_generated(self):
        """Ensures chunks around the player are generated."""
        chunk_x = self.player.x // CHUNK_SIZE
        chunk_y = self.player.y // CHUNK_SIZE

        for y in range(chunk_y - 1, chunk_y + 2):
            for x in range(chunk_x - 1, chunk_x + 2):
                if 0 <= x < self.chunk_width and 0 <= y < self.chunk_height:
                    chunk = self.chunks[y][x]
                    if not chunk.is_terrain_generated:
                        self._generate_chunk_detail(chunk, x, y)
                    self._populate_chunk_wildlife(chunk, x, y)

    def get_tile_at(self, x, y):
        if not (0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT):
            return None
        chunk_x, chunk_y = x // CHUNK_SIZE, y // CHUNK_SIZE
        local_x, local_y = x % CHUNK_SIZE, y % CHUNK_SIZE

        if not (0 <= chunk_x < self.chunk_width and 0 <= chunk_y < self.chunk_height):
            return None

        chunk = self.chunks[chunk_y][chunk_x]
        if not chunk.is_terrain_generated:
            self._generate_chunk_detail(chunk, chunk_x, chunk_y)
        return chunk.tiles[local_y][local_x]

    def get_building_at(self, x, y):
        chunk_x, chunk_y = x // CHUNK_SIZE, y // CHUNK_SIZE
        local_x, local_y = x % CHUNK_SIZE, y % CHUNK_SIZE
        chunk = self.chunks[chunk_y][chunk_x]
        if chunk.poi_type == "village" and chunk.village:
            for building in chunk.village.buildings:
                if building.x <= local_x < building.x + building.width and \
                   building.y <= local_y < building.y + building.height:
                    return building
        return None

    def handle_player_movement(self, dx, dy) -> int:
        if self.player.state.is_jailed:
            self.add_message_to_chat_log("You are in jail and cannot move freely.")
            return 1 # Default action cost

        if self.player.state.is_sitting:
            self.player_attempt_stand_up()
            return 1 # Standing up costs a turn

        if self.player.state.is_riding:
            riding_animal = next((npc for npc in self.npcs if npc.id == self.player.state.riding_animal_id), None)
            if riding_animal:
                new_x, new_y = riding_animal.x + dx, riding_animal.y + dy
                destination_tile = self.get_tile_at(new_x, new_y)
                if destination_tile and destination_tile.passable:
                    self._update_entity_position(riding_animal, new_x, new_y)
                    self._update_entity_position(self.player, new_x, new_y)
                    self._update_player_fov()
                    return int(destination_tile.properties.get("movement_cost", 1))
                else:
                    return 0 # No movement if blocked
            else:
                # Fallback in case the animal ID is somehow invalid
                self.player.state.is_riding = False
                self.player.state.riding_animal_id = None
                return 0

        new_x, new_y = self.player.x + dx, self.player.y + dy
        destination_tile = self.get_tile_at(new_x, new_y)

        if dx != 0 or dy != 0:
            self.player.state.last_dx, self.player.state.last_dy = dx, dy # Always update facing direction

        if destination_tile and destination_tile.passable:
            self._update_entity_position(self.player, new_x, new_y)

            movement_cost = int(destination_tile.properties.get("movement_cost", 1))

            # Check if player entered a building
            building = self.get_building_at(new_x, new_y)
            if building:
                # Player learns about the building upon entering
                building_name = building.building_type.replace('_', ' ')
                if building.id not in self.player.knowledge.known_locations:
                    self.player.knowledge.known_locations[building.id] = (building.global_center_x, building.global_center_y)
                    self.add_message_to_chat_log(f"You discover the {building_name}.")

                if not building.interior_decorated:
                    # Get the chunk the building is in to pass to decoration method
                    current_chunk_x = new_x // CHUNK_SIZE
                    current_chunk_y = new_y // CHUNK_SIZE
                    if 0 <= current_chunk_x < self.chunk_width and 0 <= current_chunk_y < self.chunk_height:
                        chunk_of_building = self.chunks[current_chunk_y][current_chunk_x]
                        self.decorate_building_interior(building, chunk_of_building)
                    else:
                        # This should ideally not happen if get_building_at found a building
                        self.add_message_to_chat_log("Error: Could not find chunk for building decoration.")

            self._update_player_fov() # Player moved, so update FOV

            # Clear sound events after player move (and subsequent NPC updates for that turn)
            # This means sounds last for one full game tick cycle.
            self.sound_events.clear()


            # Check for pass-through yields (e.g., from tall grass)
            if hasattr(destination_tile, 'properties') and "yields_on_pass_through" in destination_tile.properties:
                yield_data = destination_tile.properties["yields_on_pass_through"]
                if random.random() < yield_data.get("chance", 0):
                    item_key = yield_data["item_key"]
                    quantity_range = yield_data["quantity"]
                    quantity = random.randint(quantity_range[0], quantity_range[1]) if isinstance(quantity_range, list) else quantity_range

                    self.player.add_item(item_key, quantity)
                    item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
                    self.add_message_to_chat_log(f"You found {quantity} {item_name} in the tall grass.")

                    # Replace the tall grass with plains
                    chunk_x, chunk_y = new_x // CHUNK_SIZE, new_y // CHUNK_SIZE
                    local_x, local_y = new_x % CHUNK_SIZE, new_y % CHUNK_SIZE
                    plains_def = TILE_DEFINITIONS["plains"]
                    self.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = Tile(
                        plains_def["char"], plains_def["color"], plains_def["passable"], plains_def["name"], plains_def.get("properties", {})
                    )


            return movement_cost
        return 0 # No movement if tile is not passable

    def emit_sound(self, origin_x: int, origin_y: int, sound_type: str, volume: int, source_entity_id: int | None = None):
        """Emits a sound event that NPCs might react to."""
        self.sound_events.append({
            "x": origin_x, "y": origin_y,
            "type": sound_type, "volume": volume,
            "source_id": source_entity_id # Optional: ID of player/NPC that made the sound
        })
        # self.add_message_to_chat_log(f"Debug: Sound '{sound_type}' emitted at ({origin_x},{origin_y}) vol {volume}")

    def broadcast_news(self, speaker_npc: NPC, radius: int, event_to_share: Event):
        """
        Broadcasts an event to all entities within a radius.
        Used for Town Criers, warning shouts, etc.
        """
        if not event_to_share:
            return

        shout_message = f"{speaker_npc.name} shouts: 'Hear ye! {event_to_share.description}'"

        # Log if player is in range
        dist_to_player = math.sqrt((speaker_npc.x - self.player.x)**2 + (speaker_npc.y - self.player.y)**2)
        if dist_to_player <= radius:
            self.add_message_to_chat_log(shout_message)

        # Spread to nearby NPCs
        count_listeners = 0
        for npc in self.all_npcs:
            if npc.id == speaker_npc.id or npc.physical.is_dead:
                continue

            dist = math.sqrt((speaker_npc.x - npc.x)**2 + (speaker_npc.y - npc.y)**2)
            if dist <= radius:
                if self.knowledge_system.learn_event(npc, event_to_share):
                    count_listeners += 1

        # self.add_message_to_chat_log(f"Debug: {speaker_npc.name} broadcasted news to {count_listeners} people.")

    def update(self):
        """Main update function for the world, called once per game tick."""
        run_world_tick(self)
        self._update_autonomy_audit()

    def _update_autonomy_audit(self):
        """Audit the NPCs for autonomy tracking."""
        counters = {
            "visible": 0,
            "active": 0,
            "with_path": 0,
            "moved": 0,
            "idle": 0,
            "at_work_home": 0,
            "in_timed_activity": 0,
            "blocked_path_failed": 0
        }

        # Visibility check uses FOV
        fov_map = getattr(self, "player_fov_map", None)

        for npc in self.all_npcs:
            if npc.physical.is_dead or getattr(npc, "is_sleeping", False):
                continue

            counters["active"] += 1

            if fov_map is not None and 0 <= npc.y < WORLD_HEIGHT and 0 <= npc.x < WORLD_WIDTH and fov_map[npc.y, npc.x]:
                counters["visible"] += 1

            # State tracking
            if not hasattr(npc, "debug_autonomy"):
                npc.debug_autonomy = {}

            # Detect movement
            last_x = npc.debug_autonomy.get("last_x")
            last_y = npc.debug_autonomy.get("last_y")
            moved = False
            if last_x is not None and last_y is not None:
                if last_x != npc.x or last_y != npc.y:
                    moved = True
                    counters["moved"] += 1
                    npc.debug_autonomy["last_move_tick"] = self.game_time
            npc.debug_autonomy["last_x"] = npc.x
            npc.debug_autonomy["last_y"] = npc.y
            npc.debug_autonomy["moved_this_tick"] = moved

            # Path tracking
            has_path = bool(npc.schedule.current_path)
            if has_path:
                counters["with_path"] += 1

            dest = npc.schedule.current_destination_coords
            path_failed = dest is not None and not has_path
            path_blocked = has_path and not moved and npc.schedule.path_blocked_turns > 0
            if path_failed or path_blocked:
                counters["blocked_path_failed"] += 1
                npc.debug_autonomy["path_status"] = "blocked" if path_blocked else "failed"
            elif has_path:
                npc.debug_autonomy["path_status"] = "moving" if moved else "pathing"
            else:
                npc.debug_autonomy["path_status"] = "none"

            # Task tracking
            current_task = npc.schedule.current_task
            last_task = npc.debug_autonomy.get("last_task")
            if current_task != last_task:
                npc.debug_autonomy["previous_task"] = last_task
                npc.debug_autonomy["task_start_tick"] = self.game_time
            npc.debug_autonomy["last_task"] = current_task

            if current_task == "idle" or current_task == TaskType.IDLE:
                counters["idle"] += 1

            if current_task in {"working", "sleeping", "visiting_friend", "socializing", "gathering_social"}:
                counters["in_timed_activity"] += 1

            is_at_work = npc.schedule.work_building_id and getattr(self.buildings_by_id.get(npc.schedule.work_building_id), "contains_global_coords", lambda x, y: False)(npc.x, npc.y)
            is_at_home = npc.schedule.home_building_id and getattr(self.buildings_by_id.get(npc.schedule.home_building_id), "contains_global_coords", lambda x, y: False)(npc.x, npc.y)
            if is_at_work or is_at_home:
                counters["at_work_home"] += 1

        self.autonomy_counters = counters

    def _cleanup_dead_entities(self):
        """Periodically removes dead NPCs to maintain performance."""
        if self.game_time % 100 == 0:
            dead_entities = [npc for npc in self.all_npcs if npc.physical.is_dead]
            if dead_entities:
                for npc in dead_entities:
                    if isinstance(npc, Animal) and hasattr(self, "ecology"):
                        self.ecology.note_animal_death(npc)
                self._mark_entity_positions_dirty()
            self.npcs = [npc for npc in self.npcs if not npc.physical.is_dead]
            self.village_npcs = [npc for npc in self.village_npcs if not npc.physical.is_dead]

            # Note: Do not remove the player, even if dead.

    def _tick_world_item_inventories(self):
        """Advance spoilage/aging for non-player object-backed world inventories."""
        for inventory in self.items_on_map.values():
            if hasattr(inventory, "process_tick"):
                inventory.process_tick()

        for building in self.buildings_by_id.values():
            inventory = getattr(building, "building_inventory", None)
            if hasattr(inventory, "process_tick"):
                inventory.process_tick()

        for row in self.chunks:
            for chunk in row:
                if not chunk or not chunk.tiles:
                    continue
                for tile_row in chunk.tiles:
                    for tile in tile_row:
                        if not tile or not getattr(tile, "properties", None):
                            continue
                        loot_inventory = tile.properties.get("loot")
                        if hasattr(loot_inventory, "process_tick"):
                            loot_inventory.process_tick()

    def _update_spatial_partitioning(self):
        """Updates the entity chunk map for quick spatial queries."""
        self._ensure_entity_positions_current()

    def get_entities_in_radius(self, x: int, y: int, radius: int) -> list:
        """Returns a list of entities within a bounding box radius, using spatial partitioning."""
        entities = []
        min_cx = max(0, (x - radius) // CHUNK_SIZE)
        max_cx = min(self.chunk_width - 1, (x + radius) // CHUNK_SIZE)
        min_cy = max(0, (y - radius) // CHUNK_SIZE)
        max_cy = min(self.chunk_height - 1, (y + radius) // CHUNK_SIZE)

        for cy in range(min_cy, max_cy + 1):
            for cx in range(min_cx, max_cx + 1):
                chunk_entity_ids = self.entities_by_chunk.get((cx, cy), set())
                for entity_id in chunk_entity_ids:
                    entity = self.get_entity_by_id(entity_id)
                    if entity:
                        if abs(entity.x - x) <= radius and abs(entity.y - y) <= radius:
                            entities.append(entity)
        return entities

    def _trigger_event_driven_conversation(self):
        """Checks if any NPC should start a conversation with the player about a witnessed event."""
        if self.game_state != "PLAYING":
            return

        for npc in self.all_npcs:
            if npc.physical.is_dead or npc.combat.is_hostile_to_player or self.chat_ui_active:
                continue

            # Check if player is visible and close
            if npc.id in self.npc_fov_maps:
                # Need to bound check since map is [WORLD_HEIGHT, WORLD_WIDTH] which is [y, x]
                px, py = self.player.x, self.player.y
                if 0 <= px < WORLD_WIDTH and 0 <= py < WORLD_HEIGHT and self.npc_fov_maps[npc.id][py, px]:
                    if abs(npc.x - self.player.x) + abs(npc.y - self.player.y) <= 3:
                        # Find an event the NPC knows about but hasn't discussed with the player yet
                        undiscussed_events = [e for e_id, e in npc.knowledge.known_events.items() if e_id not in npc.knowledge.discussed_event_ids]
                        if undiscussed_events:
                            event_to_discuss = random.choice(undiscussed_events)
                            task_key = ("event_dialogue", npc.id, event_to_discuss.id)
                            starter_dialogue = self._poll_background_llm_task(task_key)
                            if starter_dialogue is BACKGROUND_LLM_PENDING:
                                continue
                            if starter_dialogue is not None:
                                npc.knowledge.discussed_event_ids.add(event_to_discuss.id)
                                if starter_dialogue:
                                    self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} approaches you.")
                                    self.start_npc_dialogue(npc)
                                    self.chat_ui_history.append((self.get_entity_display_name(npc), starter_dialogue))
                                    self.request_open_dialogue(npc)
                                    break
                                continue

                            # Gather context for the prompt
                            subject = self.get_entity_by_id(event_to_discuss.subject_id)
                            target = self.get_entity_by_id(event_to_discuss.target_id) if event_to_discuss.target_id else None

                            subject_name = getattr(subject, 'name', 'Someone')
                            target_name = getattr(target, 'name', 'someone')

                            prompt = LLM_PROMPTS["npc_event_conversation_starter"].format(
                                npc_name=npc.name,
                                npc_personality=npc.social.personality,
                                relationship_score=npc.social.relationships.get(self.player.id, 50),
                                event_type=event_to_discuss.type,
                                event_summary=event_to_discuss.description.format(subject=subject_name, target=target_name),
                                subject_name=subject_name,
                                target_name=target_name,
                                relationship_with_subject=npc.social.relationships.get(event_to_discuss.subject_id, 50),
                                relationship_with_target=npc.social.relationships.get(event_to_discuss.target_id, 50)
                            )
                            self._submit_background_llm_task(task_key, prompt)

    def _handle_reputation_based_reactions(self):
        """Makes NPCs react to famous or infamous characters they see."""
        if self.game_time % 10 != 0:  # Check every 10 ticks for performance
            return

        for npc in self.all_npcs:
            # Skip NPCs who are dead, already reacting, in combat, or creatures
            if npc.physical.is_dead or npc.schedule.current_task in ["fleeing_from_player", "greeting_player"] or npc.combat.is_hostile_to_player or npc.economic.profession == "Creature":
                continue

            if npc.id in self.npc_fov_maps:
                fov_map = self.npc_fov_maps[npc.id]
                # Check if the player is visible to the NPC
                if 0 <= self.player.x < WORLD_WIDTH and 0 <= self.player.y < WORLD_HEIGHT and fov_map[self.player.y, self.player.x]:
                    player_reputation = npc.knowledge.get_reputation_towards(self.player)

                    # Reaction to notorious crimes remembered about the player.
                    if player_reputation <= -50:
                        if npc.economic.profession in ["Sheriff", "Guard"]:
                            npc.combat.is_hostile_to_player = True
                            npc.schedule.current_task = "attacking_player"
                            npc.schedule.current_path = []
                            continue

                        if npc.schedule.current_task != "fleeing_from_player":
                            npc.schedule.current_task = "fleeing_from_player"
                            self.add_message_to_chat_log(
                                f"{self.get_entity_display_name(npc)} recognizes you as dangerous and flees in terror!"
                            )
                            npc.schedule.current_path = [] # Force path recalculation

                    # Reaction to favorable remembered deeds.
                    elif player_reputation >= 20:
                        if npc.social.personality in ["friendly", "gregarious", "neutral", "commoner"] and npc.schedule.current_task != "greeting_player":
                            npc.schedule.current_task = "greeting_player"
                            self.add_message_to_chat_log(
                                f"{self.get_entity_display_name(npc)} recognizes you and approaches to greet {self.player.social.title or 'a famous hero'}."
                            )
                            npc.schedule.current_path = [] # Force path recalculation

    def teach_entity_history_record(
        self,
        entity,
        record,
        source_type: str = "witnessed",
        confidence: float = 1.0,
        tick: int | None = None,
    ) -> bool:
        """Teach an entity a structured history record through the knowledge system."""
        if entity is None or record is None:
            return False
        knowledge_system = getattr(self, "knowledge_system", None)
        if knowledge_system is None:
            return False
        if tick is None:
            tick = getattr(self, "game_time", 0)
        return knowledge_system.learn_history_record(
            entity,
            record,
            source_type=source_type,
            confidence=confidence,
            tick=tick,
        )

    def share_history_record_between_entities(
        self, source, target, record_id: str
    ) -> bool:
        """Share one known history record from one entity to another."""
        if source is None or target is None or not record_id:
            return False
        record = self.history.get_event(record_id)
        if record is None:
            return False
        knowledge_system = getattr(self, "knowledge_system", None)
        if knowledge_system is None:
            return False
        return knowledge_system.share_event(source, target, record)

    def get_entity_by_id(self, entity_id: int):
        """Finds an entity (player or NPC) by its ID."""
        if not isinstance(entity_id, int):
            return None
        if entity_id == self.player.id:
            return self.player
        for npc in self.all_npcs:
            if npc.id == entity_id:
                return npc
        return None

    def is_identity_obscured(self, entity) -> bool:
        return bool(entity and hasattr(entity, "is_identity_concealed") and entity.is_identity_concealed())

    def resolve_visible_subject_id(self, observer, subject_entity) -> int | str | None:
        if subject_entity is None:
            return None
        if observer is not None and getattr(observer, "id", None) == getattr(subject_entity, "id", None):
            return getattr(subject_entity, "id", None)
        if self.is_identity_obscured(subject_entity):
            return "Unknown"
        return getattr(subject_entity, "id", None)

    def get_visible_entity_name(self, observer, entity, *, unknown_name: str = "Unknown figure") -> str:
        if entity is None:
            return unknown_name
        if observer is not None and getattr(observer, "id", None) == getattr(entity, "id", None):
            return getattr(entity, "name", unknown_name)
        if self.is_identity_obscured(entity):
            return unknown_name
        return getattr(entity, "name", unknown_name)

    def _is_placeholder_family_name(self, name: str) -> bool:
        return bool(name and PLACEHOLDER_FAMILY_NAME_RE.match(name))

    def get_relationship_to_player(self, entity) -> str | None:
        """Return the entity's relationship to the player from the player's perspective."""
        if not entity or entity == self.player:
            return None
        if hasattr(entity, "get_relationship_to"):
            return entity.get_relationship_to(self.player)
        return None

    def get_relationship_label(self, entity) -> str:
        if not entity:
            return ""
        if hasattr(entity, "get_relationship_label"):
            return entity.get_relationship_label(self.player)
        relation = self.get_relationship_to_player(entity)
        return relation.replace("_", " ").title() if relation else ""

    def get_entity_title_label(self, entity) -> str:
        if not entity:
            return ""
        if hasattr(entity, "get_title_label"):
            return entity.get_title_label()
        profession = str(getattr(getattr(entity, "economic", None), "profession", "") or "").strip()
        if not profession or profession in {"Unemployed", "Creature"}:
            return ""
        return profession

    def _set_entity_profession(self, entity, profession: str, reason: str = "") -> str:
        return set_entity_profession(entity, profession, reason=reason, game_time=self.game_time)

    def _get_coworker_roles(self, work_building, exclude_entity=None) -> list[str]:
        if not work_building:
            return []
        roles = []
        for other_npc in self.all_npcs:
            if exclude_entity is not None and other_npc.id == getattr(exclude_entity, "id", None):
                continue
            if getattr(getattr(other_npc, "schedule", None), "work_building_id", None) == work_building.id:
                roles.append(normalize_profession(getattr(getattr(other_npc, "economic", None), "profession", "")))
        return roles

    def _resolve_profession_for_work_building(self, work_building, exclude_entity=None) -> str:
        if not work_building:
            return "Unemployed"
        coworker_roles = self._get_coworker_roles(work_building, exclude_entity=exclude_entity)
        return resolve_profession_for_building(work_building.building_type, coworker_roles)

    def get_entity_display_name(self, entity, include_relationship: bool = False) -> str:
        """Return a player-facing label for an entity."""
        if not entity:
            return "Unknown"
        if hasattr(entity, "get_display_name"):
            return entity.get_display_name(viewer=self.player, include_relationship=include_relationship)
        if entity == self.player:
            return "You"
        return str(getattr(entity, "name", "Unknown")).replace("_", " ").strip() or "Unknown"

    def get_entity_relationship_summary(self, entity) -> str:
        """Return a short player-facing summary of how the player knows an NPC."""
        if not entity or entity == self.player:
            return ""

        parts = []
        relation_label = self.get_relationship_label(entity)
        if relation_label:
            parts.append(f"your {relation_label.lower()}")

        profession = getattr(getattr(entity, "economic", None), "profession", "")
        if profession and profession not in {"", "Unemployed"}:
            parts.append(profession.lower())

        attitude = getattr(entity, "attitude_to_player", "")
        if attitude:
            parts.append(attitude)

        return ", ".join(parts[:3])

    def _describe_relationship_for_prompt(self, entity) -> str:
        relation = self.get_relationship_to_player(entity)
        if not relation:
            return "No known family relation to the player."
        prompt_map = {
            "mother": "You are the player's mother.",
            "father": "You are the player's father.",
            "brother": "You are the player's brother.",
            "sister": "You are the player's sister.",
            "sibling": "You are the player's sibling.",
            "partner": "You are the player's partner.",
            "parent": "You are the player's parent.",
            "child": "You are the player's child.",
        }
        return prompt_map.get(relation, f"You are the player's {relation.replace('_', ' ')}.")

    def _llm_output_is_empty(self, response_text: str | None) -> bool:
        if response_text is None:
            return True
        normalized = str(response_text).strip()
        return normalized in {"", "{}", "[]", "null", '""'}

    def _contains_placeholder_player_reference(self, response_text: str | None) -> bool:
        if response_text is None:
            return False
        text = str(response_text)
        placeholder_patterns = [
            r"\[\s*player\s*name\s*\]",
            r"\{\s*player_name\s*\}",
            r"\bplayer_name\b",
            r"\bplayer name\b",
        ]
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in placeholder_patterns)

    def _extract_json_object_text(self, response_text: str | None) -> str | None:
        """Best-effort extraction of a JSON object from model output."""
        if response_text is None:
            return None

        text = str(response_text).strip()
        if not text:
            return None

        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
            if text.lower().startswith("json"):
                text = text[4:].lstrip()

        if text.startswith("{") and text.endswith("}"):
            return text

        start = text.find("{")
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start:index + 1]
        return None

    def _parse_llm_json_object(self, response_text: str | None):
        json_text = self._extract_json_object_text(response_text)
        if not json_text:
            return None
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            return None

    def _warn_missing_llm_once(self) -> None:
        if self._llm_warning_issued:
            return
        self._llm_warning_issued = True
        self.add_message_to_chat_log("LLM dialogue is offline. Add a GOOGLE_API_KEY or switch to Ollama for AI responses.")

    def _fallback_dialogue_greeting(self, npc_target: NPC) -> str:
        relation = self.get_relationship_label(npc_target)
        attitude = npc_target.attitude_to_player
        if npc_target.knowledge.help_needed:
            return f"Please, I need help with {npc_target.knowledge.help_needed}."
        if relation == "Mother":
            return "There you are. Are you keeping yourself fed?"
        if relation == "Father":
            return "Good to see you. How are you holding up?"
        if relation in {"Brother", "Sister", "Sibling"}:
            return "Hey. What do you need?"
        if attitude in {"warm", "friendly"}:
            return npc_target.dialogue[0] if npc_target.dialogue else "Good to see you."
        if attitude in {"hostile", "unfriendly"}:
            return "What do you want?"
        return npc_target.dialogue[0] if npc_target.dialogue else "Hello."

    def _fallback_dialogue_continue(self, npc_target: NPC, player_input_text: str) -> tuple[str, str]:
        text = player_input_text.lower().strip()
        relation = self.get_relationship_label(npc_target)

        if any(word in text for word in ["bye", "goodbye", "see you", "farewell"]):
            return ("Take care.", "end_conversation")
        if "how are you" in text or "how're you" in text:
            if relation == "Mother":
                return ("I'm managing. You should be asking how you are doing, too.", "continue_conversation")
            if relation == "Father":
                return ("Still standing. Work never stops around here.", "continue_conversation")
            if relation in {"Brother", "Sister", "Sibling"}:
                return ("I've been alright. Same village, same troubles.", "continue_conversation")
            return ("I've been alright.", "continue_conversation")
        if any(word in text for word in ["who are you", "your name", "name?"]):
            return (f"I'm {self.get_entity_display_name(npc_target)}.", "continue_conversation")
        if any(word in text for word in ["follow me", "come with me"]):
            from simulation.systems.conversation_foundation import evaluate_service_request
            if evaluate_service_request(self, self.player, npc_target, "accompany") == "accept":
                return ("Alright. Lead the way.", "start_accompany")
            return ("I have my own things to do.", "end_conversation")

        if any(word in text for word in ["guard me", "protect me", "escort me"]):
            from simulation.systems.conversation_foundation import evaluate_service_request
            if evaluate_service_request(self, self.player, npc_target, "guard") == "accept":
                return ("I've got your back.", "start_guard")
            return ("I'm no bodyguard.", "end_conversation")

        if any(word in text for word in ["stop following", "wait here", "stay here"]):
            return ("I'll wait here then.", "stop_following")
        if "trade" in text and npc_target.economic.profession in {"Merchant", "Miller", "Scribe", "Traveling Merchant"}:
            return ("Let's see what we can trade.", "start_trade")
        contextual_lines = get_contextual_dialogue_lines(npc_target, self.player, self, limit=1)
        if contextual_lines and contextual_lines[0].topic_type != "small_talk":
            return (contextual_lines[0].text, "continue_conversation")

        profile = evaluate_conversation_foundation(self, npc_target, self.player, max_distance=9999)
        topic_line, topic_goal, _topic_choice = self._resolve_conversation_topic(npc_target, self.player, profile)
        if topic_line:
            return (topic_line, topic_goal)
        if relation:
            return ("I'm listening.", "continue_conversation")
        return ("I hear you.", "continue_conversation")

    def _can_player_overhear(self, speaker) -> bool:
        distance_to_player = abs(speaker.x - self.player.x) + abs(speaker.y - self.player.y)
        return (
            distance_to_player <= self.player.physical.hearing_radius
            and distance_to_player <= getattr(speaker, "speech_volume", 0)
        )

    def _is_npc_llm_relevant_to_player(self, *entities) -> bool:
        for entity in entities:
            if entity and self._can_player_overhear(entity):
                return True
        return False

    def _is_ambient_speech_local_to_player(self, speaker, audible_radius: int | None = None) -> bool:
        if not speaker or not getattr(self, "player", None):
            return False
        distance_to_player = abs(int(getattr(speaker, "x", 0)) - int(getattr(self.player, "x", 0))) + abs(int(getattr(speaker, "y", 0)) - int(getattr(self.player, "y", 0)))
        hearing_radius = int(getattr(getattr(self.player, "physical", None), "hearing_radius", DEFAULT_HEARING_RADIUS) or DEFAULT_HEARING_RADIUS)
        if audible_radius is None:
            audible_radius = int(getattr(speaker, "speech_volume", DEFAULT_SPEECH_VOLUME) or DEFAULT_SPEECH_VOLUME)
        return distance_to_player <= min(max(1, audible_radius), max(1, hearing_radius))

    def _ambient_speech_radius_for_scene(self, speaker, scene=None) -> int:
        base_radius = int(getattr(speaker, "speech_volume", DEFAULT_SPEECH_VOLUME) or DEFAULT_SPEECH_VOLUME)
        scene_type = str(getattr(scene, "scene_type", "") or "")
        scene_tone = str(getattr(scene, "tone", "") or "")
        if scene_type == "tavern":
            return max(base_radius, 10)
        if scene_type == "celebration" or scene_tone == "celebratory":
            return max(base_radius, 12)
        if scene_type == "funeral" or scene_tone in {"grieving", "somber"}:
            return max(4, min(base_radius, 6))
        if scene_type in {"warning", "accusation"} or scene_tone in {"tense", "fearful"}:
            return max(6, min(max(base_radius, 8), 10))
        return max(1, base_radius)

    def _publish_ambient_dialogue_line(self, speaker, listener, dialogue_line, *, scene=None, activity=None):
        if dialogue_line is None:
            return None
        audible_radius = World._ambient_speech_radius_for_scene(self, speaker, scene)
        if not World._is_ambient_speech_local_to_player(self, speaker, audible_radius):
            return None
        line = add_dialogue_line_as_ambient_speech(
            self,
            speaker,
            listener,
            dialogue_line,
            scene=scene,
        )
        if line is not None and hasattr(self, "visual_effects"):
            self.visual_effects.append(FloatingTextEffect(speaker.x, speaker.y, "“…”", color=(190, 190, 220), duration=1.2, speed=0.35))
        return line

    def _publish_ambient_text(self, speaker, listener, text: str, *, scene=None, source_type="small_talk", source_record_id=None):
        audible_radius = World._ambient_speech_radius_for_scene(self, speaker, scene)
        if not World._is_ambient_speech_local_to_player(self, speaker, audible_radius):
            return None
        line = add_ambient_speech(
            self,
            speaker=speaker,
            listener=listener,
            text=text,
            source_type=source_type,
            source_record_id=source_record_id,
            audible_radius=audible_radius,
            scene=scene,
        )
        if line is not None and hasattr(self, "visual_effects"):
            self.visual_effects.append(FloatingTextEffect(speaker.x, speaker.y, "“…”", color=(190, 190, 220), duration=1.2, speed=0.35))
        return line

    def _coerce_dialogue_goal_by_profile(self, profile, goal: str) -> str:
        """Constrain freeform goals to simulation-approved outcomes for this turn."""
        if goal in profile.outcome_weights and profile.outcome_weights.get(goal, 0.0) > 0:
            return goal
        return choose_structured_conversation_outcome(profile, self)

    def _resolve_conversation_topic(self, speaker, listener, profile, group_listeners=None):
        """Select and apply a structured conversation topic payload."""
        topic_choice = self.select_conversation_topic(speaker, listener, profile, group_listeners=group_listeners)
        line, goal = apply_conversation_topic(self, speaker, listener, topic_choice, group_listeners=group_listeners)
        return line, (goal or topic_choice.goal or "continue_conversation"), topic_choice

    def _fallback_npc_social_line(self, speaker, listener, group_listeners=None, max_distance=2) -> tuple[str, str]:
        profile = self.evaluate_conversation_foundation(speaker, listener, max_distance=max_distance)
        if not profile.can_start:
            if profile.stance in {"fearful", "hostile"}:
                return ("I'd rather keep my distance.", "end_conversation")
            return ("Now isn't a good time.", "end_conversation")

        line, topic_goal, _topic_choice = self._resolve_conversation_topic(speaker, listener, profile, group_listeners=group_listeners)
        if topic_goal not in {"continue_conversation", "end_conversation", "go_to_work", "go_home", "socialize"}:
            topic_goal = "continue_conversation"
        if topic_goal != "continue_conversation":
            return (line, topic_goal)

        goal = choose_structured_conversation_outcome(profile, self)
        if goal == "socialize":
            if profile.stance == "respectful":
                return (f"It's good to see you, {listener.name}.", "socialize")
            return ("Let's talk for a bit.", "socialize")
        if goal == "go_to_work" and speaker.schedule.work_building_id:
            return ("I should get back to work soon.", "go_to_work")
        if goal == "go_home" and speaker.schedule.home_building_id:
            return ("I ought to head home before long.", "go_home")
        if goal == "end_conversation":
            if profile.tone in {"guarded", "nervous", "tense"}:
                return ("I don't have much to say right now.", "end_conversation")
            return ("We'll talk another time.", "end_conversation")
        if profile.tone == "warm":
            return (f"It's good to see you, {listener.name}.", "continue_conversation")
        if profile.tone in {"guarded", "nervous"}:
            return (line or "Let's keep this brief.", "continue_conversation")
        if profile.tone == "tense":
            return (line or "Careful now.", "continue_conversation")
        return (line or "Strange day, isn't it?", "continue_conversation")

    def _handle_npc_social_goal(self, speaker, listener, goal: str) -> None:
        if goal == "go_to_work" and speaker.schedule.work_building_id:
            dest = self._get_building_global_center_coords(speaker.schedule.work_building_id)
            if dest:
                speaker.schedule.current_task = TaskType.GOING_TO_WORK
                speaker.schedule.current_destination_coords = dest
                speaker.schedule.current_path = []
        elif goal == "go_home" and speaker.schedule.home_building_id:
            dest = self._get_building_global_center_coords(speaker.schedule.home_building_id)
            if dest:
                speaker.schedule.current_task = TaskType.GOING_HOME
                speaker.schedule.current_destination_coords = dest
                speaker.schedule.current_path = []
        elif goal == "visit_listener_home" and listener.schedule.home_building_id:
            friend_home = self.buildings_by_id.get(listener.schedule.home_building_id)
            if friend_home:
                speaker.schedule.current_task = "visiting_friend"
                speaker.task_target_entity_id = listener.id
                speaker.schedule.current_destination_coords = (friend_home.global_center_x, friend_home.global_center_y)
                speaker.schedule.current_path = []
        elif goal == "socialize":
            dest_x, dest_y = self._find_best_adjacent_tile(listener.x, listener.y, speaker)
            if dest_x is not None:
                speaker.schedule.current_task = "socializing"
                speaker.task_target_entity_id = listener.id
                speaker.schedule.current_destination_coords = (dest_x, dest_y)
                speaker.schedule.current_path = []
        elif goal == "end_conversation":
            speaker.conversation_partner_id = None
            listener.conversation_partner_id = None
        elif goal == "start_accompany":
            speaker.social.follow_target_id = listener.id
            speaker.social.follow_role = "accompany"
        elif goal == "start_guard":
            speaker.social.follow_target_id = listener.id
            speaker.social.follow_role = "guard"
        elif goal == "stop_following":
            speaker.social.follow_target_id = None
            speaker.social.follow_role = None

    def _update_entity_titles(self):
        """Periodically checks and updates titles for all entities based on fame/infamy."""
        if self.game_time % 100 != 0:  # Check every 100 ticks
            return

        entities_to_check = itertools.chain([self.player], self.all_npcs)
        for entity in entities_to_check:
            task_key = ("title_generation", entity.id)
            response_str = self._poll_background_llm_task(task_key)
            if response_str is BACKGROUND_LLM_PENDING:
                continue
            if response_str is not None:
                if response_str:
                    try:
                        response_json = json.loads(response_str)
                        new_title = response_json.get("title")
                        if new_title:
                            entity.social.title = new_title
                            if isinstance(entity, Player):
                                self.add_message_to_chat_log(f"You are now known as {new_title}.")
                            else:
                                self.add_message_to_chat_log(f"{self.get_entity_display_name(entity)} is now known as {new_title}.")
                    except json.JSONDecodeError:
                        pass
                continue

            if not entity.social.title and (entity.social.fame >= 50 or entity.social.infamy >= 50):
                # Only use public knowledge events
                recent_events = [e for e in self.global_events if e.subject_id == entity.id and e.type in ["quest_complete", "crime_witnessed", "entity_death"] and e.public_knowledge]
                actions_summary = "\n".join([e.description for e in recent_events[-5:]]) or "No specific known deeds."

                prompt = LLM_PROMPTS["player_title_generation"].format(
                    player_fame=entity.social.fame,
                    player_infamy=entity.social.infamy,
                    player_actions_summary=actions_summary
                )
                self._submit_background_llm_task(task_key, prompt)

    def _update_npc_reputations(self):
        """
        Periodically updates reputation of NPCs and players based on recent global events
        and natural decay.
        """
        # Run periodically (e.g., once a day)
        if self.game_time % DAY_LENGTH_TICKS != 0:
            return

        # 1. Decay fame/infamy for all entities
        all_entities = itertools.chain([self.player], self.all_npcs)
        for entity in all_entities:
            # Fame decay: -1 per day if > 0
            if entity.social.fame > 0:
                entity.social.fame -= 1
            # Infamy decay: -1 per day if > 0
            if entity.social.infamy > 0:
                entity.social.infamy -= 1

        # 2. Check for recent events that might affect reputation
        # (Note: Most immediate reputation effects are handled by event creation hooks
        # like handle_npc_death and _handle_witness_reaction. This is a cleanup/catch-all pass)
        recent_events = [e for e in self.global_events if self.game_time - e.timestamp <= DAY_LENGTH_TICKS]
        for event in recent_events:
            # Example: If a "heroic_act" event type existed, we could process it here.
            # Currently "entity_death" (monsters/murder) handles reputation directly.
            pass

    def _update_npc_ages(self):
        """Increments the age of all NPCs once per game day."""
        if self.game_time > 0 and self.game_time % DAY_LENGTH_TICKS == 0:
            for npc in self.all_npcs:
                npc.age += 1

    def _update_inventory_spoilage(self):
        """Checks for food spoilage in all inventories once per day."""
        # Only run once per day
        if self.game_time == 0 or self.game_time % DAY_LENGTH_TICKS != 0:
            return

        # Helper to process a specific inventory dict
        def process_inventory(inventory, owner_name="Container"):
            items_to_remove = []
            items_to_add = []

            for item_key, quantity in inventory.items():
                if item_key == "money": continue

                item_def = ITEM_DEFINITIONS.get(item_key)
                if not item_def: continue

                spoilage_chance = item_def.get("properties", {}).get("spoilage_chance", 0.0)

                if spoilage_chance > 0:
                    spoiled_count = 0
                    # For large stacks, use binomial distribution for performance approximation
                    # For small stacks, iterate
                    if quantity > 10:
                        # Expected value approx
                        spoiled_count = np.random.binomial(quantity, spoilage_chance)
                    else:
                        for _ in range(quantity):
                            if random.random() < spoilage_chance:
                                spoiled_count += 1

                    if spoiled_count > 0:
                        items_to_remove.append((item_key, spoiled_count))
                        rots_into = item_def.get("properties", {}).get("rots_into", "rotten_food")
                        items_to_add.append((rots_into, spoiled_count))

                        # Optional: Log significant spoilage for player
                        if owner_name == "Player" and spoiled_count > 0:
                            self.add_message_to_chat_log(f"{spoiled_count} {item_def['name']} rotted away.")

            # Apply changes
            for key, count in items_to_remove:
                inventory[key] -= count
                if inventory[key] <= 0:
                    del inventory[key]

            for key, count in items_to_add:
                inventory[key] = inventory.get(key, 0) + count

        # 1. Player Inventory
        process_inventory(self.player.economic.inventory, owner_name="Player")

        # 2. NPC Inventories (dicts)
        for npc in self.all_npcs:
            if not npc.physical.is_dead:
                process_inventory(npc.economic.npc_inventory, owner_name="NPC")

        # 3. Building Inventories (dicts)
        for building in self.buildings_by_id.values():
            process_inventory(building.building_inventory, owner_name="Building")

    def _find_boss_for_npc(self, npc: NPC, building: Building) -> NPC | None:
        """Finds a supervisor or senior coworker for an NPC at a building."""
        possible_bosses = []
        for other_npc in self.village_npcs:
            if other_npc.id == npc.id or other_npc.physical.is_dead:
                continue
            if other_npc.schedule.work_building_id == building.id:
                prof = other_npc.economic.profession
                # Explicit leaders
                if prof in ["Sheriff", "Lumber Mill Foreman", "Tavern Keeper", "Town Official", "Merchant"]:
                    return other_npc
                possible_bosses.append(other_npc)

        # If no explicit leader, pick a random coworker to blame/thank
        if possible_bosses:
            return random.choice(possible_bosses)
        return None

    def _evaluate_job_suitability(self, npc: NPC, job_building: Building) -> int:
        """Calculates a suitability score for an NPC and a potential job building."""
        score = random.randint(0, 20) # Base randomness

        # Personality fit
        b_type = job_building.building_type
        personality = npc.social.personality.lower()

        if "brave" in personality or "aggressive" in personality:
            if b_type in ["sheriff_office", "jail"]: score += 20
            elif b_type in ["mine", "lumber_mill"]: score += 10
        elif "smart" in personality or "studious" in personality:
            if b_type in ["library", "capital_hall"]: score += 20
            elif b_type in ["general_store"]: score += 10
        elif "greedy" in personality or "merchant" in personality:
            if b_type in ["general_store", "tavern"]: score += 20
        elif "nature" in personality or "outdoors" in personality:
            if b_type in ["farm", "fishing_hut", "lumber_mill"]: score += 20

        # Physical Stats fit (implied by combat stats)
        if hasattr(npc, 'combat') and npc.combat.max_hp > 25: # Strong/Tough
            if b_type in ["mine", "lumber_mill", "blacksmith_shop", "sheriff_office"]: score += 15

        return score

    def _clear_npc_job(self, npc: NPC, *, reason: str, message: str, employment_action: str = "quit", add_owner_grudge: bool = False) -> None:
        old_profession = npc.economic.profession
        work_building = self.buildings_by_id.get(npc.schedule.work_building_id) if npc.schedule.work_building_id else None

        if add_owner_grudge and work_building and getattr(work_building, "owner_id", None) is not None:
            npc.add_grudge(work_building.owner_id, f"{reason} ({old_profession}).")

        self._set_entity_profession(npc, "Unemployed", reason=reason)
        npc.economic.daily_wage = 0
        npc.economic.job_satisfaction = 30 if reason in {"fired", "unpaid_wages"} else 50
        npc.economic.days_unemployed = 0
        npc.economic.work_performance = 50
        npc.schedule.work_building_id = None

        self.add_message_to_chat_log(message)

        event_location = (work_building.global_center_x, work_building.global_center_y) if work_building else (npc.x, npc.y)
        self.record_employment_event(
            npc=npc,
            profession=old_profession,
            employment_action=employment_action,
            description=f"{{subject}} {message[0].lower() + message[1:]}" if message else f"{{subject}} left their job as {old_profession}.",
            location=event_location,
            building_id=work_building.id if work_building else None,
        )

    def _pay_daily_company_wages(self) -> None:
        current_day = self.game_time // max(1, DAY_LENGTH_TICKS)
        for npc in list(self.village_npcs):
            if npc.physical.is_dead or normalize_profession(npc.economic.profession) == "Unemployed":
                continue
            if npc.schedule.last_paid_day >= current_day:
                continue

            work_building = self.buildings_by_id.get(npc.schedule.work_building_id)
            if work_building is None:
                npc.schedule.last_paid_day = current_day
                continue

            # Check performance to decide if wages are paid
            if getattr(npc.economic, "work_performance", 50) <= 20:
                npc.schedule.last_paid_day = current_day
                continue

            village = self._get_village_for_npc(npc)
            wage = self._get_employment_daily_wage(npc.economic.profession, override_wage=getattr(npc.economic, "daily_wage", 0) or None, village=village)

            # Performance bonus
            if getattr(npc.economic, "work_performance", 50) > 80:
                wage += int(wage * 0.2) # 20% bonus

            if getattr(work_building, "owner_id", None) is not None:
                building_balance = self._get_trade_money_balance(work_building)
                if building_balance < wage:
                    owner_name = "your business" if getattr(work_building, "owner_id", None) == self.player.id else "the business"
                    unpaid_wage_memory = self.create_memory_event(
                        event_type="unpaid_wages",
                        subject_id=getattr(work_building, "owner_id", None),
                        target_id=npc.id,
                        importance_score=70,
                        headline=f"{npc.name} quit after missing wages at the {work_building.building_type.replace('_', ' ')}.",
                        location=(work_building.global_center_x, work_building.global_center_y),
                        metadata={
                            "building_id": work_building.id,
                            "profession": npc.economic.profession,
                            "wage": wage,
                        },
                    )
                    self.record_memory_event(npc, unpaid_wage_memory)
                    self._clear_npc_job(
                        npc,
                        reason="unpaid_wages",
                        message=f"{npc.name} quit their job as {npc.economic.profession} because {owner_name} could not pay {wage} coins in wages.",
                        employment_action="quit",
                        add_owner_grudge=True,
                    )
                    npc.schedule.last_paid_day = current_day
                    continue

                self._set_trade_money_balance(work_building, building_balance - wage)
                self._set_trade_money_balance(npc, self._get_trade_money_balance(npc) + wage)
                npc.schedule.last_paid_day = current_day
                continue

            npc.economic.money += wage
            npc.schedule.last_paid_day = current_day

    def _update_npc_careers(self):
        """
        Simulates a job market where NPCs can quit unhappy jobs and find new ones.
        Run once per day.
        """
        # Logic runs if it's exactly the start of a day (after day 0)
        # Or if force-called in tests where game_time is set manually to a multiple.
#         # print(f"DEBUG: _update_npc_careers called at game_time {self.game_time}. DAY_LENGTH_TICKS={DAY_LENGTH_TICKS}")
        if self.game_time == 0 or self.game_time % DAY_LENGTH_TICKS != 0:
             # print("DEBUG: Skipping career update (wrong time).")
             return

        self._pay_daily_company_wages()

        # --- Job Satisfaction Update & Quitting ---
        # Iterate over a copy to allow modification of lists if needed (though we modify npc attributes)
        for npc in list(self.village_npcs):
#             # print(f"DEBUG: Processing {npc.name}. Profession: {npc.economic.profession}, Satisfaction: {npc.economic.job_satisfaction}")
            if npc.physical.is_dead:
                continue

            if npc.economic.profession.lower() != "unemployed":
                if hasattr(npc, "career"):
                    npc.career.advance_day()
                # Factors affecting satisfaction
                satisfaction_change = 0

                # 1. Hunger/Thirst penalty
                if npc.physical.hunger > 50: satisfaction_change -= 5
                if npc.physical.thirst > 50: satisfaction_change -= 5

                # 2. Wealth impact
                if npc.economic.money < 10:
                    satisfaction_change -= 2 # Stress of poverty
                elif npc.economic.money > 200:
                    satisfaction_change += 1 # Financial security

                # 3. Random fluctuation (good day/bad day)
                satisfaction_change += random.randint(-5, 5)

                npc.economic.job_satisfaction = max(0, min(100, npc.economic.job_satisfaction + satisfaction_change))

#                 # print(f"DEBUG: {npc.name} new satisfaction: {npc.economic.job_satisfaction} (change: {satisfaction_change})")

                # Firing Logic (Performance check)
                if npc.economic.work_performance < 20 and random.random() < 0.1: # 10% chance to be fired if performance is very low
                    old_profession = npc.economic.profession

                    # Social Fallout: Find someone to blame (Boss)
                    work_building = self.buildings_by_id.get(npc.schedule.work_building_id)
                    if work_building:
                        boss = self._find_boss_for_npc(npc, work_building)
                        if boss:
                            npc.add_grudge(boss.id, f"Fired me from my job as {old_profession}.")
                            # self.add_message_to_chat_log(f"{npc.name} blames {boss.name} for their termination.")

                    self._clear_npc_job(
                        npc,
                        reason="fired",
                        message=f"{npc.name} was fired from their job as a {old_profession} for poor performance.",
                        employment_action="fired",
                    )

                # Quitting Logic
                if npc.economic.profession.lower() != "unemployed" and npc.economic.job_satisfaction < 10:
                    # NPC Quits
                    old_profession = npc.economic.profession
                    self._clear_npc_job(
                        npc,
                        reason="quit_job",
                        message=f"{npc.name} has quit their job as a {old_profession} due to low satisfaction.",
                        employment_action="quit",
                    )

            else: # Is Unemployed
                npc.economic.days_unemployed += 1
                # Satisfaction drops while unemployed
                npc.economic.job_satisfaction = max(0, npc.economic.job_satisfaction - 2)

        # --- Hiring Logic ---
        # Filter for unemployed NPCs who have been unemployed for at least 1 day (prevents immediate rehiring after quitting)
        unemployed_npcs = [n for n in self.village_npcs if n.economic.profession.lower() == "unemployed" and not n.physical.is_dead and n.economic.days_unemployed > 0]
        random.shuffle(unemployed_npcs) # Randomize who gets first pick

        for npc in unemployed_npcs:
            village = self._get_village_for_npc(npc)
            if not village: continue
            self._sync_village_employment_tasks(village)
            if self.handle_npc_job_seeking(npc):
                continue

            # --- Emigration Logic ---
            # If unemployed for too long, leave the village
            if npc.economic.days_unemployed > 7 and npc.economic.money < 50: # Unemployed for a week and poor
                npc.schedule.current_task = "leaving_village"
                # Set target to edge of map
                edge_x, edge_y = self._find_nearest_map_edge(npc)

                npc.schedule.current_path = self.calculate_path(npc.x, npc.y, edge_x, edge_y)
                npc.schedule.current_destination_coords = (edge_x, edge_y)

                self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} has decided to leave the village in search of better opportunities.")
                self.record_migration_event(
                    npc=npc,
                    migration_kind="emigrated",
                    description=f"{{subject}} left the village.",
                    location=(npc.x, npc.y),
                )

        # --- Job Hopping (for Employed NPCs) ---
        # Check if employed NPCs want to switch jobs
        for npc in list(self.village_npcs):
            if npc.physical.is_dead or npc.economic.profession.lower() == "unemployed": continue

            # Only consider switching if somewhat dissatisfied
            if npc.economic.job_satisfaction < 60:
                village = self._get_village_for_npc(npc)
                if not village: continue

                current_work_building = self.buildings_by_id.get(npc.schedule.work_building_id)
                if not current_work_building: continue

                current_job_score = self._evaluate_job_suitability(npc, current_work_building)

                # Look for better vacancies
                potential_jobs = []
                for building in village.buildings:
                    if "workplace" in building.category and building.id != npc.schedule.work_building_id:
                        if self._is_player_owned_workplace(building):
                            continue
                        current_workers_count = sum(1 for villager in self.village_npcs if villager.schedule.work_building_id == building.id and not villager.physical.is_dead)
                        if current_workers_count < building.max_workers:
                            potential_jobs.append(building)

                if potential_jobs:
                    best_new_job = None
                    best_new_score = -1

                    for job_building in potential_jobs:
                        score = self._evaluate_job_suitability(npc, job_building)
                        if score > best_new_score:
                            best_new_score = score
                            best_new_job = job_building

                    # Switch if significantly better (20% better + switching friction)
                    if best_new_job and best_new_score > current_job_score * 1.2 + 5:
                        old_profession = npc.economic.profession
                        self._assign_job(npc, best_new_job)
                        self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} left their job as {old_profession} to become a {npc.economic.profession}.")



        # --- Business Ownership & Hiring Logic ---
        processed_villages = set()
        for npc in list(self.village_npcs):
            if npc.physical.is_dead:
                continue
            village = self._get_village_for_npc(npc)
            if not village:
                continue

            # Check if this NPC owns any buildings in the village
            for building in village.buildings:
                if getattr(building, "owner_id", None) == npc.id and "workplace" in building.category:
                    # They are an owner, they should act as the boss
                    if npc.schedule.work_building_id != building.id:
                        # Owner should also work there if they don't already
                        self._assign_job(npc, building, profession=self._resolve_profession_for_work_building(building, exclude_entity=None), reason="business_owner")

                    current_workers_count = self._count_active_workers_for_building(building)
                    if current_workers_count < building.max_workers:
                        # Check if a job is already posted
                        open_tasks = self.town_board.get_open_employment_tasks(building.id)
                        if not open_tasks:
                            role = self._resolve_profession_for_work_building(building, exclude_entity=npc)
                            base_wage = self._get_employment_daily_wage(role, village=village)
                            # Maybe pay a bit more if they are really short
                            if current_workers_count == 0:
                                base_wage = int(base_wage * 1.2)

                            self.town_board.post_employment(
                                target_building_id=building.id,
                                profession_role=role,
                                daily_wage=max(1, base_wage),
                                poster_entity_id=npc.id
                            )

        # --- Immigration Logic ---
        # Check overall vacancies in villages and spawn new migrants
        # We'll do this per village found in chunks
        processed_villages = set()
        for y_chunk in range(self.chunk_height):
            for x_chunk in range(self.chunk_width):
                chunk = self.chunks[y_chunk][x_chunk]
                if chunk.village and chunk.village not in processed_villages:
                    village = chunk.village
                    processed_villages.add(village)

                    total_vacancies = 0
                    for building in village.buildings:
                        if "workplace" in building.category:
                            current_workers = sum(1 for v in self.village_npcs if v.schedule.work_building_id == building.id and not v.physical.is_dead)
                            total_vacancies += max(0, building.max_workers - current_workers)

                    # If there are significant vacancies, chance to spawn an immigrant
                    if total_vacancies >= 2 and random.random() < 0.2: # 20% chance if 2+ jobs open
                        # Spawn a new NPC
                        # We use _populate_village_npcs logic but for just one person
                        # Place them at town square or random edge
                        spawn_x = x_chunk * CHUNK_SIZE + CHUNK_SIZE // 2
                        spawn_y = y_chunk * CHUNK_SIZE + CHUNK_SIZE // 2
                        if "town_square_center" in village.interaction_points:
                            spawn_x, spawn_y = village.interaction_points["town_square_center"]

                        # Create a dummy chunk object to reuse population logic or just manually create
                        # Reusing _populate_village_npcs is hard because it does a batch.
                        # Let's create manually using similar logic.
                        self._spawn_migrant(village, spawn_x, spawn_y)

    def _assign_job(
        self,
        npc: NPC,
        work_building: Building,
        *,
        profession: str | None = None,
        daily_wage: int | None = None,
        reason: str = "hired",
    ) -> bool:
        """Assigns a job to an NPC at a specific building."""
        if npc is None or work_building is None:
            return False
        npc.schedule.work_building_id = work_building.id

        new_profession = normalize_profession(profession) if profession else self._resolve_profession_for_work_building(work_building, exclude_entity=npc)
        village = self._get_village_for_npc(npc)
        npc.economic.daily_wage = self._get_employment_daily_wage(new_profession, override_wage=daily_wage, village=village)
        npc.schedule.last_paid_day = self.game_time // max(1, DAY_LENGTH_TICKS)
        self._set_entity_profession(npc, new_profession, reason=reason)
        npc.economic.job_satisfaction = 70
        npc.economic.days_unemployed = 0
        npc.economic.work_performance = 50 # Reset performance

        self.add_message_to_chat_log(f"{self.get_entity_display_name(npc)} has been hired as a {new_profession}.")

        # Social Boost: Gratitude to Boss
        boss = self._find_boss_for_npc(npc, work_building)
        if boss:
            npc.social.relationships[boss.id] = min(100, npc.social.relationships.get(boss.id, 50) + 20)
            # Boss likes the new hire too
            boss.social.relationships[npc.id] = min(100, boss.social.relationships.get(npc.id, 50) + 10)

        self.record_employment_event(
            npc=npc,
            profession=new_profession,
            employment_action="hired",
            description=f"{{subject}} started a new job as a {new_profession}.",
            location=(work_building.global_center_x, work_building.global_center_y),
            building_id=work_building.id,
        )
        return True


    def _spawn_raiding_party(self, source_village, target_village):
        """Spawns a raiding party from source_village to attack target_village."""
        if not source_village or not target_village: return

        # Pick a spawn location near the edge of the source village chunk
        # For simplicity, spawn at town square of source
        spawn_x, spawn_y = 0, 0
        if "town_square_center" in source_village.interaction_points:
            spawn_x, spawn_y = source_village.interaction_points["town_square_center"][0]
        else:
            return

        target_coords = None
        if "town_square_center" in target_village.interaction_points:
            target_coords = target_village.interaction_points["town_square_center"][0]
        else:
            return

        party_size = random.randint(2, 4)
        for i in range(party_size):
            # Offset spawns slightly
            dx, dy = random.randint(-2, 2), random.randint(-2, 2)
            raider = NPC(
                x=max(0, min(WORLD_WIDTH - 1, spawn_x + dx)),
                y=max(0, min(WORLD_HEIGHT - 1, spawn_y + dy)),
                name=f"Raider of Village {source_village.id[:4]}",
                dialogue=["Die, scum!", "For our village!", "Give me your gold!"],
                personality="aggressive",
                player_id=self.player.id
            )
            self._set_entity_profession(raider, "Raider", reason="raider_spawn")
            raider.combat.max_hp = 35
            raider.combat.hp = 35
            raider.char = get_human_sprite(
                gender=getattr(raider, "gender", None),
                profession="Raider",
                age=getattr(raider, "age", None),
            )
            raider.color = (255, 100, 100) # Reddish
            raider.speed = 1.2

            # Custom properties for raiders
            raider.faction_id = source_village.id
            raider.enemy_faction_id = target_village.id

            # Start them moving towards the target
            path = self.calculate_path(raider.x, raider.y, target_coords[0], target_coords[1])
            if path:
                raider.schedule.current_path = path
                raider.schedule.current_destination_coords = target_coords
                raider.schedule.current_task = "raiding_village"
            else:
                raider.schedule.current_task = "wandering_hostile"

            self.npcs.append(raider) # Spawn as world npcs, not village_npcs
            self._mark_entity_positions_dirty()

        self.add_message_to_chat_log(f"A raiding party was spotted leaving for a rival settlement!")

    def _spawn_migrant(self, village: Village, x: int, y: int):

        """Spawns a new migrant NPC into the village."""
        prompt = LLM_PROMPTS["npc_personality"].format(
            player_criminal_points=0,
            player_hero_points=0,
            name_hint="a newcomer",
            personality_hint="hopeful, looking for work",
            family_ties_hint="none",
            attitude_to_player_hint="neutral"
        )
        llm_response = self._call_llm_for_background(prompt)
        try:
            npc_data = json.loads(llm_response)
            npc = NPC(
                x=x, y=y,
                name=npc_data.get("name", "Migrant"),
                dialogue=npc_data.get("dialogue", ["Hello, I'm looking for work."]),
                personality=npc_data.get("personality", "commoner"),
                player_id=None
            )
            self._set_entity_profession(npc, "Unemployed", reason="migrant_spawn")
            npc.economic.money = random.randint(10, 50) # Modest starting funds

            # Try to find a home
            vacant_homes = [b for b in village.buildings if b.category == "residential" and not b.residents]
            if vacant_homes:
                home = random.choice(vacant_homes)
                npc.schedule.home_building_id = home.id
                home.residents.append(npc)
                npc.knowledge.known_locations["my home"] = (home.global_center_x, home.global_center_y)

            self.village_npcs.append(npc)
            self._mark_entity_positions_dirty()
            self.add_message_to_chat_log(f"A migrant named {self.get_entity_display_name(npc)} has arrived in the village looking for work.")

        except json.JSONDecodeError:
            pass

    def _claim_rect_tiles(self, x: int, y: int, width: int, height: int, *, padding: int = 0) -> set[tuple[int, int]]:
        return {
            (tx, ty)
            for ty in range(max(0, y - padding), min(WORLD_HEIGHT, y + height + padding))
            for tx in range(max(0, x - padding), min(WORLD_WIDTH, x + width + padding))
        }

    def _claim_radius_tiles(self, center_x: int, center_y: int, radius: int) -> set[tuple[int, int]]:
        tiles: set[tuple[int, int]] = set()
        radius_sq = radius * radius
        for ty in range(max(0, center_y - radius), min(WORLD_HEIGHT, center_y + radius + 1)):
            for tx in range(max(0, center_x - radius), min(WORLD_WIDTH, center_x + radius + 1)):
                if (tx - center_x) ** 2 + (ty - center_y) ** 2 <= radius_sq:
                    tiles.add((tx, ty))
        return tiles

    def _get_village_anchor_coords(self, village: Village) -> tuple[int, int] | None:
        if "town_square_center" in getattr(village, "interaction_points", {}):
            return village.interaction_points["town_square_center"][0]
        if getattr(village, "buildings", None):
            return village.buildings[0].global_center_x, village.buildings[0].global_center_y
        return None

    def _is_claimable_terrain(self, x: int, y: int) -> bool:
        if not (0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT):
            return False
        tile = self.get_tile_at(x, y)
        # Territory can reserve woodland/brush for future clearing; only water/off-map is invalid.
        return bool(tile and getattr(tile, "name", "") not in {"Water", "Deep Water"})

    def create_land_claim(
        self,
        claim_type: str,
        claimed_tiles: set[tuple[int, int]] | None = None,
        *,
        reserved_tiles: set[tuple[int, int]] | None = None,
        owner_type: str = "settlement",
        owner_id: str | int | None = None,
        settlement_id: str | None = None,
        priority: int = 1,
        expansion_pressure: int = 0,
        metadata: dict | None = None,
    ) -> LandClaim | None:
        claimed_tiles = {tile for tile in (claimed_tiles or set()) if self._is_claimable_terrain(*tile)}
        reserved_tiles = {tile for tile in (reserved_tiles or set()) if self._is_claimable_terrain(*tile)}
        if not claimed_tiles and not reserved_tiles:
            return None
        claim = LandClaim(
            claim_type=claim_type,
            claimed_tiles=claimed_tiles,
            reserved_tiles=reserved_tiles,
            owner_type=owner_type,
            owner_id=owner_id,
            settlement_id=settlement_id,
            priority=priority,
            expansion_pressure=expansion_pressure,
            metadata=dict(metadata or {}),
        )
        self.land_claims_by_id[claim.id] = claim
        village = self._get_village_by_id(settlement_id)
        if village is not None and claim.id not in village.territory_claim_ids:
            village.territory_claim_ids.append(claim.id)
        return claim

    def _get_village_by_id(self, settlement_id: str | None) -> Village | None:
        if settlement_id is None:
            return None
        for village in getattr(self, "villages", []):
            if getattr(village, "id", None) == settlement_id:
                return village
        atlas = getattr(self, "atlas", None)
        if atlas and hasattr(atlas, "get_village"):
            return atlas.get_village(settlement_id)
        for row in getattr(self, "chunks", []):
            for chunk in row:
                village = getattr(chunk, "village", None)
                if getattr(village, "id", None) == settlement_id:
                    return village
        return None

    def get_land_claims_at(self, x: int, y: int, *, include_reserved: bool = True) -> list[LandClaim]:
        claims = [
            claim for claim in self.land_claims_by_id.values()
            if claim.active and claim.contains(x, y, include_reserved=include_reserved)
        ]
        claims.sort(key=lambda claim: claim.priority, reverse=True)
        return claims

    def get_land_claim_summary(self, x: int, y: int) -> str | None:
        claims = self.get_land_claims_at(x, y)
        if not claims:
            return None
        primary = claims[0]
        if (x, y) in primary.reserved_tiles and (x, y) not in primary.claimed_tiles:
            return f"{primary.label()} (reserved)"
        return primary.label()

    def get_claim_debug_color(self, claim: LandClaim | None) -> tuple[int, int, int] | None:
        if claim is None:
            return None
        colors = {
            "settlement_core": (120, 160, 255),
            "rural_expansion": (80, 130, 210),
            "reserved_expansion": (160, 160, 90),
            "farm": (80, 180, 80),
            "ranch": (170, 140, 80),
            "hunting": (100, 140, 80),
            "logging": (70, 120, 70),
            "business": (180, 140, 210),
            "construction_reservation": (210, 180, 90),
        }
        return colors.get(claim.claim_type, (180, 180, 180))

    def _claim_conflicts_for_type(self, existing: LandClaim, new_type: str, settlement_id: str | None) -> bool:
        if not existing.active:
            return False
        broad_settlement = {"settlement_core", "rural_expansion"}
        if existing.settlement_id is not None and settlement_id is not None and existing.settlement_id != settlement_id:
            return True
        if new_type in broad_settlement:
            return existing.settlement_id not in {None, settlement_id}
        if existing.claim_type in broad_settlement and existing.settlement_id == settlement_id:
            return False
        if existing.claim_type == "reserved_expansion" and existing.settlement_id == settlement_id:
            return False
        return existing.claim_type in {
            "farm", "ranch", "hunting", "logging", "business", "construction_reservation", "reserved_expansion"
        }

    def _claim_tiles_have_conflict(self, tiles: set[tuple[int, int]], claim_type: str, settlement_id: str | None) -> bool:
        for tx, ty in tiles:
            for claim in self.get_land_claims_at(tx, ty):
                if self._claim_conflicts_for_type(claim, claim_type, settlement_id):
                    return True
        return False

    def ensure_settlement_territory(self, village: Village) -> LandClaim | None:
        existing_core = next(
            (self.land_claims_by_id.get(claim_id) for claim_id in getattr(village, "territory_claim_ids", [])
             if self.land_claims_by_id.get(claim_id) and self.land_claims_by_id[claim_id].claim_type == "settlement_core"),
            None,
        )
        anchor = self._get_village_anchor_coords(village)
        if anchor is None:
            return existing_core
        core_tiles = self._claim_radius_tiles(anchor[0], anchor[1], 8)
        for building in getattr(village, "buildings", []):
            core_tiles |= self._claim_rect_tiles(building.global_origin_x, building.global_origin_y, building.width, building.height, padding=1)
        core_tiles = {
            tile for tile in core_tiles
            if not self._claim_tiles_have_conflict({tile}, "settlement_core", village.id)
        }
        if existing_core is None:
            existing_core = self.create_land_claim(
                "settlement_core",
                core_tiles,
                owner_type="settlement",
                owner_id=village.id,
                settlement_id=village.id,
                priority=10,
                metadata={"jurisdiction": True, "anchor": anchor, "radius": 8},
            )
        else:
            existing_core.claimed_tiles |= core_tiles
            existing_core.metadata.setdefault("jurisdiction", True)
        for building in getattr(village, "buildings", []):
            if getattr(building, "territory_claim_id", None) is None and existing_core is not None:
                building.territory_claim_id = existing_core.id
        self._ensure_village_rural_claim(village, anchor)
        self._claim_existing_village_building_territory(village)
        return existing_core

    def _ensure_village_rural_claim(self, village: Village, anchor: tuple[int, int]) -> LandClaim | None:
        existing = next(
            (self.land_claims_by_id.get(claim_id) for claim_id in getattr(village, "territory_claim_ids", [])
             if self.land_claims_by_id.get(claim_id) and self.land_claims_by_id[claim_id].claim_type == "rural_expansion"),
            None,
        )
        radius = 18
        tiles = {
            tile for tile in self._claim_radius_tiles(anchor[0], anchor[1], radius)
            if not self._claim_tiles_have_conflict({tile}, "rural_expansion", village.id)
        }
        if existing is None:
            return self.create_land_claim(
                "rural_expansion",
                tiles,
                owner_type="settlement",
                owner_id=village.id,
                settlement_id=village.id,
                priority=3,
                metadata={"jurisdiction": True, "anchor": anchor, "radius": radius},
            )
        existing.claimed_tiles |= tiles
        existing.metadata.setdefault("radius", radius)
        return existing

    def _claim_existing_village_building_territory(self, village: Village) -> None:
        for building in getattr(village, "buildings", []):
            self._ensure_building_land_claim(building, village)

    def _building_claim_type(self, building_type: str, category: str) -> str | None:
        if building_type in {"ranch", "stable", "pasture"}:
            return "ranch"
        if building_type in {"farm", "field"} or "agricultural" in category:
            return "farm"
        if building_type in {"hunting_lodge", "hunter_lodge"}:
            return "hunting"
        if building_type in {"logging_camp", "lumber_mill"}:
            return "logging"
        if "workplace" in category or "commercial" in category:
            return "business"
        return None

    def _ensure_building_land_claim(self, building: Building, village: Village | None = None) -> LandClaim | None:
        existing_id = getattr(building, "territory_claim_id", None)
        existing = self.land_claims_by_id.get(existing_id)
        if existing is not None and existing.claim_type != "settlement_core":
            return existing
        settlement_id = getattr(building, "settlement_id", None) or getattr(village, "id", None)
        claim_type = self._building_claim_type(getattr(building, "building_type", ""), getattr(building, "category", ""))
        if claim_type is None:
            return existing
        padding = {"farm": 4, "ranch": 7, "hunting": 12, "logging": 10, "business": 1}.get(claim_type, 1)
        tiles = self._claim_rect_tiles(building.global_origin_x, building.global_origin_y, building.width, building.height, padding=padding)
        tiles = {
            tile for tile in tiles
            if not self._claim_tiles_have_conflict({tile}, claim_type, settlement_id)
        }
        claim = self.create_land_claim(
            claim_type,
            tiles,
            owner_type="building",
            owner_id=building.id,
            settlement_id=settlement_id,
            priority={"farm": 7, "ranch": 6, "hunting": 5, "logging": 5, "business": 8}.get(claim_type, 5),
            metadata={"building_id": building.id, "resource_use": claim_type},
        )
        if claim is not None:
            building.territory_claim_id = claim.id
        return claim

    def _expand_settlement_reserved_land(self, village: Village, project_type: str | None = None) -> LandClaim | None:
        anchor = self._get_village_anchor_coords(village)
        if anchor is None:
            return None
        existing = next(
            (self.land_claims_by_id.get(claim_id) for claim_id in getattr(village, "territory_claim_ids", [])
             if self.land_claims_by_id.get(claim_id) and self.land_claims_by_id[claim_id].claim_type == "reserved_expansion"),
            None,
        )
        pressure = self._calculate_settlement_expansion_pressure(village)
        radius = int((existing.metadata.get("radius", 20) if existing else 20) + max(1, pressure // 40))
        ring = self._claim_radius_tiles(anchor[0], anchor[1], radius) - self._claim_radius_tiles(anchor[0], anchor[1], max(0, radius - 4))
        candidates = {
            tile for tile in ring
            if not self._claim_tiles_have_conflict({tile}, "reserved_expansion", village.id)
        }
        if existing is None:
            existing = self.create_land_claim(
                "reserved_expansion",
                set(),
                reserved_tiles=candidates,
                owner_type="settlement",
                owner_id=village.id,
                settlement_id=village.id,
                priority=2,
                expansion_pressure=pressure,
                metadata={"project_type": project_type, "radius": radius},
            )
        else:
            existing.reserved_tiles |= candidates
            existing.expansion_pressure = pressure
            existing.metadata["radius"] = radius
            if project_type:
                existing.metadata["project_type"] = project_type
        return existing

    def _calculate_settlement_expansion_pressure(self, village: Village) -> int:
        residents = sum(len(getattr(b, "residents", [])) for b in village.buildings if b.category == "residential")
        capacity = sum(2 for b in village.buildings if b.category == "residential")
        pressure = max(0, residents - capacity + 1) * 40 if residents >= capacity else 0
        if sum(int(qty) for qty in getattr(village, "supply", {}).values()) > 200:
            pressure += 25
        if any(getattr(need, "settlement_id", None) == village.id for need in getattr(self.town_board, "economic_needs", [])):
            pressure += 35
        return pressure

    def _has_road_near(self, x: int, y: int, radius: int = 6) -> bool:
        for ty in range(max(0, y - radius), min(WORLD_HEIGHT, y + radius + 1)):
            for tx in range(max(0, x - radius), min(WORLD_WIDTH, x + radius + 1)):
                tile = self.get_tile_at(tx, ty)
                if tile and "road" in getattr(tile, "name", "").lower():
                    return True
        return False

    def _get_owner_wealth_tier(self, owner_id: int | None) -> str:
        if owner_id is None:
            return "middle"
        owner = self.get_entity_by_id(owner_id)
        if not owner:
            return "middle"
        # Player is assumed middle/rich based on wealth if we implement that, for now let's just use money
        money = getattr(owner.economic, "money", 0) if hasattr(owner, "economic") else 0
        if money > 500: return "rich"
        if money < 50: return "poor"
        return "middle"

    def _construction_footprint_tiles(self, recipe_key: str, x: int, y: int, variant_id: str | None = None) -> set[tuple[int, int]]:
        recipe = CONSTRUCTION_RECIPES.get(recipe_key, {})
        if recipe.get("source") == "building":
            from simulation.systems.architecture import BUILDING_ARCHETYPES
            width = int(recipe.get("width", 1))
            height = int(recipe.get("height", 1))
            yard_size = 0
            if recipe_key in BUILDING_ARCHETYPES:
                archetype = BUILDING_ARCHETYPES[recipe_key]
                variant = None
                if variant_id:
                    for v in archetype.variants:
                        if v.id == variant_id:
                            variant = v
                            break
                if not variant:
                    variant = archetype.get_variant("middle")
                if variant:
                    width = variant.width
                    height = variant.height
                    yard_size = variant.fenced_yard_size

            total_w = width + yard_size * 2
            total_h = height + yard_size * 2
            start_x = max(1, x - yard_size)
            start_y = max(1, y - yard_size)
            return self._claim_rect_tiles(start_x, start_y, total_w, total_h)
        return {(x, y)}

    def _can_reserve_land_for_construction(self, recipe_key: str, x: int, y: int, settlement_id: str | None, variant_id: str | None = None) -> bool:
        footprint = self._construction_footprint_tiles(recipe_key, x, y, variant_id)
        if any(not self._is_claimable_terrain(tx, ty) for tx, ty in footprint):
            return False
        # Building MUST fit entirely within a single chunk to prevent drawing errors during rendering
        chunk_x = x // CHUNK_SIZE
        chunk_y = y // CHUNK_SIZE
        if any(tx // CHUNK_SIZE != chunk_x or ty // CHUNK_SIZE != chunk_y for tx, ty in footprint):
            return False
        return not self._claim_tiles_have_conflict(footprint, "construction_reservation", settlement_id)

    def _find_valid_building_spot(self, village: Village, width: int, height: int) -> tuple[int, int] | None:
        """Find a claim-valid, access-aware spot near a village instead of random unreserved land."""
        self.ensure_settlement_territory(village)
        anchor = self._get_village_anchor_coords(village)
        if anchor is None:
            return None
        self._expand_settlement_reserved_land(village)

        search_radius_min = 6
        search_radius_max = 60
        candidates: list[tuple[int, int, int]] = []
        for y in range(max(5, anchor[1] - search_radius_max), min(WORLD_HEIGHT - height - 5, anchor[1] + search_radius_max) + 1, 2):
            for x in range(max(5, anchor[0] - search_radius_max), min(WORLD_WIDTH - width - 5, anchor[0] + search_radius_max) + 1, 2):
                dist = abs(x - anchor[0]) + abs(y - anchor[1])
                if dist < search_radius_min or dist > search_radius_max:
                    continue
                footprint = self._claim_rect_tiles(x, y, width, height)
                if any(not self._is_claimable_terrain(tx, ty) for tx, ty in footprint):
                    continue
                if self._claim_tiles_have_conflict(footprint, "construction_reservation", village.id):
                    continue
                collision = False
                for b in village.buildings:
                    if (x < b.global_origin_x + b.width + 2 and x + width + 2 > b.global_origin_x and
                        y < b.global_origin_y + b.height + 2 and y + height + 2 > b.global_origin_y):
                        collision = True
                        break
                if collision:
                    continue
                road_bonus = 30 if self._has_road_near(x + width // 2, y + height // 2) else 0
                reserved_bonus = 15 if any(
                    claim.claim_type == "reserved_expansion" and claim.settlement_id == village.id
                    for tile in footprint for claim in self.get_land_claims_at(*tile)
                ) else 0
                score = road_bonus + reserved_bonus - dist
                candidates.append((score, x, y))
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][1], candidates[0][2]

    def _update_player_career(self):
        """Updates the player's career status daily using standardized NPC logic."""
        if self.game_time == 0 or self.game_time % DAY_LENGTH_TICKS != 0:
            return

        if not self.player.economic.job_building_id:
            return

        self.player.career.advance_day()

        # 1. Decay performance (natural attrition if not working)
        # Check if player is currently at work (end of day check is harsh but simple)
        work_building = self.buildings_by_id.get(self.player.economic.job_building_id)
        is_at_work = False
        if work_building:
            if work_building.contains_global_coords(self.player.x, self.player.y):
                is_at_work = True

        if is_at_work:
            self.player.economic.work_performance = min(100, self.player.economic.work_performance + 10)
            if hasattr(self.player, "gain_skill_experience"):
                self.player.gain_skill_experience("labor", 3)
        else:
            self.player.economic.work_performance -= 10 # Penalty for absence at check time

        self.player.economic.work_performance = max(0, self.player.economic.work_performance)

        # 2. Handle Wages
        if self.player.economic.work_performance > 20:
            wage = getattr(self.player.economic, "daily_wage", 0)
            if wage == 0:
                village = None
                if self.player.economic.job_building_id:
                    building = self.buildings_by_id.get(self.player.economic.job_building_id)
                    if building and building.settlement_id:
                        atlas = getattr(self, "atlas", None)
                        if atlas and hasattr(atlas, "get_village"):
                            village = atlas.get_village(building.settlement_id)
                wage = self._get_employment_daily_wage(self.player.economic.profession, village=village)

            # Performance bonus
            if self.player.economic.work_performance > 80:
                wage += int(wage * 0.2)

            self.player.economic.money += wage
            self.add_message_to_chat_log(f"You received {wage} coins in wages from your job as {self.player.economic.profession}.")
        else:
            self.add_message_to_chat_log(f"You did not perform well enough to receive wages today.")

        # 3. Handle Firing
        if self.player.economic.work_performance <= 0:
            self.add_message_to_chat_log(f"You have been fired from your job as {self.player.economic.profession} due to poor performance!")
            self._set_entity_profession(self.player, "Unemployed", reason="player_fired")
            self.player.economic.job_building_id = None
            self.player.economic.days_employed = 0
            self.player.economic.work_performance = 50
            return

        self.player.economic.days_employed += 1

    def _select_village_construction_project(self, village: Village) -> str | None:
        residents = sum(len(getattr(b, "residents", [])) for b in village.buildings if b.category == "residential")
        capacity = sum(2 for b in village.buildings if b.category == "residential")
        if residents >= capacity:
            return "house"

        total_stored = sum(int(qty) for qty in getattr(village, "supply", {}).values())
        has_warehouse = any(getattr(b, "building_type", "") == "warehouse" for b in village.buildings)
        if total_stored > 200 and not has_warehouse:
            return "warehouse"

        economic_needs = getattr(getattr(self, "town_board", None), "economic_needs", [])
        has_workshop = any(getattr(b, "building_type", "") == "workshop" for b in village.buildings)
        if not has_workshop and any(getattr(need, "settlement_id", None) == village.id and getattr(need, "type", "") == "service" for need in economic_needs):
            return "workshop"
        return None

    def _plan_village_expansion(self, village: Village):
        """Creates a construction site when housing, storage, or service pressure exists."""
        if self._get_village_blueprints(village):
            return # Finish current project first

        project_type = self._select_village_construction_project(village)
        if project_type is None:
            return

        project = VILLAGE_BUILDING_PROJECTS.get(project_type)
        recipe = CONSTRUCTION_RECIPES.get(project_type, {})
        width = int(project.get("width", recipe.get("width", 1))) if project else int(recipe.get("width", 1))
        height = int(project.get("height", recipe.get("height", 1))) if project else int(recipe.get("height", 1))
        spot = self._find_valid_building_spot(village, width, height)
        if not spot:
            return

        blueprint = self.place_construction_blueprint(project_type, spot[0], spot[1], settlement_id=village.id)
        if blueprint is not None:
            blueprint.settlement_id = village.id
            blueprint.refresh_status()
            self._refresh_blueprint_map_marker(blueprint)
            self.log_event("construction_started", f"The village started building a new {project_type}.", -1, location=spot)

    def _npc_maybe_start_construction_project(self, npc: NPC, village: Village | None = None) -> ConstructionBlueprint | None:
        """Allow an autonomous NPC owner/foreman to request a pressure-driven project."""
        village = village or self._get_village_for_npc(npc, by_coords=True)
        if village is None or self._get_village_blueprints(village):
            return None
        project_type = self._select_village_construction_project(village)
        if project_type is None:
            return None
        recipe = CONSTRUCTION_RECIPES.get(project_type, {})
        spot = self._find_valid_building_spot(village, int(recipe.get("width", 1)), int(recipe.get("height", 1)))
        if spot is None:
            return None
        blueprint = self.place_construction_blueprint(project_type, spot[0], spot[1], owner_id=getattr(npc, "id", None), requester_id=getattr(npc, "id", None), settlement_id=village.id)
        if blueprint is not None:
            blueprint.settlement_id = village.id
            blueprint.refresh_status()
            self._refresh_blueprint_map_marker(blueprint)
        return blueprint

    def _is_blueprint_active(self, blueprint: ConstructionBlueprint | None) -> bool:
        if blueprint is None:
            return False
        return self._is_chunk_active(self.get_chunk_coords(blueprint.x, blueprint.y))

    def _advance_village_construction(self, village: Village):
        """Progresses offscreen construction projects through material-limited abstraction."""
        village_blueprints = self._get_village_blueprints(village)
        if not village_blueprints:
            return

        blueprint = village_blueprints[0]
        if self._is_blueprint_active(blueprint):
            blueprint.refresh_status()
            self._refresh_blueprint_map_marker(blueprint)
            return

        total_required = max(1, sum(int(quantity) for quantity in blueprint.required_materials.values()))
        materials_per_day = max(1, math.ceil(total_required / 5))
        moved_materials = 0

        for item_key, remaining_qty in list(blueprint.remaining_materials().items()):
            while remaining_qty > 0 and village.supply.get(item_key, 0) > 0 and moved_materials < materials_per_day:
                village.supply[item_key] -= 1
                if village.supply[item_key] <= 0:
                    del village.supply[item_key]
                item_reference = ItemReference(item_key)
                if not blueprint.deposit_item_reference(item_reference):
                    village.supply[item_key] = village.supply.get(item_key, 0) + 1
                    break
                self._complete_one_blueprint_task(blueprint, item_key)
                moved_materials += 1
                remaining_qty -= 1

        if blueprint.has_all_materials():
            completed = blueprint.apply_work(max(10, math.ceil(blueprint.required_work / 4)))
            self._refresh_blueprint_map_marker(blueprint)
            if completed:
                completed_build = self._complete_construction_blueprint(blueprint)
                if completed_build:
                    self.log_event(
                        "construction_complete",
                        f"The village completed a new {blueprint.target_build}.",
                        -1,
                        location=(blueprint.x, blueprint.y),
                    )
        else:
            blueprint.refresh_status()
            self._refresh_blueprint_map_marker(blueprint)

    def _is_sleeping_work_hour(self) -> bool:
        current_time_in_day = self.game_time % max(1, DAY_LENGTH_TICKS)
        work_start_tick = int(DAY_LENGTH_TICKS * WORK_START_TIME_RATIO)
        work_end_tick = int(DAY_LENGTH_TICKS * WORK_END_TIME_RATIO)
        return work_start_tick <= current_time_in_day < work_end_tick

    def _get_hourly_wage_amount(self, daily_wage: int) -> int:
        working_hours = max(1, int(round((WORK_END_TIME_RATIO - WORK_START_TIME_RATIO) * 24)))
        return max(1, int(round(max(0, int(daily_wage)) / working_hours)))

    def _apply_sleeping_npc_needs(self, npc: NPC) -> None:
        if npc is None or getattr(getattr(npc, "physical", None), "is_dead", False):
            return
        if hasattr(npc.physical, "hunger"):
            npc.physical.hunger = min(npc.physical.max_hunger, npc.physical.hunger + max(1, npc.physical.max_hunger // 24))
        if hasattr(npc.physical, "thirst"):
            npc.physical.thirst = min(npc.physical.max_thirst, npc.physical.thirst + max(1, npc.physical.max_thirst // 20))
        if npc.physical.hunger > int(npc.physical.max_hunger * 0.6) and npc.economic.money > 0:
            npc.economic.money -= 1
            npc.physical.hunger = max(0, npc.physical.hunger - 12)
        if npc.physical.thirst > int(npc.physical.max_thirst * 0.6) and npc.economic.money > 0:
            npc.economic.money -= 1
            npc.physical.thirst = max(0, npc.physical.thirst - 16)

    def _apply_abstract_production_for_worker(self, npc: NPC, building: Building) -> None:
        if npc is None or building is None:
            return
        profession_data = get_profession_data(npc.economic.profession) or {}
        sub_task_sequence = profession_data.get("default_sub_task_sequence", [])
        produced_anything = False

        for sub_task_id in sub_task_sequence:
            sub_task_data = get_sub_task_data(npc.economic.profession, sub_task_id) or {}
            consumes = sub_task_data.get("consumes_item_from_workplace", {})
            if any(building.building_inventory.get(item_key, 0) < quantity for item_key, quantity in consumes.items()):
                continue
            produces = sub_task_data.get("produces_item_at_workplace", {})
            if sub_task_data.get("produces_item_at_workplace_from_tile_harvest") and getattr(building, "building_type", "") == "farm":
                building.building_inventory["wheat"] = building.building_inventory.get("wheat", 0) + 1
                produced_anything = True
                break
            if produces:
                for item_key, quantity in consumes.items():
                    building.building_inventory[item_key] = building.building_inventory.get(item_key, 0) - quantity
                    if building.building_inventory[item_key] <= 0:
                        del building.building_inventory[item_key]
                for item_key, quantity in produces.items():
                    building.building_inventory[item_key] = building.building_inventory.get(item_key, 0) + quantity
                produced_anything = True
                break

        if not produced_anything and getattr(building, "building_type", "") == "farm":
            building.building_inventory["wheat"] = building.building_inventory.get("wheat", 0) + 1

    def process_abstract_simulation(self) -> None:
        interval = max(1, DAY_LENGTH_TICKS // 24)
        current_hour = self.game_time // interval
        if current_hour <= self.last_abstract_simulation_hour:
            return
        self.last_abstract_simulation_hour = current_hour

        sleeping_npcs = [
            npc
            for npc in itertools.chain(self.village_npcs, self.npcs)
            if getattr(npc, "is_sleeping", False) and not getattr(getattr(npc, "physical", None), "is_dead", False)
        ]
        if not sleeping_npcs:
            return

        building_workers: dict[str, list[NPC]] = {}
        for npc in sleeping_npcs:
            self._apply_sleeping_npc_needs(npc)
            work_building_id = getattr(getattr(npc, "schedule", None), "work_building_id", None)
            if work_building_id:
                building_workers.setdefault(work_building_id, []).append(npc)
            elif self._is_sleeping_work_hour() and getattr(getattr(npc, "economic", None), "daily_wage", 0) > 0:
                npc.economic.money += self._get_hourly_wage_amount(npc.economic.daily_wage)

        if not self._is_sleeping_work_hour():
            return

        for building_id, workers in building_workers.items():
            building = self.buildings_by_id.get(building_id)
            if building is None or self._is_building_active(building):
                continue
            building_balance = self._get_trade_money_balance(building)
            for worker in workers:
                hourly_wage = self._get_hourly_wage_amount(getattr(worker.economic, "daily_wage", 0))
                if building_balance >= hourly_wage:
                    building_balance -= hourly_wage
                    worker.economic.money += hourly_wage
                    self._apply_abstract_production_for_worker(worker, building)
            self._set_trade_money_balance(building, building_balance)

    def _update_abstract_simulation(self):
        """
        Runs a lightweight simulation for off-screen villages to simulate high-level events
        like births, deaths, and economic production/consumption, creating a living history.
        """
        # This should not run on every single tick. Let's run it once per day.
        if self.game_time % DAY_LENGTH_TICKS != 0:
            return

        player_chunk_x = self.player.x // CHUNK_SIZE
        player_chunk_y = self.player.y // CHUNK_SIZE

        for y_chunk in range(self.chunk_height):
            for x_chunk in range(self.chunk_width):
                chunk = self.chunks[y_chunk][x_chunk]
                if not chunk.village:
                    continue

                # Calculate distance to player
                dist = max(abs(x_chunk - player_chunk_x), abs(y_chunk - player_chunk_y))

                if dist > ABSTRACT_SIMULATION_DISTANCE_CHUNKS:
                    village = chunk.village
                    village_npcs = [npc for npc in self.village_npcs if self._get_village_for_npc(npc) == village]
                    if not village_npcs:
                        continue

                    # --- Economic Simulation ---
                    # 1. Production
                    for npc in village_npcs:
                        profession_data = get_profession_data(npc.economic.profession)
                        if not profession_data:
                            continue

                        # Simplified production logic
                        # Seasonal Farmer Production
                        if npc.economic.profession == "Farmer":
                            current_season = self.seasons[self.current_season_index]
                            production_amount = 0
                            if current_season == "Spring":
                                production_amount = 2 # Planting season, low output
                            elif current_season == "Summer":
                                production_amount = 5 # Growing/maintenance
                            elif current_season == "Autumn":
                                production_amount = 15 # Harvest!
                            elif current_season == "Winter":
                                production_amount = 0 # Nothing grows

                            if production_amount > 0:
                                village.supply["wheat"] = village.supply.get("wheat", 0) + production_amount

                        # General production from sub-tasks
                        if profession_data and "default_sub_task_sequence" in profession_data:
                            for sub_task_id in profession_data["default_sub_task_sequence"]:
                                sub_task_data = get_sub_task_data(npc.economic.profession, sub_task_id)
                                if not sub_task_data: continue

                                # Consume resources
                                consumes = sub_task_data.get("consumes_item_from_workplace", {})
                                can_produce = True
                                for item_key, qty in consumes.items():
                                    if village.supply.get(item_key, 0) < qty:
                                        can_produce = False
                                        # Production failed, increase demand for the missing resource
                                        village.demand[item_key] = village.demand.get(item_key, 0) + qty
                                        break # Stop processing this sub-task

                                if can_produce:
                                    # Consume the items
                                    for item_key, qty in consumes.items():
                                        village.supply[item_key] -= qty
                                        if village.supply[item_key] <= 0:
                                            del village.supply[item_key]

                                    # Produce the items
                                    produces = sub_task_data.get("produces_item_at_workplace", {})
                                    for prod_item_key, prod_qty in produces.items():
                                        village.supply[prod_item_key] = village.supply.get(prod_item_key, 0) + prod_qty


                    # Wildlife hunting: offscreen abstraction must still consume ecology population.
                    self._process_offscreen_hunting_for_village(village, [npc for npc in village_npcs if self._is_hunter_role(npc)])

                    # 2. Consumption (basic needs)
                    num_villagers = len(village_npcs)
                    # Everyone needs food
                    food_needed = num_villagers * 1 # 1 food item per person per day
                    consumed_food = 0
                    for food_key in ("bread", "processed_meat", "cooked_meat", "cooked_venison", "cooked_mutton", "cooked_fish", "raw_venison", "raw_meat"):
                        if consumed_food >= food_needed:
                            break
                        available_food = village.supply.get(food_key, 0)
                        if available_food <= 0:
                            continue
                        consumed = min(food_needed - consumed_food, available_food)
                        consumed_food += consumed
                        village.supply[food_key] = available_food - consumed
                        if village.supply[food_key] <= 0:
                            del village.supply[food_key]

                    # If there's a shortfall, demand for food increases
                    food_shortfall = food_needed - consumed_food
                    if food_shortfall > 0:
                        village.demand["food"] = village.demand.get("food", 0) + food_shortfall

                    # --- Construction & Expansion ---
                    self._plan_village_expansion(village)
                    self._advance_village_construction(village)

                    # --- Abstract Trade Simulation ---
                    # Find a partner village to trade with
                    # For simplicity, pick a random other village. In future, use distance.
                    if len(self.villages) > 1:
                        partner_village = random.choice([v for v in self.villages if v != village])

                        # Export Surplus Logic
                        # If we have too much of something (Supply > Demand * 2 or absolute > 50) and they have low supply
                        for item_key, qty in list(village.supply.items()):
                            if qty > 50 or qty > village.demand.get(item_key, 0) * 2:
                                partner_supply = partner_village.supply.get(item_key, 0)
                                if partner_supply < 10: # They are low
                                    trade_qty = 10
                                    village.supply[item_key] -= trade_qty
                                    partner_village.supply[item_key] = partner_supply + trade_qty

                                    # Trading improves relations
                                    current_rel = village.village_relationships.get(partner_village.id, 0)
                                    village.village_relationships[partner_village.id] = min(100, current_rel + 2)

                                    partner_rel = partner_village.village_relationships.get(village.id, 0)
                                    partner_village.village_relationships[village.id] = min(100, partner_rel + 2)

                                    # Log the trade event
                                    self.log_event(
                                        event_type="trade_deal",
                                        description=f"A caravan from this village sold {trade_qty} {item_key} to a neighboring settlement.",
                                        subject_id=-1, # System event
                                        location=village.interaction_points.get("town_square_center", (0,0))
                                    )
                                    # Record local event for history
                                    village.local_events.append(self.global_events[-1])

                    # --- Faction Diplomacy / Warfare ---
                    if len(self.villages) > 1:
                        for other_village in self.villages:
                            if other_village.id == village.id: continue

                            # Random events that worsen relationships if not trading
                            if random.random() < 0.05:
                                current_rel = village.village_relationships.get(other_village.id, 0)
                                village.village_relationships[other_village.id] = max(-100, current_rel - 5)
                                other_village.village_relationships[village.id] = max(-100, current_rel - 5)

                            # Declare war if relationships fall too low
                            if village.village_relationships.get(other_village.id, 0) < -50:
                                if other_village.id not in village.at_war_with:
                                    village.at_war_with.add(other_village.id)
                                    other_village.at_war_with.add(village.id)

                                    self.log_event(
                                        event_type="war_declared",
                                        description=f"Tensions boiled over and this village has declared war on a neighbor.",
                                        subject_id=-1,
                                        location=village.interaction_points.get("town_square_center", (0,0))
                                    )
                                    village.local_events.append(self.global_events[-1])


                            # Make peace if at war but relationships recover (unlikely without intervention but possible)
                            if other_village.id in village.at_war_with and village.village_relationships.get(other_village.id, 0) > -10:
                                village.at_war_with.remove(other_village.id)
                                other_village.at_war_with.remove(village.id)

                                self.log_event(
                                    event_type="peace_declared",
                                    description=f"A peace treaty was signed with a rival settlement.",
                                    subject_id=-1,
                                    location=village.interaction_points.get("town_square_center", (0,0))
                                )
                                village.local_events.append(self.global_events[-1])

                            # Dispatch raiding parties if still at war
                            if other_village.id in village.at_war_with:
                                if random.random() < 0.1: # 10% chance per day per enemy village
                                    self._spawn_raiding_party(village, other_village)
                                    self.log_event(
                                        event_type="raiding_party_dispatched",
                                        description=f"A raiding party was sent to attack a rival village.",
                                        subject_id=-1,
                                        location=village.interaction_points.get("town_square_center", (0,0))
                                    )
                                    village.local_events.append(self.global_events[-1])

                    # --- Birth Simulation ---
                    # Find potential couples (for simplicity, any two adults living together)
                    potential_parents = [npc for npc in village_npcs if 18 < npc.age < 50]
                    if len(potential_parents) >= 2 and random.random() < 0.05: # 5% chance of a birth event per day
                        parent1 = random.choice(potential_parents)
                        parent2 = random.choice(potential_parents)
                        if parent1.id != parent2.id:
                            # Create a new Child NPC
                            child_name = f"Child of {parent1.name}"
                            # Inherit home from parent1
                            home_id = parent1.schedule.home_building_id
                            home_coords = (parent1.x, parent1.y) # Default to parent's location if home not found
                            if home_id:
                                home_building = self.buildings_by_id.get(home_id)
                                if home_building:
                                    home_coords = (home_building.global_center_x, home_building.global_center_y)

                            child = NPC(
                                x=home_coords[0],
                                y=home_coords[1],
                                name=child_name,
                                dialogue=["Goo goo gaga."],
                                personality="child",
                                player_id=self.player.id
                            )
                            child.age = 0
                            self._set_entity_profession(child, "Child", reason="birth")
                            child.schedule.home_building_id = home_id

                            # Add to family ties
                            child.social.family_ties["mother_id"] = parent1.id # Simplified
                            child.social.family_ties["father_id"] = parent2.id
                            existing_siblings = [
                                other for other in self.village_npcs
                                if isinstance(other, NPC)
                                and (
                                    getattr(getattr(other, "social", None), "family_ties", {}).get("mother_id") == parent1.id
                                    or getattr(getattr(other, "social", None), "family_ties", {}).get("father_id") == parent2.id
                                )
                            ]
                            if existing_siblings:
                                child.social.family_ties["sibling_ids"] = [sibling.id for sibling in existing_siblings]
                                for sibling in existing_siblings:
                                    sibling_ties = getattr(getattr(sibling, "social", None), "family_ties", {})
                                    sibling_ids = sibling_ties.setdefault("sibling_ids", [])
                                    if child.id not in sibling_ids:
                                        sibling_ids.append(child.id)
                            for parent in (parent1, parent2):
                                parent_ties = getattr(getattr(parent, "social", None), "family_ties", {})
                                child_ids = parent_ties.setdefault("child_ids", [])
                                if child.id not in child_ids:
                                    child_ids.append(child.id)

                            # Add to world
                            self.village_npcs.append(child)
                            self._mark_entity_positions_dirty()
                            if home_id:
                                home_building = self.buildings_by_id.get(home_id)
                                if home_building:
                                    home_building.residents.append(child)

                            self.record_birth_event(
                                child=child,
                                parent_ids=(parent1.id, parent2.id),
                                description=f"A child, {child.name}, was born to {parent1.name} and {parent2.name}.",
                                location=(x_chunk * CHUNK_SIZE, y_chunk * CHUNK_SIZE),
                            )
                            # self.add_message_to_chat_log(f"A child was born in a distant village.")

                    # --- Death Simulation (Old Age) ---
                    elderly_npcs = [npc for npc in village_npcs if npc.age > 70]
                    for elder in elderly_npcs:
                        # Chance of dying increases with age
                        if random.random() < (elder.age - 70) / 100.0:
                            self.record_death_event(
                                deceased=elder,
                                description="{subject} died of old age.",
                                location=(x_chunk * CHUNK_SIZE, y_chunk * CHUNK_SIZE),
                                cause_of_death="old_age",
                                settlement_id=getattr(village, "id", None),
                                region_id=getattr(village, "region_id", None),
                            )
                            # In a full abstract sim, we would remove the NPC from the world here.
                            # For now, we just log it. A more complex system would be needed to truly remove them.
                            # self.handle_npc_death(elder) # This could be problematic if the NPC is referenced elsewhere.

    def _process_npc_witness_events(self):
        """
        Periodically checks for global events and adds them to the knowledge
        of NPCs who could have witnessed them.
        """
        # Only process this periodically for performance
        if self.game_time % 10 != 0:
            return

        # Check events that have happened in the last 10 ticks
        recent_events = [event for event in self.global_events if self.game_time - event.timestamp <= 10]

        if not recent_events:
            return

        potential_witnesses = list(self.all_npcs)
        for event in recent_events:
            if not event.location:
                continue

            event_x, event_y = event.location

            for npc in potential_witnesses:
                if npc.physical.is_dead or isinstance(npc, Animal) or (hasattr(event, 'subject_id') and event.subject_id == npc.id) or event.id in npc.knowledge.known_events:
                        continue

                # Check if NPC can see the event's location
                if npc.id in self.npc_fov_maps:
                    fov_map = self.npc_fov_maps[npc.id]
                    if 0 <= event_x < WORLD_WIDTH and 0 <= event_y < WORLD_HEIGHT:
                        if fov_map[event_y, event_x]:
                            # NPC witnessed the event. Add to their knowledge.
                            self.knowledge_system.learn_event(npc, event)

    def _process_npc_gossip_reaction(self):
        """Apply simple deterministic reactions to remembered social events."""
        for npc in self.all_npcs:
            if isinstance(npc, Animal) or npc.physical.is_dead:
                continue
            memories = getattr(getattr(npc, "knowledge", None), "known_memories", {})
            if not memories:
                continue

            unreacted_memories = [
                memory for memory in memories.values()
                if memory.id not in npc.knowledge.reacted_to_event_ids
            ]
            if not unreacted_memories:
                continue
            unreacted_memories.sort(key=lambda memory: (-memory.importance_score, -memory.timestamp, memory.id))
            memory = unreacted_memories[0]

            if memory.event_type == "murder" and memory.subject_id not in {None, npc.id}:
                npc.social.relationships[memory.subject_id] = npc.social.relationships.get(memory.subject_id, 50) - 10
            elif memory.event_type == "unpaid_wages" and memory.subject_id is not None:
                npc.add_grudge(memory.subject_id, f"Heard about unpaid wages affecting {memory.target_id}.")

            npc.knowledge.reacted_to_event_ids.add(memory.id)

    def _get_village_at_coords(self, x: int, y: int) -> Village | None:
        """Gets the village object at a given world coordinate, if one exists."""
        chunk_x = x // CHUNK_SIZE
        chunk_y = y // CHUNK_SIZE
        if 0 <= chunk_x < self.chunk_width and 0 <= chunk_y < self.chunk_height:
            chunk = self.chunks[chunk_y][chunk_x]
            if chunk and chunk.village:
                return chunk.village
        return None

    def _get_witnesses_to_action(self, action_x: int, action_y: int, action_type: str) -> list[NPC]:
        """
        Finds NPCs who witness an act.
        A witness must have line of sight to the action.
        For crimes, filters based on profession/personality.
        """
        witnesses = []
        potential_witnesses = self.all_npcs

        for npc in potential_witnesses:
            if npc.is_dead or isinstance(npc, Animal):
                continue

            # Check visibility
            can_see_action = False
            if npc.id in self.npc_fov_maps:
                fov_map = self.npc_fov_maps[npc.id]
                if 0 <= action_x < WORLD_WIDTH and 0 <= action_y < WORLD_HEIGHT:
                    if fov_map[action_y, action_x]: # Note: FOV map is [y, x]
                        can_see_action = True

            if can_see_action:
                # If it's a crime, apply logic about who cares/reports
                if action_type in ["assault", "lockpicking", "theft"]:
                    if npc.economic.profession in ["Guard", "Sheriff"]:
                        witnesses.append(npc)
                    elif npc.social.personality not in ["careless", "fearful"]:
                        witnesses.append(npc)
                else:
                    # General event, anyone seeing it is a witness
                    witnesses.append(npc)

        return witnesses

    def _broadcast_combat_memory(self, attacker, defender, weapon_name: str, actual_damage: int, new_statuses: set[str]):
        """Constructs and logs a deterministic memory string for a combat event."""
        if actual_damage <= 0:
            return

        attacker_name = attacker.name if hasattr(attacker, "name") else "Someone"
        defender_name = defender.name if hasattr(defender, "name") else "someone"
        body_part = defender.combat.last_hit_part if hasattr(defender, "combat") and getattr(defender.combat, "last_hit_part", None) else "body"

        memory_str = f"Witnessed {attacker_name} strike {defender_name}'s {body_part} with {weapon_name} for {actual_damage} damage."

        if "broken_leg" in new_statuses:
            memory_str += " ...causing a broken_leg."

        # Add to attacker and defender
        if hasattr(attacker, "knowledge") and hasattr(attacker.knowledge, "long_term_memory"):
            attacker.knowledge.long_term_memory.append(memory_str)
        if hasattr(defender, "knowledge") and hasattr(defender.knowledge, "long_term_memory"):
            defender.knowledge.long_term_memory.append(memory_str)

        # Broadcast to witnesses in FOV
        for w_npc in self.all_npcs:
            if w_npc.id == attacker.id or w_npc.id == defender.id or w_npc.physical.is_dead:
                continue

            if w_npc.id in self.npc_fov_maps:
                if 0 <= defender.x < WORLD_WIDTH and 0 <= defender.y < WORLD_HEIGHT:
                    if self.npc_fov_maps[w_npc.id][defender.y, defender.x]:
                        if hasattr(w_npc, "knowledge") and hasattr(w_npc.knowledge, "long_term_memory"):
                            w_npc.knowledge.long_term_memory.append(memory_str)

    def _handle_witness_reaction(self, witness: NPC, crime_type: str, criminal: Player or NPC, victim: NPC | None = None):
        """Determines how an NPC reacts to witnessing a crime using an LLM prompt."""
        if witness.combat.is_hostile_to_player or witness.schedule.current_task in ["fleeing_from_player", "going_to_report_crime", "combat_action_flee_from_player"]:
            return

        visible_criminal_id = self.resolve_visible_subject_id(witness, criminal)
        visible_criminal_name = self.get_visible_entity_name(witness, criminal, unknown_name="Unknown culprit")

        victim_name = "N/A"
        witness_attitude_to_victim = "N/A"
        if victim:
            victim_name = victim.name
            if witness.economic.profession == victim.economic.profession and witness.economic.profession not in ["Unemployed", "Farmer"]:
                 witness_attitude_to_victim = "friendly"
            else:
                 witness_attitude_to_victim = "neutral"

        # Grant Infamy for witnessed crimes
        criminal.social.infamy += 5
        if isinstance(criminal, Player):
            self.add_message_to_chat_log("Your infamy has increased by 5.")
        else:
            self.add_message_to_chat_log(f"{self.get_entity_display_name(criminal)}'s infamy has increased by 5.")

        # Record the crime as structured history.
        self.record_crime_event(
            crime_kind=crime_type,
            suspect_id=visible_criminal_id,
            victim_id=victim.id if victim else None,
            witness_ids=(witness.id,),
            description=f"{{subject}} was witnessed by {witness.name} committing the crime of {crime_type}.",
            location=(witness.x, witness.y),
        )

        prompt = LLM_PROMPTS["npc_witness_reaction"].format(
            witness_name=witness.name,
            witness_personality=witness.social.personality,
            witness_profession=witness.economic.profession,
            witness_attitude_to_criminal=witness.attitude_to_player,
            witness_attitude_to_victim=witness_attitude_to_victim,
            crime_type=crime_type,
            criminal_name=visible_criminal_name,
            victim_name=victim_name
        )

        response_str = self._call_llm(prompt)
        if not response_str:
            self.add_message_to_chat_log(f"{self.get_entity_display_name(witness)} seems confused by what they saw. (LLM Error)")
            return

        try:
            response_json = json.loads(response_str)
            reaction = response_json.get("reaction")
            dialogue = response_json.get("dialogue", f"{witness.name} gasps!")
            grudge_reason = response_json.get("grudge_reason")

            self.add_message_to_chat_log(dialogue) # Show the witness's verbal reaction

            if grudge_reason and isinstance(visible_criminal_id, int):
                current_day = self.game_time // DAY_LENGTH_TICKS
                witness.add_grudge(
                    visible_criminal_id,
                    grudge_reason,
                    severity=55,
                    current_day=current_day,
                    decay_days=8,
                )
                # Make this message conditional on the criminal being the player for clarity
                if isinstance(criminal, Player):
                    self.add_message_to_chat_log(f"({self.get_entity_display_name(witness)} now holds a grudge against you: {grudge_reason})")

            if reaction == "become_hostile":
                witness.combat.is_hostile_to_player = True
            elif reaction == "report_crime":
                sheriff_office = self._find_nearest_building_of_type(witness, "sheriff_office")
                if sheriff_office:
                    witness.schedule.current_task = "going_to_report_crime"
                    witness.task_target_coords = (sheriff_office.global_center_x, sheriff_office.global_center_y)
                    witness.schedule.current_path = [] # Clear path for new destination
                else:
                    self.add_message_to_chat_log(f"{self.get_entity_display_name(witness)} wants to report the crime but doesn't know where the sheriff is.")
            elif reaction == "flee":
                witness.schedule.current_task = "combat_action_flee_from_player"
                witness.schedule.current_path = [] # Force path recalculation
            elif reaction == "admonish":
                # The grudge already lowered the relationship, so this is just a verbal action.
                pass
            elif reaction == "ignore":
                # Do nothing.
                pass

        except json.JSONDecodeError:
            self.add_message_to_chat_log(f"{self.get_entity_display_name(witness)} seems unsure how to react. (LLM Format Error: {response_str})")

    def _update_economy(self):
        """Periodically updates the supply and demand of all villages."""
        from simulation.systems.economy import simulate_village_economy
        for y_chunk in range(self.chunk_height):
            for x_chunk in range(self.chunk_width):
                chunk = self.chunks[y_chunk][x_chunk]
                if chunk.village:
                    village = chunk.village
                    # Decay demand over time
                    for item_key in list(village.demand.keys()):
                        village.demand[item_key] *= 0.99
                        if village.demand[item_key] < 1:
                            del village.demand[item_key]

                    # Recalculate supply from scratch
                    village.supply = {}
                    for building in village.buildings:
                        for item_key, quantity in building.building_inventory.items():
                            village.supply[item_key] = village.supply.get(item_key, 0) + quantity

                    # Run advanced macroscopic simulation if tick aligns
                    if self.game_time % 100 == 0:
                        simulate_village_economy(self, village)

    def get_dynamic_price(self, item_key: str, village: Village, merchant: NPC | None = None) -> int:
        """Calculates the dynamic price of an item based on village supply and demand."""
        base_price = ITEM_DEFINITIONS.get(item_key, {}).get("value", 0)
        if not village:
            price_modifier = 1.0
        else:
            supply = village.supply.get(item_key, 1)  # Avoid division by zero
            demand = village.demand.get(item_key, 1)

            # Simple formula: price = base_price * (demand / supply)
            # Add clamping to prevent extreme prices
            price_modifier = max(0.2, min(5.0, demand / supply))

        memory_reputation = merchant.knowledge.get_reputation_towards(self.player) if merchant is not None else 0
        if memory_reputation <= -40:
            price_modifier *= 1.5
        elif memory_reputation >= 10:
            price_modifier *= 0.8

        dynamic_price = int(base_price * price_modifier)

        return max(1, dynamic_price) # Ensure price is at least 1

    def _is_player_near_workstation(self, required_workstation: str) -> bool:
        """Checks if the player is adjacent to a required workstation."""
        if not required_workstation:
            return True # No workstation required

        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                tile = self.get_tile_at(self.player.x + dx, self.player.y + dy)
                if tile and hasattr(tile, 'properties') and tile.properties.get("workstation_type") == required_workstation:
                    return True
        return False

    def craft_item(self, item_key: str):
        """Crafts an item if the player has the required resources and provides feedback on failure."""
        if item_key not in ITEM_DEFINITIONS:
            self.add_message_to_chat_log(f"You don't know how to craft '{item_key}'.")
            return

        item_def = ITEM_DEFINITIONS[item_key]
        recipe = item_def.get("crafting_recipe", {})
        if not recipe:
            self.add_message_to_chat_log(f"There is no recipe for '{item_def['name']}'.")
            return

        # Check for ingredients first
        for resource_key, required_qty in recipe.items():
            if not self.player.has_item(resource_key, required_qty):
                resource_name = ITEM_DEFINITIONS.get(resource_key, {}).get("name", resource_key)
                self.add_message_to_chat_log(f"You don't have enough {resource_name}. (Need {required_qty})")
                return

        # Check for workstation
        required_workstation = item_def.get("required_workstation")
        if required_workstation and not self._is_player_near_workstation(required_workstation):
            self.add_message_to_chat_log(f"You need to be near a {required_workstation} to craft this.")
            return

        # All checks passed, proceed to consume resources and craft
        for resource_key, required_qty in recipe.items():
            if not self.player.remove_item(resource_key, required_qty):
                self.add_message_to_chat_log(f"Error consuming {resource_key} for crafting. Aborted.")
                return

        # Add crafted item
        self.player.add_item(item_key, 1)
        if hasattr(self.player, "gain_skill_experience"):
            self.player.gain_skill_experience("crafting", 5)
        self.add_message_to_chat_log(f"You crafted a {ITEM_DEFINITIONS[item_key]['name']}!")


    def use_item(self, item_key: str):
        """Uses an item from the player's inventory."""
        item_def = ITEM_DEFINITIONS.get(item_key)
        if not item_def:
            self.add_message_to_chat_log(f"You don't know how to use '{item_key}'.")
            return

        # Handle equipping armor
        if "armor" in item_def.get("item_type_tags", []):
            self.player.equip_armor(item_key)
            return

        # Check if trying to use (extinguish) an active light source by "using" its lit state key
        if self.player.equipment.equipped_light_item_key == item_key and item_def.get("properties", {}).get("emits_light"):
            # This means player is trying to "use" their currently lit torch, so extinguish it.
            extinguish_becomes_key = item_def.get("properties", {}).get("on_extinguish_becomes")
            if extinguish_becomes_key:
                self.player.add_item(extinguish_becomes_key, 1)

            self.add_message_to_chat_log(f"You extinguish your {self.player.equipment.equipped_light_item_key}.")
            self.player.equipment.equipped_light_item_key = None
            self.player.equipment.current_personal_light_radius = 0
            self.player.equipment.light_source_active_until_tick = -1
            self._update_player_fov()
            return

        # Standard item usage from inventory
        if not self.player.has_item(item_key):
            self.add_message_to_chat_log(f"You don't have any {item_def.get('name', item_key)} to use.")
            return

        on_use_effect = item_def.get("on_use_effect")

        if on_use_effect == "light_torch":
            if self.player.equipment.equipped_light_item_key: # Already has a light source active
                self.add_message_to_chat_log(f"You already have a {self.player.equipment.equipped_light_item_key} lit.")
                return

            # Consume the unlit_torch
            self.player.remove_item(item_key, 1)

            # Activate "torch_lit" state
            lit_torch_def = ITEM_DEFINITIONS.get("torch_lit", {})
            self.player.equipment.equipped_light_item_key = "torch_lit" # Use the key for the lit definition
            self.player.equipment.current_personal_light_radius = lit_torch_def.get("properties", {}).get("light_radius", 0)
            duration = lit_torch_def.get("properties", {}).get("duration_ticks", -1)
            if duration > 0:
                self.player.equipment.light_source_active_until_tick = self.game_time + duration
            else:
                self.player.equipment.light_source_active_until_tick = -1 # Infinite or not applicable

            self.add_message_to_chat_log(f"You light the {item_def.get('name', item_key)}. It casts a warm glow.")
            self._update_player_fov()
            return

        # Existing healing logic (or other on_use dictionary based effects)
        on_use_dict = item_def.get("on_use")
        if on_use_dict:
            heal_amount = on_use_dict.get("heal_amount")
            if heal_amount:
                if self.player.combat.hp >= self.player.combat.max_hp:
                    self.add_message_to_chat_log("You are already at full health!")
                else:
                    self.player.combat.hp = min(self.player.combat.max_hp, self.player.combat.hp + heal_amount)
                    self.player.remove_item(item_key, 1)
                    self.add_message_to_chat_log(f"You used a {item_def['name']} and healed {heal_amount} HP.")
                    self.visual_effects.append(FloatingTextEffect(self.player.x, self.player.y, f"+{heal_amount}", color=(0, 255, 0)))
                    consumed = True

            reduces_hunger_amount = on_use_dict.get("reduces_hunger")
            if reduces_hunger_amount:
                if self.player.physical.hunger > 0 :
                    self.player.physical.hunger = max(0, self.player.physical.hunger - reduces_hunger_amount)
                    self.add_message_to_chat_log(f"You eat the {item_def['name']}. You feel less hungry.")
                    if not consumed: # Consume item if not already consumed by healing
                        self.player.remove_item(item_key, 1)
                    consumed = True
                    update_player_needs_system(self, initial_setup=True) # Update status messages immediately
                else:
                    self.add_message_to_chat_log(f"You are not hungry enough to eat the {item_def['name']}.")


            reduces_thirst_amount = on_use_dict.get("reduces_thirst")
            if reduces_thirst_amount:
                if self.player.physical.thirst > 0:
                    self.player.physical.thirst = max(0, self.player.physical.thirst - reduces_thirst_amount)
                    self.add_message_to_chat_log(f"You drink the {item_def.get('name', item_key)}. You feel less thirsty.")
                    if not consumed: # Consume item if not already consumed
                        self.player.remove_item(item_key, 1)
                    consumed = True
                    update_player_needs_system(self, initial_setup=True) # Update status messages immediately
                else:
                    self.add_message_to_chat_log(f"You are not thirsty enough for the {item_def.get('name', item_key)}.")

            if consumed:
                return # Action taken

        # Fallback if no specific use effect handled
        self.add_message_to_chat_log(f"You can't figure out how to use the {item_def.get('name', item_key)} right now.")

    def player_can_craft(self, item_key: str) -> bool:
        """Checks if the player has the resources and is near the required workstation to craft an item."""
        if item_key not in ITEM_DEFINITIONS:
            return False

        item_def = ITEM_DEFINITIONS[item_key]
        recipe = item_def.get("crafting_recipe", {})
        if not recipe:
            return False

        # Check for ingredients
        for resource_key, required_qty in recipe.items():
            if not self.player.has_item(resource_key, required_qty):
                return False

        # Check for workstation
        required_workstation = item_def.get("required_workstation")
        if required_workstation and not self._is_player_near_workstation(required_workstation):
            return False

        return True

    def drop_item_on_map(self, item_key: str, quantity: int, x: int, y: int):
        """Drops an item or stack of items onto the map at specified coordinates."""
        if quantity <= 0:
            return

        if (x, y) not in self.items_on_map:
            self.items_on_map[(x, y)] = Inventory()

        self.items_on_map[(x, y)].add_item(item_key, quantity)

        # self.add_message_to_chat_log(f"Dropped {quantity} {ITEM_DEFINITIONS.get(item_key,{}).get('name',item_key)} at ({x},{y}).") # Optional debug

    def drop_item_reference_on_map(self, item_reference, x: int, y: int):
        """Drops a concrete item object onto the map without losing metadata."""
        if item_reference is None:
            return
        if (x, y) not in self.items_on_map:
            self.items_on_map[(x, y)] = Inventory()
        self.items_on_map[(x, y)].add_item_reference(item_reference)

    def remove_item_from_map(self, item_key: str, quantity: int, x: int, y: int) -> bool:
        """Removes a specified quantity of an item from the map at coordinates. Returns True if successful."""
        if quantity <= 0: return False
        if (x, y) in self.items_on_map:
            items_at_loc = self.items_on_map[(x, y)]
            if items_at_loc.remove_item(item_key, quantity):
                if not items_at_loc:
                    del self.items_on_map[(x, y)]
                return True
            return False
        return False

    def pop_item_reference_from_map(self, item_key: str, x: int, y: int) -> ItemReference | None:
        inventory = self.items_on_map.get((x, y))
        if inventory is None or not hasattr(inventory, "pop_item_reference"):
            return None
        item_reference = inventory.pop_item_reference(item_key)
        if inventory and len(inventory) <= 0:
            self.items_on_map.pop((x, y), None)
        elif not inventory:
            self.items_on_map.pop((x, y), None)
        return item_reference

    def complete_quest(self, quest_id: str, quest_giver_npc: NPC):
        """Handles player attempting to complete a quest."""
        quest_giver_name = self.get_entity_display_name(quest_giver_npc)
        if quest_id not in self.player.knowledge.active_quests:
            self.add_message_to_chat_log("Error: Quest not found or not active.")
            if self.chat_ui_active and self.chat_ui_target_npc == quest_giver_npc:
                self.chat_ui_history.append((quest_giver_name, "Are you sure we had an arrangement like that?"))
            return

        active_quest_data = self.player.knowledge.active_quests[quest_id]
        is_static_quest = quest_id in QUEST_DEFINITIONS

        # --- Check Completion Conditions ---
        is_complete = False
        if active_quest_data["type"] == "fetch":
            if self.player.has_item(active_quest_data["item_to_fetch_key"], active_quest_data["item_fetch_count"]):
                is_complete = True
        elif active_quest_data["type"] == "kill":
            if active_quest_data["progress"] >= active_quest_data["target_count"]:
                is_complete = True

        # --- Handle Dialogue and Rewards ---
        if is_complete:
            # Consume items for fetch quests
            if active_quest_data["type"] == "fetch":
                self.player.remove_item(active_quest_data["item_to_fetch_key"], active_quest_data["item_fetch_count"])

            log_message = f"Quest '{active_quest_data['title']}' completed."
            completion_dialogue = "Thank you so much! You're a lifesaver."

            if is_static_quest:
                quest_def = QUEST_DEFINITIONS.get(quest_id, {})
                reward_money = quest_def.get("reward_money", 0)
                if reward_money > 0:
                    self.player.economic.money += reward_money

                reward_items = quest_def.get("reward_items", {})
                for item_key, quantity in reward_items.items():
                    self.player.add_item(item_key, quantity)

                self.player.social.fame += 10 # Standard fame for static quests
                log_message = quest_def.get("completion_message_log", log_message)
                completion_dialogue = quest_def.get("dialogue_complete_report", completion_dialogue)

                self.log_event(
                    event_type="quest_complete",
                    description=f"{{subject}} completed the quest: {active_quest_data['title']}",
                    subject_id=self.player.id,
                    location=(self.player.x, self.player.y)
                )
            else: # Dynamic quest
                reward_money = 25
                self.player.economic.money += reward_money
                self.add_message_to_chat_log(f"You received {reward_money} money.")

                quest_giver_npc.physical.hunger = 0
                quest_giver_npc.physical.thirst = 0
                quest_giver_npc.social.relationships[self.player.id] = quest_giver_npc.social.relationships.get(self.player.id, 50) + 15


            self.add_message_to_chat_log(log_message)
            if hasattr(self.player, "gain_skill_experience"):
                self.player.gain_skill_experience("questing", 8)

            # Update quest status
            del self.player.knowledge.active_quests[quest_id]
            self.player.knowledge.completed_quests.append(quest_id)

            # Dialogue
            if self.chat_ui_active:
                self.chat_ui_history.append((quest_giver_name, completion_dialogue))
        else:
            # Dialogue for incomplete quest
            if self.chat_ui_active:
                if active_quest_data["type"] == "fetch":
                    item_name = active_quest_data['item_to_fetch_key'].replace('_', ' ')
                    self.chat_ui_history.append((quest_giver_name, f"It looks like you still don't have the {active_quest_data['item_fetch_count']} {item_name} I need."))
                elif active_quest_data["type"] == "kill":
                    quest_def = QUEST_DEFINITIONS.get(quest_id, {})
                    remaining = active_quest_data["target_count"] - active_quest_data["progress"]
                    incomplete_dialogue = quest_def.get("dialogue_incomplete_report", f"You still need to defeat {remaining} more.").format(remaining_count=remaining)
                    self.chat_ui_history.append((quest_giver_name, incomplete_dialogue))
    def player_attempt_fish(self, water_x: int, water_y: int):
        """Handles the player's attempt to fish."""
        if not self.player.has_item("fishing_rod"):
            self.add_message_to_chat_log("You need a fishing rod to fish.")
            return

        target_tile = self.get_tile_at(water_x, water_y)
        if not (target_tile and target_tile.name in ["Water", "Deep Water"]):
            self.add_message_to_chat_log("You can't fish there.")
            return

        self.add_message_to_chat_log("You cast your line into the water...")

        if random.random() < 0.3: # 30% chance to catch a fish
            fish_types = ["fish", "salmon", "trout"]
            fish_caught = random.choice(fish_types)
            self.player.add_item(f"raw_{fish_caught}")
            self.add_message_to_chat_log(f"You caught a {fish_caught}!")
        else:
            self.add_message_to_chat_log("You didn't catch anything.")

    def npc_attempt_fish(self, npc, water_x, water_y):
        """Handles an NPC's attempt to fish."""
        target_tile = self.get_tile_at(water_x, water_y)
        if not (target_tile and target_tile.name in ["Water", "Deep Water"]):
            return

        if random.random() < 0.2: # 20% chance for NPC to catch a fish
            fish_types = ["fish", "salmon", "trout"]
            fish_caught = random.choice(fish_types)
            work_building = self.buildings_by_id.get(npc.schedule.work_building_id)
            if work_building:
                work_building.building_inventory[f"raw_{fish_caught}"] = work_building.building_inventory.get(f"raw_{fish_caught}", 0) + 1
                self.add_message_to_chat_log(self.text.entity_caught_fish(npc, fish_caught))

    def player_attempt_till_soil(self, target_x: int, target_y: int):
        """Handles the player's attempt to till soil."""
        if not self.player.has_item("stone_hoe"):
            self.add_message_to_chat_log("You need a hoe to till the soil.")
            return

        target_tile = self.get_tile_at(target_x, target_y)
        if not (target_tile and target_tile.name == "Plains"):
            self.add_message_to_chat_log("You can only till plains.")
            return

        self.add_message_to_chat_log("You till the soil.")
        tilled_soil_def = TILE_DEFINITIONS["tilled_soil"]
        self._change_map_tile((target_x, target_y), tilled_soil_def)

        # Handle tool durability
        hoe_reference = self.player.get_item_reference("stone_hoe")
        if hoe_reference is not None:
            broke = hoe_reference.degrade(1)
            if broke:
                self.player.remove_item("stone_hoe", 1)
                self.add_message_to_chat_log("Your stone hoe broke!")
            else:
                self.add_message_to_chat_log(f"Your stone hoe shows some wear (Durability: {hoe_reference.current_durability}/{hoe_reference.max_durability}).")

    def player_attempt_plant_seeds(self, target_x: int, target_y: int):
        """Handles the player's attempt to plant seeds."""
        if not self.player.has_item("wheat_seeds"):
            self.add_message_to_chat_log("You don't have any seeds to plant.")
            return

        target_tile = self.get_tile_at(target_x, target_y)
        if not (target_tile and target_tile.name == "Tilled Soil"):
            self.add_message_to_chat_log("You can only plant seeds on tilled soil.")
            return

        self.player.remove_item("wheat_seeds", 1)
        self.add_message_to_chat_log("You plant the seeds.")
        wheat_plant_def = TILE_DEFINITIONS["wheat_plant_growing"]
        self._change_map_tile((target_x, target_y), wheat_plant_def)

    def player_attempt_harvest(self, target_x: int, target_y: int):
        """Handles the player's attempt to harvest a crop."""
        target_tile = self.get_tile_at(target_x, target_y)
        if not (target_tile and hasattr(target_tile, 'properties') and target_tile.properties.get("is_harvestable")):
            self.add_message_to_chat_log("There is nothing to harvest here.")
            return

        self.add_message_to_chat_log("You begin to harvest the crop...")

        if random.random() < 0.8: # 80% chance to successfully harvest
            harvest_yield = target_tile.properties.get("harvest_yield_item_key")
            if harvest_yield:
                self.player.add_item(harvest_yield, 1)
                if hasattr(self.player, "gain_skill_experience"):
                    self.player.gain_skill_experience("farming", 4)
                self.add_message_to_chat_log(f"You harvested one {harvest_yield}.")
                becomes_on_harvest = target_tile.properties.get("becomes_on_harvest_key")
                if becomes_on_harvest and becomes_on_harvest in TILE_DEFINITIONS:
                    revert_tile_def = TILE_DEFINITIONS[becomes_on_harvest]
                    self._change_map_tile((target_x, target_y), revert_tile_def)
                else:
                    # Fallback: turn it back to tilled_soil if key is missing
                    self._change_map_tile((target_x, target_y), TILE_DEFINITIONS["tilled_soil"])
            else:
                 self.add_message_to_chat_log("The crop is not ready to be harvested or yields nothing.")

        else:
            self.add_message_to_chat_log("You failed to harvest the crop.")

    def player_attempt_cook(self, x: int, y: int):
        """Handles the player's attempt to cook food at a fire."""
        target_tile = self.get_tile_at(x, y)
        if not (target_tile and target_tile.properties.get("workstation_type") == "fire"):
            self.add_message_to_chat_log("You need a fire to cook.")
            return

        # Find cookable items in inventory
        cookable_items = []
        for item_key, count in list(self.player.economic.inventory.items()):
            if item_key == "item_references":
                continue
            # Iterate all items to find if they are a product of cooking this ingredient
            for product_key, product_def in ITEM_DEFINITIONS.items():
                recipe = product_def.get("crafting_recipe")
                workstation = product_def.get("required_workstation")

                if recipe and workstation == "fire" and item_key in recipe:
                     cookable_items.append((item_key, product_key))

        if not cookable_items:
            self.add_message_to_chat_log("You have nothing to cook.")
            return

        # For now, just cook the first available item found
        # Future: Context menu selection
        ingredient_key, product_key = cookable_items[0]

        if self.player.remove_item(ingredient_key, 1):
            self.player.add_item(product_key, 1)
            product_name = ITEM_DEFINITIONS[product_key]["name"]
            self.add_message_to_chat_log(f"You cook a {product_name}.")
        else:
             self.add_message_to_chat_log("Something went wrong with cooking.")

    def player_attempt_smoke(self, x: int, y: int):
        """Handles the player's attempt to smoke meat at a smoking rack."""
        target_tile = self.get_tile_at(x, y)
        if not (target_tile and target_tile.properties.get("workstation_type") == "smoking_rack"):
            self.add_message_to_chat_log("You need a smoking rack to smoke meat.")
            return

        # Smoking requires raw meat/fish AND fuel (raw_log)
        if not self.player.has_item("raw_log", 1):
            self.add_message_to_chat_log("You need wood to fuel the smoking rack.")
            return

        # Find smokable items
        smokable_items = []
        for item_key, count in list(self.player.economic.inventory.items()):
            if item_key == "item_references":
                continue

            # Map raw -> smoked
            smoked_version = None
            if item_key == "raw_meat" or item_key == "raw_venison" or item_key == "raw_mutton":
                smoked_version = "smoked_meat"
            elif item_key == "raw_fish":
                smoked_version = "smoked_fish"

            if smoked_version:
                smokable_items.append((item_key, smoked_version))

        if not smokable_items:
            self.add_message_to_chat_log("You have no raw meat or fish to smoke.")
            return

        # Smoke the first available item
        ingredient_key, product_key = smokable_items[0]

        if self.player.remove_item(ingredient_key, 1):
            if self.player.remove_item("raw_log", 1):
                self.player.add_item(product_key, 1)
                product_name = ITEM_DEFINITIONS[product_key]["name"]
                self.add_message_to_chat_log(f"You smoke the meat into {product_name}.")
            else:
                # Refund meat if wood failed (shouldn't happen due to check, but safety)
                self.player.add_item(ingredient_key, 1)
                self.add_message_to_chat_log("Error: Failed to consume wood.")
        else:
             self.add_message_to_chat_log("Something went wrong with smoking.")

    def player_attempt_forge(self, x: int, y: int):
        """Handles the player's attempt to use an anvil."""
        target_tile = self.get_tile_at(x, y)
        interaction_hint = target_tile.properties.get("interaction_hint") if target_tile and hasattr(target_tile, "properties") else None
        if not (target_tile and interaction_hint == "forge"):
            self.add_message_to_chat_log("You need an anvil to forge.")
            return

        self.add_message_to_chat_log("You hammer away at the anvil, but lack a crafting blueprint.")

    def player_attempt_build(self, recipe_key: str, x: int, y: int):
        """Handles the player's attempt to build a structure or furniture."""
        if recipe_key not in CONSTRUCTION_RECIPES:
            self.add_message_to_chat_log("Unknown construction recipe.")
            return

        recipe = CONSTRUCTION_RECIPES[recipe_key]
        materials = recipe.get("materials", {})
        existing_blueprint = self.get_blueprint_at(x, y)
        if existing_blueprint:
            if existing_blueprint.target_build != recipe_key:
                self.add_message_to_chat_log("A different construction project is already here.")
                return
            if self.deposit_actor_material_into_blueprint(self.player, existing_blueprint):
                if existing_blueprint.has_all_materials():
                    self.add_message_to_chat_log(f"All materials are delivered for the {recipe['name']}; construction work can begin.")
                else:
                    self.add_message_to_chat_log(f"You add materials to the {recipe['name']} construction site.")
            elif existing_blueprint.has_all_materials():
                completed = existing_blueprint.apply_work(25)
                self._refresh_blueprint_map_marker(existing_blueprint)
                if completed:
                    self._complete_construction_blueprint(existing_blueprint)
                    self.add_message_to_chat_log(f"You finish building the {recipe['name']}.")
                else:
                    self.add_message_to_chat_log(f"You work on the {recipe['name']} ({existing_blueprint.construction_stage}).")
            else:
                self.add_message_to_chat_log(existing_blueprint.stalled_reason or "You do not have any of the required materials to deposit.")
            return

        # Validate location
        target_tile = self.get_tile_at(x, y)
        if not target_tile:
            return # Off map

        # Basic checks: prevent building on water or deep water unless it's a bridge (future)
        if target_tile.name in ["Water", "Deep Water"]:
             self.add_message_to_chat_log("You cannot build on water.")
             return

        # Check collision with entities (Player, NPCs, Animals)
        # We don't want to build a wall on top of someone
        for entity in [self.player] + self.npcs + self.village_npcs:
            if entity.x == x and entity.y == y:
                 self.add_message_to_chat_log("You cannot build here; someone is in the way.")
                 return

        # Prevent building on top of existing structures or blocking items if not allowed
        # For tiles (walls/floors), we generally replace the existing tile.
        # For decorations (furniture), we check if passability is required or if it overlaps.

        build_source = recipe.get("source", "decoration")
        tile_def_key = recipe.get("tile_def_key")

        if build_source == "tile":
            new_tile_def = TILE_DEFINITIONS.get(tile_def_key)
        elif build_source == "building":
            new_tile_def = {"name": recipe.get("name", recipe_key)}
        else:
            new_tile_def = DECORATION_ITEM_DEFINITIONS.get(tile_def_key)

        if not new_tile_def:
            self.add_message_to_chat_log("Error: Construction definition not found.")
            return

        blueprint = self.place_construction_blueprint(recipe_key, x, y)
        if blueprint is None:
            self.add_message_to_chat_log("Could not place a construction site here.")
            return

        remaining_items = ", ".join(
            f"{qty} {ITEM_DEFINITIONS.get(item_key, {}).get('name', item_key)}"
            for item_key, qty in blueprint.remaining_materials().items()
        )
        self.add_message_to_chat_log(f"You place a construction site for {recipe['name']}. Needed: {remaining_items}.")
