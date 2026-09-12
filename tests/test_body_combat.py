"""Persistent anatomy contracts and the playable human/wolf entry points."""
import pickle
import random
from types import SimpleNamespace
from unittest.mock import patch, Mock

import pytest
import config
from engine import NPC, Player
from entities.anatomy import Anatomy
from entities.animal import Animal
from entities import body_model as rules
from simulation.systems import body_combat as combat
from simulation.systems.medical import update_npc_medical_state
from tests.world_cache import fresh_world


@pytest.fixture
def world():
    world = fresh_world(seed=451, pre_simulate=False)
    world.player.x, world.player.y = 50, 50
    world.npcs = [Animal(51, 50, name="Grey Wolf", animal_type="wolf")]
    world.village_npcs = []
    world.game_time = 100
    combat.advance_bodies(world)
    return world


def test_connected_plans_and_no_damage_spill():
    for plan, count in [("human", 15), ("wolf", 17)]:
        body = rules.upgrade(Anatomy.humanoid(), plan)
        assert len(body.parts) == count
        region = "left_forearm" if plan == "human" else "left_front_leg"
        child = "left_hand" if plan == "human" else "left_front_paw"
        rules.inflict(body, region, "crush", 24, 0)
        assert rules.part_function(body, child) == 0
        assert rules.tissue_damage(body, "head") == dict(skin=0, muscle=0, bone=0, vital=0)
        assert body.death_cause is None


def test_fractures_accumulate_across_hits():
    body = rules.upgrade(Anatomy.humanoid())
    rules.inflict(body, "left_forearm", "crush", 6, 0)
    assert not body.wounds[0].fracture
    rules.inflict(body, "left_forearm", "crush", 6, 1)
    assert all(w.fracture for w in body.wounds)


def test_legacy_migration_preserves_injuries_and_random_stream():
    body = Anatomy.humanoid()
    body.hp_proxy["left_leg"] = 0
    rng = random.getstate()
    rules.upgrade(body, now=40)
    assert random.getstate() == rng
    assert body.wounds[0].fracture
    assert rules.part_function(body, "left_foot") <= .35
    snapshot = pickle.dumps(body)
    rules.upgrade(body, now=500)
    assert snapshot == pickle.dumps(body)


def test_blood_clock_save_load_and_pause():
    body = rules.upgrade(Anatomy.humanoid())
    rules.inflict(body, "left_forearm", "puncture", 10, 0)
    rules.advance(body, 40)
    restored = pickle.loads(pickle.dumps(body))
    rules.advance(restored, 40)
    rules.advance(restored, 20)
    assert restored.blood == body.blood
    rules.advance(body, 70)
    rules.advance(restored, 70)
    assert restored.blood == body.blood
    assert restored.wounds == body.wounds


def test_long_sleep_cannot_resurrect_blood_loss():
    body = rules.upgrade(Anatomy.humanoid())
    rules.inflict(body, "left_forearm", "cut", 23, 0)
    rules.advance(body, config.DAY_LENGTH_TICKS, resting=True)
    assert body.death_cause == "blood loss"
    body.set_total_hp(35)
    assert body.get_total_hp() == 0


def test_hp_is_derived_and_not_a_wound_cure():
    body = rules.upgrade(Anatomy.humanoid())
    wound = rules.inflict(body, "left_leg", "crush", 14, 0)
    body.set_total_hp(35)
    assert wound.healing == 0
    assert wound.fracture
    with pytest.raises(TypeError):
        body.hp_proxy["left_leg"] = 10


def test_attack_uses_equipped_weapon_not_bag_and_never_llm(world):
    target = world.npcs[0]
    world.player.add_item("axe_stone")
    with patch.object(world, "_call_llm", side_effect=AssertionError("Combat contacted model")), patch("random.randint", side_effect=[15, 3]):
        result = world.player_attempt_attack(target, target_part="left_front_leg")
    assert result.hit and target.combat.anatomy.wounds[-1].weapon == "punch"
    world.game_time += 5
    assert world.use_item("axe_stone")
    with patch("random.randint", side_effect=[15, 4]):
        result = world.player_attempt_attack(target, target_part="right_front_leg")
    assert result.hit
    assert target.combat.anatomy.wounds[-1].weapon == "Stone Axe"
    assert target.combat.anatomy.wounds[-1].kind == "cut"
    assert not world.player.has_item("axe_stone")


def test_kick_bite_and_range_recovery(world):
    wolf = world.npcs[0]
    with patch("random.randint", side_effect=[15, 4]):
        result = world.player_attempt_attack(wolf, "kick", "left_front_leg")
    assert result.hit and wolf.combat.anatomy.wounds[-1].weapon == "kick"
    assert not world.player_attempt_attack(wolf).attempted
    with patch("random.randint", side_effect=[15, 6]):
        result = world.npc_attempt_attack_player(wolf, world.player)
    assert result.hit
    assert world.player.combat.anatomy.wounds[-1].kind == "puncture"
    wolf.x += 10
    world.game_time += 20
    assert not world.player_attempt_attack(wolf).attempted


