"""Ordinary input, real tick combat, witnesses and recovery decisions."""
import pickle
import random
from collections import Counter
from types import SimpleNamespace

import pytest

import config
import main
from data.tiles import TILE_DEFINITIONS
from engine import NPC
from entities.animal import Animal
from entities.anatomy import Anatomy
from entities import body_model as rules
from simulation.systems import body_combat as combat, combat_response as response
from simulation.systems.medical import update_npc_medical_state, needs_recovery
from tests.world_cache import fresh_world


@pytest.fixture
def world():
    world = fresh_world(seed=451, pre_simulate=False)
    world.game_time = config.DAY_LENGTH_TICKS // 2
    for x in range(43, 63):
        for y in range(43, 63):
            world.get_tile_at(x, y)
            world._change_map_tile((x, y), TILE_DEFINITIONS["plains"])
    world._update_entity_position(world.player, 50, 50)
    world.npcs = [Animal(56, 50, name="Grey Wolf", animal_type="wolf")]
    world.village_npcs = []
    world._mark_entity_positions_dirty()
    combat.advance_bodies(world)
    world._update_light_level_and_fov()
    world._update_player_fov()
    random.seed(117)
    return world


def add_person(world, name, x, y, profession="Farmer"):
    person = NPC(x, y, name=name)
    person.economic.profession = profession
    world.village_npcs.append(person)
    combat.ensure_body(person, world.game_time)
    world._mark_entity_positions_dirty()
    return person


def test_ordinary_wolf_approaches_and_bites_through_real_ticks(world):
    wolf = world.npcs[0]
    wolf.combat.is_hostile_to_player = True
    positions = []
    for _ in range(28):
        world.update()
        positions.append((wolf.x, wolf.y))
        if world.player.physical.is_dead:
            break
    assert len(set(positions)) > 1
    assert any(w.kind == "puncture" and w.attacker_id == wolf.id for w in world.player.combat.anatomy.wounds)
    assert not world._background_llm_tasks


@pytest.mark.parametrize("key,action", [(None, "punch"), (None, "kick"), ("axe_stone", "attack"), ("knife_stone", "attack")])
def test_target_picker_and_real_equipment_entry_points(world, key, action):
    wolf = world.npcs[0]
    world._update_entity_position(wolf, 51, 50)
    wolf.combat.is_hostile_to_player = True
    if key:
        world.player.add_item(key)
        assert world.use_item(key)
    world._update_player_fov()
    main.handle_playing_input(SimpleNamespace(sym=main.tcod.event.KeySym.F), world, None)
    ctx = world.interaction_context
    assert ctx["active"] and ctx["combat_picker"]
    assert ctx["target_entities"][ctx["selected_entity_index"]]["data"] is wolf
    ctx["selected_action_index"] = ctx["available_actions"].index(action.capitalize())
    world.is_paused = True
    before = world.game_time
    assert main.execute_interaction(world, None)
    assert world.game_time > before
    assert world.player.combat.anatomy.attack_ready_tick <= world.game_time
    assert not ctx["active"]
    assert world.player_combat_target_id == wolf.id
    # Time was advanced through simulation, not merely added to the clock.
    assert wolf.combat.anatomy.last_body_tick > before
    assert wolf.combat.anatomy.attack_ready_tick > before or response.distance(wolf, world.player) > 1


def test_invalid_paused_attack_does_not_spend_time(world):
    main.open_combat_menu(world)
    world.is_paused = True
    now = world.game_time
    assert not main.execute_interaction(world, None)
    assert world.game_time == now
    assert world.interaction_context["active"]


def test_paused_injured_movement_spends_real_ticks_and_cannot_free_kite(world):
    body = world.player.combat.anatomy
    rules.inflict(body, "left_leg", "crush", 16, world.game_time)
    world.is_paused = True
    before = world.game_time
    assert main.handle_playing_input(SimpleNamespace(sym=main.tcod.event.KeySym.LEFT), world, None)
    assert world.game_time-before >= 2
    assert world.npcs[0].combat.anatomy.last_body_tick == world.game_time


