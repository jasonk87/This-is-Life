# rendering/console_renderer.py

from tcod_compat import tcod
import textwrap
import itertools
from config import (
    SCREEN_WIDTH, SCREEN_HEIGHT, MAP_WIDTH, MAP_HEIGHT, STATUS_PANEL_WIDTH,
    MINIMAP_WIDTH, MINIMAP_HEIGHT, MINIMAP_X, MINIMAP_Y,
    COLOR_PLAYER_STATUS_WET, COLOR_PLAYER_STATUS_FREEZING, COLOR_CURSOR_INFO_TEXT,
    WORLD_WIDTH, WORLD_HEIGHT, CHUNK_SIZE
)
from data.tiles import TILE_DEFINITIONS
from data.items import ITEM_DEFINITIONS
from data.construction import CONSTRUCTION_RECIPES
from entities.animal import Animal
from engine import Player

def draw_status_panel(console, world):
    """Draws the status panel on the right side of the screen."""
    panel_x = MAP_WIDTH
    console.draw_frame(x=panel_x, y=0, width=STATUS_PANEL_WIDTH, height=SCREEN_HEIGHT,
                       title="Status", clear=True, fg=(255, 255, 255), bg=(0, 0, 0))

    y = 2

    # --- Time & Season ---
    day = world.game_time // (24 * 60)
    hour = (world.game_time // 60) % 24
    minute = world.game_time % 60
    time_str = f"Day {day}, {hour:02d}:{minute:02d}"
    season = world.seasons[world.current_season_index]
    weather = world.weather.replace('_', ' ').title()

    console.print(x=panel_x + 1, y=y, string=time_str, fg=(200, 200, 200))
    y += 1
    console.print(x=panel_x + 1, y=y, string=f"{season} - {weather}", fg=(150, 150, 255))
    y += 2

    # --- Vitals ---
    # HP Bar
    hp_pct = world.player.combat.hp / world.player.combat.max_hp
    bar_width = STATUS_PANEL_WIDTH - 4
    filled_width = int(bar_width * hp_pct)

    console.print(x=panel_x + 1, y=y, string="Health:", fg=(255, 100, 100))
    y += 1
    console.draw_rect(x=panel_x + 1, y=y, width=bar_width, height=1, ch=ord('░'), fg=(100, 0, 0)) # Empty
    if filled_width > 0:
        console.draw_rect(x=panel_x + 1, y=y, width=filled_width, height=1, ch=ord('█'), fg=(255, 0, 0)) # Filled
    console.print(x=panel_x + 2, y=y, string=f"{world.player.combat.hp}/{world.player.combat.max_hp}", fg=(255, 255, 255))
    y += 2

    # Hunger
    hunger_pct = min(1.0, world.player.physical.hunger / world.player.physical.max_hunger)
    filled_hunger = int(bar_width * hunger_pct)
    hunger_color = (0, 255, 0)
    if hunger_pct > 0.5: hunger_color = (255, 255, 0)
    if hunger_pct > 0.8: hunger_color = (255, 0, 0)

    console.print(x=panel_x + 1, y=y, string="Hunger:", fg=(255, 255, 0))
    y += 1
    console.draw_rect(x=panel_x + 1, y=y, width=bar_width, height=1, ch=ord('░'), fg=(50, 50, 0))
    if filled_hunger > 0:
        console.draw_rect(x=panel_x + 1, y=y, width=filled_hunger, height=1, ch=ord('█'), fg=hunger_color)
    y += 2

    # Thirst
    thirst_pct = min(1.0, world.player.physical.thirst / world.player.physical.max_thirst)
    filled_thirst = int(bar_width * thirst_pct)
    thirst_color = (0, 255, 255)
    if thirst_pct > 0.5: thirst_color = (0, 150, 255)
    if thirst_pct > 0.8: thirst_color = (0, 0, 255)

    console.print(x=panel_x + 1, y=y, string="Thirst:", fg=(0, 200, 255))
    y += 1
    console.draw_rect(x=panel_x + 1, y=y, width=bar_width, height=1, ch=ord('░'), fg=(0, 0, 50))
    if filled_thirst > 0:
        console.draw_rect(x=panel_x + 1, y=y, width=filled_thirst, height=1, ch=ord('█'), fg=thirst_color)
    y += 2

    # Status Effects
    if world.player.physical.status_effects:
        console.print(x=panel_x + 1, y=y, string="Conditions:", fg=(200, 200, 200))
        y += 1
        for effect in world.player.physical.status_effects:
            color = (255, 255, 255)
            if effect == "Wet": color = COLOR_PLAYER_STATUS_WET
            elif effect == "Freezing": color = COLOR_PLAYER_STATUS_FREEZING
            elif effect == "Overheating": color = (255, 100, 0)
            console.print(x=panel_x + 2, y=y, string=f"! {effect}", fg=color)
            y += 1
        y += 1

    # Active Quest (Top Priority)
    active_quests = list(world.player.knowledge.active_quests.values())
    if active_quests:
        console.print(x=panel_x + 1, y=y, string="Current Objective:", fg=(255, 215, 0))
        y += 1
        quest = active_quests[0]
        # Wrap title if too long
        title_lines = textwrap.wrap(quest["title"], width=STATUS_PANEL_WIDTH - 2)
        for line in title_lines:
            console.print(x=panel_x + 1, y=y, string=line, fg=(255, 255, 255))
            y += 1

        # Simple progress
        if quest["type"] == "fetch":
            item_key = quest["item_to_fetch_key"]
            req = quest["item_fetch_count"]
            curr = 0
            for item in world.player.economic.inventory:
                if item["key"] == item_key:
                    curr += item.get("quantity", 1)
            console.print(x=panel_x + 2, y=y, string=f"({curr}/{req})", fg=(200, 200, 200))
            y += 1
        elif quest["type"] == "kill":
            req = quest.get("target_count", 1)
            curr = quest.get("progress", 0)
            console.print(x=panel_x + 2, y=y, string=f"({curr}/{req})", fg=(200, 200, 200))
            y += 1

        if len(active_quests) > 1:
            console.print(x=panel_x + 1, y=y, string=f"+ {len(active_quests)-1} more (Press Q)", fg=(100, 100, 100))
            y += 1

    y += 1

    # Faction Reputations (Condensed)
    console.print(x=panel_x + 1, y=y, string="Reputation:", fg=(150, 150, 150))
    y += 1
    for faction, rep in world.player.social.reputation.items():
        if rep != 0:
            console.print(x=panel_x + 2, y=y, string=f"{faction[:3].upper()}: {rep}", fg=(200, 200, 200))
            y += 1

def draw_minimap(console, world):
    """Draws a minimap in the corner of the screen."""
    # Draw frame for the minimap
    console.draw_frame(x=MINIMAP_X, y=MINIMAP_Y, width=MINIMAP_WIDTH, height=MINIMAP_HEIGHT,
                       title="World Map", clear=True, fg=(255, 255, 255), bg=(0, 0, 0))

    world_map = world.get_world_map_data() # This method needs to exist in World

    for y in range(MINIMAP_HEIGHT - 2):
        for x in range(MINIMAP_WIDTH - 2):
            map_x = int((x / (MINIMAP_WIDTH - 2)) * world.chunk_width)
            map_y = int((y / (MINIMAP_HEIGHT - 2)) * world.chunk_height)

            if 0 <= map_y < world.chunk_height and 0 <= map_x < world.chunk_width:
                tile_info = world_map[map_y][map_x]
                char, color, bg_color = tile_info['char'], tile_info['color'], tile_info['bg_color']

                console.print(x=MINIMAP_X + 1 + x, y=MINIMAP_Y + 1 + y, string=char, fg=color, bg=bg_color)

    # Draw player position on minimap
    player_map_x = int((world.player.x / world.width) * (MINIMAP_WIDTH - 2))
    player_map_y = int((world.player.y / world.height) * (MINIMAP_HEIGHT - 2))
    console.print(x=MINIMAP_X + 1 + player_map_x, y=MINIMAP_Y + 1 + player_map_y,
                  string="@", fg=(255, 0, 0))


def draw_cursor_info(console, world, camera_x, camera_y):
    """Draws information about the tile under the mouse cursor."""
    mouse_x, mouse_y = world.mouse_x, world.mouse_y
    if not (0 <= mouse_x < MAP_WIDTH and 0 <= mouse_y < MAP_HEIGHT):
        return

    world_x, world_y = camera_x + mouse_x, camera_y + mouse_y

    info_str = ""
    tile = world.get_tile_at(world_x, world_y)
    if tile:
        info_str = f"Tile: {tile.name} ({world_x}, {world_y})"

        # Add weather info to the cursor
        info_str += f" | Weather: {world.weather}"

        if tile.name == "Animal Corpse" and "animal_type" in tile.properties:
            info_str += f" ({tile.properties['animal_type'].replace('_', ' ')})"

    if info_str:
        # Print info at the bottom of the map view
        console.print(x=1, y=MAP_HEIGHT - 1, string=info_str, fg=COLOR_CURSOR_INFO_TEXT)

def is_visible(world, x, y):
    """Checks if a world coordinate is within the player's local FOV map."""
    fov_map = getattr(world, 'player_fov_map', None)
    if fov_map is None:
        # Fallback if FOV system isn't fully initialized
        return True

    if 0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT:
        return fov_map[y, x]
    return False

def _draw_visual_effect(console, effect, camera_x, camera_y):
    effect_type = getattr(effect, "effect_type", None)
    draw_x = int(round(getattr(effect, "x", 0))) - camera_x
    draw_y = int(round(getattr(effect, "y", 0))) - camera_y
    if not (0 <= draw_x < console.width and 0 <= draw_y < console.height):
        return

    if effect_type == "floating_text":
        console.print(x=draw_x, y=draw_y, string=getattr(effect, "text", ""), fg=getattr(effect, "color", (255, 255, 255)))
    elif effect_type == "projectile":
        console.print(x=draw_x, y=draw_y, string=getattr(effect, "char", "*"), fg=getattr(effect, "color", (255, 255, 0)))

def draw(console, world, camera_x, camera_y):
    """Draws the main game screen."""
    console.clear()

    # Draw the map
    fov_map = getattr(world, 'player_fov_map', None)
    exp_map = world.explored_map
    
    for y in range(MAP_HEIGHT):
        map_y = camera_y + y
        if not (0 <= map_y < WORLD_HEIGHT):
            continue
            
        chunk_y = map_y // CHUNK_SIZE
        local_y = map_y % CHUNK_SIZE
        chunk_row = world.chunks[chunk_y]

        for x in range(MAP_WIDTH):
            map_x = camera_x + x
            if not (0 <= map_x < WORLD_WIDTH):
                continue

            chunk_x = map_x // CHUNK_SIZE
            chunk = chunk_row[chunk_x]

            if not chunk.is_terrain_generated:
                world._generate_chunk_detail(chunk, chunk_x, chunk_y)

            tile = chunk.tiles[local_y][map_x % CHUNK_SIZE]

            if tile:
                is_in_fov = fov_map[map_y, map_x] if fov_map is not None else True
                if is_in_fov:
                    console.print(x=x, y=y, string=chr(tile.char), fg=tile.color)
                    exp_map[map_y, map_x] = True
                elif exp_map[map_y, map_x]:
                    console.print(x=x, y=y, string=chr(tile.char), fg=(100, 100, 100)) # Explored but not visible

    # Draw path visualizer
    if hasattr(world.player.state, 'current_path') and world.player.state.current_path:
        for px, py in world.player.state.current_path:
            screen_x = px - camera_x
            screen_y = py - camera_y
            if 0 <= screen_x < MAP_WIDTH and 0 <= screen_y < MAP_HEIGHT:
                # Draw path markers (e.g., small dots)
                # Only if visible in player FOV
                if is_visible(world, px, py):
                    console.print(x=screen_x, y=screen_y, string="•", fg=(0, 255, 0))

    # Draw Visual Effects
    for effect in world.visual_effects:
        _draw_visual_effect(console, effect, camera_x, camera_y)

    # Draw entities
    all_entities = itertools.chain(world.npcs, world.village_npcs, [world.player])
    for entity in sorted(all_entities, key=lambda e: e.render_order.value if hasattr(e, 'render_order') else 0):
        if isinstance(entity, Player) and entity.state.is_riding:
            continue

        # Use render coordinates if available (for smooth movement), else fall back to logic coordinates
        r_x = getattr(entity, 'render_x', entity.x)
        r_y = getattr(entity, 'render_y', entity.y)

        # Cast to int for grid rendering
        draw_x = int(round(r_x))
        draw_y = int(round(r_y))

        # Check visibility based on the *logical* position (so they don't disappear while moving into FOV)
        # Or check draw_x/y? Checking logical x/y is safer for consistency with FOV map.
        if is_visible(world, entity.x, entity.y) or is_visible(world, draw_x, draw_y):
            if 0 <= draw_x - camera_x < MAP_WIDTH and 0 <= draw_y - camera_y < MAP_HEIGHT:
                bg_color = (100, 0, 50) if isinstance(entity, Player) else None
                console.print(x=draw_x - camera_x, y=draw_y - camera_y,
                              string=chr(entity.char), fg=entity.color, bg=bg_color)

    draw_status_panel(console, world)
    # draw_minimap(console, world)
    draw_cursor_info(console, world, camera_x, camera_y)

    # Draw chat/interaction UI if active
    if world.interaction_context["active"]:
        draw_interaction_menu(console, world)

    if world.game_state == "CRAFTING_MENU":
        draw_crafting_menu(console, world)

    if world.game_state == "BUILDING_MENU":
        draw_building_menu(console, world)

    if world.game_state == "INFO_MENU":
        draw_info_menu(console, world)

    if world.game_state == "KNOWLEDGE_MENU":
        draw_knowledge_menu(console, world)

    if world.game_state == "QUEST_MENU":
        draw_quest_menu(console, world)

    if world.game_state == "BOOK_READING":
        draw_book_reading_ui(console, world)

    if world.game_state == "TRADE_MENU" or world.trade_ui_active:
        draw_trade_menu(console, world)

    if world.game_state == "HELP_MENU":
        draw_help_menu(console)

    # Draw weather overlay
    draw_weather_overlay(console, world, camera_x, camera_y)

    # Draw Mouse Tooltip/Examine
    if 0 <= world.mouse_x < MAP_WIDTH and 0 <= world.mouse_y < MAP_HEIGHT:
        mouse_world_x = camera_x + world.mouse_x
        mouse_world_y = camera_y + world.mouse_y

        # Check if visible
        if is_visible(world, mouse_world_x, mouse_world_y):
            tile = world.get_tile_at(mouse_world_x, mouse_world_y)
            if tile:
                info_text = tile.name

                # Check for entities
                entities_here = []
                for entity in itertools.chain([world.player], world.all_npcs):
                    if entity.x == mouse_world_x and entity.y == mouse_world_y:
                        if hasattr(entity, "physical") and entity.physical.is_dead:
                            entities_here.append(f"Dead {entity.name}")
                        else:
                            entities_here.append(entity.name)

                if (mouse_world_x, mouse_world_y) in world.items_on_map:
                    items = world.items_on_map[(mouse_world_x, mouse_world_y)]
                    if items:
                        entities_here.append(f"Items ({len(items)})")

                if entities_here:
                    info_text += f" | {', '.join(entities_here)}"

                # Draw tooltip string near bottom right of map
                console.print(x=1, y=MAP_HEIGHT - 1, string=info_text, fg=COLOR_CURSOR_INFO_TEXT, bg=(0,0,0))

    # Draw chat log at the bottom
    y = SCREEN_HEIGHT - 6
    console.draw_frame(x=0, y=y, width=MAP_WIDTH, height=6, title="Log",
                       clear=True, fg=(255, 255, 255), bg=(0, 0, 0))
    for i, message in enumerate(world.chat_log[-4:]):
        console.print(x=1, y=y + 1 + i, string=message)

def draw_weather_overlay(console, world, camera_x, camera_y):
    """Draws a simple screen overlay based on the current weather."""
    if world.weather in ["clear", "heatwave"]:
        return

    import random

    # Simple stateless particle effect using map coordinates hash
    if world.weather == "rain" or world.weather == "storm":
        char = "'"
        color = (100, 150, 255) if world.weather == "rain" else (150, 150, 200)
        density = 0.1 if world.weather == "rain" else 0.3
    elif world.weather == "snow":
        char = "*"
        color = (255, 255, 255)
        density = 0.05
    else:
        return

    # Offset by time to create movement
    time_offset = world.game_time % 100

    for y in range(MAP_HEIGHT):
        for x in range(MAP_WIDTH):
            # Using coordinate hash to generate deterministic pseudo-random layout that changes with time
            h = hash((x + camera_x + time_offset, y + camera_y + time_offset)) % 1000
            if h < density * 1000:
                if is_visible(world, camera_x + x, camera_y + y):
                    console.print(x=x, y=y, string=char, fg=color)

def draw_interaction_menu(console, world):
    """Draws the context-sensitive interaction menu."""
    ctx = world.interaction_context
    x, y = world.mouse_x, world.mouse_y

    # Find longest action to determine menu width
    longest_action = 0
    if ctx["available_actions"]:
        longest_action = max(len(action) for action in ctx["available_actions"])
    width = max(15, longest_action + 4)
    height = len(ctx["available_actions"]) + 2

    # Adjust position to keep menu on screen
    if x + width > MAP_WIDTH:
        x = MAP_WIDTH - width
    if y + height > MAP_HEIGHT:
        y = MAP_HEIGHT - height

    console.draw_frame(x=x, y=y, width=width, height=height,
                       title=f"Interact: {ctx['target_entities'][ctx['selected_entity_index']]['name']}",
                       clear=True, fg=(255, 255, 255), bg=(50, 50, 50))

    for i, action in enumerate(ctx["available_actions"]):
        text_color = (255, 255, 255)
        if i == ctx["selected_action_index"]:
            text_color = (0, 255, 255) # Highlight selected action
        console.print(x=x + 1, y=y + 1 + i, string=action, fg=text_color)

def draw_crafting_menu(console, world):
    """Draws the crafting menu UI."""
    menu_width = 50
    x = (MAP_WIDTH - menu_width) // 2
    all_recipes = world.crafting_menu_context.get("all_recipes", [])
    num_recipes = len(all_recipes)
    menu_height = min(30, num_recipes + 4) # Limit height
    y = (SCREEN_HEIGHT - menu_height) // 2

    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Crafting", clear=True)

    if not all_recipes:
        console.print_box(x=x+1, y=y+1, width=menu_width-2, height=menu_height-2,
                          string="No recipes available.", fg=(128, 128, 128))
        return

    selected_index = world.crafting_menu_context.get("selected_recipe_index", 0)
    scroll_offset = world.crafting_menu_context.get("scroll_offset", 0)
    display_height = menu_height - 2

    # Adjust scroll offset if selection is out of view
    if selected_index < scroll_offset:
        scroll_offset = selected_index
    elif selected_index >= scroll_offset + display_height:
        scroll_offset = selected_index - display_height + 1
    world.crafting_menu_context["scroll_offset"] = scroll_offset

    # Display recipes
    for i in range(display_height):
        list_index = scroll_offset + i
        if list_index < num_recipes:
            recipe_key = all_recipes[list_index]
            item_def = TILE_DEFINITIONS.get(recipe_key, {}) # Using TILE_DEFINITIONS, assuming item defs are there.
            item_name = item_def.get("name", recipe_key)
            can_craft = world.player_can_craft(recipe_key)
            color = (255, 255, 255) if can_craft else (128, 128, 128)
            if list_index == selected_index:
                color = (0, 255, 255)
            console.print(x=x + 2, y=y + 1 + i, string=item_name, fg=color)

    # Display selected recipe details
    if 0 <= selected_index < num_recipes:
        details_x = x + menu_width
        details_width = 40
        details_height = 20
        console.draw_frame(x=details_x, y=y, width=details_width, height=details_height, title="Recipe Details", clear=True)

        selected_key = all_recipes[selected_index]
        item_def = TILE_DEFINITIONS.get(selected_key, {})
        recipe = item_def.get("crafting_recipe", {})

        detail_y = y + 2
        console.print(x=details_x + 2, y=detail_y, string=f"Requires:", fg=(255, 255, 0))
        detail_y += 1
        for res_key, qty in recipe.items():
            res_def = TILE_DEFINITIONS.get(res_key, {})
            res_name = res_def.get("name", res_key)
            has_enough = world.player.has_item(res_key, qty)
            color = (255, 255, 255) if has_enough else (255, 0, 0)
            console.print(x=details_x + 3, y=detail_y, string=f"- {res_name}: {qty}", fg=color)
            detail_y += 1

        req_station = item_def.get("required_workstation")
        if req_station:
            detail_y += 1
            is_near = world._is_player_near_workstation(req_station)
            color = (255, 255, 255) if is_near else (255, 0, 0)
            console.print(x=details_x + 2, y=detail_y, string=f"Needs: {req_station}", fg=color)

def draw_building_menu(console, world):
    """Draws the building menu UI."""
    menu_width = 50
    x = (MAP_WIDTH - menu_width) // 2
    all_recipes = world.building_menu_context.get("all_recipes", [])
    num_recipes = len(all_recipes)
    menu_height = min(30, num_recipes + 4)
    y = (SCREEN_HEIGHT - menu_height) // 2

    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Construction", clear=True)

    if not all_recipes:
        console.print_box(x=x+1, y=y+1, width=menu_width-2, height=menu_height-2,
                          string="No construction options.", fg=(128, 128, 128))
        return

    selected_index = world.building_menu_context.get("selected_recipe_index", 0)
    scroll_offset = world.building_menu_context.get("scroll_offset", 0)
    display_height = menu_height - 2

    if selected_index < scroll_offset:
        scroll_offset = selected_index
    elif selected_index >= scroll_offset + display_height:
        scroll_offset = selected_index - display_height + 1
    world.building_menu_context["scroll_offset"] = scroll_offset

    for i in range(display_height):
        list_index = scroll_offset + i
        if list_index < num_recipes:
            recipe_key = all_recipes[list_index]
            recipe = CONSTRUCTION_RECIPES.get(recipe_key, {})
            name = recipe.get("name", recipe_key)

            # Check if player has materials
            can_build = True
            for mat_key, mat_qty in recipe.get("materials", {}).items():
                if not world.player.has_item(mat_key, mat_qty):
                    can_build = False
                    break

            color = (255, 255, 255) if can_build else (128, 128, 128)
            if list_index == selected_index:
                color = (0, 255, 255)
            console.print(x=x + 2, y=y + 1 + i, string=name, fg=color)

    # Display details
    if 0 <= selected_index < num_recipes:
        details_x = x + menu_width
        details_width = 40
        details_height = 20
        console.draw_frame(x=details_x, y=y, width=details_width, height=details_height, title="Build Details", clear=True)

        selected_key = all_recipes[selected_index]
        recipe = CONSTRUCTION_RECIPES.get(selected_key, {})

        detail_y = y + 2
        console.print(x=details_x + 2, y=detail_y, string=f"Materials:", fg=(255, 255, 0))
        detail_y += 1
        for mat_key, mat_qty in recipe.get("materials", {}).items():
            item_def = ITEM_DEFINITIONS.get(mat_key)
            tile_def = TILE_DEFINITIONS.get(mat_key)
            mat_name = (
                (item_def or {}).get("name")
                or (tile_def or {}).get("name")
                or mat_key.replace("_", " ").title()
            )
            has_enough = world.player.has_item(mat_key, mat_qty)
            color = (255, 255, 255) if has_enough else (255, 0, 0)
            console.print(x=details_x + 3, y=detail_y, string=f"- {mat_name}: {mat_qty}", fg=color)
            detail_y += 1

        description = recipe.get("description", "")
        if description:
            detail_y += 1
            console.print_box(x=details_x + 2, y=detail_y, width=details_width-4, height=5, string=description, fg=(200, 200, 200))

def draw_info_menu(console, world):
    """Draws the player information menu (stats and inventory)."""
    menu_width = 60
    x = (MAP_WIDTH - menu_width) // 2
    menu_height = 40
    y = (SCREEN_HEIGHT - menu_height) // 2

    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Character Information", clear=True)

    # Stats section
    stat_y = y + 2
    console.print(x=x + 2, y=stat_y, string=f"Fame: {world.player.social.fame}", fg=(255, 255, 0))
    stat_y += 1
    console.print(x=x + 2, y=stat_y, string=f"Infamy: {world.player.social.infamy}", fg=(255, 0, 0))
    stat_y += 1
    if world.player.social.title:
        console.print(x=x + 2, y=stat_y, string=f"Title: {world.player.social.title}", fg=(0, 255, 255))
    stat_y += 2

    # Equipment section
    stat_y += 1
    console.print(x=x + 2, y=stat_y, string="Equipment:", fg=(255, 255, 0))
    stat_y += 1

    # Show active light source
    light_str = "None"
    if world.player.equipment.equipped_light_item_key:
        light_def = TILE_DEFINITIONS.get(world.player.equipment.equipped_light_item_key) or ITEM_DEFINITIONS.get(world.player.equipment.equipped_light_item_key, {})
        light_str = light_def.get("name", world.player.equipment.equipped_light_item_key)
    console.print(x=x + 3, y=stat_y, string=f"- Light Source: {light_str}")
    stat_y += 1

    # Show armor slots
    for slot in ["head", "body", "hands", "feet"]:
        item_key = world.player.equipment.equipped_armor.get(slot)
        item_str = "None"
        if item_key:
            item_def = TILE_DEFINITIONS.get(item_key) or ITEM_DEFINITIONS.get(item_key, {})
            item_str = item_def.get("name", item_key)
        console.print(x=x + 3, y=stat_y, string=f"- {slot.capitalize()}: {item_str}")
        stat_y += 1

    stat_y += 1

    # Inventory section
    inv_y = stat_y
    console.print(x=x + 2, y=inv_y, string=f"Inventory ({len(world.player.economic.inventory)} items):", fg=(255, 255, 0))
    inv_y += 1

    # Aggregate inventory for display
    display_inventory = {}
    for item in world.player.economic.inventory:
        key = item["key"]
        qty = item.get("quantity", 1)
        display_inventory[key] = display_inventory.get(key, 0) + qty

    for item_key, quantity in sorted(display_inventory.items()):
        item_def = TILE_DEFINITIONS.get(item_key) or ITEM_DEFINITIONS.get(item_key, {})
        item_name = item_def.get("name", item_key)
        console.print(x=x + 3, y=inv_y, string=f"- {item_name}: {quantity}")
        inv_y += 1

    inv_y += 2
    console.print(x=x + 2, y=inv_y, string="Active Quests:", fg=(255, 255, 0))
    inv_y += 1
    if not world.player.knowledge.active_quests:
        console.print(x=x + 3, y=inv_y, string="- None", fg=(128, 128, 128))
    else:
        for quest_id, quest_data in world.player.knowledge.active_quests.items():
            console.print(x=x + 3, y=inv_y, string=f"- {quest_data['title']}")
            inv_y += 1


def draw_trade_menu(console, world):
    """Draws the trade menu UI."""
    menu_width = 60
    menu_height = 24
    x = (MAP_WIDTH - menu_width) // 2
    y = (SCREEN_HEIGHT - menu_height) // 2
    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Trade", clear=True)

    target_name = world.trade_ui_npc_target.name if world.trade_ui_npc_target else "Trader"
    mode = "Selling to" if world.trade_ui_player_selling else "Buying from"
    console.print(x=x + 2, y=y + 2, string=f"{mode} {target_name}", fg=(255, 255, 0))
    console.print(x=x + 2, y=y + 3, string="TAB switch view | ENTER trade | ESC close", fg=(180, 180, 180))

    items = world.trade_ui_player_inventory_snapshot if world.trade_ui_player_selling else world.trade_ui_merchant_inventory_snapshot
    selected_index = world.trade_ui_player_item_index if world.trade_ui_player_selling else world.trade_ui_merchant_item_index

    if not items:
        console.print(x=x + 2, y=y + 5, string="No items available.", fg=(150, 150, 150))
        return

    visible_height = menu_height - 7
    scroll_offset = max(0, min(selected_index, max(0, len(items) - visible_height)))
    for row in range(visible_height):
        item_index = scroll_offset + row
        if item_index >= len(items):
            break

        item_key, quantity, price = items[item_index]
        item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
        color = (0, 255, 255) if item_index == selected_index else (255, 255, 255)
        console.print(
            x=x + 2,
            y=y + 5 + row,
            string=f"{item_name[:28]:28} x{quantity:<3} {price:>4}g",
            fg=color,
        )


def draw_knowledge_menu(console, world):
    """Draws the player's knowledge menu (known books, etc.)."""
    menu_width = 60
    menu_height = 30
    x = (MAP_WIDTH - menu_width) // 2
    y = (SCREEN_HEIGHT - menu_height) // 2

    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Knowledge", clear=True)

    line = y + 2
    console.print(x=x + 2, y=line, string="Books Read:", fg=(255, 255, 0))
    line += 1

    if not world.player.knowledge.known_books:
        console.print(x=x + 3, y=line, string="- None", fg=(128, 128, 128))
    else:
        for book_id in sorted(list(world.player.knowledge.known_books)):
            book = next((b for b in world.books if b.id == book_id), None)
            if book:
                console.print(x=x + 3, y=line, string=f"- {book.title}")
                line += 1

def draw_quest_menu(console, world):
    """Draws the quest log menu."""
    menu_width = 70
    menu_height = 40
    x = (MAP_WIDTH - menu_width) // 2
    y = (SCREEN_HEIGHT - menu_height) // 2

    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Quest Log", clear=True)

    # List width
    list_width = 25
    details_x = x + list_width + 1

    # Draw separator line
    console.draw_rect(x=x+list_width, y=y+1, width=1, height=menu_height-2, ch=ord('|'), fg=(100, 100, 100))

    active_quests = list(world.player.knowledge.active_quests.values())
    num_quests = len(active_quests)

    if not active_quests:
        console.print(x=x + 2, y=y + 2, string="No active quests.", fg=(150, 150, 150))
        return

    ctx = world.quest_menu_context
    selected_index = ctx.get("selected_quest_index", 0)
    scroll_offset = ctx.get("scroll_offset", 0)
    list_height = menu_height - 4

    # Scrolling logic
    if selected_index < 0: selected_index = 0
    if selected_index >= num_quests: selected_index = num_quests - 1
    ctx["selected_quest_index"] = selected_index

    if selected_index < scroll_offset:
        scroll_offset = selected_index
    elif selected_index >= scroll_offset + list_height:
        scroll_offset = selected_index - list_height + 1
    ctx["scroll_offset"] = scroll_offset

    # Draw List
    for i in range(list_height):
        idx = scroll_offset + i
        if idx < num_quests:
            quest = active_quests[idx]
            title = quest["title"]
            if len(title) > list_width - 3:
                title = title[:list_width - 6] + "..."

            color = (255, 255, 255)
            if idx == selected_index:
                color = (0, 255, 255)
                console.print(x=x + 1, y=y + 2 + i, string=">", fg=color)

            console.print(x=x + 3, y=y + 2 + i, string=title, fg=color)

    # Draw Details
    if 0 <= selected_index < num_quests:
        selected_quest = active_quests[selected_index]

        detail_y = y + 2
        # Title
        console.print_box(x=details_x + 1, y=detail_y, width=menu_width - list_width - 3, height=2, string=selected_quest["title"], fg=(255, 255, 0))
        detail_y += 2

        # Description
        desc = selected_quest["description"]
        desc_height = console.get_height_rect(x=details_x + 1, y=detail_y, width=menu_width - list_width - 3, height=10, string=desc)
        console.print_box(x=details_x + 1, y=detail_y, width=menu_width - list_width - 3, height=desc_height, string=desc)
        detail_y += desc_height + 1

        # Objectives
        console.print(x=details_x + 1, y=detail_y, string="Objectives:", fg=(200, 200, 200))
        detail_y += 1

        if selected_quest["type"] == "fetch":
            item_name = selected_quest["item_to_fetch_key"].replace("_", " ").title()
            count = selected_quest["item_fetch_count"]

            # Check player inventory for progress display
            current_count = 0
            for item in world.player.economic.inventory:
                if item["key"] == selected_quest["item_to_fetch_key"]:
                    current_count += item.get("quantity", 1)

            progress_str = f"- Fetch {item_name}: {current_count}/{count}"
            color = (0, 255, 0) if current_count >= count else (255, 255, 255)
            console.print(x=details_x + 2, y=detail_y, string=progress_str, fg=color)

        elif selected_quest["type"] == "kill":
            target_count = selected_quest.get("target_count", 1)
            progress = selected_quest.get("progress", 0)
            progress_str = f"- Defeat targets: {progress}/{target_count}"
            color = (0, 255, 0) if progress >= target_count else (255, 255, 255)
            console.print(x=details_x + 2, y=detail_y, string=progress_str, fg=color)

def draw_help_menu(console):
    """Draws the help menu with controls."""
    menu_width = 50
    menu_height = 30
    x = (MAP_WIDTH - menu_width) // 2
    y = (SCREEN_HEIGHT - menu_height) // 2

    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Help / Controls", clear=True)

    controls = [
        ("Movement", "Arrows / Left Click"),
        ("Interact", "E / Right Click"),
        ("Wait", "."),
        ("Talk", "T"),
        ("Character Info", "I"),
        ("Crafting", "C"),
        ("Building", "B"),
        ("Quests", "Q (Planned)"),
        ("Help", "?"),
        ("Save & Menu", "ESC"),
    ]

    y_offset = y + 3
    for action, key in controls:
        console.print(x=x + 4, y=y_offset, string=f"{action:<20} : {key}")
        y_offset += 2

    console.print(x=x + menu_width // 2, y=y + menu_height - 3, string="Press ESC to close", alignment=tcod.CENTER)


def draw_book_reading_ui(console, world):
    """Draws the UI for reading a book."""
    ctx = world.book_reading_context
    book_id = ctx.get("book_id")
    if not book_id:
        return

    book = next((b for b in world.books if b.id == book_id), None)
    if not book:
        return

    menu_width = 80
    menu_height = 50
    x = (MAP_WIDTH - menu_width) // 2
    y = (SCREEN_HEIGHT - menu_height) // 2

    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title=f"Reading: {book.title}", clear=True)

    # Content preparation
    header = f"by {book.author_name} ({book.year_written})\n\n"
    full_text = header + book.content

    # Text wrapping
    text_width = menu_width - 4
    wrapped_lines = []
    for line in full_text.splitlines():
        if line:
            wrapped_lines.extend(textwrap.wrap(line, width=text_width))
        else:
            wrapped_lines.append("") # Preserve empty lines

    # Scrolling
    scroll_offset = ctx.get("scroll_offset", 0)
    display_height = menu_height - 4

    # Bound scrolling (simple method)
    max_scroll = max(0, len(wrapped_lines) - display_height)
    if scroll_offset > max_scroll:
        scroll_offset = max_scroll
        ctx["scroll_offset"] = scroll_offset # Update context to clamp it

    visible_lines = wrapped_lines[scroll_offset : scroll_offset + display_height]

    for i, line in enumerate(visible_lines):
        console.print(x=x + 2, y=y + 2 + i, string=line)

    # Scrollbar indicator (optional but helpful)
    if len(wrapped_lines) > display_height:
        pct = scroll_offset / max_scroll
        bar_y = int(y + 2 + (display_height * pct))
        if bar_y >= y + menu_height - 1: bar_y = y + menu_height - 2
        console.print(x=x + menu_width - 1, y=bar_y, string="█", fg=(100, 100, 100))
