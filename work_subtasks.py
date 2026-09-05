"""Command objects for completed NPC work sub-tasks."""

from __future__ import annotations

import random

from config import DAY_LENGTH_TICKS, DAYS_PER_SEASON
from data.animals import ANIMAL_DEFINITIONS
from data.decorations import DECORATION_ITEM_DEFINITIONS
from data.items import ITEM_DEFINITIONS
from data.tiles import TILE_DEFINITIONS
from entities.items import roll_crafted_item_quality
from entities.tree import Tree
from simulation.records import CensusSnapshot


class CompletedWorkSubTaskCommand:
    """Command object for applying the effects of a completed work sub-task."""

    def execute(self, world, npc, work_building, sub_task_data: dict):
        raise NotImplementedError


class ChopTreesSubTaskCommand(CompletedWorkSubTaskCommand):
    def execute(self, world, npc, work_building, sub_task_data: dict):
        tree_tile_obj = world.get_tile_at(npc.sub_task_target_coords[0], npc.sub_task_target_coords[1])
        if not (isinstance(tree_tile_obj, Tree) and tree_tile_obj.is_choppable):
            return False

        original_tree_type = tree_tile_obj.tree_type
        yielded_resources = tree_tile_obj.chop()
        logs_collected = yielded_resources.get("raw_log", 0)

        stump_key = tree_tile_obj.becomes_on_chop_key
        stump_def = TILE_DEFINITIONS.get(stump_key)
        if stump_def:
            world._change_map_tile(npc.sub_task_target_coords, stump_def, original_tree_type=original_tree_type)
            new_stump_tile = world.get_tile_at(npc.sub_task_target_coords[0], npc.sub_task_target_coords[1])
            if new_stump_tile:
                new_stump_tile.regrowth_timer = 100

        if logs_collected > 0:
            npc.add_item("raw_log", logs_collected)
            from engine import FloatingTextEffect
            world.visual_effects.append(FloatingTextEffect(npc.x, npc.y, f"+{logs_collected} Wood", color=(50, 255, 50)))
        return True


class ButcherCarcassSubTaskCommand(CompletedWorkSubTaskCommand):
    def execute(self, world, npc, work_building, sub_task_data: dict):
        target_tile_obj = world.get_tile_at(npc.sub_task_target_coords[0], npc.sub_task_target_coords[1])
        if not (target_tile_obj and target_tile_obj.name == "Animal Corpse"):
            return False

        animal_type = target_tile_obj.properties.get("animal_type")
        if animal_type in ANIMAL_DEFINITIONS:
            animal_def = ANIMAL_DEFINITIONS[animal_type]
            loot_table = animal_def.get("loot_drops", {})
            for item_key, loot_info in loot_table.items():
                if random.random() < loot_info.get("chance", 0):
                    quantity_info = loot_info["quantity"]
                    if isinstance(quantity_info, list) and len(quantity_info) == 2:
                        quantity = random.randint(quantity_info[0], quantity_info[1])
                    else:
                        quantity = int(quantity_info)
                    if quantity > 0:
                        npc.add_item(item_key, quantity)
                        from engine import FloatingTextEffect
                        item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
                        world.visual_effects.append(FloatingTextEffect(npc.x, npc.y, f"+{quantity} {item_name}", color=(50, 255, 50)))

        bones_def = DECORATION_ITEM_DEFINITIONS["bones"]
        world._change_map_tile(npc.sub_task_target_coords, bones_def)
        return True


class AddItemToNpcInventorySubTaskCommand(CompletedWorkSubTaskCommand):
    def __init__(self, item_key: str, quantity: int, *, crafted: bool = False):
        self.item_key = item_key
        self.quantity = quantity
        self.crafted = crafted

    def execute(self, world, npc, work_building, sub_task_data: dict):
        if self.crafted:
            npc.craft_item(self.item_key, self.quantity)
        else:
            npc.add_item(self.item_key, self.quantity)
        from engine import FloatingTextEffect
        item_name = ITEM_DEFINITIONS.get(self.item_key, {}).get("name", self.item_key)
        world.visual_effects.append(FloatingTextEffect(npc.x, npc.y, f"+{self.quantity} {item_name}", color=(50, 255, 50)))
        return True


