"""Embodied injury display, finite arrows, and conservation across weapon markets."""
import pickle
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest
import main
from config import DAY_LENGTH_TICKS as DAY
from data.items import ITEM_DEFINITIONS
from data.tiles import TILE_DEFINITIONS
from engine import NPC, Building
from entities import body_model as rules
from entities.animal import Animal
from entities.items import ItemReference
from simulation.world_model import Village
from simulation.systems import body_combat as combat
from simulation.systems.weapon_economy import market_trade
from tests.test_combat_gameplay import world
from tests.test_world_art import native_art


def test_weapon_component_icons_match_the_named_catalog():
    from data.dawnlike import ITEM_SPRITES
    for key in ("bowstring", "arrow_shaft", "arrowhead", "feather", "iron_spear"):
        assert ITEM_DEFINITIONS[key]["char"] == ITEM_SPRITES[key]


def test_new_weapon_recipes_have_viable_base_material_economics():
    for key in ("bowstring", "short_bow", "arrow_shaft", "arrowhead", "arrow", "iron_spear"):
        item = ITEM_DEFINITIONS[key]
        inputs = sum(ITEM_DEFINITIONS[material]["value"]*qty
                     for material,qty in item["crafting_recipe"].items())
        output = item["value"]*item.get("crafting_output",1)
        assert output > inputs, f"{key}: material cost {inputs}, batch value {output}"


def bow(world, arrows=3):
    world.player.add_item("short_bow")
    world.use_item("short_bow")
    if arrows:
        world.player.add_item("arrow",arrows)
    return world.player.equipment.weapon.item_reference


@pytest.mark.parametrize("roll,hit",[(1,False),(20,True)])
def test_shot_consumes_one_arrow_on_hit_or_miss_and_uses_archery(world,roll,hit):
    weapon = bow(world)
    before = weapon.current_durability
    wolf = world.npcs[0]
    with patch("simulation.systems.body_combat.random.randint",return_value=roll):
        result = world.player_attempt_attack(wolf)
    assert result.attempted and result.hit == hit
    assert world.player.economic.inventory.get("arrow") == 2
    assert weapon.current_durability == before-1
    assert world.player.combat.anatomy.attack_ready_tick == world.game_time+6
    assert world.player.combat.anatomy.last_attack_kind == "shoot"
    assert any(e.effect_type == "projectile" for e in world.visual_effects)
    if hit:
        assert wolf.combat.anatomy.wounds[-1].kind == "puncture"
        assert world.player.skills.experience["archery"] > 0


@pytest.mark.parametrize("blocked",["ammo","range","arm","terrain","person","cooldown"])
def test_invalid_shot_never_spends_ammo_or_weapon_durability(world,blocked):
    weapon = bow(world,0 if blocked == "ammo" else 3)
    before = world.player.economic.inventory.get("arrow",0),weapon.current_durability
    if blocked == "range": world._update_entity_position(world.npcs[0],64,50)
    if blocked == "arm": rules.inflict(world.player.combat.anatomy,"left_arm","crush",25,world.game_time)
    if blocked == "terrain": world._change_map_tile((53,50),dict(char="#",name="Wall",passable=False,color=(99,99,99),properties={"blocks_fov":True}))
    if blocked == "person":
        world.village_npcs.append(NPC(53,50,name="Bystander"))
        world._mark_entity_positions_dirty()
    if blocked == "cooldown": world.player.combat.anatomy.attack_ready_tick = world.game_time+2
    assert not world.player_attempt_attack(world.npcs[0]).attempted
    assert (world.player.economic.inventory.get("arrow",0),weapon.current_durability) == before


