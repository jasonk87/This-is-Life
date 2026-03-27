from __future__ import annotations

from dataclasses import dataclass, field


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
    "library": ("Scribe", "Scribe"),
    "capital_hall": ("Town Official", "Town Official"),
    "jail": ("Guard", "Guard"),
    "blacksmith_shop": ("Blacksmith", "Blacksmith"),
    "clinic": ("Healer", "Healer"),
}


@dataclass
class CareerHistoryEntry:
    role: str
    reason: str = ""
    game_time: int | None = None


@dataclass
class CareerState:
    current_role: str = "Unemployed"
    track: str = "commoner"
    level: int = 0
    tenure_days: int = 0
    history: list[CareerHistoryEntry] = field(default_factory=list)

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


def resolve_profession_for_building(building_type: str, coworker_roles: list[str] | tuple[str, ...] = ()) -> str:
    normalized_building = str(building_type or "").strip().lower()
    if normalized_building == "general_store" or "shop" in normalized_building or "market" in normalized_building:
        return "Merchant"

    lead_role, worker_role = BUILDING_ROLE_RULES.get(
        normalized_building,
        (normalized_building.replace("_", " ").title(), normalized_building.replace("_", " ").title()),
    )
    if lead_role == worker_role:
        return lead_role
    if lead_role in coworker_roles:
        return worker_role
    return lead_role


def set_entity_profession(entity, profession: str, reason: str = "", game_time: int | None = None):
    normalized = normalize_profession(profession)
    if hasattr(entity, "economic"):
        entity.economic.profession = normalized
    if hasattr(entity, "career"):
        entity.career.set_role(normalized, reason=reason, game_time=game_time)
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
