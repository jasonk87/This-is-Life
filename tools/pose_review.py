"""Native modular-pose fixtures. Scripted review states, not emergent events.

Uses the production rig, furniture contacts and actual owned equipment. No
source art, save games or external services are changed by this harness.
"""

import argparse
from pathlib import Path
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
from entities.base import Appearance, NPC
from rendering import character_layers as layers, interior_art, pixel_scene as pixels
from rendering.people_art import Activity
from tools.capture_ui_font_check import _save
from tools.character_review import wear


def action_sequence(world, actor, record):
    """Drive one disposable NPC through real handlers in a staged test clearing.

    Setup deliberately relocates the actor and places test fixtures. After that,
    movement, tree work, hauling, sitting and speech use production handlers.
    This is an integration scenario, NOT evidence of spontaneous NPC decisions.
    """
    from data.decorations import DECORATION_ITEM_DEFINITIONS as DECOR
    from data.tiles import TILE_DEFINITIONS
    from presentation.ambient_speech import add_ambient_speech
    from rendering import actor_motion, people_art, furniture_occupancy
    from simulation.activity import advance_activity
    from simulation.systems.interaction import ActionIntent
    from simulation.systems.scheduling import run_npc_furniture_interaction_policy

    # Outside building-local tile maps, which correctly override the chunk map.
    ox, oy = next((x,y) for y in range(20,300,20) for x in range(20,300,20)
                  if all(world.get_building_at(x+dx,y+dy) is None
                         for dy in range(9) for dx in range(11)))
    for y in range(oy,oy+9):
        for x in range(ox,ox+11):
            world.get_tile_at(x,y)  # Ensure the disposable chunk is loaded.
            world._change_map_tile((x,y),TILE_DEFINITIONS["wood_floor"])
    chair,bed,tree = (ox+4,oy+4),(ox+7,oy+3),(ox+3,oy+2)
    world._change_map_tile(chair,DECOR["wooden_chair"])
    world._change_map_tile(bed,DECOR["wooden_bed"])
    from data.dawnlike import TREE_SPRITES
    tree_def = dict(char=TREE_SPRITES["oak_tree"], color=(34,139,34), passable=False,
                    name="Oak Tree", properties={"is_tree":True,"blocks_fov":True})
    world._change_map_tile(tree,tree_def)
    if getattr(actor,"render_disabled",False):
        world.wake_entity(actor)
    actor.is_sleeping = actor.is_sitting = False
    actor.current_activity = None
    actor.task_context,actor.task_context_data = None,{}
    actor.task_timer = 0
    actor.schedule.current_task = "idle"
    actor.schedule.current_path = []
    actor.schedule.active_interaction_id = None
    world._update_entity_position(actor,ox+3,oy+4)
    actor.render_x,actor.render_y = actor.x,actor.y
    world._update_entity_position(world.player,ox+5,oy+6)
    world.player.render_x,world.player.render_y = world.player.x,world.player.y
    world._update_light_level_and_fov()
    world._update_player_fov()
    world.active_ambient_speech.clear()
    actor_motion.reset()
    identity,held = layers.signature(actor),layers.equipped(actor,"weapon")
    results = []

    def capture(label,expected):
        assert layers.signature(actor) == identity
        assert layers.equipped(actor,"weapon") == held
        image,activity,token = people_art.body_frame(world,actor,4)
        assert activity.kind == expected, (label,activity)
        results.append((label,activity.kind,token[-1],token[7]))
        record(label,world,actor)

    def step():
        world.game_time += 1
        world._update_npc_movement()

    def settle():
        actor.render_x,actor.render_y = actor.x,actor.y
        world.game_time += 5

    def route(target):
        actor.schedule.current_path = world.calculate_path(actor.x,actor.y,*target) or []
        actor.schedule.current_destination_coords = target
        for _ in range(40):
            if (actor.x,actor.y) == target:
                break
            step()
        assert (actor.x,actor.y) == target
        settle()

    capture("01-standing","idle")
    actor.schedule.current_path = world.calculate_path(actor.x,actor.y,ox+3,oy+3)
    step()
    capture("02-walking","walk")
    settle()
    resolver = world.interaction_resolver
    result = resolver.resolve(ActionIntent(actor.id,"chop_tree",target_pos=tree),world)
    assert result.success
    actor.schedule.active_interaction_id = result.started_interaction_id
    capture("03-working","chop")
    for _ in range(20):
        if result.started_interaction_id not in resolver.active_interactions:
            break
        world.game_time += 1
        resolver.advance_active_interaction(result.started_interaction_id,world)
    assert world.items_on_map[tree].get("raw_log",0) > 0
    actor.schedule.active_interaction_id = None
    stockpile = world.create_stockpile(ox+8,oy+6,accepted_item_types={"raw_log"},max_item_count=50)
    assert stockpile
    assert world._assign_source_to_stockpile_haul_task(actor,item_key="raw_log")
    route(tuple(actor.task_context_data["source"]["coords"]))
    assert world._handle_npc_stockpile_haul_task(actor)
    step()
    capture("04-carrying-while-walking","carry")
    for _ in range(40):
        if actor.task_context != "stockpile_hauling":
            break
        step()
        world._handle_npc_stockpile_haul_task(actor)
    assert actor.task_context != "stockpile_hauling"
    route((chair[0]-1,chair[1]))
    logical = (actor.x,actor.y)
    assert resolver.resolve(ActionIntent(actor.id,"sit_on_chair",target_pos=chair,
                                          payload={"duration":4}),world).success
    capture("05-seated","sit")
    assert (actor.x,actor.y) == logical  # Render attachment never moves the NPC.
    add_ambient_speech(world,speaker=actor,text="The timber is delivered.",
                       source_type="activity",ttl_ticks=2)
    capture("06-seated-talking","talk")
    for _ in range(8):
        world.game_time += 1
        run_npc_furniture_interaction_policy(world,actor)
        advance_activity(actor,world)
        if not actor.is_sitting:
            break
    assert not actor.is_sitting
    assert furniture_occupancy.attachment_for(world,actor) is None
    capture("07-standing-again","idle")
    route((bed[0]-1,bed[1]))
    assert resolver.resolve(ActionIntent(actor.id,"sleep_in_bed",target_pos=bed),world).success
    capture("08-sleeping","sleep")
    assert furniture_occupancy.attachment_for(world,actor).kind == "reclining"
    return results