def test_bow_can_hunt_legacy_body_animals_without_upgrading_them(world):
    bow(world)
    deer = Animal(56,50,name="Deer",animal_type="deer")
    world.npcs = [deer]
    world._mark_entity_positions_dirty()
    before = deer.combat.hp
    with patch("simulation.systems.body_combat.random.randint",side_effect=lambda lo,hi:20 if hi == 20 else min(3,hi)):
        result = world.player_attempt_attack(deer)
    assert result.attempted and result.hit
    assert deer.combat.hp < before
    assert deer.combat.anatomy.body_plan is None
    assert world.player.economic.inventory.get("arrow") == 2


def test_scar_forms_from_real_healing_and_survives_save_without_impairment(world):
    body = world.player.combat.anatomy
    wound = rules.inflict(body,"head","cut",3,world.game_time,weapon="Knife")
    wound.dressed = True
    rules.advance(body,world.game_time+DAY*5,resting=True)
    assert wound.healing == 1 and len(body.scars) == 1
    scar = body.scars[0]
    assert scar.part == "head" and scar.weapon == "Knife"
    restored = pickle.loads(pickle.dumps(body))
    rules.advance(restored,restored.last_body_tick+DAY,resting=True)
    assert len(restored.scars) == 1
    assert rules.tissue_damage(restored,"head")["skin"] == 0
    assert rules.capabilities(restored)["grip"] == 1


def test_marks_follow_pose_and_do_not_mutate_cached_clean_person(world,native_art):
    from rendering import character_layers as layers
    from rendering.people_art import Activity
    import numpy as np
    actor = world.player
    # Face and bare hand are visible regardless of wardrobe.
    clean,_,clean_token = layers.frame(world,actor,4,Activity("idle"),"south",0,False,None)
    copied = clean.copy()
    rules.inflict(actor.combat.anatomy,"right_hand","cut",5,world.game_time)
    for posture,kind in ((None,"idle"),("seated","sit"),("reclining","sleep")):
        image,_,token = layers.frame(world,actor,4,Activity(kind),"south",0,False,posture)
        assert token != clean_token
        assert ((image[:,:,0]>110)&(image[:,:,1]<70)&(image[:,:,2]<70)).any()
    assert np.array_equal(clean,copied)


def test_blood_stays_on_the_struck_garment_when_clothes_change(world):
    from rendering.body_marks import signature
    actor = world.player
    actor.equipment.body.bind(ItemReference("wool_shirt"))
    old = actor.equipment.body.item_reference
    world._update_entity_position(world.npcs[0],51,50)
    with patch("simulation.systems.body_combat.random.randint",return_value=6):
        combat.attack(world,world.npcs[0],actor,target_part="torso")
    assert old.blood_stains
    actor.equipment.body.bind(ItemReference("wool_shirt"))
    assert not any(m[2] == "stain" for m in signature(actor,world.game_time))
    actor.equipment.body.bind(old)
    assert any(m[2] == "stain" for m in signature(actor,world.game_time))
    assert pickle.loads(pickle.dumps(old)).blood_stains == old.blood_stains


def test_player_crafts_batch_from_real_inputs_at_workbench(world):
    world._change_map_tile((50,49),TILE_DEFINITIONS["plains"])
    tile = world.get_tile_at(50,49)
    tile.properties = {"workstation_type":"workbench"}
    world.player.add_item("wooden_plank")
    before = world.player.economic.inventory.get("wooden_plank",0)
    world.craft_item("arrow_shaft")
    assert world.player.economic.inventory.get("arrow_shaft",0) == 4
    assert world.player.economic.inventory.get("wooden_plank",0) == before-1
    world.craft_item("arrow")
    assert not world.player.economic.inventory.get("arrow",0)


