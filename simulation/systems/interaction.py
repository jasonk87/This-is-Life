"""Unified interaction layer for resolving both player and NPC intents."""

from __future__ import annotations

import dataclasses
import uuid

from simulation.ids import new_id
from typing import Any

from config import CHUNK_SIZE
from simulation.systems.body_combat import work_progress


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
        self.interaction_id: str = new_id()
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
        actor = world.get_entity_by_id(self.actor_id)
        efficiency_fn = getattr(world, "get_actor_work_efficiency", None)
        multiplier = 1.0
        efficiency_meta = {"work_tag": "woodcutting"}
        if callable(efficiency_fn):
            multiplier, efficiency_meta = efficiency_fn(actor, "woodcutting")
        progress = work_progress(self, multiplier)
        self.remaining_work = max(0, self.remaining_work - progress)
        apply_xp = getattr(world, "_apply_actor_skill_experience", None)
        if callable(apply_xp):
            apply_xp(actor, work_tag="woodcutting", progress_amount=progress, task=None)
        if self.remaining_work > 0 and progress <= 0:
            reporter = getattr(world, "_warn_simulation_validation", None)
            if callable(reporter):
                reporter("interaction_progress_stalled", (self.interaction_id, "chop_tree"), "ChopTreeInteraction made no progress this tick.", actor=actor, metadata={"interaction_id": self.interaction_id})

        traces = [
            ("interaction_efficiency_applied", {"work_tag": "woodcutting", "base_progress": 1, "modified_progress": progress, "remaining_work": self.remaining_work, **dict(efficiency_meta or {})}),
            ("interaction_progress_modified", {"work_tag": "woodcutting", "base_progress": 1, "modified_progress": progress, "remaining_work": self.remaining_work}),
            ("tree_chop_progress", {"remaining_work": self.remaining_work}),
        ]
        cues = ["chop_tree"]

        return ActionResult(
            success=True,
            intent=self.intent,
            cues_to_fire=cues,
            traces_to_log=traces,
            metadata={"remaining_work": self.remaining_work}
        )

    def complete(self, world: Any) -> ActionResult:
        target_x, target_y = self.target_pos

        # Replace tree with stump using world's existing replace_tile logic if available
        # or manual tile replacement (which depends on specific world implementation)
        from data.tiles import TILE_DEFINITIONS
        from tile_types import Tile

        stump_def = TILE_DEFINITIONS.get("stump_generic")

        if stump_def:
            if hasattr(world, "_change_map_tile"):
                # Use engine.py API directly if available
                world._change_map_tile((target_x, target_y), stump_def)
            else:
                chunk_x, chunk_y = target_x // CHUNK_SIZE, target_y // CHUNK_SIZE
                local_x, local_y = target_x % CHUNK_SIZE, target_y % CHUNK_SIZE

                chunk = world.chunks.get(chunk_y, {}).get(chunk_x)
                if chunk:
                    chunk.tiles[local_y][local_x] = Tile(
                        char=stump_def["char"],
                        color=stump_def["color"],
                        passable=stump_def["passable"],
                        name=stump_def["name"],
                        properties=stump_def.get("properties", {})
                    )
                    world.transparency_map[target_y, target_x] = not chunk.tiles[local_y][local_x].blocks_fov

            # Spawn logs
            from data.items import ITEM_DEFINITIONS
            from entities.items import Inventory, ItemReference

            log_def = ITEM_DEFINITIONS.get("raw_log")
            if log_def:
                world.items_on_map[(target_x, target_y)] = world.items_on_map.get((target_x, target_y)) or Inventory()
                inventory = world.items_on_map[(target_x, target_y)]

                if hasattr(inventory, "add_item_reference"):
                    inventory.add_item_reference(ItemReference("raw_log"))
                handler = getattr(world, "on_tree_resource_created", None)
                if callable(handler):
                    handler(item_key="raw_log", coords=(target_x, target_y), actor_id=self.actor_id)

        return ActionResult(
            success=True,
            intent=self.intent,
            cues_to_fire=["chop_tree"],
            traces_to_log=[
                ("tree_chopped", {"target_pos": self.target_pos}),
                ("raw_log_created", {"target_pos": self.target_pos, "item_key": "raw_log"}),
            ]
        )

    def cancel(self, world: Any, reason: str) -> ActionResult:
        return ActionResult(
            success=False,
            intent=self.intent,
            reason=reason,
            traces_to_log=[("interaction_cancelled", {"reason": reason})]
        )


