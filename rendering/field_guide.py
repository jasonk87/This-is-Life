"""A readable, scrollable field guide with permanently visible vitals.

Uses the existing sensory descriptions: UI convenience grants no extra world
knowledge. The last hovered observation stays available while reading it.
"""
import textwrap

from config import MAP_WIDTH, MAP_HEIGHT, SCREEN_HEIGHT, STATUS_PANEL_WIDTH
from rendering import widgets, ui_theme as theme
from presentation.sensory_observation import list_tile_focus_targets, describe_focus_target

BODY_TOP = 15
BODY_HEIGHT = 26


def draw_field_guide(console, world, camera_x, camera_y):
    from rendering import console_renderer as cr
    x, width = MAP_WIDTH, STATUS_PANEL_WIDTH
    widgets.panel(console, x, 0, width, SCREEN_HEIGHT, title="Field Guide", bg=theme.PANEL_BG_DEEP)
    inner_x, inner_w = x+2, width-4
    for row, line in enumerate(textwrap.wrap(str(world.player.name), inner_w)[:2]):
        widgets.text_line(console, inner_x, 2+row, line, color=theme.HEADING)
    widgets.text_line(console, inner_x, 5, world.player.economic.profession, width=inner_w, color=theme.TEXT_DIM)
    widgets.text_line(console, inner_x, 6, f"{world.player.economic.money} coins", width=inner_w, color=theme.SUCCESS)
    widgets.rule(console, inner_x, 7, inner_w)
    widgets.heading(console, inner_x, 8, "Body / Needs")
    p = world.player.physical
    body = getattr(world.player.combat, "anatomy", None)
    blood = f"Blood {body.blood:.0%}" if body and body.body_plan else "Body: not examined"
    widgets.text_line(console, inner_x, 9, blood, width=inner_w,
                      color=theme.DANGER if body and body.blood < .6 else theme.TEXT)
    widgets.meter(console, inner_x, 10, inner_w, "HU", p.hunger, p.max_hunger, cr._hunger_meter_colors(p.hunger/max(1,p.max_hunger)))
    widgets.meter(console, inner_x, 11, inner_w, "TH", p.thirst, p.max_thirst, cr._thirst_meter_colors(p.thirst/max(1,p.max_thirst)))
    widgets.text_line(console, inner_x, 12, "HU hunger TH thirst", width=width-3, color=theme.TEXT_MUTED)
    widgets.rule(console, inner_x, 13, inner_w)

    rows = []
    def line(text, color=theme.TEXT_DIM):
        for part in textwrap.wrap(str(text), width=inner_w) or [""]:
            rows.append(widgets.Row(part, color=color))
    def heading(text):
        if rows:
            line("")
        line(text, theme.HEADING)

    if p.status_effects:
        heading("Condition")
        for effect in p.status_effects:
            line(f"! {effect}", theme.WARNING)
    body = getattr(world.player.combat, "anatomy", None)
    if body is not None and body.body_plan:
        from entities.body_model import wounds_summary
        heading("Body / Injuries")
        for detail in wounds_summary(body):
            line(detail)
        if body.wounds:
            line("Bag [U]: use bandage / splint", theme.INFO)
    heading("Here & Now")
    from simulation.systems.settlements import current
    village = current(world)
    line(village.name if village else "Countryside", theme.HEADING)
    destination = getattr(world.player, "known_settlements", {}).get(getattr(world.player, "travel_destination_id", None))
    if destination and (not village or getattr(world.player, "travel_destination_id", None) != village.id):
        tx, ty = destination["coords"]
        line(f"To {destination['name']}: {tx}, {ty}", theme.INFO)
        dx, dy = tx-world.player.x, ty-world.player.y
        line(f"{abs(dx)} tiles {'east' if dx >= 0 else 'west'}, {abs(dy)} {'south' if dy >= 0 else 'north'}")
    line(cr._format_world_clock(world.game_time))
    line("PAUSED" if getattr(world, "is_paused", False) else f"Time: {getattr(world,'simulation_speed',1):g}x", theme.WARNING)
    line(f"{cr.current_season_name(world)} / {world.weather.replace('_',' ').title()}", theme.INFO)
    tile = world.get_tile_at(world.player.x, world.player.y)
    standing, _ = cr._get_focus_summary(world)
    line(standing or (tile.name if tile else "Unknown terrain"))
    line(f"At {world.player.x}, {world.player.y}", theme.TEXT_MUTED)
    active_bounties = [c for c in getattr(world, "bounty_contracts", {}).values() if c.status in {"accepted", "escorting"}]
    if active_bounties:
        heading("Contracts / Alive Only")
        for contract in active_bounties:
            line(f"{contract.target_name}: {contract.status}", theme.WARNING)
            line(f"Last report: {contract.last_seen}")
    focus = cr._get_focus_target(world, camera_x, camera_y)
    if focus.get("label"):
        line(f"Facing: {focus['label']}", theme.WARNING)

    mx, my = getattr(world,"mouse_x",-1), getattr(world,"mouse_y",-1)
    if 0 <= mx < MAP_WIDTH and 3 <= my < MAP_HEIGHT:
        inspection = cr._get_hover_inspect(world, camera_x, camera_y)
        observation = []
        if inspection:
            for target in list_tile_focus_targets(world, *inspection["coords"]):
                observation.append(describe_focus_target(world, target))
        world._ui_field_observation = (inspection, observation)
    inspection, observation = getattr(world, "_ui_field_observation", (None, []))
    if inspection:
        heading("Under the Cursor")
        line(inspection["tile"], theme.SUCCESS)
        line(f"At {inspection['coords'][0]}, {inspection['coords'][1]}", theme.TEXT_MUTED)
        if inspection.get("object"):
            line(inspection["object"], theme.INFO)
        if inspection.get("property"):
            line(inspection["property"], theme.HEADING)
        for text in observation:
            line(text)
        if inspection.get("territory"):
            line(inspection["territory"], theme.TEXT_MUTED)
        if inspection.get("social"):
            line(inspection["social"], theme.SOCIAL)
        if getattr(world,"show_autonomy_overlay",False) and inspection.get("autonomy_summary"):
            line(inspection["autonomy_summary"], theme.SOCIAL)
    else:
        heading("Observe")
        line("Hover over the world to inspect.", theme.TEXT_MUTED)
        line("L for a closer look.", theme.TEXT_MUTED)

    heading("Nearby")
    nearby = cr._get_visible_nearby_entities(world, limit=4)
    for distance, entity in nearby:
        name = world.get_entity_display_name(entity, include_relationship=True)
        if isinstance(entity, cr.Animal):
            name = getattr(entity,"animal_type","Animal").replace("_"," ").title()
        line(f"{distance}t  {name}")
    if not nearby:
        line("None visible", theme.TEXT_MUTED)
    quests = list(world.player.knowledge.active_quests.values())
    if quests:
        heading("Journal [Q]")
        for quest in quests:
            line(quest.get("title","Task"), theme.INFO)
            if quest.get("type") == "fetch":
                key = quest.get("item_to_fetch_key", "")
                line(f"Fetch {cr._construction_material_name(key)}")
                line(f"{world.player.economic.inventory.get(key,0)}/{quest.get('item_fetch_count',0)} collected")
    heading("Reputation")
    reps = [(f,r) for f,r in world.player.social.reputation.items() if r]
    for faction, reputation in reps:
        line(f"{faction.replace('_',' ').title()}: {reputation}")
    if not reps:
        line("Neutral", theme.TEXT_MUTED)
    if getattr(world,"show_autonomy_overlay",False):
        heading("Autonomy [F3]")
        for key,value in getattr(world,"autonomy_counters",{}).items():
            line(f"{key.replace('_',' ')}: {value}")

    region = widgets.ListRegion(inner_x, BODY_TOP, inner_w, BODY_HEIGHT)
    offset = widgets.list_view(console, region, rows, selected_index=None, show_cursor=False,
                               scroll_offset=getattr(world,"field_guide_scroll",0))
    world.field_guide_scroll = offset
    world.field_guide_max_scroll = max(0,len(rows)-BODY_HEIGHT)
    widgets.text_line(console, inner_x, 42, "Wheel: read more", width=inner_w, color=theme.TEXT_MUTED)
    cr._draw_minimap_panel(console, world, x, 44, width, SCREEN_HEIGHT-44)