def test_workshop_produces_components_and_bow_without_equipping_worker(world):
    worker = NPC(50,50,name="Bowyer")
    worker.economic.profession = "Carpenter"
    shop = Building(0,0,5,5,building_type="carpenter_shop",category="commercial_workplace")
    stock = shop.building_inventory
    for key,quantity in (("raw_log",2),("cloth",1),("iron_ingot",1),("feather",1)):
        stock.add_item(key,quantity)
    # Separate smith/carpenter stations share a controlled stock fixture here;
    # every production call still consumes actual component objects.
    for key in ("wooden_plank","wooden_plank","bowstring","short_bow"):
        assert world._craft_recipe_at_workplace(worker,shop,key)
    assert stock.get("short_bow",0) == 1
    assert stock.get_item_reference("short_bow").crafter_name == "Bowyer"
    assert not worker.equipment.weapon
    assert not world._craft_recipe_at_workplace(worker,shop,"short_bow")
    assert stock.get("short_bow",0) == 1


def market(world, name):
    v = Village()
    b = Building(0,0,5,5,building_type="general_store",category="commercial_workplace")
    v.add_building(b)
    world.buildings_by_id[b.id] = b
    world._set_trade_money_balance(b,1000)
    return v,b


def test_two_village_trade_moves_same_authored_weapon_and_conserves_money(world):
    first, source = market(world,"first")
    second, destination = market(world,"second")
    merchant = NPC(0,0,name="Trader")
    merchant.is_sleeping = True  # Existing off-camera arrival path.
    merchant.economic.profession = "Traveling Merchant"
    merchant.economic.money = 500
    item = ItemReference("short_bow",quality="Masterwork",crafter_name="Ada")
    source.building_inventory.add_item_reference(item)
    source.building_inventory.add_item("short_bow")
    total = sum(world._get_trade_money_balance(p) for p in (source,destination,merchant))
    assert market_trade(world,merchant,first) == 1
    assert merchant.economic.npc_inventory.has_item_reference(item)
    assert market_trade(world,merchant,second) == 1
    assert destination.building_inventory.has_item_reference(item)
    assert item.crafter_name == "Ada" and item.quality == "Masterwork"
    assert sum(world._get_trade_money_balance(p) for p in (source,destination,merchant)) == total
    assert market_trade(world,merchant,second) == 0  # No buying back one's delivery.


def test_market_does_not_manufacture_weapons_from_supply_totals(world):
    v,b = market(world,"empty")
    v.supply["short_bow"] = 100
    merchant = NPC(0,0,name="Trader")
    merchant.is_sleeping = True
    merchant.economic.money = 500
    assert market_trade(world,merchant,v) == 0
    assert not merchant.economic.npc_inventory.get("short_bow",0)


def test_no_hp_meter_in_ordinary_world_and_blood_is_pinned(world,native_art):
    from rendering import console_renderer as cr
    console = main.create_console()
    main._ensure_zoom_state(world)
    with patch.object(cr,"_draw_entity_health_bars") as old_bars:
        cr.draw(console,world,0,0)
        old_bars.assert_not_called()
    from config import MAP_WIDTH
    text = " ".join("".join(chr(v) for v in row) for row in console.ch[:14,MAP_WIDTH:])
    assert "Blood" in text and "HP" not in text
    bow(world)
    world.player_attempt_attack(world.npcs[0])
    world.update_animations(.15)
    cr.draw(console,world,*main._get_camera_origin(world))  # Native projectile rendering accepts its glyph.


