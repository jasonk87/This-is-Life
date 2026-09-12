"""Native renderer fixtures for wounds/scars and real-input archery. No model use."""
import json
from pathlib import Path
import random
import main
from engine import World, NPC
from entities import body_model as rules
from entities.animal import Animal
from entities.items import ItemReference
from config import DAY_LENGTH_TICKS as DAY
from data.tiles import TILE_DEFINITIONS
from rendering import character_layers as layers, pixel_scene as pixels, widgets, console_renderer as cr
from rendering.people_art import Activity
from simulation.systems import body_combat as combat
from tools.capture_ui_font_check import _save


def run():
    out = Path("artifacts/scars-archery")
    out.mkdir(parents=True,exist_ok=True)
    world = World(seed=451,player_first_name="Mara")
    tiles,console = main.load_custom_tileset(),main.create_console()
    actor = NPC(50,50,name="Elias")
    actor.appearance.facial_hair = "short_beard"
    actor.equipment.body.bind(ItemReference("wool_shirt"))
    actor.equipment.legs.bind(ItemReference("wool_trousers"))
    actor.equipment.feet.bind(ItemReference("leather_boots"))
    body = combat.ensure_body(actor,world.game_time)
    for part in ("head","right_hand"):
        rules.inflict(body,part,"cut",4,world.game_time,weapon="Knife")
    actor.add_item("bandage",2)
    console.clear(bg=(22,30,28))
    widgets.text_line(console,2,1,"ONE PERSON / REAL WOUNDS, DRESSINGS, SCARS",color=(223,193,120))
    for col,title in enumerate(("Fresh cuts","Dressed","Healed scars")):
        if col == 1:
            combat.treat(world,actor,actor,"bandage")
            combat.treat(world,actor,actor,"bandage")
        if col == 2:
            rules.advance(body,world.game_time+DAY*7,resting=True)
        x = 4+col*32
        widgets.text_line(console,x,4,title,color=(223,193,120))
        for row,(kind,posture) in enumerate((("idle",None),("sit","seated"),("sleep","reclining"))):
            image,_,token = layers.frame(world,actor,6,Activity(kind),"south",0,False,posture)
            pixels.stamp(console,image,(x+3)*16,(7+row*14)*16,token=token)
            widgets.text_line(console,x,6+row*14,kind,color=(163,181,159))
    _save(console,tiles,out/"01-wound-history.png")
    # Initial layout only is staged. The shot below uses ordinary F/Enter input.
    ox,oy = next((x,y) for y in range(20,300,20) for x in range(20,300,20)
                 if all(world.get_building_at(x+dx,y+dy) is None for dx in range(18) for dy in range(18)))
    for x in range(ox,ox+18):
        for y in range(oy,oy+18):
            world.get_tile_at(x,y)
            world._change_map_tile((x,y),TILE_DEFINITIONS["plains"])
    world._update_entity_position(world.player,ox+6,oy+8)
    wolf = Animal(ox+13,oy+8,name="Grey Wolf",animal_type="wolf")
    world.npcs,world.village_npcs = [wolf],[]
    world._mark_entity_positions_dirty()
    world.player.equipment.weapon.bind(ItemReference("short_bow"))
    world.player.add_item("arrow",4)
    combat.advance_bodies(world)
    world._update_light_level_and_fov()
    world._update_player_fov()
    world.game_state,world.is_paused = "PLAYING",False
    main._ensure_zoom_state(world)
    world.zoom_index = 2
    world.mouse_x = world.mouse_y = -1
    random.seed(73)
    main.open_combat_menu(world)
    main.execute_interaction(world,None)
    main.open_combat_menu(world)
    world.update_animations(.15)
    cr.draw(console,world,*main._get_camera_origin(world))
    _save(console,tiles,out/"02-archery.png")
    report = dict(scars=len(body.scars),dressing_supplies_left=actor.economic.npc_inventory.get("bandage",0),
                  arrows_remaining=world.player.economic.inventory.get("arrow",0),
                  attack_recovery=world.player.combat.anatomy.attack_ready_tick-world.game_time,
                  pending_model_tasks=len(world._background_llm_tasks))
    (out/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__": run()