def test_realtime_movement_obeys_recovery_instead_of_advancing_clock_on_key_repeat(world):
    world.is_paused = False
    event = SimpleNamespace(sym=main.tcod.event.KeySym.LEFT)
    before = world.game_time
    assert main.handle_playing_input(event, world, None)
    location = (world.player.x, world.player.y)
    assert not main.handle_playing_input(event, world, None)
    assert (world.player.x, world.player.y) == location
    assert world.game_time == before
    world.update()
    assert main.handle_playing_input(event, world, None)


def test_guard_intervenes_civilian_escapes_without_blame_on_player(world):
    wolf = world.npcs[0]
    world._update_entity_position(wolf, 51, 50)
    guard = add_person(world, "Rowan", 53, 49, "Guard")
    civilian = add_person(world, "Tessa", 51, 48)
    wolf.combat.is_hostile_to_player = True
    combat.attack(world, wolf, world.player)
    assert guard.wildlife_emergency["threat_id"] == wolf.id
    assert guard.wildlife_emergency["victim_id"] == world.player.id
    old_distance = response.distance(civilian, wolf)
    guard_started = False
    civilian_retreated = False
    for _ in range(20):
        world.update()
        guard_started |= guard.combat.anatomy.attack_ready_tick > 0
        civilian_retreated |= response.distance(civilian, wolf) > old_distance
    assert guard_started
    assert civilian_retreated
    assert not guard.combat.is_hostile_to_player
    assert world.player.economic.bounty == 0
    assert any(w.attacker_id == guard.id for w in wolf.combat.anatomy.wounds)
    assert any(wolf.name in entry and world.player.name in entry for entry in guard.knowledge.long_term_memory)


def test_unseen_attack_does_not_give_guards_omniscient_knowledge(world):
    wolf = world.npcs[0]
    world._update_entity_position(wolf, 51, 50)
    guard = add_person(world, "Far Guard", 100, 100, "Guard")
    combat.attack(world, wolf, world.player)
    assert getattr(guard, "wildlife_emergency", None) is None
    assert not guard.combat.is_hostile_to_player


def test_wildlife_alarm_is_local_and_names_the_reported_threat(world):
    speaker = add_person(world, "Watchman", 50, 50, "Guard")
    nearby = add_person(world, "Nearby guard", 48, 49, "Guard")
    distant = add_person(world, "Distant guard", 70, 70, "Guard")
    response.raise_wildlife_alarm(world, speaker, world.npcs[0], world.player)
    assert nearby.wildlife_emergency["threat_id"] == world.npcs[0].id
    assert nearby.wildlife_emergency["last_seen"] == (56, 50)
    assert not getattr(distant, "wildlife_emergency", None)
    assert not nearby.combat.is_hostile_to_player


def test_wildlife_witnessing_works_off_camera(world):
    victim = add_person(world, "Miller", 50, 50)
    guard = add_person(world, "Remote Guard", 53, 49, "Guard")
    wolf = world.npcs[0]
    world._update_entity_position(wolf, 51, 50)
    world._update_entity_position(world.player, 200, 200)
    world.npc_fov_maps.clear()
    combat.attack(world, wolf, victim)
    assert guard.wildlife_emergency["victim_id"] == victim.id
    assert guard.wildlife_emergency["threat_id"] == wolf.id


def test_sound_expires_while_player_is_stationary_and_care_is_not_interrupted(world):
    from simulation.systems.perception import expire_sounds, update_npc_sound_perception
    healer = add_person(world, "Healer", 50, 49, "Healer")
    healer.schedule.current_task = "treating_patient"
    world.emit_sound(50, 50, "combat_attack", 10, world.npcs[0].id)
    update_npc_sound_perception(world, healer)
    assert healer.schedule.current_task == "treating_patient"
    before = (world.player.x, world.player.y)
    world.game_time += 3
    expire_sounds(world)
    assert not world.sound_events
    assert (world.player.x, world.player.y) == before


