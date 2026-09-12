"""Preset encounter, ordinary input and world ticks; no aimed/forced damage.

Only starting terrain, actors, hostility and owned supplies are arranged.
Wolves, guards, civilians and healers make their own production-rule decisions.
"""
import json
from pathlib import Path
import random

import engine
import main
from config import DAY_LENGTH_TICKS
from data.tiles import TILE_DEFINITIONS
from entities.animal import Animal
from entities.items import ItemReference
from rendering.console_renderer import draw
from simulation.systems import body_combat as combat
from simulation.systems.combat_response import distance
from tools.capture_ui_font_check import _save


def run():
    world = engine.World(seed=451, player_first_name="Mara")
    world.game_time = DAY_LENGTH_TICKS//2
    ox, oy = next((x, y) for y in range(20, 300, 20) for x in range(20, 300, 20)
                  if all(world.get_building_at(x+dx, y+dy) is None for dx in range(16) for dy in range(16)))
    for x in range(ox, ox+16):
        for y in range(oy, oy+16):
            world.get_tile_at(x, y)
            world._change_map_tile((x, y), TILE_DEFINITIONS["plains"])
    player = world.player
    world._update_entity_position(player, ox+8, oy+8)
    wolf = Animal(player.x+5, player.y, name="Grey Wolf", animal_type="wolf")
    wolf.combat.is_hostile_to_player = True
    guard = engine.NPC(player.x-2, player.y-1, name="Rowan")
    guard.economic.profession = "Guard"
    guard.equipment.weapon.bind(ItemReference("axe_stone"))
    healer = engine.NPC(player.x-3, player.y+2, name="Elara")
    healer.economic.profession = "Healer"
    healer.add_item("bandage", 8)
    healer.add_item("splint", 4)
    civilian = engine.NPC(player.x, player.y-3, name="Tessa")
    world.npcs, world.village_npcs = [wolf], [guard, healer, civilian]
    from simulation.starting_wardrobe import seed_starting_wardrobes
    seed_starting_wardrobes(world)  # Starting possessions for these preset actors.
    world._mark_entity_positions_dirty()
    for key in ("wool_shirt", "wool_trousers", "leather_boots", "axe_stone"):
        player.add_item(key)
        world.use_item(key)
    combat.advance_bodies(world)
    random.seed(117)
    world.is_paused = True
    world.game_state = "PLAYING"
    world.mouse_x = world.mouse_y = -1
    main._ensure_zoom_state(world)
    world.zoom_index = 2
    tiles, console = main.load_custom_tileset(), main.create_console()
    out = Path("artifacts/body-combat/playable")
    out.mkdir(parents=True, exist_ok=True)

    def capture(name):
        world._update_light_level_and_fov()
        world._update_player_fov()
        for actor in [player, *world.all_npcs]:
            actor.render_x, actor.render_y = actor.x, actor.y
        draw(console, world, *main._get_camera_origin(world))
        console.print(2, 4, "PRESET ENCOUNTER / REAL INPUT + WORLD TICKS", fg=(234, 209, 158))
        _save(console, tiles, str(out / f"{name}.png"))

    world._update_light_level_and_fov()
    world._update_player_fov()
    main.open_combat_menu(world)
    capture("01-combat-picker")
    world.interaction_context["active"] = False
    witnessed = False
    for _ in range(180):
        world.update()
        if player.combat.anatomy.wounds and not witnessed:
            capture("02-witnessed-attack")
            witnessed = True
        if player.physical.is_dead or wolf.physical.is_dead or distance(player, wolf) > 14:
            break
        if (distance(player, wolf) <= 1 and combat.can_act(player)
                and world.game_time >= player.combat.anatomy.attack_ready_tick):
            main.open_combat_menu(world)
            ctx = world.interaction_context
            if ctx.get("active"):
                target_index = next((i for i, entry in enumerate(ctx["target_entities"]) if entry["data"] is wolf), None)
                if target_index is not None:
                    ctx["selected_entity_index"] = target_index
                    main.execute_interaction(world, None)
                ctx["active"] = False
    capture("03-encounter-outcome")
    for _ in range(300):
        if player.physical.is_dead:
            break
        world.update()
    if not player.physical.is_dead:
        world.examine_body()
    capture("04-after-care")
    report = dict(ticks=world.game_time-DAY_LENGTH_TICKS//2, player_alive=not player.physical.is_dead,
                  wolf_alive=not wolf.physical.is_dead, wolf_distance=distance(player, wolf),
                  player_wounds=len(player.combat.anatomy.wounds),
                  dressed_wounds=sum(w.dressed for w in player.combat.anatomy.wounds),
                  healer_bandages_remaining=healer.economic.npc_inventory.get("bandage", 0),
                  healer_task=healer.schedule.current_task,
                  healer_distance=distance(healer, player),
                  healer_path_length=len(healer.schedule.current_path),
                  healer_timer=healer.task_timer,
                  healer_alive=not healer.physical.is_dead,
                  guard_hostile_to_player=guard.combat.is_hostile_to_player,
                  pending_model_tasks=len(world._background_llm_tasks))
    (out / "outcome.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    run()