class PurchaseFromSupplierSubTaskCommand(CompletedWorkSubTaskCommand):
    def __init__(self, supplier_getter_name: str, item_key: str, quantity: int, deposit_to_work_building: bool = False, log_message: str | None = None):
        self.supplier_getter_name = supplier_getter_name
        self.item_key = item_key
        self.quantity = quantity
        self.deposit_to_work_building = deposit_to_work_building
        self.log_message = log_message

    def execute(self, world, npc, work_building, sub_task_data: dict):
        supplier = getattr(world, self.supplier_getter_name)(npc)
        if not supplier:
            return False

        village = world._get_village_for_npc(npc)
        item_price = world.get_dynamic_price(self.item_key, village)
        total_cost = item_price * self.quantity
        if npc.economic.money < total_cost or supplier.building_inventory.get(self.item_key, 0) < self.quantity:
            return False

        moved_quantity = world._move_item_between_inventories(supplier.building_inventory, npc.economic.npc_inventory, self.item_key, self.quantity)
        if moved_quantity < self.quantity:
            return False
        npc.economic.money -= total_cost
        if self.deposit_to_work_building:
            world._move_item_between_inventories(npc.economic.npc_inventory, work_building.building_inventory, self.item_key, self.quantity)

        if self.log_message:
            world.add_message_to_chat_log(self.log_message.format(npc=npc.name, quantity=self.quantity))
        return True


class FetchWoodSubTaskCommand(CompletedWorkSubTaskCommand):
    def execute(self, world, npc, work_building, sub_task_data: dict):
        lumber_mill = world.buildings_by_id.get(npc.sub_task_target_coords)
        if not (lumber_mill and lumber_mill.building_type == "lumber_mill"):
            return False

        village = world._get_village_for_npc(npc)
        plank_price = world.get_dynamic_price("wooden_plank", village)
        planks_to_buy = 5
        if npc.economic.money >= plank_price * planks_to_buy and lumber_mill.building_inventory.get("wooden_plank", 0) >= planks_to_buy:
            lumber_mill.building_inventory["wooden_plank"] -= planks_to_buy
            npc.economic.money -= plank_price * planks_to_buy
            work_building.building_inventory["wooden_plank"] = work_building.building_inventory.get("wooden_plank", 0) + planks_to_buy
            return True
        return False


class WorkBuildingConversionSubTaskCommand(CompletedWorkSubTaskCommand):
    def __init__(self, consumed_item: str, consumed_amount: int, produced_item: str, produced_amount: int):
        self.consumed_item = consumed_item
        self.consumed_amount = consumed_amount
        self.produced_item = produced_item
        self.produced_amount = produced_amount

    def execute(self, world, npc, work_building, sub_task_data: dict):
        if work_building.building_inventory.get(self.consumed_item, 0) < self.consumed_amount:
            return False

        work_building.building_inventory[self.consumed_item] -= self.consumed_amount
        if hasattr(work_building.building_inventory, "add_item"):
            quality = roll_crafted_item_quality(
                career_level=getattr(getattr(npc, "career", None), "level", 0),
                work_performance=getattr(getattr(npc, "economic", None), "work_performance", 50),
            )
            work_building.building_inventory.add_item(
                self.produced_item,
                self.produced_amount,
                quality=quality,
                crafter_name=npc.name,
            )
        else:
            work_building.building_inventory[self.produced_item] = work_building.building_inventory.get(self.produced_item, 0) + self.produced_amount
        return True


class WriteBookSubTaskCommand(CompletedWorkSubTaskCommand):
    def execute(self, world, npc, work_building, sub_task_data: dict):
        if hasattr(world, "try_begin_scribe_chronicle"):
            return bool(world.try_begin_scribe_chronicle(npc))
        return False


