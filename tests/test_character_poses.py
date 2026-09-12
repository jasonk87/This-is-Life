"""Embodied character contracts: shared identity, joint contact and state truth."""

import copy
import pickle
import random
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

import main
from entities.base import Appearance, NPC
from rendering import character_layers as layers, character_pose as poses
from rendering import people_art as people, interior_art, actor_motion, pixel_scene as pixels
from runtime_compat import np
from tests.test_world_art import native_art, clear_composites
from tests.test_furniture_occupancy import occupied_room, sit
from tools.character_review import wear
from tools.street_review import activity_actor


def elias():
    actor = NPC(5, 5, "Elias")
    actor.gender, actor.age = "male", 35
    actor.appearance = Appearance(hairstyle="short", facial_hair="full_beard", face_variant=0)
    for key in ("wool_shirt", "wool_trousers", "leather_boots"):
        wear(actor, key)
    return actor


@pytest.mark.parametrize("kind,posture", [("idle",None), ("walk",None), ("sit","seated"),
    ("sleep","reclining"), ("carry",None), ("chop",None), ("talk",None)])
def test_same_person_and_actual_gear_survive_every_pose(native_art, kind, posture):
    actor = elias()
    state = layers.signature(actor)
    before = pickle.dumps(actor)
    rig = layers.rig(state,"south",kind,1,posture,item="raw_log")
    assert pickle.dumps(actor) == before
    # Every pose mounts the same identity head, not a profession-specific person.
    pose = poses.layout("south",kind,1,posture,kind=="walk")
    head = layers.identity_head(state,"south",rest=pose.reclined)
    # Unoccluded crown: raised tools can legitimately overlap the outer margin.
    top = rig[pose.head[1]:pose.head[1]+10,26:38]
    crown = head[:10,12:24]
    mask = crown[:,:,3] > 250
    assert np.array_equal(top[mask],crown[mask])
    assert layers.signature(pickle.loads(before)) == state
    for slot, replacement in (("body","leather_jerkin"),("legs","linen_trousers"),
                              ("feet","leather_shoes"),("head","wool_cap")):
        changed = pickle.loads(before)
        wear(changed,replacement)
        new = layers.rig(layers.signature(changed),"south",kind,1,posture,item="raw_log")
        assert not np.array_equal(new,rig), (kind,slot)
        assert layers.signature(changed)[1:8] == state[1:8]


@pytest.mark.parametrize("key", ["wooden_chair","wooden_bed","bed_simple"])
@pytest.mark.parametrize("zoom", [1,2,3,4])
def test_furniture_socket_is_exact_and_never_drifts(native_art,key,zoom):
    world,actor,_ = occupied_room(key,zoom)
    if "bed" in key:
        actor.x,actor.is_sleeping = 6,True
    else:
        sit(world,actor)
    before = copy.deepcopy(actor.__dict__)
    for tick in (0,2,4,6,40):
        world.game_time = tick
        image,_,token,px,py = people.placement(world,actor,zoom,0,0)
        fixture,fx,fy = interior_art.placement(key,zoom,6,5,0,0)
        ax,ay = layers.support_socket(image,token)
        bx,by = interior_art.support_socket(key,fixture)
        assert (px+ax,py+ay) == (fx+bx,fy+by)
    assert actor.__dict__ == before


def test_sitting_bends_knees_without_shrinking_head_or_chest(native_art):
    stand = poses.layout("south")
    seated = poses.layout("south","sit",posture="seated")
    assert seated.head[0] == stand.head[0]
    assert seated.knees[0][0] < seated.hips[0][0]
    assert seated.knees[1][0] > seated.hips[1][0]
    assert seated.ankles[0][1] > seated.knees[0][1] > seated.hips[0][1]
    actor = elias()
    images = [layers.frame(NS(),actor,4,people.Activity(k),"south",0,False,p)[0]
              for k,p in (("idle",None),("sit","seated"))]
    assert images[0].shape[1] == images[1].shape[1]
    assert images[1].shape[0] < images[0].shape[0]


@pytest.mark.parametrize("direction", ["south","east","north","west"])
def test_carry_keeps_grip_while_legs_walk_and_item_changes_in_cache(native_art,direction):
    actor = elias()
    state = layers.signature(actor)
    for phase in range(4):
        pose = poses.layout(direction,"carry",phase,moving=True)
        # Both palms stay level with the load despite alternating legs.
        assert max(abs(hand[1]-pose.chest[1]) for hand in pose.hands) <= 16
    a = layers.rig(state,direction,"carry",1,moving=True,item="raw_log")
    b = layers.rig(state,direction,"carry",3,moving=True,item="raw_log")
    assert not np.array_equal(a,b)
    front_a = layers.frame(NS(),actor,4,people.Activity("carry","raw_log"),direction,1,True,None)
    front_b = layers.frame(NS(),actor,4,people.Activity("carry","bread"),direction,1,True,None)
    assert front_a[2] != front_b[2]
    assert not np.array_equal(front_a[0],front_b[0])