def test_armor_is_regional_and_only_hit_armor_wears(world):
    player = world.player
    player.add_item("iron_breastplate")
    player.equip_armor("iron_breastplate")
    assert combat.armor_at(player, "torso")[0] == "body"
    assert combat.armor_at(player, "left_forearm") == (None, None)
    with patch("random.randint", side_effect=[15, 6]):
        result = combat.attack(world, world.npcs[0], player, target_part="left_forearm")
    assert result.absorbed == 0
    assert not player.equipment.equipped_armor_durability
    world.game_time += 6
    with patch("random.randint", side_effect=[15, 6]):
        result = combat.attack(world, world.npcs[0], player, target_part="torso")
    assert result.absorbed > 0
    assert "body" in player.equipment.equipped_armor_durability


def test_disabled_hand_drops_exact_weapon_once(world):
    player = world.player
    player.add_item("axe_stone", initial_durability=12)
    world.use_item("axe_stone")
    ref = combat.held_reference(player)
    rules.inflict(player.combat.anatomy, "right_forearm", "crush", 24, 100)
    combat.sync_body(world, player)
    combat.sync_body(world, player)
    assert not player.equipment.weapon
    inventory = world.items_on_map[(50, 50)]
    assert inventory.has_item_reference(ref)
    assert inventory.get("axe_stone") == 1
    assert ref.current_durability == 12


def test_bandage_and_splint_consume_supplies_without_resetting_wound(world):
    player = world.player
    wound = rules.inflict(player.combat.anatomy, "left_lower_leg", "cut", 25, 100)
    player.add_item("bandage")
    player.add_item("splint")
    assert world.use_item("bandage")
    assert wound.dressed and not player.has_item("bandage")
    assert world.use_item("splint")
    assert wound.splinted and not player.has_item("splint")
    assert wound.healing == 0 and "broken_leg" in player.physical.status_effects
    world.game_time += config.DAY_LENGTH_TICKS
    combat.advance_bodies(world)
    assert not player.physical.is_dead
    assert 0 < wound.healing < .2
    assert "broken_leg" in player.physical.status_effects


def test_healer_treats_player_with_real_supplies(world):
    healer = NPC(50, 51, name="Healer")
    healer.economic.profession = "Healer"
    healer.add_item("bandage")
    world.village_npcs = [healer]
    wound = rules.inflict(world.player.combat.anatomy, "left_lower_leg", "puncture", 9, 100)
    update_npc_medical_state(world, healer)
    assert healer.task_target_entity_id == world.player.id
    healer.task_timer = 0
    update_npc_medical_state(world, healer)
    assert wound.dressed
    assert wound.healing == 0
    assert not healer.economic.npc_inventory.get("bandage")


def test_incapacitation_death_and_finalization_once(world):
    target = world.npcs[0]
    target.combat.anatomy.blood = .35
    combat.sync_body(world, target)
    assert not combat.can_act(target)
    assert not world.npc_attempt_attack_player(target, world.player).attempted
    with patch.object(world, "handle_npc_death") as death:
        rules.inflict(target.combat.anatomy, "head", "crush", 35, 100, world.player.id)
        combat.sync_body(world, target)
        combat.sync_body(world, target)
        assert target.physical.is_dead
        assert death.call_count == 1


def test_fractional_movement_and_work_really_slow(world):
    actor = world.player
    rules.inflict(actor.combat.anatomy, "left_leg", "crush", 14, 100)
    moves = [combat.movement_budget(actor, n, 1) for n in range(100, 110)]
    assert 0 < sum(moves) < 10
    assert combat.movement_budget(actor, 109, 1) == 0
    interaction = SimpleNamespace()
    assert sum(combat.work_progress(interaction, .4) for _ in range(10)) == 4


def test_injured_wolf_reacts_to_actual_attacker(world):
    wolf = world.npcs[0]
    rules.inflict(wolf.combat.anatomy, "left_front_leg", "crush", 23, 100, world.player.id)
    with patch.object(world, "get_tile_at", return_value=SimpleNamespace(passable=True)):
        assert combat.retreat_if_injured(world, wolf)
    assert wolf.schedule.current_task == "fleeing_injury"
    assert wolf.schedule.current_path[-1] != (world.player.x, world.player.y)