class BuildInteraction(ActiveInteraction):
    def __init__(self, intent: ActionIntent):
        super().__init__(intent)
        self.blueprint_id = intent.payload.get("blueprint_id")
        self.component_id = intent.payload.get("component_id")
        self.animation_cue = "build"
        self.remaining_work = 0

    def can_start(self, world: Any) -> bool:
        blueprint = world.blueprints_by_id.get(self.blueprint_id)
        if not blueprint:
            return False

        comp = next((c for c in blueprint.components if c.id == self.component_id), None)
        if not comp:
            return False

        if not comp.has_all_materials() or comp.status == "complete":
            return False

        actor = world.get_entity_by_id(self.actor_id)
        if not actor:
            return False

        dx = abs(actor.x - comp.x)
        dy = abs(actor.y - comp.y)
        if dx > 1 or dy > 1:
            return False

        claim_available = getattr(world, "_construction_component_available_for_actor", None)
        claim_component = getattr(world, "_claim_construction_component", None)
        if callable(claim_available) and not claim_available(blueprint, comp, actor):
            return False
        if callable(claim_component) and not claim_component(blueprint, comp, actor, reason="build_interaction"):
            return False

        self.remaining_work = max(1, comp.required_work - comp.build_progress)

        return True

    def can_continue(self, world: Any) -> bool:
        return self.can_start(world)

    def advance_tick(self, world: Any) -> ActionResult:
        blueprint = world.blueprints_by_id.get(self.blueprint_id)
        if not blueprint:
            return ActionResult(success=False, intent=self._original_intent(), reason="blueprint_not_found")

        actor = world.get_entity_by_id(self.actor_id)
        efficiency_fn = getattr(world, "get_actor_work_efficiency", None)
        multiplier = 1.0
        efficiency_meta = {"work_tag": "construction"}
        if callable(efficiency_fn):
            multiplier, efficiency_meta = efficiency_fn(actor, "construction")
        amount = work_progress(self, multiplier, base=10)
        self.remaining_work = max(0, self.remaining_work - amount)
        apply_xp = getattr(world, "_apply_actor_skill_experience", None)
        if callable(apply_xp):
            apply_xp(actor, work_tag="construction", progress_amount=amount, task=None)

        blueprint.apply_work(amount, self.component_id)

        return ActionResult(
            success=True,
            intent=self._original_intent(),
            cues_to_fire=[self.animation_cue],
            traces_to_log=[
                ("interaction_efficiency_applied", {"work_tag": "construction", "base_progress": 10, "modified_progress": amount, "remaining_work": self.remaining_work, **dict(efficiency_meta or {})}),
                ("interaction_progress_modified", {"work_tag": "construction", "base_progress": 10, "modified_progress": amount, "remaining_work": self.remaining_work}),
                ("build_progress", {"blueprint_id": self.blueprint_id, "component_id": self.component_id, "remaining": self.remaining_work}),
            ],
            consumed_time=amount
        )

    def _original_intent(self) -> ActionIntent:
        return ActionIntent(
            actor_id=self.actor_id,
            action_type="build",
            target_pos=self.target_pos,
            payload={"blueprint_id": self.blueprint_id, "component_id": self.component_id}
        )

    def cancel(self, world: Any, reason: str) -> ActionResult:
        blueprint = world.blueprints_by_id.get(self.blueprint_id)
        if reason in {"cannot_continue", "blueprint_not_found", "component_unavailable"}:
            releaser = getattr(world, "_release_construction_component_claim", None)
            if callable(releaser):
                releaser(blueprint, self.component_id, self.actor_id, reason=f"build_cancelled:{reason}")

        # Regardless of reason: the actor is no longer actively working
        # this blueprint right now, so their entry in the coarser
        # blueprint.assigned_workers list needs to go. That list is a
        # separate tracking structure from the fine-grained component
        # claim above (see World._assign_construction_task_to_npc, which
        # appends here just for being "sent toward" a blueprint, and has
        # its own early-return fast path that treats anyone still in this
        # list as permanently already-assigned). Without this, an actor
        # interrupted here - e.g. by "survival_override" - stayed in
        # assigned_workers forever, even once free again, so they'd never
        # be re-evaluated for real work again.
        #
        # Deliberately NOT extending the component-claim release above to
        # every reason: for a temporary interruption like
        # "survival_override" the claim is meant to persist for a grace
        # window so the same actor can resume their own progress instead
        # of losing it to whoever else picks the blueprint up next (see
        # tests/test_construction_foundation.py's
        # test_interrupted_component_claim_expires_and_allows_resume) -
        # this fix only closes the assigned_workers bookkeeping leak, it
        # doesn't touch that expiry/resume behavior.
        if blueprint is not None and self.actor_id in getattr(blueprint, "assigned_workers", []):
            blueprint.assigned_workers.remove(self.actor_id)

        return ActionResult(
            success=False,
            intent=self._original_intent(),
            reason=reason,
            traces_to_log=[("build_cancelled", {"blueprint_id": self.blueprint_id, "component_id": self.component_id, "reason": reason})]
        )

    def complete(self, world: Any) -> ActionResult:
        blueprint = world.blueprints_by_id.get(self.blueprint_id)
        component = next((c for c in getattr(blueprint, "components", []) if c.id == self.component_id), None) if blueprint else None
        recorder = getattr(world, "_record_component_claim_trace", None)
        if callable(recorder) and component is not None:
            recorder("component_claim_released", blueprint, component, self.actor_id, reason="component_completed")
        return ActionResult(
            success=True,
            intent=self._original_intent(),
            traces_to_log=[("component_completed", {"blueprint_id": self.blueprint_id, "component_id": self.component_id})]
        )



