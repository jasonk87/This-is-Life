from simulation.systems.task_types import TaskType
"""
This module defines the base classes for all entities in the game world,
including NPCs and specialized creature types.
"""
import random
import re
from dataclasses import dataclass, field
from typing import Any
from config import DAY_LENGTH_TICKS, DEFAULT_SPEECH_VOLUME, DEFAULT_HEARING_RADIUS

# Judgment call (see CombatStats.hostility_grace_expires_tick / NPC.take_damage):
# how long incidental (non-deliberate) hostility lingers before it's eligible
# to decay in World._decay_incidental_npc_hostility. A few in-game hours -
# long enough that a genuinely ongoing scuffle doesn't get cut short by a
# lucky timing window, short enough that a villager who got hurt by illness
# or a stray hit doesn't stay a permanent enemy.
NPC_HOSTILITY_GRACE_TICKS = DAY_LENGTH_TICKS // 4
from data.dawnlike import ANIMAL_SPRITES, get_human_sprite
from data.items import ITEM_DEFINITIONS
from entities.anatomy import Anatomy
from entities.human_behaviors import NPCBrain, NPCTaskState
from entities.items import EquipmentSlot, Inventory, ItemReference, roll_crafted_item_quality
from entities.metabolism import MetabolismComponent
from entities.social import (
    AspirationComponent,
    AspirationType,
    GrudgeRecord,
    HistoryFactReactionState,
    KnowledgeComponent,
    LocalOpinionRecord,
    TravelComponent,
)
from simulation.activity import ensure_activity_state
from simulation.careers import CareerState, infer_career_level, normalize_profession, set_entity_profession
from simulation.skills import SkillTracker

PLACEHOLDER_FAMILY_NAME_RE = re.compile(r"^(Mother|Father|Brother|Sister)\s+Family_\d+$", re.IGNORECASE)

@dataclass
class CombatStats:
    """Stores combat-related attributes for an entity."""
    anatomy: Anatomy = field(default_factory=Anatomy.humanoid)
    toughness: str = "average"
    is_hostile_to_player: bool = False
    # Set only when is_hostile_to_player is flipped True by take_damage's
    # generic, attacker-agnostic fallback (below) - the least purpose-built
    # of the game's hostility triggers, as opposed to raider logic, the
    # wanted-NPC pursuit system, Sheriff/Guard bounty response, or
    # wolf-desperation attacks, which all set is_hostile_to_player directly
    # at their own call sites for a deliberate narrative reason and leave
    # this field untouched. See World._decay_incidental_npc_hostility in
    # engine.py, which is the only thing that reads it.
    hostility_grace_expires_tick: int | None = None
    combat_behavior: str = "defensive"
    base_attack_name: str = "fists"
    base_attack_damage_dice: str = "1d3"
    attack_range: int = 1
    target_entity_id: int | None = None
    last_hit_part: str | None = None
    defense_bonus: int = 0

    @property
    def body_parts_hp(self):
        return self.anatomy.hp_proxy

    @property
    def body_parts_max_hp(self):
        return self.anatomy.max_hp_proxy

    @property
    def max_hp(self):
        return self.anatomy.get_total_max_hp()

    @max_hp.setter
    def max_hp(self, value):
        self.anatomy.scale_total_max_hp(value)

    @property
    def hp(self):
        return self.anatomy.get_total_hp()

    @hp.setter
    def hp(self, value):
        self.anatomy.set_total_hp(value)

