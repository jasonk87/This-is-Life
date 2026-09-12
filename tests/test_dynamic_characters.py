"""Individual identity, actual wearables, and saved simulation-time grooming."""

import copy
import pickle
import random
from types import SimpleNamespace as NS

import pytest

import main
from config import DAY_LENGTH_TICKS as DAY
from data.items import ITEM_DEFINITIONS
from engine import World
from entities.base import Appearance, Equipment, NPC
from entities.items import EquipmentSlot
from rendering import character_layers as layers, people_art, pixel_scene
from simulation.systems.appearance import (
    advance_actor_appearance,
    advance_appearance,
    groom,
    identity_for,
)
from tests.test_world_art import native_art


def person(**appearance):
    return NS(
        id="persistent-person",
        name="Elias",
        gender="male",
        age=32,
        appearance=Appearance(hairstyle="short", **appearance),
        equipment=Equipment(),
        economic=NS(profession="Baker", inventory={}),
        physical=NS(is_dead=False),
    )


def test_identity_does_not_depend_on_job_name_clothes_or_random():
    actor = person()
    before = random.getstate()
    identity, state = identity_for(actor), layers.signature(actor)
    actor.economic.profession = "Guard"
    actor.name = "Renamed person"
    assert identity_for(actor) == identity
    assert layers.signature(actor) == state
    assert random.getstate() == before
    advance_actor_appearance(actor, 0)
    assert actor.appearance.face_variant == identity[0]
    assert identity_for(pickle.loads(pickle.dumps(actor))) == identity


def test_growth_follows_game_time_and_survives_save():
    actor = person(facial_hair="none")
    advance_actor_appearance(actor, 0)
    for day, style in ((2, "stubble"), (7, "short_beard"), (21, "full_beard")):
        actor = pickle.loads(pickle.dumps(actor))
        advance_actor_appearance(actor, day * DAY)
        assert actor.appearance.facial_hair == style
        assert actor.appearance.beard_days == pytest.approx(day)
        advance_actor_appearance(actor, day * DAY)
        assert actor.appearance.beard_days == pytest.approx(day)


def test_legacy_appearance_and_equipment_backfill_without_reroll():
    ap = Appearance.__new__(Appearance)
    ap.__setstate__(
        {"hairstyle": "braided", "hair_color": "red", "facial_hair": "mustache", "skin_tone": "tan"}
    )
    gear = Equipment.__new__(Equipment)
    gear.__setstate__({"equipped_armor": {"head": "iron_helmet", "body": None}})
    assert ap.face_variant == -1 and ap.beard_last_tick is None
    assert ap.hairstyle == "braided" and ap.hair_color == "red"
    assert isinstance(gear.feet, EquipmentSlot) and isinstance(gear.legs, EquipmentSlot)
    assert gear.equipped_armor["head"] == "iron_helmet" and "legs" in gear.equipped_armor


@pytest.mark.parametrize("condition", ["child", "dead", "disabled", "animal"])
def test_no_unearned_growth(condition):
    actor = person()
    if condition == "child":
        actor.age = 10
    if condition == "dead":
        actor.physical.is_dead = True
    if condition == "disabled":
        actor.appearance.beard_growth_enabled = False
    if condition == "animal":
        actor.animal_type = "cat"
    advance_actor_appearance(actor, 0)
    advance_actor_appearance(actor, 30 * DAY)
    assert actor.appearance.facial_hair == "none"


def test_macro_actor_grows_but_repeated_paused_ticks_do_not():
    actor = person()
    actor.render_disabled = True
    world = NS(game_time=0, player=None, all_npcs=[actor, actor])
    advance_appearance(world)
    world.game_time = 8 * DAY + 123
    advance_appearance(world)
    days = actor.appearance.beard_days
    advance_appearance(world)
    assert actor.appearance.beard_days == days
    assert actor.appearance.facial_hair == "short_beard"