class WorkshopInteraction(ActiveInteraction):
    def __init__(self, intent: ActionIntent):
        super().__init__(intent)
        self.workshop_id = intent.payload.get("workshop_id")
        self.recipe = intent.payload.get("recipe", "raw_log_to_plank")
        self.production_task_id = intent.payload.get("production_task_id")
        self.remaining_work = 8
        self.animation_cue = "build"

    def can_start(self, world: Any) -> bool:
        workshop = getattr(world, "workshops_by_id", {}).get(self.workshop_id)
        actor = world.get_entity_by_id(self.actor_id)
        if workshop is None or actor is None or not workshop.operational:
            return False
        if abs(actor.x - workshop.x) > 1 or abs(actor.y - workshop.y) > 1:
            reporter = getattr(world, "_warn_simulation_validation", None)
            if callable(reporter):
                reporter("workshop_interaction_out_of_range", (self.workshop_id, self.actor_id, "start"), "Actor must be adjacent to workshop to begin transform.", actor=actor, metadata={"workshop_id": self.workshop_id})
            return False
        if workshop.occupied_by_actor_id not in {None, self.actor_id}:
            return False
        if workshop.input_buffer.get("raw_log", 0) <= 0:
            return False
        return True

    def can_continue(self, world: Any) -> bool:
        workshop = getattr(world, "workshops_by_id", {}).get(self.workshop_id)
        actor = world.get_entity_by_id(self.actor_id)
        if workshop is None or actor is None:
            return False
        if abs(actor.x - workshop.x) > 1 or abs(actor.y - workshop.y) > 1:
            reporter = getattr(world, "_warn_simulation_validation", None)
            if callable(reporter):
                reporter("workshop_interaction_out_of_range", (self.workshop_id, self.actor_id, "continue"), "Actor moved out of workshop interaction range.", actor=actor, metadata={"workshop_id": self.workshop_id})
            return False
        return workshop.operational and workshop.input_buffer.get("raw_log", 0) > 0

    def advance_tick(self, world: Any) -> ActionResult:
        actor = world.get_entity_by_id(self.actor_id)
        efficiency_fn = getattr(world, "get_actor_work_efficiency", None)
        multiplier = 1.0
        efficiency_meta = {"work_tag": "crafting"}
        if callable(efficiency_fn):
            multiplier, efficiency_meta = efficiency_fn(actor, "crafting")
        progress = work_progress(self, multiplier)
        self.remaining_work = max(0, self.remaining_work - progress)
        apply_xp = getattr(world, "_apply_actor_skill_experience", None)
        if callable(apply_xp):
            apply_xp(actor, work_tag="crafting", progress_amount=progress, task=None)
        return ActionResult(
            success=True,
            intent=self.intent,
            cues_to_fire=[self.animation_cue],
            traces_to_log=[
                ("interaction_efficiency_applied", {"work_tag": "crafting", "base_progress": 1, "modified_progress": progress, "remaining_work": self.remaining_work, **dict(efficiency_meta or {})}),
                ("interaction_progress_modified", {"work_tag": "crafting", "base_progress": 1, "modified_progress": progress, "remaining_work": self.remaining_work}),
                ("workshop_progress", {"workshop_id": self.workshop_id, "recipe": self.recipe, "remaining_work": self.remaining_work}),
            ],
        )

    def complete(self, world: Any) -> ActionResult:
        workshop = getattr(world, "workshops_by_id", {}).get(self.workshop_id)
        if workshop is None:
            return ActionResult(success=False, intent=self.intent, reason="workshop_missing")
        consumed = workshop.input_buffer.pop_item_reference("raw_log")
        if consumed is None:
            return ActionResult(success=False, intent=self.intent, reason="missing_inputs")
        workshop.reserved_input_entity_ids = []
        from entities.items import ItemReference
        plank = ItemReference("wooden_plank")
        workshop.output_buffer.add_item_reference(plank)
        workshop.last_used_tick = int(getattr(world, "game_time", 0) or 0)
        releaser = getattr(world, "_release_workshop_lock", None)
        if callable(releaser):
            releaser(workshop, self.actor_id)
        return ActionResult(success=True, intent=self.intent, traces_to_log=[("workshop_output_created", {"workshop_id": self.workshop_id, "recipe": self.recipe, "output_item_key": "wooden_plank"}), ("workshop_interaction_completed", {"workshop_id": self.workshop_id, "recipe": self.recipe})])

    def cancel(self, world: Any, reason: str) -> ActionResult:
        workshop = getattr(world, "workshops_by_id", {}).get(self.workshop_id)
        releaser = getattr(world, "_release_workshop_lock", None)
        if workshop is not None and callable(releaser):
            workshop.reserved_input_entity_ids = []
            releaser(workshop, self.actor_id)
        return ActionResult(success=False, intent=self.intent, reason=reason, traces_to_log=[("workshop_interaction_cancelled", {"workshop_id": self.workshop_id, "reason": reason})])


