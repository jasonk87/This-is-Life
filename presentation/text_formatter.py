from __future__ import annotations

from data.environment import WEATHER_DEFINITIONS


class WorldTextFormatter:
    """Builds player-facing text from game state instead of ad-hoc string assembly."""

    def __init__(self, world):
        self.world = world

    def entity_name(self, entity, include_relationship: bool = False) -> str:
        if entity is None:
            return "Unknown"
        if hasattr(entity, "get_display_name"):
            return entity.get_display_name(viewer=self.world.player, include_relationship=include_relationship)
        return str(getattr(entity, "name", "Unknown")).replace("_", " ").strip() or "Unknown"

    def season_changed(self, season_name: str) -> str:
        return f"The season has changed to {season_name}."

    def weather_changed(self, weather_key: str) -> str:
        weather_name = WEATHER_DEFINITIONS.get(weather_key, {}).get("name", str(weather_key).replace("_", " ").title())
        return f"The weather has changed to {weather_name}."

    def entity_attacks(self, attacker, target, damage: int) -> str:
        return f"{self.entity_name(attacker)} attacks {self.entity_name(target)} for {damage} damage!"

    def entity_died(self, entity) -> str:
        return f"{self.entity_name(entity)} has died!"

    def entity_apprehends_you(self, entity) -> str:
        return f"{self.entity_name(entity)} apprehends you! You are under arrest."

    def entity_grazes_on(self, entity, tile_name: str) -> str:
        return f"{self.entity_name(entity)} grazes on {tile_name}."

    def entity_reports_your_crimes(self, entity) -> str:
        return f"{self.entity_name(entity)} reports your crimes to the authorities!"

    def entity_caught_fish(self, entity, fish_name: str) -> str:
        return f"{self.entity_name(entity)} caught a {fish_name}!"