def pose_sheet(console, tiles, out, phase=1, outfit="wool"):
    actor = NPC(0, 0, "Elias")
    actor.gender, actor.age = "male", 35
    actor.appearance = Appearance(hairstyle="short", hair_color="brown",
                                 facial_hair="full_beard", skin_tone="light", face_variant=0)
    for item in ("wool_shirt", "wool_trousers", "leather_boots"):
        wear(actor, item)
    if outfit == "armor":
        for item in ("iron_breastplate","iron_helmet","axe_stone"):
            wear(actor,item)
    elif outfit == "cloak":
        for item in ("fur_cloak","wool_cap","knife_stone"):
            wear(actor,item)
    actor.add_item("raw_log", 3)
    columns = (("STAND", "idle", None), ("WALK", "walk", None),
               ("SIT", "sit", "wooden_chair"), ("SLEEP", "sleep", "wooden_bed"),
               ("CARRY", "carry", None), ("WORK", "chop", None), ("TALK", "talk", None))
    console.clear(bg=(23, 31, 30))
    pixels.begin_frame()
    console.print(2, 1, f"ELIAS / ONE PERSON, SEVEN POSES / {outfit.upper()}", fg=(226, 202, 148))
    console.print(2, 2, "Controlled renderer fixture / same face, beard and actual clothing", fg=(154, 173, 160))
    for row, direction in enumerate(("south", "east", "north", "west")):
        console.print(2, 5+row*11, direction.upper(), fg=(155, 173, 160))
        for col, (label, kind, furniture) in enumerate(columns):
            x, y = (3+col*11)*16, (6+row*11)*16
            posture = ("seated" if kind=="sit" else "reclining") if furniture else None
            facing = "south" if furniture else direction
            activity = Activity(kind, "raw_log" if kind=="carry" else None)
            image, _, token = layers.frame(NS(), actor, 5, activity, facing, phase,
                                          kind in {"walk", "carry"}, posture)
            px, py = x+(144-image.shape[1])//2, y+144-image.shape[0]
            if furniture:
                fixture = interior_art.object_pixels(furniture, 5)
                fx, fy = x+(144-fixture.shape[1])//2, y+144-fixture.shape[0]
                pixels.stamp(console,fixture,fx,fy,token=("pose-fixture",furniture))
                ax, ay = interior_art.support_socket(furniture,fixture)
                bx, by = layers.support_socket(image,token)
                px, py = fx+ax-bx, fy+ay-by
            pixels.stamp(console,image,px,py,token=token)
            if furniture:
                pixels.stamp(console,interior_art.foreground_pixels(furniture,5),fx,fy,
                             token=("pose-cover",furniture))
            if row==0:
                console.print(3+col*11,4,label,fg=(222,196,143))
    suffix = "" if outfit=="wool" else f"-{outfit}"
    _save(console,tiles,str(out / f"same-person-poses-{phase}{suffix}.png"))


def main_review():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="artifacts/embodied-characters")
    parser.add_argument("--sequence", action="store_true")
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True,exist_ok=True)
    tiles, console = main.load_custom_tileset(), main.create_console()
    for phase in range(4):
        pose_sheet(console,tiles,out,phase)
    for outfit in ("armor","cloak"):
        pose_sheet(console,tiles,out,1,outfit)
    if args.sequence:
        import engine
        from rendering.console_renderer import draw
        engine.ENABLE_LLM_CONNECTION = engine.ENABLE_OLLAMA_CONNECTION = False
        world = engine.World(seed=123,player_first_name="Mara")
        world._pre_simulate_world()
        world.is_paused,world.game_state = True,"PLAYING"
        world.mouse_x = world.mouse_y = -1
        main._ensure_zoom_state(world)
        world.zoom_index = 2
        actor = next(a for a in world.village_npcs if not a.physical.is_dead and not getattr(a,"animal_type",None))
        for key in ("wool_shirt","wool_trousers","leather_boots","knife_stone"):
            wear(actor,key)

        def record(label,world,actor):
            draw(console,world,*main._get_camera_origin(world))
            console.print(2,4,f"SCRIPTED INTEGRATION: {label}",fg=(234,209,158))
            _save(console,tiles,str(out / f"action-{label}.png"))

        print(action_sequence(world,actor,record))
    print(f"Native pose fixtures: {out.resolve()}")


if __name__ == "__main__":
    main_review()