class EatingInteraction(ActiveInteraction):
    def __init__(self, intent: ActionIntent):
        super().__init__(intent)
        self.food_id = intent.payload.get("food_id")
        self.food_pos = tuple(intent.payload.get("food_pos", (0, 0)))
        self.item_key = intent.payload.get("item_key", "simple_food")
        self.nutrition_value = float(intent.payload.get("nutrition_value", 0.3) or 0.3)
        self.remaining_work = int(intent.payload.get("eat_work_required", 4) or 4)

    def can_start(self, world: Any) -> bool:
        actor = world.get_entity_by_id(self.actor_id)
        if actor is None:
            return False
        if abs(actor.x - self.food_pos[0]) > 1 or abs(actor.y - self.food_pos[1]) > 1:
            reporter = getattr(world, "_warn_simulation_validation", None)
            if callable(reporter):
                reporter("eating_out_of_range", (self.actor_id, self.food_id, "start"), "Actor must be adjacent to food to start eating.", actor=actor, metadata={"food_id": self.food_id})
            return False
        inv = getattr(world, "items_on_map", {}).get(self.food_pos)
        if inv is None:
            return False
        if hasattr(inv, "has_item") and inv.has_item(self.item_key, 1):
            return True
        counter = getattr(world, "_iter_inventory_item_counts", None)
        if callable(counter):
            return any(key == self.item_key and quantity > 0 for key, quantity in counter(inv))
        return bool(getattr(inv, "get", lambda *_:0)(self.item_key,0) > 0)

    def can_continue(self, world: Any) -> bool:
        return self.can_start(world)

    def advance_tick(self, world: Any) -> ActionResult:
        self.remaining_work = max(0, self.remaining_work - 1)
        return ActionResult(success=True, intent=self.intent, traces_to_log=[("eating_interaction_progress", {"food_id": self.food_id, "remaining_work": self.remaining_work})])

    def complete(self, world: Any) -> ActionResult:
        actor = world.get_entity_by_id(self.actor_id)
        inv = getattr(world, "items_on_map", {}).get(self.food_pos)
        if inv is None:
            return ActionResult(success=False, intent=self.intent, reason="food_missing")
        ref = inv.pop_item_reference(self.item_key)
        if ref is None:
            warn = getattr(world, "_warn_simulation_validation", None)
            if callable(warn):
                warn("eating_double_consumption_prevented", (self.food_id, self.actor_id), "Food was already consumed/reserved by another actor.", actor=actor, metadata={"food_id": self.food_id})
            return ActionResult(success=False, intent=self.intent, reason="food_missing")
        actor.hunger = max(0.0, float(getattr(actor, "hunger", 0.0) or 0.0) - float(self.nutrition_value))
        actor.hunger_last_eat_tick = int(getattr(world, "game_time", 0) or 0)
        releaser = getattr(world, "_release_food_reservation", None)
        if callable(releaser):
            releaser(self.food_id, actor_id=self.actor_id, reason="eating_completed")
        actor.hunger_target_food_id = None
        actor.hunger_nutrition_pending = 0.0
        return ActionResult(success=True, intent=self.intent, traces_to_log=[("eating_interaction_completed", {"food_id": self.food_id, "nutrition_value": self.nutrition_value}), ("hunger_food_consumed", {"food_id": self.food_id, "hunger": actor.hunger}), ("hunger_reduced", {"hunger": actor.hunger})])

    def cancel(self, world: Any, reason: str) -> ActionResult:
        releaser = getattr(world, "_release_food_reservation", None)
        if callable(releaser):
            releaser(self.food_id, actor_id=self.actor_id, reason="eating_cancelled")
        return ActionResult(success=False, intent=self.intent, reason=reason, traces_to_log=[("eating_interaction_cancelled", {"food_id": self.food_id, "reason": reason})])

