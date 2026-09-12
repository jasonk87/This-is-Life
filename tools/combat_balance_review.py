"""Reproducible local-dice balance audit, not spontaneous gameplay evidence."""
from collections import Counter
import json
from pathlib import Path
import random

import config
from data.tiles import TILE_DEFINITIONS
from engine import World
from entities.animal import Animal
from entities.anatomy import Anatomy
from entities.items import ItemReference
from entities import body_model as rules
from simulation.systems import body_combat as combat
from simulation.skills import SkillTracker


def sample_bites(world, encounters=100, seed=20260912):
    """100 fresh encounters x three unaimed bites, with production attack rules."""
    player = world.player
    wolf = Animal(player.x+1, player.y, name="Audit Wolf", animal_type="wolf")
    world.npcs, world.village_npcs = [wolf], []
    world._mark_entity_positions_dirty()
    reports = {}
    for scenario, clothing in (("unarmored", {}), ("wool_and_boots", {
            "body": "wool_shirt", "legs": "wool_trousers", "feet": "leather_boots"})):
        random.seed(seed)
        regions = Counter()
        attempts = hits = wounds = new_fractures = fresh_hits = fresh_fractures = 0
        for _ in range(encounters):
            player.combat.anatomy = rules.upgrade(Anatomy.humanoid(), now=world.game_time)
            wolf.combat.anatomy = rules.upgrade(Anatomy.humanoid(), "wolf", now=world.game_time)
            wolf.skills = SkillTracker()  # Fresh encounter, not 100 fights of training.
            player.physical.is_dead = wolf.physical.is_dead = False
            player.physical.status_effects.clear()
            world.game_state = "PLAYING"
            for slot in ("body", "head", "legs", "feet", "hands", "weapon"):
                getattr(player.equipment, slot).clear()
            for slot, key in clothing.items():
                getattr(player.equipment, slot).bind(ItemReference(key))
            for bite in range(3):
                before = {w.part for w in player.combat.anatomy.wounds if w.fracture}
                result = combat.attack(world, wolf, player)
                after = {w.part for w in player.combat.anatomy.wounds if w.fracture}
                attempts += result.attempted
                hits += result.hit
                wounds += result.wound_id is not None
                new_fractures += len(after-before)
                if result.hit:
                    regions[result.part] += 1
                if bite == 0:
                    fresh_hits += result.hit
                    fresh_fractures += len(after-before)
                world.game_time += 5
        reports[scenario] = dict(encounters=encounters, attempts=attempts, hits=hits,
            wounds=wounds, target_regions=dict(sorted(regions.items())),
            new_fractured_regions=new_fractures, first_bite_hits=fresh_hits,
            first_bite_fractures=fresh_fractures)
    body = rules.upgrade(Anatomy.humanoid())
    body.blood = .5
    recovery = []
    for day in range(1, 8):
        rules.advance(body, day*config.DAY_LENGTH_TICKS, resting=True)
        recovery.append(dict(day=day, blood=round(body.blood, 4)))
    reports["separate_50_percent_blood_reserve_fixture"] = recovery
    return reports


def run():
    world = World(seed=451)
    world.game_time = config.DAY_LENGTH_TICKS//2
    world._update_entity_position(world.player, 50, 50)
    for x in (50, 51):
        world.get_tile_at(x, 50)
        world._change_map_tile((x, 50), TILE_DEFINITIONS["plains"])
    reports = sample_bites(world)
    output = Path("artifacts/body-combat/balance-audit.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    run()
