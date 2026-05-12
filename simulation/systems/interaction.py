"""Unified interaction layer for resolving both player and NPC intents."""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any


@dataclasses.dataclass
class ActionIntent:
    actor_id: str | int
    action_type: str
    target_id: str | int | None = None
    target_pos: tuple[int, int] | None = None
    source: str = "npc"  # "player" | "npc" | "sandbox"
    payload: dict[str, Any] = dataclasses.field(default_factory=dict)
    created_tick: int | None = None


@dataclasses.dataclass
class ActionResult:
    success: bool
    intent: ActionIntent
    reason: str | None = None
    cues_to_fire: list[str] = dataclasses.field(default_factory=list)
    traces_to_log: list[tuple[str, dict[str, Any]]] = dataclasses.field(default_factory=list)
    consumed_time: int = 0
    started_interaction_id: str | None = None
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


class ActiveInteraction:
    def __init__(self, intent: ActionIntent):
        self.interaction_id: str = str(uuid.uuid4())
        self.actor_id: str | int = intent.actor_id
        self.action_type: str = intent.action_type
        self.target_id: str | int | None = intent.target_id
        self.target_pos: tuple[int, int] | None = intent.target_pos
        self.remaining_work: int = 0
        self.animation_cue: str | None = None
        self.interruptible: bool = True
        self.metadata: dict[str, Any] = {}
        self.intent: ActionIntent = intent

    def can_start(self, world: Any) -> bool:
        raise NotImplementedError

    def can_continue(self, world: Any) -> bool:
        raise NotImplementedError

    def advance_tick(self, world: Any) -> ActionResult | None:
        raise NotImplementedError

    def complete(self, world: Any) -> ActionResult:
        raise NotImplementedError

    def cancel(self, world: Any, reason: str) -> ActionResult:
        raise NotImplementedError


class ChopTreeInteraction(ActiveInteraction):
    def __init__(self, intent: ActionIntent):
        super().__init__(intent)
        self.remaining_work = 10
        self.animation_cue = "chop_tree"

    def can_start(self, world: Any) -> bool:
        actor = world.get_entity_by_id(self.actor_id)
        if not actor:
            return False

        target_x, target_y = self.target_pos
        tile = world.get_tile_at(target_x, target_y)

        if not tile or not hasattr(tile, "properties") or tile.properties.get("is_tree") is not True:
            return False

        dx = abs(actor.x - target_x)
        dy = abs(actor.y - target_y)
        if dx > 1 or dy > 1:
            return False

        return True

    def can_continue(self, world: Any) -> bool:
        actor = world.get_entity_by_id(self.actor_id)
        if not actor or getattr(actor.physical, "is_dead", False):
            return False

        target_x, target_y = self.target_pos
        tile = world.get_tile_at(target_x, target_y)

        if not tile or not hasattr(tile, "properties") or tile.properties.get("is_tree") is not True:
            return False

        dx = abs(actor.x - target_x)
        dy = abs(actor.y - target_y)
        if dx > 1 or dy > 1:
            return False

        return True

    def advance_tick(self, world: Any) -> ActionResult | None:
        self.remaining_work -= 1

        traces = [("tree_chop_progress", {"remaining_work": self.remaining_work})]
        cues = ["chop_tree"]

        return ActionResult(
            success=True,
            intent=self.intent,
            cues_to_fire=cues,
            traces_to_log=traces,
            metadata={"remaining_work": self.remaining_work}
        )

    def complete(self, world: Any) -> ActionResult:
        actor = world.get_entity_by_id(self.actor_id)
        target_x, target_y = self.target_pos

        # Replace tree with stump using world's existing replace_tile logic if available
        # or manual tile replacement (which depends on specific world implementation)
        from data.decorations import DECORATION_ITEM_DEFINITIONS
        from tile_types import Tile

        stump_def = DECORATION_ITEM_DEFINITIONS.get("tree_stump")

        if stump_def:
            chunk_x, chunk_y = target_x // world.CHUNK_SIZE, target_y // world.CHUNK_SIZE
            local_x, local_y = target_x % world.CHUNK_SIZE, target_y % world.CHUNK_SIZE

            chunk = world.chunks.get(chunk_y, {}).get(chunk_x)
            if chunk:
                chunk.tiles[local_y][local_x] = Tile(
                    char=stump_def["char"],
                    color=stump_def["color"],
                    passable=stump_def["passable"],
                    name=stump_def["name"],
                    properties=stump_def["properties"]
                )
                world.transparency_map[target_y, target_x] = not chunk.tiles[local_y][local_x].blocks_fov

                # Spawn logs
                from data.items import ITEM_DEFINITIONS
                from engine import ItemReference

                log_def = ITEM_DEFINITIONS.get("wood_log")
                if log_def:
                    world.items_on_map[(target_x, target_y)] = world.items_on_map.get((target_x, target_y)) or getattr(world, "Inventory", dict)()
                    inventory = world.items_on_map[(target_x, target_y)]

                    if hasattr(inventory, "add_item_reference"):
                        inventory.add_item_reference(ItemReference("wood_log"))

        return ActionResult(
            success=True,
            intent=self.intent,
            cues_to_fire=["chop_tree"],
            traces_to_log=[("tree_chopped", {"target_pos": self.target_pos})]
        )

    def cancel(self, world: Any, reason: str) -> ActionResult:
        return ActionResult(
            success=False,
            intent=self.intent,
            reason=reason,
            traces_to_log=[("interaction_cancelled", {"reason": reason})]
        )


