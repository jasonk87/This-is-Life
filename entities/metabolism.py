"""Active survival/metabolism component for entity physical state."""
from __future__ import annotations

from dataclasses import dataclass

from entities.pickle_compat import dataclass_setstate


# A body is not the air around it.
#
# Both copies of this model - here and in simulation/systems/survival.py - set
# the target body temperature to `ambient + insulation`, which is the
# temperature of the air, not of a person standing in it. Nothing in the game
# reaches the 35-38.5C band that counts as healthy: the warmest season modifier
# is Summer at 25 and the default insulation is 2. Measured on a Spring day,
# an NPC's body temperature fell from 37.0 to 17.0 within about 120 ticks and
# stayed there, permanently "Freezing". Freezing costs 1 HP per 576 ticks - 25
# a day against 35 max HP - so every villager in the world was dying of cold on
# a mild spring afternoon, and a two-day run took a village from 116 to 16.
#
# A body holds itself near 37 and the environment pushes it off that mark, so
# that is what this computes. The coupling is deliberately weak: ordinary
# weather is survivable, and it takes real cold (a winter night, a mountain, a
# snowfield) or real heat (a desert at midday in summer) to move someone out of
# the safe band.
NORMAL_BODY_TEMPERATURE = 37.0
COMFORTABLE_AMBIENT = 20.0
AMBIENT_COUPLING = 0.10


def body_equilibrium_temperature(ambient_temperature: float, insulation: float) -> float:
    """Game-unit thermal load: insulation conserves heat, it does not create it.

    Clothing offsets cold up to comfort. In warm air the body can still shed
    heat; clothing adds a retention burden only above the 30C warm-room band.
    This keeps a clothed worker safe beside a hearth without capping genuine
    environmental heat or making a winter night harmless.
    """
    insulation = max(0.0, insulation)
    cold_load = min(0.0, ambient_temperature + insulation - COMFORTABLE_AMBIENT)
    warm_load = max(0.0, ambient_temperature - COMFORTABLE_AMBIENT)
    retained_heat = max(0.0, ambient_temperature - 30.0) * min(1.0, insulation / 20.0)
    return NORMAL_BODY_TEMPERATURE + (cold_load + warm_load + retained_heat) * AMBIENT_COUPLING


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

        target_temp_equilibrium = body_equilibrium_temperature(
            ambient_temperature, total_insulation
        )
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

    def __setstate__(self, state):
        dataclass_setstate(self, state)