@dataclass
class PhysicalState:
    """Stores physical attributes and states for an entity."""
    metabolism: MetabolismComponent = field(default_factory=MetabolismComponent)
    status_effects: list[str] = field(default_factory=list)
    is_dead: bool = False
    hunger_level_msg: str = ""
    thirst_level_msg: str = ""
    sickness_level_msg: str = ""
    is_wet: bool = False
    wetness_timer: int = 0
    is_sheltered: bool = False
    hearing_radius: int = DEFAULT_HEARING_RADIUS

    @property
    def hunger(self) -> int:
        return self.metabolism.hunger

    @hunger.setter
    def hunger(self, value: int) -> None:
        self.metabolism.hunger = value

    @property
    def max_hunger(self) -> int:
        return self.metabolism.max_hunger

    @max_hunger.setter
    def max_hunger(self, value: int) -> None:
        self.metabolism.max_hunger = value

    @property
    def thirst(self) -> int:
        return self.metabolism.thirst

    @thirst.setter
    def thirst(self, value: int) -> None:
        self.metabolism.thirst = value

    @property
    def max_thirst(self) -> int:
        return self.metabolism.max_thirst

    @max_thirst.setter
    def max_thirst(self, value: int) -> None:
        self.metabolism.max_thirst = value

    @property
    def sickness(self) -> int:
        return self.metabolism.sickness

    @sickness.setter
    def sickness(self, value: int) -> None:
        self.metabolism.sickness = value

    @property
    def max_sickness(self) -> int:
        return self.metabolism.max_sickness

    @max_sickness.setter
    def max_sickness(self, value: int) -> None:
        self.metabolism.max_sickness = value

    @property
    def temperature(self) -> float:
        return self.metabolism.temperature

    @temperature.setter
    def temperature(self, value: float) -> None:
        self.metabolism.temperature = value

    @property
    def base_temperature_resistance(self) -> float:
        return self.metabolism.base_temperature_resistance

    @base_temperature_resistance.setter
    def base_temperature_resistance(self, value: float) -> None:
        self.metabolism.base_temperature_resistance = value

    @property
    def clothing_insulation(self) -> float:
        return self.metabolism.clothing_insulation

    @clothing_insulation.setter
    def clothing_insulation(self, value: float) -> None:
        self.metabolism.clothing_insulation = value

    def process_tick(self, **kwargs) -> None:
        self.metabolism.process_tick(status_effects=self.status_effects, **kwargs)

@dataclass
class SocialState:
    """Stores social and reputational attributes for an entity."""
    personality: str = "normal"
    is_town_crier: bool = False
    family_ties: dict = field(default_factory=lambda: {"description": "none"})
    relationships: dict = field(default_factory=dict)
    grudges: dict[int, GrudgeRecord] = field(default_factory=dict)
    local_opinions: dict[int, LocalOpinionRecord] = field(default_factory=dict)
    recent_social_reactions: list[dict[str, Any]] = field(default_factory=list)
    opinion_modifiers: dict[int, float] = field(default_factory=dict)
    reacted_history_fact_ids: set[str] = field(default_factory=set)
    reacted_history_fact_state: dict[str, HistoryFactReactionState] = field(default_factory=dict)
    reputation: dict[str, int] = field(default_factory=dict)
    shared_experience_ticks: dict[int, int] = field(default_factory=dict)
    follow_target_id: int | None = None
    follow_role: str | None = None
    social_skill: int = 5
    fame: int = 0
    infamy: int = 0
    title: str = ""

@dataclass
class EconomicState:
    """Stores economic attributes for an entity."""
    wealth_level: str = "average"
    money: int = 0
    npc_inventory: Inventory = field(default_factory=Inventory)
    profession: str = "unemployed"
    job_satisfaction: int = 50
    days_unemployed: int = 0
    work_performance: int = 50 # 0-100, tracks recent job performance
    daily_wage: int = 0
    active_contracts: dict = field(default_factory=dict)
    pending_contract_offer: Any | None = None
    bounty: int = 0
    job_building_id: str | None = None
    days_employed: int = 0

    def __setattr__(self, name, value):
        if name == "npc_inventory" and not isinstance(value, Inventory):
            value = Inventory(value or {})
        super().__setattr__(name, value)

    @property
    def inventory(self) -> Inventory:
        return self.npc_inventory

    @inventory.setter
    def inventory(self, value) -> None:
        self.npc_inventory = value

    @property
    def job_performance(self) -> int:
        return self.work_performance

    @job_performance.setter
    def job_performance(self, value: int) -> None:
        self.work_performance = int(value)

