"""Read-only examination of persistent anatomy using the game's panel language."""
import textwrap

from entities.body_model import capabilities, tissue_damage, wounds_summary
from rendering import widgets, ui_theme as theme
from config import DAY_LENGTH_TICKS


def draw_body_menu(console, world):
    actor = world.get_entity_by_id(getattr(world, "body_menu_target_id", world.player.id))
    geometry = widgets.centered_menu(78, 44)
    widgets.panel(console, *geometry, title="Body & Injuries", focused=True)
    x, y, width = geometry.inner_x, geometry.inner_y, geometry.inner_width
    if actor is None:
        widgets.text_line(console, x, y, "This person is no longer here.")
        return
    body = actor.combat.anatomy
    widgets.text_line(console, x, y, actor.name, color=theme.HEADING, width=width)
    widgets.text_line(console, x, y+1, "Persistent wounds / tissue function / recovery", color=theme.TEXT_MUTED, width=width)
    rows = []
    def row(text, color=theme.TEXT):
        rows.extend(widgets.Row(line, color=color) for line in (textwrap.wrap(text, width-2) or [""]))
    if body.body_plan:
        summaries = wounds_summary(body)
        for index, summary in enumerate(summaries[:3]):
            widgets.text_line(console, x, y+3+index, summary, color=theme.TEXT, width=width-16)
        # Same persistent face and actual worn layers as the inventory/world.
        from rendering import character_layers as layers, pixel_scene as pixels
        if not getattr(actor, "animal_type", None) and layers.enabled(world):
            from rendering.people_art import Activity
            kind = "unconscious" if "unconscious" in actor.physical.status_effects else "idle"
            image, _, token = layers.frame(world, actor, 3, Activity(kind), "south", 0, False, None)
            pixels.stamp(console, image, (x+width-8)*16, (y+2)*16, token=token)
        widgets.rule(console, x, y+8, width)
        row("WOUNDS / RECOVERY", theme.HEADING)
        active = [w for w in body.wounds if w.healing < 1 or w.permanent]
        if not active:
            row("No active wounds.", theme.SUCCESS)
        for wound in active:
            state = "fracture + " if wound.fracture else ""
            row(f"#{wound.id:02d}  {wound.part.replace('_', ' ')}: {state}{wound.kind}", theme.WARNING)
            care = ", ".join(label for label, present in (("dressed", wound.dressed), ("splinted", wound.splinted), ("lasting damage", bool(wound.permanent))) if present) or "untreated"
            row(f"     Day {wound.created_tick//DAY_LENGTH_TICKS} / {wound.weapon or 'prior injury'} / {wound.healing:.0%} healed / {care}", theme.TEXT_DIM)
        row("")
        row("TISSUE DAMAGE  |  skin / muscle / bone / vital", theme.HEADING)
        injured_parts = dict.fromkeys(w.part for w in body.wounds if w.healing < 1 or w.permanent)
        for name in injured_parts:
            damage = tissue_damage(body, name)
            detail = " / ".join(f"{damage[layer]:.0%}" if layer in damage else "--" for layer in ("skin", "muscle", "bone", "vital"))
            row(f"{name.replace('_', ' ')}: {detail}")
        caps = capabilities(body)
        row(f"Sight {caps['sight']:.0%} | Breathing {caps['breathing']:.0%}", theme.TEXT_DIM)
        if body.scars:
            row("")
            row("SCARS / HISTORY", theme.HEADING)
            for scar in body.scars:
                row(f"{scar.part.replace('_', ' ')}: healed {scar.kind} scar / {scar.weapon or 'old injury'} / Day {scar.formed_tick//DAY_LENGTH_TICKS}", theme.TEXT_DIM)
        if body.death_cause:
            row(f"Died: {body.death_cause}", theme.DANGER)
        row("")
        row("TREATMENT", theme.HEADING)
        row("Bandage or salve: dress one bleeding wound. Splint: stabilize a fractured part. Supplies are consumed; tissue damage remains.", theme.TEXT_DIM)
        row("Deep wounds can still bleed after dressing. Rest supports recovery; severe injuries may leave permanent impairment.", theme.TEXT_DIM)
    else:
        row("This creature does not yet have a detailed body plan.")
    region = widgets.ListRegion(x, y+10, width, 26)
    world.body_menu_scroll = widgets.list_view(console, region, rows, selected_index=None,
        show_cursor=False, scroll_offset=getattr(world, "body_menu_scroll", 0))
    world.body_menu_max_scroll = max(0, len(rows)-26)
    widgets.hint_bar(console, x, geometry.hint_row, width,
                     [("T", "treat (10 ticks)"), ("Up/Down", "scroll"), ("Esc", "close")])
