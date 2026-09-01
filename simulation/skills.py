"""Shared skill progression helpers for entities."""
from __future__ import annotations

from dataclasses import dataclass, field

from entities.pickle_compat import dataclass_setstate


DEFAULT_SKILL_LEVELS = {
    "melee": 5,
    "crafting": 1,
    "farming": 1,
    "labor": 1,
    "questing": 1,
}


@dataclass
class SkillTracker:
    """Track per-skill levels and experience using lightweight progressive thresholds."""

    levels: dict[str, int] = field(default_factory=lambda: DEFAULT_SKILL_LEVELS.copy())
    experience: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.levels = {
            skill_name: max(1, int(level))
            for skill_name, level in (self.levels or DEFAULT_SKILL_LEVELS).items()
        }
        self.experience = {
            skill_name: max(0, int(xp))
            for skill_name, xp in (self.experience or {}).items()
        }

    def ensure_skill(self, skill_name: str, default_level: int = 1) -> None:
        self.levels.setdefault(skill_name, max(1, int(default_level)))
        self.experience.setdefault(skill_name, 0)

    def get_level(self, skill_name: str, default_level: int = 1) -> int:
        self.ensure_skill(skill_name, default_level=default_level)
        return self.levels[skill_name]

    def __setstate__(self, state):
        dataclass_setstate(self, state)
        # __post_init__'s normalization doesn't re-run on unpickle (only
        # __setstate__ does) - re-apply it so a restored tracker gets the
        # same int-coercion/floor-at-1 guarantees a freshly constructed one
        # does, in case a legacy pickle had raw/unnormalized values.
        self.__post_init__()

    def xp_to_next_level(self, skill_name: str) -> int:
        level = self.get_level(skill_name)
        return 10 + (level - 1) * 5

    def gain_experience(self, skill_name: str, amount: int, *, default_level: int = 1) -> dict:
        self.ensure_skill(skill_name, default_level=default_level)
        gained = max(0, int(amount))
        if gained == 0:
            return {"skill": skill_name, "gained": 0, "leveled_up": False, "old_level": self.levels[skill_name], "new_level": self.levels[skill_name]}

        old_level = self.levels[skill_name]
        self.experience[skill_name] += gained
        leveled_up = False

        while self.experience[skill_name] >= self.xp_to_next_level(skill_name):
            self.experience[skill_name] -= self.xp_to_next_level(skill_name)
            self.levels[skill_name] += 1
            leveled_up = True

        return {
            "skill": skill_name,
            "gained": gained,
            "leveled_up": leveled_up,
            "old_level": old_level,
            "new_level": self.levels[skill_name],
            "remaining_xp": self.experience[skill_name],
        }
