import re

with open('engine.py', 'r') as f:
    engine_code = f.read()

# 1. Update _get_noticeboard_menu_entries in engine.py
search_entries = """    def _get_noticeboard_menu_entries(self):
        entries: list[tuple[str, str]] = []
        for task in self._get_noticeboard_menu_tasks():
            entries.append(("haul", task.id))
        for task in self.town_board.get_open_employment_tasks():
            entries.append(("job", task.id))
        return entries"""

replace_entries = """    def _get_noticeboard_menu_entries(self):
        entries: list[tuple[str, str]] = []
        for task in self._get_noticeboard_menu_tasks():
            entries.append(("haul", task.id))
        for task in self.town_board.get_open_employment_tasks():
            entries.append(("job", task.id))
        for need in getattr(self.town_board, "economic_needs", []):
            entries.append(("need", need.id))
        return entries"""

engine_code = engine_code.replace(search_entries, replace_entries)

with open('engine.py', 'w') as f:
    f.write(engine_code)


with open('rendering/console_renderer.py', 'r') as f:
    render_code = f.read()

# 2. Update draw_noticeboard_menu in console_renderer.py
search_render = """        if notice_id.startswith("job:"):
            job_task = world.town_board.get_employment_task(notice_id.split(":", 1)[1])
            if job_task is None:
                continue
            building = world.buildings_by_id.get(job_task.target_building_id)
            building_name = str(getattr(building, "building_type", "Unknown")).replace("_", " ")
            line = f"JOB: {job_task.profession_role} @ {building_name} - {job_task.daily_wage}/day"
            color = (0, 255, 255) if list_index == selected_index else (144, 220, 255)
        else:
            task = world.town_board.get_task(notice_id.split(":", 1)[1] if ":" in notice_id else notice_id)
            if task is None:
                continue
            blueprint = world.blueprints_by_id.get(task.blueprint_id)
            if blueprint is None:
                continue
            status = "Claimed" if task.assigned_entity_id == world.player.id else "Open"
            line = f"HAUL: {task.item_key.replace('_', ' ')} -> {blueprint.target_build.replace('_', ' ')} @ ({task.destination_x},{task.destination_y}) [{status}]"
            color = (0, 255, 255) if list_index == selected_index else ((255, 255, 255) if status == "Open" else (255, 215, 0))"""

replace_render = """        if notice_id.startswith("job:"):
            job_task = world.town_board.get_employment_task(notice_id.split(":", 1)[1])
            if job_task is None:
                continue
            building = world.buildings_by_id.get(job_task.target_building_id)
            building_name = str(getattr(building, "building_type", "Unknown")).replace("_", " ")
            line = f"JOB: {job_task.profession_role} @ {building_name} - {job_task.daily_wage}/day"
            color = (0, 255, 255) if list_index == selected_index else (144, 220, 255)
        elif notice_id.startswith("need:"):
            need_id = notice_id.split(":", 1)[1]
            need = next((n for n in getattr(world.town_board, "economic_needs", []) if n.id == need_id), None)
            if need is None:
                continue
            line = f"NEED: {need.description}"
            color = (0, 255, 255) if list_index == selected_index else (255, 100, 100)
        else:
            task = world.town_board.get_task(notice_id.split(":", 1)[1] if ":" in notice_id else notice_id)
            if task is None:
                continue
            blueprint = world.blueprints_by_id.get(task.blueprint_id)
            if blueprint is None:
                continue
            status = "Claimed" if task.assigned_entity_id == world.player.id else "Open"
            line = f"HAUL: {task.item_key.replace('_', ' ')} -> {blueprint.target_build.replace('_', ' ')} @ ({task.destination_x},{task.destination_y}) [{status}]"
            color = (0, 255, 255) if list_index == selected_index else ((255, 255, 255) if status == "Open" else (255, 215, 0))"""

render_code = render_code.replace(search_render, replace_render)

with open('rendering/console_renderer.py', 'w') as f:
    f.write(render_code)
