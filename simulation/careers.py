from __future__ import annotations

from dataclasses import dataclass, field

from entities.pickle_compat import dataclass_setstate


UNEMPLOYED_PROFESSIONS = {"Unemployed", "unemployed", ""}
CREATURE_PROFESSIONS = {"Creature"}

PROFESSION_TRACKS = {
    "Sheriff": "law",
    "Deputy": "law",
    "Guard": "law",
    "Militia": "law",
    "Town Official": "civic",
    "Merchant": "trade",
    "Traveling Merchant": "trade",
    "Farmer": "agriculture",
    "Miller": "agriculture",
    "Baker": "agriculture",
    "Fisherman": "food",
    "Hunter": "food",
    "Butcher": "food",
    "Healer": "care",
    "Blacksmith": "craft",
    "Carpenter": "craft",
    "Woodcutter": "craft",
    "Lumber Mill Foreman": "craft",
    "Miner": "craft",
    "Scribe": "scholarship",
    "Tavern Keeper": "hospitality",
    "Unemployed": "commoner",
    "Child": "youth",
    "Creature": "creature",
    "Raider": "outlaw",
    "Cultist": "cult",
}

PROFESSION_CAPABILITIES = {
    "Merchant": {"trade", "commerce"},
    "Traveling Merchant": {"trade", "commerce", "travel"},
    "Miller": {"trade", "craft"},
    "Scribe": {"trade", "scholarship"},
    "Sheriff": {"law", "quest_authority", "mercenary_authority"},
    "Deputy": {"law"},
    "Guard": {"law", "mercenary_authority"},
    "Militia": {"law"},
    "Town Official": {"civic", "authority"},
    "Lumber Mill Foreman": {"management", "job_offers"},
    "Healer": {"medical"},
    "Blacksmith": {"repair"},
}

BUILDING_ROLE_RULES = {
    "sheriff_office": ("Sheriff", "Deputy"),
    "lumber_mill": ("Lumber Mill Foreman", "Woodcutter"),
    "general_store": ("Merchant", "Merchant"),
    "tavern": ("Tavern Keeper", "Tavern Keeper"),
    "farm": ("Farmer", "Farmer"),
    "mine": ("Miner", "Miner"),
    "carpenter_shop": ("Carpenter", "Carpenter"),
    "mill": ("Miller", "Miller"),
    "bakery": ("Baker", "Baker"),
    "fishing_hut": ("Fisherman", "Fisherman"),
    "butcher_shop": ("Butcher", "Hunter"),
    "hunting_lodge": ("Hunter", "Hunter"),
    "hunter_lodge": ("Hunter", "Hunter"),
    "library": ("Scribe", "Scribe"),
    "capital_hall": ("Town Official", "Town Official"),
    "jail": ("Guard", "Guard"),
    "blacksmith_shop": ("Blacksmith", "Blacksmith"),
    "clinic": ("Healer", "Healer"),
}


# Age thresholds for gradual work-performance decline (ideation-audit item
# 3: previously age affected nothing but the old-age death roll (age > 70,
# see engine.py's _simulate_village_population_lifecycle) and the
# child/adult sprite split - zero productivity effect at all). Chosen to
# be gradual, not a cliff: decline starts well before the old-age
# mortality threshold so it reads as "slowing down over a couple of
# decades" rather than a sudden late-life drop. The floor
# (WORK_PERFORMANCE_AGE_FLOOR) is deliberately kept above every
# consequential work_performance threshold elsewhere in engine.py
# (<=20 skips that day's pay, <20 has a 10% daily firing chance - see
# _pay_daily_company_wages/_update_npc_careers) so aging alone can never
# talk an elderly NPC out of a paycheck or into losing their job on its
# own - this dampens the ceiling on how good elderly workers can get, not
# a backdoor forced-retirement mechanic.
WORK_PERFORMANCE_AGE_DECLINE_START = 55
WORK_PERFORMANCE_AGE_DECLINE_END = 80
WORK_PERFORMANCE_AGE_FLOOR = 60


def get_age_work_performance_ceiling(age: int | None) -> int:
    """Returns the highest work_performance an NPC of this age can reach.

    100 at or below WORK_PERFORMANCE_AGE_DECLINE_START, linearly declining
    to WORK_PERFORMANCE_AGE_FLOOR by WORK_PERFORMANCE_AGE_DECLINE_END, held
    at the floor beyond that. `age=None` (e.g. the player, who has no age
    field at all in this codebase) is treated as unaffected.

    This only caps work_performance *increases* - it's applied at the
    handful of call sites that raise the value (see
    simulation/systems/work.py), never used to actively lower an
    already-set value on its own. An NPC who was already above their new,
    lower ceiling simply can't climb any higher until the normal
    idle-at-work decay (-1/tick, see work.py) brings them back down to it -
    a real, gradual decline driven by ordinary daily ticks rather than an
    instant markdown the moment they cross an age threshold.
    """
    if age is None or age <= WORK_PERFORMANCE_AGE_DECLINE_START:
        return 100
    if age >= WORK_PERFORMANCE_AGE_DECLINE_END:
        return WORK_PERFORMANCE_AGE_FLOOR
    span_years = WORK_PERFORMANCE_AGE_DECLINE_END - WORK_PERFORMANCE_AGE_DECLINE_START
    span_points = 100 - WORK_PERFORMANCE_AGE_FLOOR
    progress = (age - WORK_PERFORMANCE_AGE_DECLINE_START) / span_years
    return round(100 - progress * span_points)