def test_layered_carry_item_is_composited_at_hands_with_back_occlusion(native_art):
    state = layers.signature(elias())
    for direction in ("south","north"):
        pose = poses.layout(direction,"carry")
        blank = layers.rig(state,direction,"carry")
        carrying = layers.rig(state,direction,"carry",item="raw_log")
        center = (slice(pose.chest[1]+3,pose.chest[1]+10),slice(29,35))
        if direction=="north":
            assert np.array_equal(blank[center],carrying[center])
        else:
            assert not np.array_equal(blank[center],carrying[center])
    world,actor = activity_actor("carry")
    with patch.object(pixels,"stamp") as stamp:
        people.draw_person(main.create_console(),world,actor,0,0,5,5)
    assert not any(c.kwargs["token"][0] in {"carry32-small","equipment32"}
                   for c in stamp.call_args_list)


@pytest.mark.parametrize("kind", ["chop","hammer","prepare","eat","talk","fight"])
def test_action_gestures_articulate_the_wrist_without_changing_identity(native_art,kind):
    state = layers.signature(elias())
    a,b = (layers.rig(state,"east",kind,p) for p in (0,1))
    assert not np.array_equal(a,b)
    assert np.array_equal(a[:15,24:37],b[:15,24:37])
    for phase in range(4):
        image = layers.rig(state,"south",kind,phase)
        assert not image[0,:,3].any()  # No clipped raised tool/head.
        assert not image[:,-1,3].any()


@pytest.mark.parametrize("kind,posture", [("idle",None),("carry",None),("chop",None),
                                         ("sit","seated"),("sleep","reclining")])
def test_equipped_weapon_follows_hand_or_belt_and_invalidates_frame(native_art,kind,posture):
    actor = elias()
    activity = people.Activity(kind,"raw_log" if kind=="carry" else None)
    a = layers.frame(NS(),actor,4,activity,"south",0,False,posture)
    wear(actor,"knife_stone")
    b = layers.frame(NS(),actor,4,activity,"south",0,False,posture)
    assert a[2] != b[2] and not np.array_equal(a[0],b[0])
    assert layers.equipped(actor,"weapon") == "knife_stone"


def test_pose_renderer_does_not_advance_simulation_or_rng(native_art):
    world,actor,_ = occupied_room()
    sit(world,actor)
    before,rng,fov = pickle.dumps(actor),random.getstate(),world.player_fov_map.copy()
    for _ in range(3):
        people.draw_person(main.create_console(),world,actor,0,0,5,5)
    assert pickle.dumps(actor) == before
    assert random.getstate() == rng
    assert np.array_equal(world.player_fov_map,fov)


def test_matching_equipped_axe_is_the_work_tool_not_a_second_belt_item(native_art):
    actor = elias()
    wear(actor,"axe_stone")
    assert poses.active_tool("chop",layers.equipped(actor,"weapon")) == "axe_stone"
    assert poses.active_tool("hammer","axe_stone") is None
    assert poses.active_tool("chop","knife_stone") is None
    state = layers.signature(actor)
    poses.clear()
    with patch.object(pixels,"tile_pixels",wraps=pixels.tile_pixels) as tile:
        poses.render(state,"south","chop",1,None,held="axe_stone")
    from data.dawnlike import ITEM_SPRITES
    assert [c.args[0] for c in tile.call_args_list] == [ITEM_SPRITES["axe_stone"]]


def test_removing_carried_inventory_removes_carry_even_if_schedule_is_stale(native_art):
    world,actor = activity_actor("carry")
    assert people.body_frame(world,actor,3)[1].kind == "carry"
    actor.economic.npc_inventory.clear()
    assert people.body_frame(world,actor,3)[1].kind != "carry"


def test_walk_to_chair_then_speech_is_not_hidden_by_movement_grace(native_art):
    from presentation.ambient_speech import add_ambient_speech
    world,actor,_ = occupied_room()
    actor.x = actor.render_x = 4
    people.body_frame(world,actor,3)
    actor.x = actor.render_x = 5
    world.game_time = 1
    assert people.body_frame(world,actor,3)[1].kind == "walk"
    sit(world,actor)
    add_ambient_speech(world,speaker=actor,text="A moment to rest.",ttl_ticks=2)
    _,activity,token = people.body_frame(world,actor,3)
    assert activity.kind == "talk" and token[-1] == "seated" and not token[7]
    world.game_time = 3
    assert people.body_frame(world,actor,3)[1].kind == "sit"


def test_one_npc_real_action_sequence_retains_identity_and_gear(native_art,monkeypatch):
    import engine
    from tools.pose_review import action_sequence
    monkeypatch.setattr(engine,"ENABLE_LLM_CONNECTION",False)
    monkeypatch.setattr(engine,"ENABLE_OLLAMA_CONNECTION",False)
    world = engine.World(seed=123)
    world._pre_simulate_world()
    actor = next(a for a in world.village_npcs if not a.physical.is_dead and not getattr(a,"animal_type",None))
    for key in ("wool_shirt","wool_trousers","leather_boots","knife_stone"):
        wear(actor,key)

    def check_render(label,world,actor):
        before,rng = pickle.dumps(actor),random.getstate()
        people.body_frame(world,actor,4)
        assert pickle.dumps(actor) == before
        assert random.getstate() == rng

    result = action_sequence(world,actor,check_render)
    assert [r[1] for r in result] == ["idle","walk","chop","carry","sit","talk","idle","sleep"]
    assert result[3][3] is True  # Real movement AND carrying, not just a queued path.
    assert result[5][2:] == ("seated",False)