class InteractionResolver:
    def __init__(self):
        self.active_interactions: dict[str, ActiveInteraction] = {}

    def resolve(self, intent: ActionIntent, world: Any) -> ActionResult:
        actor = world.get_entity_by_id(intent.actor_id)
        if not actor:
            return ActionResult(success=False, intent=intent, reason="actor_not_found")
        from simulation.systems.body_combat import can_act, functions_for
        if not can_act(actor):
            return ActionResult(success=False, intent=intent, reason="incapacitated")
        if intent.action_type in ("chop_tree", "build", "workshop_transform") and functions_for(actor)["grip"] < .1:
            return ActionResult(success=False, intent=intent, reason="unable_to_work")

        if intent.action_type == "open_door":
            return self._resolve_open_door(intent, world, actor)
        elif intent.action_type == "pickup_item":
            return self._resolve_pickup_item(intent, world, actor)
        elif intent.action_type == "sit_on_chair" or intent.action_type == "sleep_in_bed":
            return self._resolve_sit_or_sleep(intent, world, actor)
        elif intent.action_type == "chop_tree":
            return self._resolve_chop_tree(intent, world, actor)
        elif intent.action_type == "build":
            return self._resolve_build(intent, world, actor)
        elif intent.action_type == "workshop_transform":
            return self._resolve_workshop_transform(intent, world, actor)
        elif intent.action_type == "eat_food":
            interaction = EatingInteraction(intent)
            if not interaction.can_start(world):
                return ActionResult(success=False, intent=intent, reason="cannot_start_eating")
            self.active_interactions[interaction.interaction_id] = interaction
            return ActionResult(success=True, intent=intent, started_interaction_id=interaction.interaction_id
            )

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

            if hasattr(world, "_change_map_tile"):
                world._change_map_tile((target_x, target_y), new_door_def)
            else:
                chunk_x, chunk_y = target_x // CHUNK_SIZE, target_y // CHUNK_SIZE
                local_x, local_y = target_x % CHUNK_SIZE, target_y % CHUNK_SIZE

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

            start_activity(
                actor,
                "sitting",
                actor.leisure_timer,
                location=(actor.x, actor.y),
                anchor_coords=(target_x, target_y),
                world=world
            )

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


    def _resolve_workshop_transform(self, intent: ActionIntent, world: Any, actor: Any) -> ActionResult:
        interaction = WorkshopInteraction(intent)
        if not interaction.can_start(world):
            return ActionResult(success=False, intent=intent, reason="cannot_start_workshop_transform")
        self.active_interactions[interaction.interaction_id] = interaction
        return ActionResult(success=True, intent=intent, started_interaction_id=interaction.interaction_id, traces_to_log=[("workshop_interaction_started", {"workshop_id": interaction.workshop_id, "recipe": interaction.recipe})])

    def _resolve_build(self, intent: ActionIntent, world: Any, actor: Any) -> ActionResult:
        blueprint_id = intent.payload.get("blueprint_id")
        component_id = intent.payload.get("component_id")
        for active in self.active_interactions.values():
            if (
                getattr(active, "action_type", None) == "build"
                and getattr(active, "blueprint_id", None) == blueprint_id
                and getattr(active, "component_id", None) == component_id
            ):
                return ActionResult(success=False, intent=intent, reason="component_already_building")

        interaction = BuildInteraction(intent)
        if not interaction.can_start(world):
            return ActionResult(success=False, intent=intent, reason="cannot_start")

        self.active_interactions[interaction.interaction_id] = interaction
        return ActionResult(success=True, intent=intent, started_interaction_id=interaction.interaction_id, traces_to_log=[("build_started", {"blueprint_id": interaction.blueprint_id})])

    def cancel_active_interaction(self, interaction_id: str, world: Any, reason: str) -> ActionResult | None:
        interaction = self.active_interactions.pop(interaction_id, None)
        if not interaction:
            return None
        return interaction.cancel(world, reason=reason)

    def cancel_actor_interaction(self, actor_id: str | int, world: Any, reason: str) -> ActionResult | None:
        found_id = None
        for iid, interaction in self.active_interactions.items():
            if interaction.intent.actor_id == actor_id:
                found_id = iid
                break
        if found_id:
            return self.cancel_active_interaction(found_id, world, reason)
        return None

    def advance_active_interaction(self, interaction_id: str, world: Any) -> ActionResult | None:
        interaction = self.active_interactions.get(interaction_id)
        if not interaction:
            return None
        from simulation.systems.body_combat import can_act, functions_for
        actor = world.get_entity_by_id(interaction.actor_id)
        if actor is None or not can_act(actor) or (interaction.action_type in ("chop_tree", "build", "workshop_transform") and functions_for(actor)["grip"] < .1):
            del self.active_interactions[interaction_id]
            return interaction.cancel(world, reason="incapacitated")

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