@dataclass
class CareerHistoryEntry:
    role: str
    reason: str = ""
    game_time: int | None = None

    def __setstate__(self, state):
        dataclass_setstate(self, state)


@dataclass
class CareerState:
    current_role: str = "Unemployed"
    track: str = "commoner"
    level: int = 0
    tenure_days: int = 0
    history: list[CareerHistoryEntry] = field(default_factory=list)

    def __setstate__(self, state):
        dataclass_setstate(self, state)

    def set_role(self, role: str, reason: str = "", game_time: int | None = None):
        normalized = normalize_profession(role)
        if normalized == self.current_role:
            return
        self.current_role = normalized
        self.track = infer_career_track(normalized)
        self.level = infer_career_level(normalized)
        self.tenure_days = 0
        self.history.append(CareerHistoryEntry(role=normalized, reason=reason, game_time=game_time))

    def advance_day(self):
        self.tenure_days += 1

    def is_unemployed(self) -> bool:
        return is_unemployed_profession(self.current_role)

    def is_creature(self) -> bool:
        return is_creature_profession(self.current_role)

    def display_title(self) -> str:
        if self.is_unemployed() or self.is_creature():
            return ""
        return self.current_role


def normalize_profession(profession: str | None) -> str:
    text = str(profession or "").strip()
    if text in UNEMPLOYED_PROFESSIONS:
        return "Unemployed"
    return text or "Unemployed"


def is_unemployed_profession(profession: str | None) -> bool:
    return normalize_profession(profession) == "Unemployed"


def is_creature_profession(profession: str | None) -> bool:
    return normalize_profession(profession) in CREATURE_PROFESSIONS


def infer_career_track(role: str | None) -> str:
    normalized = normalize_profession(role)
    return PROFESSION_TRACKS.get(normalized, "commoner")


def infer_career_level(role: str | None) -> int:
    normalized = normalize_profession(role)
    if normalized in {"Sheriff", "Lumber Mill Foreman", "Town Official"}:
        return 2
    if normalized in {"Deputy", "Guard", "Merchant", "Farmer", "Miner", "Blacksmith", "Carpenter", "Miller", "Baker", "Fisherman", "Scribe", "Healer", "Woodcutter", "Hunter", "Tavern Keeper"}:
        return 1
    return 0


def _is_generic_merchant_building(normalized_building: str) -> bool:
    building_tokens = normalized_building.split("_")
    return (
        normalized_building == "general_store"
        or "shop" in building_tokens
        or "market" in building_tokens
    )


def resolve_profession_for_building(building_type: str, coworker_roles: list[str] | tuple[str, ...] = ()) -> str:
    normalized_building = str(building_type or "").strip().lower()

    rule = BUILDING_ROLE_RULES.get(normalized_building)
    if rule is None and _is_generic_merchant_building(normalized_building):
        return "Merchant"

    fallback_role = normalized_building.replace("_", " ").title()
    lead_role, worker_role = rule if rule else (fallback_role, fallback_role)
    if lead_role == worker_role:
        return lead_role
    if lead_role in coworker_roles:
        return worker_role
    return lead_role


def get_roles_for_building(building_type: str) -> list[str]:
    normalized_building = str(building_type or "").strip().lower()

    rule = BUILDING_ROLE_RULES.get(normalized_building)
    if rule is None and _is_generic_merchant_building(normalized_building):
        return ["Merchant"]

    fallback_role = normalized_building.replace("_", " ").title()
    lead_role, worker_role = rule if rule else (fallback_role, fallback_role)
    roles: list[str] = []
    for role in (lead_role, worker_role):
        if role not in roles:
            roles.append(role)
    return roles


def set_entity_profession(entity, profession: str, reason: str = "", game_time: int | None = None):
    normalized = normalize_profession(profession)
    if hasattr(entity, "economic"):
        entity.economic.profession = normalized
    if hasattr(entity, "career"):
        entity.career.set_role(normalized, reason=reason, game_time=game_time)
    ai_brain = getattr(entity, "ai_brain", None)
    if ai_brain and hasattr(ai_brain, "assign_profession"):
        ai_brain.assign_profession(normalized)
    return normalized


def get_entity_profession(entity) -> str:
    if entity is None:
        return "Unemployed"
    return normalize_profession(getattr(getattr(entity, "economic", None), "profession", None))


def entity_has_profession(entity, profession: str) -> bool:
    return get_entity_profession(entity) == normalize_profession(profession)


def entity_has_any_profession(entity, professions) -> bool:
    normalized = {normalize_profession(profession) for profession in professions}
    return get_entity_profession(entity) in normalized


def entity_in_track(entity, track: str) -> bool:
    if entity is None:
        return False
    if hasattr(entity, "career"):
        role = getattr(entity.career, "current_role", None)
        return infer_career_track(role) == track
    return infer_career_track(get_entity_profession(entity)) == track


def profession_has_capability(profession: str | None, capability: str) -> bool:
    normalized = normalize_profession(profession)
    return capability in PROFESSION_CAPABILITIES.get(normalized, set())


def entity_has_capability(entity, capability: str) -> bool:
    return profession_has_capability(get_entity_profession(entity), capability)