def test_healer_reaches_patient_and_finishes_care_through_full_ticks(world):
    world.npcs = []  # No active predator: this isolates arrival/treatment from flight.
    world._mark_entity_positions_dirty()
    healer = add_person(world, "Healer", 46, 49, "Healer")
    healer.add_item("bandage", 2)
    wound = rules.inflict(world.player.combat.anatomy, "left_forearm", "puncture", 8, world.game_time)
    world.emit_sound(50, 50, "combat_attack", 10, world.player.id)
    for _ in range(80):
        world.update()
        if wound.dressed:
            break
    assert wound.dressed and wound.treated_by == healer.id
    assert healer.economic.npc_inventory.get("bandage", 0) == 1
    assert wound.healing < .1


def test_healer_waits_at_safety_boundary_instead_of_repeatedly_reentering_fight(world):
    healer = add_person(world, "Healer", 42, 50, "Healer")
    healer.add_item("bandage", 2)
    wolf = world.npcs[0]
    world._update_entity_position(wolf, 50, 51)
    rules.inflict(world.player.combat.anatomy, "left_forearm", "puncture", 8, world.game_time)
    response.remember_threat(world, healer, wolf, world.player)
    for _ in range(5):
        update_npc_medical_state(world, healer)
        assert healer.schedule.current_task == "waiting_for_safe_treatment"
        assert not healer.schedule.current_path
    assert healer.economic.npc_inventory.get("bandage", 0) == 2


def test_existing_wildlife_alarm_state_never_turns_guards_against_player(world):
    guard = add_person(world, "Alarm Guard", 53, 49, "Guard")
    guard.is_frightened = True
    guard.threat_source_ids = [world.npcs[0].id]
    guard.schedule.current_task = "alerting_guards"
    guard.schedule.game_time_last_updated = 0
    world._update_npc_schedules()
    assert not guard.combat.is_hostile_to_player
    assert guard.wildlife_emergency["threat_id"] == world.npcs[0].id


def test_fighting_a_wolf_is_remembered_without_criminal_reputation(world):
    wolf = world.npcs[0]
    world._update_entity_position(wolf, 51, 50)
    guard = add_person(world, "Witness Guard", 50, 49, "Guard")
    for _ in range(8):
        world.player_attempt_attack(wolf)
        world.game_time += 4
    records = [event for event in world.global_events if event.type == "wildlife_combat"]
    assert records
    assert any(f.record_type == "wildlife_combat" for f in guard.knowledge.known_history_facts.values())
    assert guard.knowledge.get_reputation_towards(world.player, current_tick=world.game_time) == 0
    world.game_time += (-world.game_time) % 10
    world._handle_reputation_based_reactions()
    assert not guard.combat.is_hostile_to_player
    assert world.player.economic.bounty == 0


def test_witness_memory_survives_save_and_expires_without_player_hostility(world):
    guard = add_person(world, "Guard", 53, 49, "Guard")
    response.remember_threat(world, guard, world.npcs[0], world.player)
    saved = pickle.loads(pickle.dumps(guard))
    assert saved.wildlife_emergency == guard.wildlife_emergency
    guard.schedule.current_task = "protecting_from_wildlife"
    world.game_time = guard.wildlife_emergency["expires"]+1
    assert not response.respond_to_wildlife(world, guard)
    assert guard.wildlife_emergency is None
    assert guard.schedule.current_task == "idle"


def test_injured_wolf_really_moves_away_from_attacker(world):
    wolf = world.npcs[0]
    wolf.combat.is_hostile_to_player = True
    rules.inflict(wolf.combat.anatomy, "left_front_leg", "cut", 23, world.game_time, world.player.id)
    starting = response.distance(wolf, world.player)
    for _ in range(8):
        world.update()
    assert response.distance(wolf, world.player) > starting
    assert wolf.schedule.current_task in ("fleeing_injury", "resting")


