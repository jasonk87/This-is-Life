"""Brain and job behavior components for humanoid NPCs."""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from config import DAY_LENGTH_TICKS
from data.professions import get_profession_data


@dataclass
class NPCTaskState:
    task_target_item_details: dict | None = None
    current_sub_task: str | None = None
    sub_task_target_coords: tuple[int, int] | None = None
    sub_task_timer: int = 0
    task_timer: int = 0
    leisure_timer: int = 0
    sub_task_zone_target: str | None = None
    current_sub_task_sequence_index: int = 0
    task_target_entity_id: int | None = None
    task_target_coords: tuple[int, int] | None = None
    task_context: str | None = None
    task_context_data: dict | str | None = None
    woodcutter_search_radius: int = 15


class JobBehavior:
    """Base strategy for profession-specific work behavior."""

    profession_name: str = "Unemployed"

    def take_turn(self, entity, world) -> bool:
        return False

    def get_search_radius(self) -> int | None:
        return None

    def set_search_radius(self, value: int) -> None:
        return None


class IdleBehavior(JobBehavior):
    profession_name = "Unemployed"


class WanderBehavior(JobBehavior):
    profession_name = "Wander"


class StructuredWorkBehavior(JobBehavior):
    def __init__(self, profession_name: str):
        self.profession_name = profession_name

    def take_turn(self, entity, world) -> bool:
        return world._handle_npc_work_sub_tasks(entity)


class WoodcutterBehavior(StructuredWorkBehavior):
    def __init__(self):
        super().__init__("Woodcutter")
        self.state = SimpleNamespace(search_radius=15)

    def get_search_radius(self) -> int | None:
        return self.state.search_radius

    def set_search_radius(self, value: int) -> None:
        self.state.search_radius = value


class SleepBehavior(JobBehavior):
    profession_name = "Sleep"


class HaulingBehavior(JobBehavior):
    profession_name = "Hauling"

    FREE_TIME_TASKS = {"idle", "wandering", "at home", "idle_confused"}

    def take_turn(self, entity, world) -> bool:
        current_task = getattr(getattr(entity, "schedule", None), "current_task", "") or ""
        if current_task in {"hauling_to_source", "hauling_to_blueprint"}:
            if not hasattr(world, "_handle_npc_hauling_task"):
                return False
            return world._handle_npc_hauling_task(entity)

        is_unemployed = str(getattr(getattr(entity, "economic", None), "profession", "") or "").strip().lower() == "unemployed"
        if not is_unemployed and current_task not in self.FREE_TIME_TASKS:
            return False
        if getattr(getattr(entity, "schedule", None), "current_path", None):
            return False
        if not hasattr(world, "_assign_haul_task_to_npc"):
            return False
        return world._assign_haul_task_to_npc(entity)


def build_job_behavior(profession: str | None) -> JobBehavior:
    normalized = str(profession or "Unemployed").strip() or "Unemployed"
    if normalized == "Woodcutter":
        return WoodcutterBehavior()
    profession_data = get_profession_data(normalized)
    if profession_data and profession_data.get("sub_tasks"):
        return StructuredWorkBehavior(normalized)
    if normalized in {"Unemployed", "Child", "Creature"}:
        return IdleBehavior()
    return StructuredWorkBehavior(normalized)


class NPCBrain:
    """Owns schedule/task state and delegates to profession behaviors."""

    URGENT_HUNGER_THRESHOLD = 70
    DESPERATE_HUNGER_THRESHOLD = 90
    URGENT_THIRST_THRESHOLD = 70
    DESPERATE_THIRST_THRESHOLD = 85
    NON_INTERRUPTIBLE_TASKS = {
        "attacking_player",
        "moving_to_attack_player",
        "fleeing_from_player",
        "holding_position_combat",
        "combat_action_use_healing_item",
        "combat_action_move_to_cover",
        "investigating_sound",
        "going_to_report_crime",
        "seeking_healer",
        "waiting_for_treatment",
        "resting_in_bed",
        "treating_patient",
        "approaching_player_for_help",
    }

    def __init__(self, profession: str = "Unemployed", task_state: NPCTaskState | None = None):
        self.task_state = task_state or NPCTaskState()
        self.idle_behavior = IdleBehavior()
        self.wander_behavior = WanderBehavior()
        self.sleep_behavior = SleepBehavior()
        self.hauling_behavior = HaulingBehavior()
        self.work_behavior = build_job_behavior(profession)
        self.last_equipment_evaluation_day = -1

    def assign_profession(self, profession: str) -> None:
        current_radius = self.get_search_radius()
        self.work_behavior = build_job_behavior(profession)
        if current_radius is not None and self.get_search_radius() is not None:
            self.set_search_radius(current_radius)

    def get_search_radius(self) -> int | None:
        return self.work_behavior.get_search_radius()

    def set_search_radius(self, value: int) -> None:
        self.work_behavior.set_search_radius(value)

    def take_turn(self, entity, world) -> bool:
        self._evaluate_owned_gear(entity, world)
        if self._handle_survival_overrides(entity, world):
            return True
        if self.hauling_behavior.take_turn(entity, world):
            return True
        return world._run_humanoid_schedule_logic(entity)

    def _evaluate_owned_gear(self, entity, world) -> bool:
        if getattr(getattr(entity, "physical", None), "is_dead", False):
            return False
        current_day = getattr(world, "game_time", 0) // max(1, DAY_LENGTH_TICKS)
        if current_day == self.last_equipment_evaluation_day:
            return False
        self.last_equipment_evaluation_day = current_day
        if hasattr(entity, "evaluate_and_upgrade_equipment"):
            return bool(entity.evaluate_and_upgrade_equipment())
        return False

    def _handle_survival_overrides(self, entity, world) -> bool:
        if getattr(getattr(entity, "physical", None), "is_dead", False):
            return False
        if getattr(getattr(entity, "combat", None), "is_hostile_to_player", False):
            return False

        current_task = getattr(getattr(entity, "schedule", None), "current_task", "") or ""
        if current_task in self.NON_INTERRUPTIBLE_TASKS:
            return False

        thirst = getattr(getattr(entity, "physical", None), "thirst", 0)
        hunger = getattr(getattr(entity, "physical", None), "hunger", 0)

        if thirst >= self.URGENT_THIRST_THRESHOLD or current_task == "seeking_water":
            if world._handle_npc_survival_need(
                entity,
                need_type="thirst",
                urgent_threshold=self.URGENT_THIRST_THRESHOLD,
                desperate_threshold=self.DESPERATE_THIRST_THRESHOLD,
            ):
                return True

        if hunger >= self.URGENT_HUNGER_THRESHOLD or current_task == "seeking_food":
            if world._handle_npc_survival_need(
                entity,
                need_type="hunger",
                urgent_threshold=self.URGENT_HUNGER_THRESHOLD,
                desperate_threshold=self.DESPERATE_HUNGER_THRESHOLD,
            ):
                return True

        return False