@dataclass
class Schedule:
    """Stores scheduling and task-related attributes for an entity."""
    home_building_id: int | None = None
    work_building_id: int | None = None
    current_destination_coords: tuple[int, int] | None = None
    current_path: list = field(default_factory=list)
    path_blocked_turns: int = 0
    last_blocked_position: tuple[int, int] | None = None
    current_task: str = TaskType.IDLE
    previous_task: str = TaskType.IDLE
    game_time_last_updated: int = 0
    last_paid_day: int = 0
    # NPC jail state (mirrors PlayerState.is_jailed/jail_cell_coords/
    # jail_time_remaining, but lives on Schedule since NPCs have no
    # PlayerState). See World._serve_npc_jail_time in engine.py.
    is_jailed: bool = False
    jail_cell_coords: tuple[int, int] | None = None
    jail_time_remaining: int = 0

@dataclass
class Equipment:
    """Stores entity equipment."""
    weapon: EquipmentSlot = field(default_factory=EquipmentSlot)
    body: EquipmentSlot = field(default_factory=EquipmentSlot)
    head: EquipmentSlot = field(default_factory=EquipmentSlot)
    equipped_armor: dict[str, str | None] = field(default_factory=lambda: {"head": None, "body": None, "hands": None, "feet": None})
    equipped_light_item_key: str | None = None
    light_source_active_until_tick: int = -1
    current_personal_light_radius: int = 0

    def __setattr__(self, name, value):
        if name in {"weapon", "body", "head"} and not isinstance(value, EquipmentSlot):
            value = EquipmentSlot(value)
        super().__setattr__(name, value)