def test_self_treatment_consumes_supplies_then_worker_takes_recovery_leave(world):
    worker = add_person(world, "Miller", 47, 47)
    body = worker.combat.anatomy
    wound = rules.inflict(body, "left_leg", "puncture", 14, world.game_time)
    worker.add_item("bandage", 2)
    worker.add_item("splint", 1)
    update_npc_medical_state(world, worker)
    assert wound.dressed
    assert worker.economic.npc_inventory.get("bandage", 0) == 1
    if wound.fracture:
        world.game_time += 20
        update_npc_medical_state(world, worker)
        assert wound.splinted
    assert needs_recovery(worker)
    assert worker.schedule.current_task == "recovering_from_injury"
    worker.ai_brain.take_turn(worker, world)
    world._run_humanoid_schedule_logic(worker)
    assert worker.schedule.current_task == "recovering_from_injury"
    assert wound.healing < 1


def test_unconscious_person_cannot_self_treat_but_healer_can(world):
    patient = world.player
    body = patient.combat.anatomy
    wound = rules.inflict(body, "left_forearm", "puncture", 10, world.game_time)
    body.blood = .35
    patient.add_item("bandage", 1)
    assert not combat.treat(world, patient, patient)
    healer = add_person(world, "Healer", 50, 49, "Healer")
    healer.add_item("bandage", 1)
    assert combat.treat(world, healer, patient)
    assert wound.dressed and wound.treated_by == healer.id
    assert patient.economic.inventory.get("bandage", 0) == 1
    assert healer.economic.npc_inventory.get("bandage", 0) == 0
    assert body.blood == .35


def test_healer_skill_improves_stabilization_not_instant_tissue_repair(world):
    healer = add_person(world, "Healer", 50, 49, "Healer")
    qualities = []
    for level in (1, 16):
        world.player.combat.anatomy = rules.upgrade(Anatomy.humanoid(), now=world.game_time)
        wound = rules.inflict(world.player.combat.anatomy, "left_forearm", "puncture", 10, world.game_time)
        healer.skills.levels["medicine"] = level
        healer.add_item("bandage", 1)
        assert combat.treat(world, healer, world.player)
        qualities.append((wound.dressing_quality, rules.bleeding_rate(world.player.combat.anatomy, world.game_time)))
        assert wound.healing == 0
    assert qualities[1][0] > qualities[0][0]
    assert qualities[1][1] < qualities[0][1]


def test_major_blood_loss_is_not_replaced_overnight_and_supplies_matter():
    rested = rules.upgrade(Anatomy.humanoid())
    rested.blood = .5
    deprived = pickle.loads(pickle.dumps(rested))
    rules.advance(rested, config.DAY_LENGTH_TICKS, resting=True)
    rules.advance(deprived, config.DAY_LENGTH_TICKS, resting=True, nourishment=.3)
    assert .5 < rested.blood <= .58
    assert .5 < deprived.blood < rested.blood
    restored = pickle.loads(pickle.dumps(rested))
    rules.advance(restored, config.DAY_LENGTH_TICKS, resting=True)
    assert restored.blood == rested.blood


def test_wolf_target_weights_are_symmetric_and_not_fixed_to_one_calf():
    wolf = rules.upgrade(Anatomy.humanoid(), "wolf")
    human = rules.upgrade(Anatomy.humanoid())
    weights = dict(zip(human.parts, combat.target_weights(wolf, human)))
    for part in weights:
        if part.startswith("left_"):
            assert weights[part] == weights[part.replace("left_", "right_")]
    random.seed(52)
    regions = Counter(random.choices(list(weights), list(weights.values()), k=1000))
    assert len(regions) == 15
    assert regions["left_lower_leg"] < 150
    assert regions["right_lower_leg"] < 150