def test_bow_hunter_spends_arrow_then_collects_and_delivers_real_feathers(world):
    hunter = NPC(50,49,name="Hunter")
    hunter.economic.profession = "Hunter"
    hunter.equipment.weapon.bind(ItemReference("short_bow"))
    hunter.add_item("arrow",2)
    bird = Animal(56,49,name="Turkey",animal_type="turkey")
    world.npcs,world.village_npcs = [bird],[hunter]
    drop = Building(0,0,5,5,building_type="butcher_shop",category="commercial_workplace",global_chunk_x_start=43,global_chunk_y_start=43)
    world.buildings_by_id[drop.id] = drop
    hunter.task_context = "hunting"
    hunter.task_context_data = dict(state="pursuing",prey_id=bird.id,dropoff_building_id=drop.id)
    world._mark_entity_positions_dirty()
    with patch("simulation.systems.body_combat.random.randint",side_effect=lambda lo,hi:20 if hi == 20 else max(lo,min(3,hi))):
        assert world._handle_npc_hunting_task(hunter)
    assert bird.physical.is_dead
    assert world.get_tile_at(56,49).properties["animal_type"] == "turkey"
    assert world.get_entity_by_id(bird.id) is None
    assert hunter.economic.npc_inventory.get("arrow",0) == 1
    assert hunter.task_context_data["state"] == "field_dressing"
    assert hunter.economic.npc_inventory.get("feather",0) == 0
    world._update_entity_position(hunter,56,48)
    world._handle_npc_hunting_task(hunter)
    feathers = hunter.economic.npc_inventory.get("feather",0)
    assert 3 <= feathers <= 6
    assert world.get_tile_at(56,49).name != "Animal Corpse"
    world._update_entity_position(hunter,drop.global_center_x,drop.global_center_y)
    world._handle_npc_hunting_task(hunter)
    assert drop.building_inventory.get("feather",0) == feathers
    assert hunter.economic.npc_inventory.get("feather",0) == 0


@pytest.mark.parametrize("arrows,in_village", [(0,True), (3,True), (3,False)])
def test_hunter_rearms_only_from_actual_workplace_stock(world, arrows, in_village):
    from config import CHUNK_SIZE
    hunter = NPC(50,49,name="Hunter")
    hunter.equipment.weapon.bind(ItemReference("short_bow"))
    bird = Animal(56,49,name="Turkey",animal_type="turkey")
    world.npcs, world.village_npcs = [bird], [hunter]
    village = Village()
    drop = Building(0,0,5,5,building_type="butcher_shop",category="commercial_workplace",
                    global_chunk_x_start=48,global_chunk_y_start=47)
    village.add_building(drop)
    world.chunks[49//CHUNK_SIZE][50//CHUNK_SIZE].village = village if in_village else None
    world.buildings_by_id[drop.id] = drop
    drop.building_inventory.add_item("arrow", arrows)
    references = list(drop.building_inventory.iter_item_references("arrow"))
    hunter.task_context = "hunting"
    hunter.task_context_data = dict(state="pursuing",prey_id=bird.id,dropoff_building_id=drop.id)
    world._mark_entity_positions_dirty()
    assert world._handle_npc_hunting_task(hunter)
    assert not bird.physical.is_dead
    assert hunter.economic.npc_inventory.get("arrow",0) == arrows
    assert drop.building_inventory.get("arrow",0) == 0
    assert all(hunter.economic.npc_inventory.has_item_reference(ref) for ref in references)


def test_pre_scar_save_fields_backfill_cleanly(world):
    from entities.anatomy import Anatomy
    body = Anatomy.__new__(Anatomy)
    state = dict(world.player.combat.anatomy.__dict__)
    state.pop("scars")
    state.pop("last_attack_kind")
    body.__setstate__(state)
    assert body.scars == [] and body.last_attack_kind == "fight"
    old_shirt = ItemReference.__new__(ItemReference)
    state = dict(ItemReference("wool_shirt").__dict__)
    state.pop("blood_stains")
    old_shirt.__setstate__(state)
    assert old_shirt.blood_stains == {}


def test_workshop_station_and_component_batch_are_real(world):
    smith = NPC(50,50,name="Smith")
    shop = Building(0,0,5,5,building_type="blacksmith_shop",category="commercial_workplace")
    shop.building_inventory.add_item("iron_ingot")
    assert world._craft_recipe_at_workplace(smith,shop,"arrowhead")
    assert shop.building_inventory.get("arrowhead",0) == 8
    assert not shop.building_inventory.get("iron_ingot",0)
    shop.building_inventory.add_item("wooden_plank",2)
    shop.building_inventory.add_item("bowstring")
    assert not world._craft_recipe_at_workplace(smith,shop,"short_bow")
    assert shop.building_inventory.get("wooden_plank",0) == 2