def test_explicit_trim_needs_owned_knife_and_never_grows_hair():
    actor = person(facial_hair="full_beard")
    world = NS(game_time=0)
    assert not groom(actor, world)[0]
    assert actor.appearance.facial_hair == "full_beard"
    actor.economic.inventory["knife_stone"] = 1
    assert groom(actor, world, "short_beard")[0]
    assert actor.appearance.beard_days == 7
    assert groom(actor, world, "none")[0]
    assert not groom(actor, world, "short_beard")[0]
    advance_actor_appearance(actor, 2 * DAY)
    assert actor.appearance.facial_hair == "stubble"


def test_direct_grooming_edit_resets_old_growth_accumulator():
    actor = person(facial_hair="full_beard")
    advance_actor_appearance(actor, 0)
    actor.appearance.facial_hair = "none"
    advance_actor_appearance(actor, 25 * DAY)
    assert actor.appearance.facial_hair == "none"
    assert actor.appearance.beard_days == 0


def test_growth_starts_when_a_child_reaches_adulthood():
    actor = person()
    actor.age = 17
    advance_actor_appearance(actor, 0)
    actor.age = 18
    advance_actor_appearance(actor, 3 * DAY)
    assert actor.appearance.facial_hair == "stubble"


def test_new_world_clothing_is_owned_idempotent_and_rng_independent():
    from simulation.starting_wardrobe import seed_starting_wardrobes

    npc = NPC(0, 0)
    npc.add_item("iron_breastplate", 1)
    owned = npc.economic.npc_inventory.get_item_reference("iron_breastplate")
    assert npc.equip_item_reference("body", owned)
    world = NS(all_npcs=[npc])
    rng = random.getstate()
    seed_starting_wardrobes(world)
    assert random.getstate() == rng
    assert npc.get_equipped_item_reference("body") is owned
    boots = npc.get_equipped_item_reference("feet")
    assert boots is not None
    npc.unequip_item("feet")
    seed_starting_wardrobes(world)
    assert npc.get_equipped_item_reference("feet") is None
    assert npc.economic.npc_inventory.has_item_reference(boots)


def test_npc_chooses_useful_owned_footwear_through_existing_upgrade_logic():
    npc = NPC(0, 0)
    npc.add_item("leather_boots", 1)
    assert npc.evaluate_and_upgrade_equipment()
    assert layers.equipped(npc, "feet") == "leather_boots"


def test_groom_input_uses_real_tool_and_updates_saved_state():
    from tcod_compat import tcod
    from tests.test_inventory_use import _key

    world = World(seed=194)
    world.player.appearance.facial_hair = "full_beard"
    world.player.add_item("knife_stone", 1)
    main.handle_inventory_menu_input(_key(getattr(tcod.event.KeySym, "s", ord("s"))), world)
    assert world.player.appearance.facial_hair == "none"
    assert world.player.appearance.beard_days == 0


@pytest.mark.parametrize(
    "key,slot",
    [
        ("wool_shirt", "body"),
        ("wool_cap", "head"),
        ("linen_trousers", "legs"),
        ("wool_trousers", "legs"),
        ("leather_boots", "feet"),
        ("leather_shoes", "feet"),
    ],
)
def test_npc_wears_real_owned_item_and_returns_it_on_swap(key, slot):
    npc = NPC(0, 0)
    npc.add_item(key, 1)
    item = npc.economic.npc_inventory.get_item_reference(key)
    assert npc.equip_item_reference(slot, item)
    assert layers.equipped(npc, slot) == key
    assert npc.get_equipped_item_reference(slot) is item
    assert not npc.economic.npc_inventory.has_item_reference(item)
    npc.unequip_item(slot)
    assert npc.economic.npc_inventory.has_item_reference(item)
    assert layers.equipped(npc, slot) is None
    assert ITEM_DEFINITIONS[key]["crafting_recipe"]


def test_player_can_change_boots_from_actual_inventory():
    world = World(seed=190, player_first_name="Test")
    world.use_item("leather_boots")
    assert layers.equipped(world.player, "feet") is None
    for key in ("leather_boots", "leather_shoes"):
        world.player.add_item(key, 1)
        world.use_item(key)
        assert layers.equipped(world.player, "feet") == key
    assert world.player.has_item("leather_boots")