class WriteBiographySubTaskCommand(CompletedWorkSubTaskCommand):
    def execute(self, world, npc, work_building, sub_task_data: dict):
        candidates = []
        for potential_subject in world.village_npcs + [world.player]:
            if potential_subject.id == npc.id:
                continue
            score = potential_subject.social.fame + potential_subject.social.infamy
            if score > 0:
                candidates.append((score, potential_subject))

        candidates.sort(key=lambda x: x[0], reverse=True)
        subject = candidates[0][1] if candidates else random.choice(world.village_npcs)
        subject_events = [e for e in npc.knowledge.known_events.values() if e.subject_id == subject.id]

        if len(subject_events) >= 1:
            new_book = world.records.compile_biography(
                title=f"Biography: {subject.name}",
                author_id=npc.id,
                author_name=npc.name,
                year_written=world.game_time // (DAY_LENGTH_TICKS * DAYS_PER_SEASON * 4),
                subject_name=subject.name,
                subject_title=subject.social.title,
                fame=subject.social.fame,
                infamy=subject.social.infamy,
                subject_events=subject_events,
            )
            world.records.register_book_item(new_book, work_building.building_inventory)
            world.add_message_to_chat_log(f"{npc.name} has written a biography of {subject.name}.")
            return True

        new_book = world.records.compile_biography(
            title=f"Biography: {subject.name}",
            author_id=npc.id,
            author_name=npc.name,
            year_written=world.game_time // (DAY_LENGTH_TICKS * DAYS_PER_SEASON * 4),
            subject_name=subject.name,
            subject_title=subject.social.title,
            fame=subject.social.fame,
            infamy=subject.social.infamy,
            subject_events=[],
        )
        world.records.register_book_item(new_book, work_building.building_inventory)
        world.add_message_to_chat_log(f"{npc.name} has written a general biography of {subject.name}.")
        return True


class CompileCensusSubTaskCommand(CompletedWorkSubTaskCommand):
    def execute(self, world, npc, work_building, sub_task_data: dict):
        village = world._get_village_for_npc(npc)
        if village:
            citizens = [n for n in world.village_npcs if world._get_village_for_npc(n) == village]
        else:
            citizens = world.village_npcs
        if not citizens:
            citizens = [npc]

        population = len(citizens)
        wealth_values = [n.economic.money for n in citizens]
        total_wealth = sum(wealth_values)
        avg_wealth = total_wealth / max(1, len(wealth_values))
        richest = max(citizens, key=lambda n: n.economic.money)
        poorest = min(citizens, key=lambda n: n.economic.money)

        professions = {}
        for citizen in citizens:
            profession = citizen.economic.profession
            professions[profession] = professions.get(profession, 0) + 1

        year = world.game_time // (DAY_LENGTH_TICKS * DAYS_PER_SEASON * 4)
        snapshot = world.records.record_census_snapshot(
            CensusSnapshot(
                village_name=village.name if village and hasattr(village, "name") else "Unknown",
                year=year,
                population=population,
                total_wealth=total_wealth,
                average_wealth=int(avg_wealth),
                richest_name=richest.name,
                richest_wealth=richest.economic.money,
                poorest_name=poorest.name,
                poorest_wealth=poorest.economic.money,
                profession_counts=professions,
            )
        )
        new_book = world.records.compile_census_report(
            title=f"Census Report {year}",
            author_id=npc.id,
            author_name=npc.name,
            snapshot=snapshot,
        )
        world.records.register_book_item(new_book, work_building.building_inventory)
        world.add_message_to_chat_log(f"{npc.name} has filed the official census.")
        return True