Knowledge = KnowledgeComponent

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
        self.original_color_before_sleep = self.color
        self.speech_volume: int = DEFAULT_SPEECH_VOLUME
        self.hearing_radius: int = DEFAULT_HEARING_RADIUS
        self.is_sleeping = False
        self.render_disabled = False
        self.macro_x = x
        self.macro_y = y
        self._sleeping_ai_brain = None
        self._sleeping_render_state: dict = {}

        # Conversation state
        self.conversation_partner_id: int | None = None
        self.current_conversation: list[str] = []
        self.conversation_cooldown: int = 0
        self.last_conversation_time: int = 0

        self.combat, self.physical, self.social = CombatStats(), PhysicalState(), SocialState()
        self.economic, self.schedule = EconomicState(), Schedule()
        self.equipment, self.knowledge = Equipment(), Knowledge()
        self.career = CareerState()
        self.skills = SkillTracker()
        self.aspiration = AspirationComponent(aspiration_type=random.choice(list(AspirationType)))
        self.travel = TravelComponent()
        ensure_activity_state(self)

        self.social.personality = personality
        if isinstance(family_ties, str):
            self.social.family_ties = {"description": family_ties}
        else:
            self.social.family_ties = family_ties
        self.economic.wealth_level = wealth_level

        if self.player_id:
            self._initialize_relationships(attitude_to_player, self.player_id)

        self.ai_brain = NPCBrain(profession=self.economic.profession, task_state=NPCTaskState())
        self.work_tags: set[str] = {"woodcutting", "hauling", "construction", "crafting"}
        self.skill_levels: dict[str, int] = {"woodcutting": 1, "hauling": 1, "construction": 1, "crafting": 1}
        self.preferred_work_types: list[str] = []
        self.fatigue_modifier: float = 0.0
        self.recent_task_history: list[str] = []
        self.current_work_focus: str | None = None
        self.work_efficiency_modifiers: dict[str, float] = {"woodcutting": 1.0, "hauling": 1.0, "construction": 1.0, "crafting": 1.0}
        self.skill_experience_by_tag: dict[str, float] = {"woodcutting": 0.0, "hauling": 0.0, "construction": 0.0, "crafting": 0.0}
        self.last_skill_gain_tick: int = 0
        self.specialization_pressure: dict[str, float] = {"woodcutting": 0.0, "hauling": 0.0, "construction": 0.0, "crafting": 0.0}
        self.recent_skill_usage: list[str] = []
        self.actor_work_profile: dict[str, object] = {
            "dominant_work_tag": "hauling",
            "recent_work_summary": "No strong labor trend yet.",
            "specialization_summary": "General labor profile.",
            "fatigue_state": "rested",
            "work_identity_label": "General Laborer",
            "work_history_snapshot": [],
            "preferred_task_bias": [],
            "lifetime_work_totals": {"woodcutting": 0, "hauling": 0, "construction": 0, "crafting": 0},
        }
        self.cold_exposure: float = 0.0
        self.warmth_state: str = "neutral"
        self.last_warmed_tick: int = 0
        self.last_cold_tick: int = 0
        self.exposure_fatigue_modifier: float = 0.0
        self.sheltered_state: bool = False
        self.last_sheltered_tick: int = 0
        self.current_shelter_id: str | None = None
        self.shelter_exposure_modifier: float = 1.0
        self.survival_override_reason: str | None = None
        self.survival_override_active: bool = False
        self.survival_override_started_tick: int = 0
        self.survival_override_target_id: str | None = None
        self.survival_override_target_position: tuple[int, int] | None = None
        self.survival_override_recovery_threshold: float = 0.7
        self.survival_override_previous_task_id: str | None = None
        self.survival_override_cooldown_until_tick: int = 0
        self.resting_state: bool = False
        self.resting_since_tick: int = 0
        self.current_rest_target_id: str | None = None
        self.fatigue_recovery_modifier: float = 1.0
        self.active_survival_pressure: str | None = None
        self.deferred_survival_pressures: list[str] = []
        self.survival_pressure_scores: dict[str, float] = {}
        self.survival_pressure_records: dict[str, dict] = {}
        self.last_survival_override_switch_tick: int = 0
        self.hunger: float = 0.0
        self.hunger_rate_per_tick: float = 0.01
        self.hunger_override_threshold: float = 0.7
        self.hunger_recovery_threshold: float = 0.3
        self.hunger_last_eat_tick: int = 0
        self.hunger_target_food_id: str | None = None
        self.hunger_nutrition_pending: float = 0.0
        self.den_location: tuple[int, int] | None = None
        self.desire_for_furniture, self.is_frightened = 0, False
        self.threat_source_ids: list[str] = []
        self.defense_bonus = 0
        self.debug_autonomy: dict = {}
        set_entity_profession(self, self.economic.profession, reason="spawn")

    def _task_state_holder(self):
        ai_brain = getattr(self, "ai_brain", None)
        if ai_brain is None:
            self.ai_brain = NPCBrain(profession=self.economic.profession, task_state=NPCTaskState())
            return self.ai_brain.task_state
        if getattr(ai_brain, "task_state", None) is None:
            ai_brain.task_state = NPCTaskState()
        return ai_brain.task_state

    @property
    def task_target_item_details(self):
        return self._task_state_holder().task_target_item_details

    @task_target_item_details.setter
    def task_target_item_details(self, value):
        self._task_state_holder().task_target_item_details = value

    @property
    def current_sub_task(self):
        return self._task_state_holder().current_sub_task

    @current_sub_task.setter
    def current_sub_task(self, value):
        self._task_state_holder().current_sub_task = value

    @property
    def sub_task_target_coords(self):
        return self._task_state_holder().sub_task_target_coords

    @sub_task_target_coords.setter
    def sub_task_target_coords(self, value):
        self._task_state_holder().sub_task_target_coords = value

    @property
    def sub_task_timer(self):
        return self._task_state_holder().sub_task_timer

    @sub_task_timer.setter
    def sub_task_timer(self, value):
        self._task_state_holder().sub_task_timer = value

    @property
    def task_timer(self):
        return self._task_state_holder().task_timer

    @task_timer.setter
    def task_timer(self, value):
        self._task_state_holder().task_timer = value

    @property
    def leisure_timer(self):
        return self._task_state_holder().leisure_timer

    @leisure_timer.setter
    def leisure_timer(self, value):
        self._task_state_holder().leisure_timer = value

    @property
    def sub_task_zone_target(self):
        return self._task_state_holder().sub_task_zone_target

    @sub_task_zone_target.setter
    def sub_task_zone_target(self, value):
        self._task_state_holder().sub_task_zone_target = value

    @property
    def current_sub_task_sequence_index(self):
        return self._task_state_holder().current_sub_task_sequence_index

    @current_sub_task_sequence_index.setter
    def current_sub_task_sequence_index(self, value):
        self._task_state_holder().current_sub_task_sequence_index = value

    @property
    def woodcutter_search_radius(self):
        ai_brain = getattr(self, "ai_brain", None)
        if ai_brain and hasattr(ai_brain, "get_search_radius") and ai_brain.get_search_radius() is not None:
            return ai_brain.get_search_radius()
        return self._task_state_holder().woodcutter_search_radius

    @woodcutter_search_radius.setter
    def woodcutter_search_radius(self, value):
        ai_brain = getattr(self, "ai_brain", None)
        if ai_brain and hasattr(ai_brain, "get_search_radius") and ai_brain.get_search_radius() is not None:
            ai_brain.set_search_radius(value)
        self._task_state_holder().woodcutter_search_radius = value

    @property
    def task_target_entity_id(self):
        return self._task_state_holder().task_target_entity_id

    @task_target_entity_id.setter
    def task_target_entity_id(self, value):
        self._task_state_holder().task_target_entity_id = value

    @property
    def task_target_coords(self):
        return self._task_state_holder().task_target_coords

    @task_target_coords.setter
    def task_target_coords(self, value):
        self._task_state_holder().task_target_coords = value

    @property
    def task_context(self):
        return self._task_state_holder().task_context

    @task_context.setter
    def task_context(self, value):
        self._task_state_holder().task_context = value

    @property
    def task_context_data(self):
        return self._task_state_holder().task_context_data

    @task_context_data.setter
    def task_context_data(self, value):
        self._task_state_holder().task_context_data = value

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

    def add_grudge(
        self,
        target_id: int,
        reason: str,
        *,
        severity: int = 35,
        current_day: int = 0,
        decay_days: int = 5,
        persistent: bool = False,
    ):
        """
        Adds a grudge against a target entity, significantly lowering the relationship score.
        """
        existing = self.social.grudges.get(target_id)
        bounded_severity = max(1, min(100, int(severity)))
        if existing and isinstance(existing, GrudgeRecord):
            existing.reason = reason or existing.reason
            existing.severity = max(existing.severity, bounded_severity)
            existing.last_updated_day = current_day
            existing.decay_days = decay_days
            existing.persistent = existing.persistent or persistent
        else:
            self.social.grudges[target_id] = GrudgeRecord(
                target_id=target_id,
                reason=reason,
                severity=bounded_severity,
                created_day=current_day,
                last_updated_day=current_day,
                decay_days=decay_days,
                persistent=persistent,
            )
        self.social.relationships[target_id] = self.social.relationships.get(target_id, 50) - 40
        self.social.relationships[target_id] = max(0, self.social.relationships[target_id])

    def decay_grudges(self, current_day: int) -> None:
        """Decay non-persistent grudges over time and clear expired entries."""
        to_remove: list[int] = []
        for target_id, record in list(self.social.grudges.items()):
            if not isinstance(record, GrudgeRecord):
                continue
            if record.persistent:
                continue
            days_passed = max(0, current_day - record.last_updated_day)
            if days_passed <= 0:
                continue
            record.severity = max(0, record.severity - days_passed)
            record.last_updated_day = current_day
            if record.severity <= 0 or (current_day - record.created_day) >= record.decay_days:
                to_remove.append(target_id)
        for target_id in to_remove:
            self.social.grudges.pop(target_id, None)

    def get_grudge_severity_towards(self, target_id: int | None) -> int:
        """Return normalized grudge severity toward a target."""
        if target_id is None:
            return 0
        entry = self.social.grudges.get(target_id)
        if isinstance(entry, GrudgeRecord):
            return max(0, min(100, int(entry.severity)))
        if isinstance(entry, list):
            return min(100, 20 * len(entry))
        return 0

    def get_distrust_towards(self, target) -> int:
        """Compute a simple distrust score from relationship and grudge state."""
        target_id = getattr(target, "id", None)
        relationship_score = self.social.relationships.get(target_id, 50)
        relationship_distrust = max(0, 50 - relationship_score)
        grudge_distrust = self.get_grudge_severity_towards(target_id)
        return max(relationship_distrust, grudge_distrust)

    def set_local_opinion(self, target_id: int, score: float, *, current_day: int, evidence_count: int) -> None:
        self.social.local_opinions[target_id] = LocalOpinionRecord(
            target_id=target_id,
            score=max(-100.0, min(100.0, float(score))),
            evidence_count=max(0, int(evidence_count)),
            last_updated_day=max(0, int(current_day)),
        )

    def get_local_opinion_towards(self, target) -> float:
        target_id = getattr(target, "id", None)
        if target_id is None:
            return 0.0
        record = self.social.local_opinions.get(target_id)
        if isinstance(record, LocalOpinionRecord):
            return float(record.score)
        return 0.0

    def clear_work_sub_task_state(self, *, reset_sequence: bool = False) -> None:
        """Reset structured sub-task progression state owned by ai_brain.task_state."""
        self.current_sub_task = None
        self.sub_task_target_coords = None
        self.sub_task_zone_target = None
        self.sub_task_timer = 0
        if reset_sequence:
            self.current_sub_task_sequence_index = 0

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
        relationship_base_name = base_name

        title_label = self.get_title_label()
        if title_label:
            base_name = f"{base_name} ({title_label})"

        if include_relationship and relation_label and relationship_base_name != relation_label:
            return f"{base_name} [{relation_label}]"
        return base_name

    def recalculate_stats(self):
        """Recalculates NPC stats based on equipped items."""
        self.physical.clothing_insulation = 0.0
        self.defense_bonus = 0
        for slot_name in ("body", "head"):
            item = self.get_equipped_item_reference(slot_name)
            if item is None:
                continue
            item_def = item.definition
            if item_def and "properties" in item_def:
                self.physical.clothing_insulation += item_def["properties"].get("insulation", 0.0)
                self.defense_bonus += item_def["properties"].get("defense_bonus", 0)

    def get_equipped_item_reference(self, slot_name: str) -> ItemReference | None:
        slot = getattr(self.equipment, slot_name, None)
        if slot is None or not slot:
            return None
        if getattr(slot, "item_reference", None) is not None:
            return slot.item_reference
        item_key = str(slot)
        if not item_key:
            return None
        return self.economic.npc_inventory.get_item_reference(item_key) or ItemReference(item_key)

    def is_identity_concealed(self) -> bool:
        head_item = self.get_equipped_item_reference("head")
        return bool(head_item and head_item.conceals_identity)

    def unequip_item(self, slot_name: str, *, return_to_inventory: bool = True) -> ItemReference | None:
        slot = getattr(self.equipment, slot_name, None)
        if slot is None or not slot:
            return None
        item = slot.item_reference
        if return_to_inventory and item is not None and not self.economic.npc_inventory.has_item_reference(item):
            self.economic.npc_inventory.add_item_reference(item)
        slot.clear()
        self.recalculate_stats()
        return item

    def equip_item_reference(self, slot_name: str, item: ItemReference | None) -> bool:
        if item is None:
            return False
        expected_slot = {"weapon": "main_hand", "body": "body", "head": "head"}.get(slot_name)
        if expected_slot is None or item.equip_slot != expected_slot:
            return False

        slot = getattr(self.equipment, slot_name, None)
        current_item = self.get_equipped_item_reference(slot_name)
        if current_item is item and getattr(slot, "item_reference", None) is item:
            return True

        if self.economic.npc_inventory.has_item_reference(item):
            self.economic.npc_inventory.extract_item_reference(item)
        elif current_item is not item:
            return False

        self.unequip_item(slot_name)
        slot.bind(item)
        self.recalculate_stats()
        return True

    def evaluate_and_upgrade_equipment(self, *, minimum_upgrade_margin: float = 0.5) -> bool:
        slot_candidates = {
            "weapon": [],
            "body": [],
            "head": [],
        }
        expected_slots = {"weapon": "main_hand", "body": "body", "head": "head"}
        for item in self.economic.npc_inventory.iter_item_references():
            for slot_name, equip_slot in expected_slots.items():
                if item.equip_slot == equip_slot:
                    slot_candidates[slot_name].append(item)
                    break

        upgraded = False
        for slot_name, candidates in slot_candidates.items():
            current_item = self.get_equipped_item_reference(slot_name)
            current_score = current_item.evaluate_utility() if current_item else 0.0
            best_item = max(candidates, key=lambda candidate: candidate.evaluate_utility(), default=None)
            if best_item is None:
                continue
            best_score = best_item.evaluate_utility()
            required_margin = 0.0 if current_item is None else max(minimum_upgrade_margin, current_score * 0.1)
            if best_score <= current_score + required_margin:
                continue
            if self.equip_item_reference(slot_name, best_item):
                upgraded = True
        return upgraded

    def add_item(self, item_key: str, quantity: int = 1, *, quality: str = "Normal", crafter_name: str | None = None):
        """Adds an item to the NPC's inventory."""
        self.economic.npc_inventory.add_item(item_key, quantity, quality=quality, crafter_name=crafter_name)

    def craft_item(self, item_key: str, quantity: int = 1):
        """Add an authored crafted item to the NPC inventory with rolled quality."""
        normalized_profession = normalize_profession(self.economic.profession)
        if hasattr(self, "career") and self.career.current_role != normalized_profession:
            self.career.set_role(normalized_profession)
        career_level = max(
            getattr(getattr(self, "career", None), "level", 0),
            infer_career_level(normalized_profession),
            self.skills.get_level("crafting"),
        )
        quality = roll_crafted_item_quality(career_level=career_level, work_performance=self.economic.work_performance)
        self.add_item(item_key, quantity, quality=quality, crafter_name=self.name)
        self.evaluate_and_upgrade_equipment()
        self.skills.gain_experience("crafting", max(1, int(quantity)) * 4)
        return quality

    def has_item(self, item_key: str, quantity: int = 1) -> bool:
        """Checks if the NPC has a sufficient quantity of an item."""
        return self.economic.npc_inventory.has_item(item_key, quantity)

    def remove_item(self, item_key_to_remove: str, quantity: int = 1) -> bool:
        """Removes an item from the NPC's inventory. Returns True if successful."""
        return self.economic.npc_inventory.remove_item(item_key_to_remove, quantity)

    def degrade_equipped_item(self, slot_name: str, amount: int = 1, world=None):
        """Degrade an equipped item and clear the slot if it breaks."""
        slot = getattr(self.equipment, slot_name, None)
        item = self.get_equipped_item_reference(slot_name)
        if item is None:
            return {"degraded": False, "broke": False, "item_key": None, "replacement_key": None}

        inventory = self.economic.npc_inventory
        if inventory.has_item_reference(item):
            result = inventory.degrade_item_reference(item, amount)
        else:
            broke = item.degrade(amount)
            result = {
                "degraded": True,
                "broke": broke,
                "item_key": item.key,
                "replacement_key": None,
                "current_durability": item.current_durability,
            }
            if broke:
                result["item_name"] = item.name
                if item.tool_type and "broken_tool_handle" in ITEM_DEFINITIONS:
                    inventory.add_item("broken_tool_handle", 1)
                    result["replacement_key"] = "broken_tool_handle"
        if result.get("broke") and getattr(self.equipment, slot_name) == item.key:
            self.unequip_item(slot_name, return_to_inventory=False)
            if world:
                item_name = result.get("item_name", item.key.replace("_", " ").title())
                if result.get("replacement_key"):
                    replacement_name = ITEM_DEFINITIONS[result["replacement_key"]]["name"]
                    world.add_message_to_chat_log(f"{self.name}'s {item_name} broke into {replacement_name}!")
                else:
                    world.add_message_to_chat_log(f"{self.name}'s {item_name} broke!")
        return result

    def take_damage(self, amount: int, world, *, apply_hostility: bool = True) -> bool:
        """
        Applies damage to the NPC, accounting for armor, and handles death.
        Returns True if the NPC was killed, False otherwise.

        apply_hostility: whether a non-lethal hit is allowed to flip
        is_hostile_to_player True via the fallback below. Defaults True to
        preserve existing combat behavior (player-vs-NPC and NPC-vs-NPC
        melee both still go through this path unchanged). Status-effect/
        environmental damage that isn't really "combat" at all - illness's
        untreated-worsening tick (simulation/systems/illness.py) and
        Freezing/Overheating (simulation/systems/survival.py) - now passes
        apply_hostility=False, since a villager taking incidental illness
        or weather damage becoming permanently hostile to a player who was
        nowhere near them was a real bug, not intended behavior. Checked
        starvation too: NPC hunger/thirst never calls take_damage at all
        today (only the player's own starvation does, via the separate
        Player.take_damage, which has no hostility flag to begin with), so
        there's nothing to change there.
        """
        if self.physical.is_dead:
            return False

        total_defense_bonus = 0
        body_blocks_damage = False
        head_blocks_damage = False
        if self.equipment.body and self.equipment.body in ITEM_DEFINITIONS:
            armor_def = ITEM_DEFINITIONS[self.equipment.body]
            body_defense = armor_def.get("properties", {}).get("defense_bonus", 0)
            total_defense_bonus += body_defense
            body_blocks_damage = body_defense > 0
        if self.equipment.head and self.equipment.head in ITEM_DEFINITIONS:
            armor_def = ITEM_DEFINITIONS[self.equipment.head]
            head_defense = armor_def.get("properties", {}).get("defense_bonus", 0)
            total_defense_bonus += head_defense
            head_blocks_damage = head_defense > 0

        effective_damage = max(0, amount - total_defense_bonus)
        blocked_damage = max(0, amount - effective_damage)

        if blocked_damage > 0:
            if body_blocks_damage:
                self.degrade_equipped_item("body", amount=1, world=world)
            if head_blocks_damage:
                self.degrade_equipped_item("head", amount=1, world=world)

        remaining_damage = effective_damage
        import random
        if remaining_damage > 0:
            hit_part = random.choice(list(self.combat.body_parts_hp.keys()))
            self.combat.last_hit_part = hit_part
            self.combat.anatomy.apply_damage(hit_part, remaining_damage)

            for leg_name in ["left_leg", "right_leg"]:
                if self.combat.anatomy.get_part(leg_name).hp <= 0:
                    self.combat.anatomy.get_part(leg_name).ensure_status("broken")

            if self.combat.body_parts_hp.get("left_leg", 1) <= 0 or self.combat.body_parts_hp.get("right_leg", 1) <= 0:
                if "broken_leg" not in self.physical.status_effects:
                    self.physical.status_effects.append("broken_leg")
                    if world:
                        world.add_message_to_chat_log(f"{self.name}'s leg is broken!")

        # Add visual effect if world is passed
        if world:
            from engine import FloatingTextEffect, HitFlashEffect
            world.visual_effects.append(FloatingTextEffect(self.x, self.y, str(effective_damage), color=(255, 50, 50)))
            world.visual_effects.append(HitFlashEffect(self.x, self.y))

        if self.combat.hp <= 0:
            self.combat.hp = 0
            self.physical.is_dead = True
            return True
        if apply_hostility and not self.combat.is_hostile_to_player and self.economic.profession != "Creature":
            self.combat.is_hostile_to_player = True
            # This fallback is attacker-agnostic (it doesn't know or care who
            # actually dealt the damage - could be the player, could be
            # another NPC), which makes it the bluntest, least deliberate
            # hostility trigger in the game, unlike raider logic/wanted-NPC
            # pursuit/Sheriff-Guard bounty response/wolf-desperation attacks,
            # which all set is_hostile_to_player directly for a specific,
            # deliberate reason and are meant to persist. Give this one a
            # grace window instead, so a villager who got tagged as hostile
            # from an isolated hit doesn't stay locked into combat AI against
            # a player who's since moved on (or was never actually involved -
            # see the apply_hostility=False callers above). World's tick loop
            # (_decay_incidental_npc_hostility in engine.py) clears it once
            # the grace period passes and the NPC isn't still near/seeing
            # the player.
            if world is not None:
                self.combat.hostility_grace_expires_tick = getattr(world, "game_time", 0) + NPC_HOSTILITY_GRACE_TICKS
                world.add_message_to_chat_log(f"{self.name} becomes hostile!")
        return False

class DireWolf(NPC):
    """Compatibility shim that now delegates construction to the data-driven Animal entity."""

    def __init__(self, x, y, name="Dire Wolf"):
        from data.animals import ANIMAL_DEFINITIONS
        from entities.animal import Animal

        animal = Animal(x, y, name=name, animal_type="dire_wolf", animal_definition=ANIMAL_DEFINITIONS.get("dire_wolf", {}))
        self.__dict__ = animal.__dict__