def test_sources_have_four_directions_and_keep_both_boots(native_art):
    assert len(layers._parts) >= 7
    for name, parts in layers._parts.items():
        assert len(parts) == (4 if name == "cloak" else 16)
        for image in parts:
            assert image[:, :, 3].any() and (image[:, :, 3] < 32).any()
    boots = layers._parts["lower"][8]
    assert boots[:, : boots.shape[1] // 2, 3].any()
    assert boots[:, boots.shape[1] // 2 :, 3].any()


def test_renderer_uses_appearance_and_current_equipment_without_mutation(native_art):
    actor = person(facial_hair="short_beard")
    before = copy.deepcopy(actor.__dict__)
    state = layers.signature(actor)
    original = layers.rig(state, "south").copy()
    assert actor.__dict__ == before
    actor.economic.profession = "Blacksmith"
    assert pixel_scene.np.array_equal(original, layers.rig(layers.signature(actor), "south"))
    for slot, key in (
        ("body", "wool_shirt"),
        ("legs", "wool_trousers"),
        ("feet", "leather_boots"),
        ("head", "wool_cap"),
    ):
        previous = layers.rig(layers.signature(actor), "south").copy()
        actor.equipment.equipped_armor[slot] = key
        assert not pixel_scene.np.array_equal(
            previous, layers.rig(layers.signature(actor), "south")
        )
        assert layers.signature(actor)[1:8] == state[1:8]
    actor.equipment.equipped_armor = Equipment().equipped_armor
    assert pixel_scene.np.array_equal(original, layers.rig(layers.signature(actor), "south"))


def test_body_cache_token_changes_on_groom_and_not_profession(native_art):
    from tools.street_review import activity_actor

    world, actor = activity_actor("idle")
    actor.appearance = Appearance(hairstyle="short", facial_hair="none")
    _, _, first = people_art.body_frame(world, actor, 3)
    actor.economic.profession = "Baker"
    assert people_art.body_frame(world, actor, 3)[2] == first
    actor.appearance.facial_hair = "full_beard"
    assert people_art.body_frame(world, actor, 3)[2] != first


def test_npc_grooming_checks_npc_inventory_not_empty_player_inventory():
    npc = NPC(0, 0)
    npc.appearance.facial_hair = "full_beard"
    npc.add_item("knife_stone", 1)
    assert groom(npc, NS(game_time=0))[0]


def test_clock_rewind_does_not_double_count_growth():
    actor = person()
    advance_actor_appearance(actor, 0)
    advance_actor_appearance(actor, 3 * DAY)
    advance_actor_appearance(actor, DAY)
    advance_actor_appearance(actor, 3 * DAY)
    assert actor.appearance.beard_days == 3


def test_new_footwear_participates_in_existing_death_drop_rules():
    from unittest.mock import patch

    world = World(seed=196)
    npc = next(npc for npc in world.all_npcs if not getattr(npc, "animal_type", None))
    npc.unequip_item("feet")
    npc.add_item("leather_boots", 1)
    boots = npc.economic.npc_inventory.get_item_reference("leather_boots")
    assert npc.equip_item_reference("feet", boots)
    point = (npc.x, npc.y)
    with patch("engine.random.random", return_value=0.0):
        world.handle_npc_death(npc)
    assert world.items_on_map[point].has_item_reference(boots)
    assert layers.equipped(npc, "feet") is None


def test_missing_required_atlas_disables_layered_renderer(native_art, monkeypatch):
    monkeypatch.delitem(layers._parts, "hair")
    assert not layers.enabled(NS())


def test_each_face_and_direction_changes_pixels(native_art):
    actor = person()
    images = []
    for face in range(4):
        actor.appearance.face_variant = face
        images.append(layers.rig(layers.signature(actor), "south").tobytes())
    assert len(set(images)) == 4
    assert len({layers.rig(layers.signature(actor), d).tobytes() for d in layers.DIRECTIONS}) == 4


def test_legacy_no_overlay_hair_uses_natural_cut_but_bald_stays_bald():
    actor = person()
    actor.appearance.hairstyle = "none"
    assert layers.signature(actor)[5] == "short"
    actor.appearance.hairstyle = "bald"
    assert layers.signature(actor)[5] == "bald"
