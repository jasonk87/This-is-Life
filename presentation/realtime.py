"""Wall-clock pacing and transient input, separate from simulation time."""
from dataclasses import dataclass, field

from config import SECONDS_PER_GAME_TICK


@dataclass
class RealtimeClock:
    accumulator: float = 0.0

    def tick_due(self, dt, *, speed=1.0, active=True):
        """At most one complete tick per rendered/input-serviced frame.

        Preserve fractional time at normal frame rates. Under overload, discard
        wall-clock debt, not simulation events: game time advances only when a
        complete world update actually executes. Never fast-forward after a hitch.
        """
        if not active or speed <= 0:
            self.accumulator = 0.0
            return False
        total = self.accumulator + max(0.0, dt) * speed
        if total + 1e-9 < SECONDS_PER_GAME_TICK:
            self.accumulator = total
            return False
        self.accumulator = max(0.0, total - SECONDS_PER_GAME_TICK) if total < 2*SECONDS_PER_GAME_TICK else 0.0
        return True


@dataclass
class MovementInput:
    held: list = field(default_factory=list)
    pending: object = None
    last_attempt_tick: int = -1

    def press(self, key):
        if key in self.held:
            self.held.remove(key)
        self.held.append(key)
        self.pending = key  # One buffered tap, never an unbounded repeat queue.

    def release(self, key):
        if key in self.held:
            self.held.remove(key)

    def clear(self):
        self.held.clear()
        self.pending = None
        self.last_attempt_tick = -1

    def next_key(self):
        return self.pending if self.pending is not None else self.held[-1] if self.held else None

    def __getstate__(self):
        return {}  # A save must not preserve physically held keys or queued taps.

    def __setstate__(self, state):
        self.held, self.pending, self.last_attempt_tick = [], None, -1