def test_all_llm_network_boundaries_disabled(world):
    from services.llm_gossip import AsyncLLMGossipService
    assert config.ENABLE_LLM_CONNECTION is False
    with patch("engine.requests.post", side_effect=AssertionError("Network attempted")), patch("engine.genai") as google:
        assert world._call_llm("test") == ""
        assert world._call_gemini("test") == ""
        assert world._call_ollama_backend("test") == ""
        world._submit_background_llm_task("test", "test")
        assert not world._background_llm_tasks
        assert world._poll_background_llm_task("test") == ""
        # Exercise the independent gossip transport without starting a worker.
        service = object.__new__(AsyncLLMGossipService)
        assert service._generate_text(SimpleNamespace()) == ""
        google.Client.assert_not_called()


def test_migrate_generic_broken_leg_does_not_cure_or_double_slow():
    actor = NPC(0, 0, name="Old save")
    actor.physical.status_effects.append("broken_leg")
    actor.original_speed, actor.speed = 1, .5
    body = combat.ensure_body(actor, 50)
    assert any(w.fracture for w in body.wounds)
    assert actor.speed == 1
    assert rules.capabilities(body)["movement"] < 1


def test_repeated_ordinary_axe_cuts_reach_vitals():
    body = rules.upgrade(Anatomy.humanoid(), "wolf")
    for tick in range(20):
        rules.inflict(body, "head", "cut", 7, tick)
        if body.death_cause:
            break
    assert body.death_cause == "catastrophic head injury"
    assert tick > 1  # Not a single unarmored HP subtraction.


def test_wild_wolf_does_not_seek_human_healer(world):
    wolf = world.npcs[0]
    rules.inflict(wolf.combat.anatomy, "left_front_leg", "cut", 15, 100)
    wolf.schedule.current_task = "hunting"
    update_npc_medical_state(world, wolf)
    assert wolf.schedule.current_task == "hunting"


def test_wolf_injury_does_not_blame_uninvolved_player(world):
    attacker = NPC(50, 50, name="Hunter")
    with patch("random.randint", side_effect=[20, 3]):
        combat.attack(world, attacker, world.npcs[0], target_part="head")
    assert not attacker.combat.is_hostile_to_player


def test_body_panel_is_read_only_and_scrolls_long_wound_history(world):
    import main
    from rendering.body_panel import draw_body_menu
    from tcod_compat import tcod
    body = world.player.combat.anatomy
    for tick in range(28):
        rules.inflict(body, "left_forearm", "cut", .1, tick)
    world.examine_body()
    clock, rng, saved = world.game_time, random.getstate(), pickle.dumps(body)
    console = main.create_console()
    draw_body_menu(console, world)
    assert world.body_menu_max_scroll > 0
    main.handle_body_menu_input(SimpleNamespace(sym=tcod.event.KeySym.DOWN), world)
    assert world.body_menu_scroll == 1
    assert world.game_time == clock and random.getstate() == rng
    assert pickle.dumps(body) == saved


def test_unconscious_character_uses_same_layers_in_collapsed_pose(world):
    from rendering import people_art, character_layers, character_pose
    world.player.combat.anatomy.blood = .35
    combat.sync_body(world, world.player)
    identity = character_layers.signature(world.player)
    activity = people_art.activity_for(world, world.player)
    assert activity.kind == "unconscious"
    assert character_pose.layout("south", activity.kind).reclined
    assert character_layers.signature(world.player) == identity


def test_treatment_needs_real_material_and_does_not_charge_on_failure(world):
    from simulation.systems.medical import _collect_wound_supply
    healer = NPC(50, 51, name="Elara")
    healer.economic.profession = "Healer"
    assert not _collect_wound_supply(world, healer, "bandage")
    healer.add_item("cloth")
    assert _collect_wound_supply(world, healer, "bandage")
    assert healer.economic.npc_inventory.get("bandage") == 1
    assert not healer.economic.npc_inventory.get("cloth")


def test_nearby_conversation_takes_local_fallback_with_models_off(world):
    speaker, listener = NPC(50, 50, name="Alda"), NPC(50, 51, name="Mara")
    world.village_npcs = [speaker, listener]
    with patch.object(world, "_call_llm", side_effect=AssertionError("Model attempted")):
        world._continue_npc_conversation(speaker, listener)
    assert speaker.current_conversation
    assert not world._background_llm_tasks


def test_legacy_clinic_salve_stock_remains_useful(world):
    from entities.items import Inventory
    from simulation.systems.medical import _collect_wound_supply
    healer = NPC(50, 51, name="Elara")
    healer.schedule.work_building_id = "clinic_fixture"
    stock = Inventory()
    stock.add_item("healing_salve", 1)
    world.buildings_by_id["clinic_fixture"] = SimpleNamespace(global_center_x=50, global_center_y=51, building_inventory=stock)
    assert _collect_wound_supply(world, healer, "bandage")
    assert healer.economic.npc_inventory.get("healing_salve") == 1
    assert not stock.get("healing_salve")