class InteractionResolver:
    def __init__(self):
        self.active_interactions: dict[str, ActiveInteraction] = {}

    def resolve(self, intent: ActionIntent, world: Any) -> ActionResult:
        actor = world.get_entity_by_id(intent.actor_id)
        if not actor:
            return ActionResult(success=False, intent=intent, reason="actor_not_found")

        if intent.action_type == "open_door":
            return self._resolve_open_door(intent, world, actor)
        elif intent.action_type == "pickup_item":
            return self._resolve_pickup_item(intent, world, actor)
        elif intent.action_type == "sit_on_chair" or intent.action_type == "sleep_in_bed":
            return self._resolve_sit_or_sleep(intent, world, actor)
        elif intent.action_type == "chop_tree":
            return self._resolve_chop_tree(intent, world, actor)

        return ActionResult(success=False, intent=intent, reason=f"unknown_action_type:{intent.action_type}")

    def _resolve_open_door(self, intent: ActionIntent, world: Any, actor: Any) -> ActionResult:
        target_x, target_y = intent.target_pos

        dx = abs(actor.x - target_x)
        dy = abs(actor.y - target_y)
        if dx > 1 or dy > 1:
            return ActionResult(success=False, intent=intent, reason="target_unreachable")

        target_tile = world.get_tile_at(target_x, target_y)

        if not target_tile or not target_tile.properties.get("is_door"):
            return ActionResult(success=False, intent=intent, reason="not_a_door")

        is_open = target_tile.properties.get("is_open", False)
        if is_open:
            return ActionResult(success=True, intent=intent, reason="already_open")

        new_state_key = target_tile.properties.get("opens_to")
        from data.decorations import DECORATION_ITEM_DEFINITIONS
        from tile_types import Tile

        if new_state_key and new_state_key in DECORATION_ITEM_DEFINITIONS:
            new_door_def = DECORATION_ITEM_DEFINITIONS[new_state_key]

            chunk_size = getattr(world, "CHUNK_SIZE", 32)
            chunk_x, chunk_y = target_x // chunk_size, target_y // chunk_size
            local_x, local_y = target_x % chunk_size, target_y % chunk_size

            if isinstance(world.chunks, dict):
                chunk = world.chunks.get(chunk_y, {}).get(chunk_x)
            else:
                try:
                    chunk = world.chunks[chunk_y][chunk_x]
                except IndexError:
                    chunk = None

            if chunk:
                chunk.tiles[local_y][local_x] = Tile(
                    char=new_door_def["char"],
                    color=new_door_def["color"],
                    passable=new_door_def["passable"],
                    name=new_door_def["name"],
                    properties=new_door_def["properties"]
                )
                world.transparency_map[target_y, target_x] = not chunk.tiles[local_y][local_x].blocks_fov

            return ActionResult(
                success=True,
                intent=intent,
                cues_to_fire=["open_door"],
                traces_to_log=[("door_opened", {"target_pos": (target_x, target_y)})]
            )

        return ActionResult(success=False, intent=intent, reason="door_stuck")

    def _resolve_pickup_item(self, intent: ActionIntent, world: Any, actor: Any) -> ActionResult:
        item_key = intent.payload.get("item_key")
        if not item_key:
            return ActionResult(success=False, intent=intent, reason="missing_item_key")

        target_x, target_y = intent.target_pos
        dx = abs(actor.x - target_x)
        dy = abs(actor.y - target_y)
        if dx > 1 or dy > 1:
            return ActionResult(success=False, intent=intent, reason="target_unreachable")

        inventory = world.items_on_map.get((target_x, target_y))

        if inventory is None or not hasattr(inventory, "get_item_reference"):
            return ActionResult(success=False, intent=intent, reason="no_items_at_location")

        item_reference = inventory.get_item_reference(item_key)
        if item_reference is None:
            return ActionResult(success=False, intent=intent, reason="item_not_found")

        # Try to use standard inventory logic
        if hasattr(actor, "economic") and hasattr(actor.economic, "npc_inventory"):
            success = inventory.transfer_item_reference(actor.economic.npc_inventory, item_reference)
        elif hasattr(actor, "economic") and hasattr(actor.economic, "inventory"):
            success = inventory.transfer_item_reference(actor.economic.inventory, item_reference)
        else:
            return ActionResult(success=False, intent=intent, reason="actor_cannot_carry_items")

        if success:
            return ActionResult(
                success=True,
                intent=intent,
                cues_to_fire=["haul_carry"],
                traces_to_log=[("item_picked_up", {"item_key": item_key, "target_pos": (target_x, target_y)})]
            )

        return ActionResult(success=False, intent=intent, reason="transfer_failed")

    def _resolve_sit_or_sleep(self, intent: ActionIntent, world: Any, actor: Any) -> ActionResult:
        target_x, target_y = intent.target_pos
        dx = abs(actor.x - target_x)
        dy = abs(actor.y - target_y)
        if dx > 1 or dy > 1:
            return ActionResult(success=False, intent=intent, reason="target_unreachable")

        tile = world.get_tile_at(target_x, target_y)
        if not tile or not hasattr(tile, "properties"):
            return ActionResult(success=False, intent=intent, reason="no_furniture")

        hint = tile.properties.get("interaction_hint")
        if intent.action_type == "sit_on_chair" and hint == "sit":
            from simulation.systems.scheduling import TaskType
            from simulation.activity import start_activity

            actor.schedule.current_task = getattr(TaskType, "SITTING", "sitting")
            actor.is_sitting = True
            actor.sitting_on_object_at = (target_x, target_y)
            actor.leisure_timer = intent.payload.get("duration", 40)

            # Create a simple Activity equivalent
            class SimpleActivity:
                def __init__(self, t, d):
                    self.activity_type = t
                    self.duration_ticks = d
                    self.progress_ticks = 0
                    self.associated_interaction_point = (target_x, target_y)

            actor.current_activity = SimpleActivity("sitting", actor.leisure_timer)

            return ActionResult(
                success=True,
                intent=intent,
                traces_to_log=[("started_sitting", {"target_pos": (target_x, target_y)})]
            )
        elif intent.action_type == "sleep_in_bed" and hint == "sleep":
            actor.is_sleeping = True
            actor.x, actor.y = target_x, target_y
            actor.schedule.current_path = []
            return ActionResult(
                success=True,
                intent=intent,
                traces_to_log=[("started_sleeping", {"target_pos": (target_x, target_y)})]
            )

        return ActionResult(success=False, intent=intent, reason="incompatible_furniture")

    def _resolve_chop_tree(self, intent: ActionIntent, world: Any, actor: Any) -> ActionResult:
        interaction = ChopTreeInteraction(intent)
        if not interaction.can_start(world):
            return ActionResult(success=False, intent=intent, reason="cannot_start_interaction")

        self.active_interactions[interaction.interaction_id] = interaction
        return ActionResult(
            success=True,
            intent=intent,
            started_interaction_id=interaction.interaction_id,
            traces_to_log=[("started_chop_tree", {"target_pos": intent.target_pos})]
        )

    def advance_active_interaction(self, interaction_id: str, world: Any) -> ActionResult | None:
        interaction = self.active_interactions.get(interaction_id)
        if not interaction:
            return None

        if not interaction.can_continue(world):
            del self.active_interactions[interaction_id]
            return interaction.cancel(world, reason="cannot_continue")

        result = interaction.advance_tick(world)
        if interaction.remaining_work <= 0:
            del self.active_interactions[interaction_id]
            complete_result = interaction.complete(world)
            if complete_result:
                if result:
                    complete_result.cues_to_fire.extend(result.cues_to_fire)
                    complete_result.traces_to_log.extend(result.traces_to_log)
                return complete_result

        return result
