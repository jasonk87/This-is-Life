"""Active survival/metabolism component for entity physical state."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MetabolismComponent:
    hunger: int = 0
    max_hunger: int = 100
    thirst: int = 0
    max_thirst: int = 100
    # Sickness follows the same modeling pattern as hunger/thirst, but has
    # no passive per-tick increase - it only rises via contagion (see
    # simulation/systems/illness.py). Everything else (min/max clamping,
    # property naming) mirrors hunger/thirst exactly.
    sickness: int = 0
    max_sickness: int = 100
    temperature: float = 37.0
    base_temperature_resistance: float = 2.0
    clothing_insulation: float = 0.0

    def process_tick(
        self,
        *,
        hunger_delta: int = 0,
        thirst_delta: int = 0,
        ambient_temperature: float | None = None,
        wet_penalty: bool = False,
        status_effects: list[str] | None = None,
    ) -> None:
        if hunger_delta:
            self.hunger = min(self.max_hunger, self.hunger + hunger_delta)
        if thirst_delta:
            self.thirst = min(self.max_thirst, self.thirst + thirst_delta)

        if ambient_temperature is None:
            return

        total_insulation = self.base_temperature_resistance + self.clothing_insulation
        if wet_penalty:
            total_insulation *= 0.5

        target_temp_equilibrium = ambient_temperature + total_insulation
        temp_diff = target_temp_equilibrium - self.temperature
        self.temperature += temp_diff * 0.05

        if status_effects is None:
            return

        if "Freezing" in status_effects:
            status_effects.remove("Freezing")
        if "Overheating" in status_effects:
            status_effects.remove("Overheating")

        if self.temperature < 35.0:
            status_effects.append("Freezing")
        elif self.temperature > 38.5:
            status_effects.append("Overheating")