class FarmerTileTransitionSubTaskCommand(CompletedWorkSubTaskCommand):
    def __init__(self, *, consume_output: bool = False, harvest_output: bool = False):
        self.consume_output = consume_output
        self.harvest_output = harvest_output

    def execute(self, world, npc, work_building, sub_task_data: dict):
        target_tile_obj = world.get_tile_at(npc.sub_task_target_coords[0], npc.sub_task_target_coords[1])
        original_tile_name = target_tile_obj.name if target_tile_obj else "None"
        expected_tile_name = TILE_DEFINITIONS.get(sub_task_data.get("target_tile_type_key"), {}).get("name")

        if not (target_tile_obj and original_tile_name == expected_tile_name):
            return False

        if self.harvest_output:
            if not target_tile_obj.properties.get("is_harvestable"):
                return False
            world._produce_sub_task_output(npc, work_building, sub_task_data, target_tile_obj=target_tile_obj)
            becomes_key = target_tile_obj.properties.get("becomes_on_harvest_key") or sub_task_data.get("becomes_tile_type_key")
        else:
            if self.consume_output and not world._produce_sub_task_output(npc, work_building, sub_task_data):
                return False
            becomes_key = sub_task_data.get("becomes_tile_type_key")

        new_tile_def = TILE_DEFINITIONS.get(becomes_key)
        if new_tile_def:
            world._change_map_tile(npc.sub_task_target_coords, new_tile_def)
            return True
        return False


class FishAtSpotSubTaskCommand(CompletedWorkSubTaskCommand):
    """Finishing a stint at the water's edge actually catches something.

    World.npc_attempt_fish was fully implemented and had no caller anywhere.
    The Fisherman's "fish_at_spot" declares no produces_item_at_workplace, so it
    fell through to the default command, which produces whatever the sub-task
    declares - nothing. A fisherman worked a full day at the riverbank and the
    village never saw a fish.
    """

    def execute(self, world, npc, work_building, sub_task_data: dict):
        water = world.find_water_near(npc.x, npc.y)
        if water is None:
            return False
        world.npc_attempt_fish(npc, water[0], water[1])
        return True


class DefaultProduceOutputSubTaskCommand(CompletedWorkSubTaskCommand):
    def execute(self, world, npc, work_building, sub_task_data: dict):
        return world._produce_sub_task_output(npc, work_building, sub_task_data)


def create_completed_work_sub_task_commands():
    return {
        "chop_trees": ChopTreesSubTaskCommand(),
        "butcher_carcass": ButcherCarcassSubTaskCommand(),
        "mine_ore": AddItemToNpcInventorySubTaskCommand("iron_ore", 1),
        "fetch_ore": PurchaseFromSupplierSubTaskCommand("_find_nearest_mine", "iron_ore", 5),
        "fetch_coal": PurchaseFromSupplierSubTaskCommand("_find_nearest_mine", "coal", 3, deposit_to_work_building=True),
        "fetch_wood": FetchWoodSubTaskCommand(),
        "craft_furniture": WorkBuildingConversionSubTaskCommand("wooden_plank", 2, "wooden_chair", 1),
        "fetch_wheat": PurchaseFromSupplierSubTaskCommand("_find_nearest_farm", "wheat", 5, deposit_to_work_building=True, log_message="{npc} the Miller bought {quantity} wheat."),
        "fetch_flour": PurchaseFromSupplierSubTaskCommand("_find_nearest_mill", "flour", 5, deposit_to_work_building=True),
        "write_book": WriteBookSubTaskCommand(),
        "write_biography": WriteBiographySubTaskCommand(),
        "compile_census": CompileCensusSubTaskCommand(),
        "mill_flour": WorkBuildingConversionSubTaskCommand("wheat", 1, "flour", 1),
        "fish_at_spot": FishAtSpotSubTaskCommand(),
        "till_soil": FarmerTileTransitionSubTaskCommand(),
        "plant_seeds": FarmerTileTransitionSubTaskCommand(consume_output=True),
        "harvest_crops": FarmerTileTransitionSubTaskCommand(harvest_output=True),
    }
