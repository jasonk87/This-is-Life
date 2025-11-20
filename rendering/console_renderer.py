# rendering/console_renderer.py

import tcod
from config import (
    SCREEN_WIDTH, SCREEN_HEIGHT, MAP_WIDTH, MAP_HEIGHT, STATUS_PANEL_WIDTH,
    MINIMAP_WIDTH, MINIMAP_HEIGHT, MINIMAP_X, MINIMAP_Y,
    COLOR_PLAYER_STATUS_WET, COLOR_PLAYER_STATUS_FREEZING, COLOR_CURSOR_INFO_TEXT
)
from data.tiles import TILE_DEFINITIONS
from data.construction import CONSTRUCTION_RECIPES
from entities.animal import Animal
from engine import Player

def draw_status_panel(console, world):
    """Draws the status panel on the right side of the screen."""
    panel_x = MAP_WIDTH
    console.draw_frame(x=panel_x, y=0, width=STATUS_PANEL_WIDTH, height=SCREEN_HEIGHT,
                       title="Status", clear=True, fg=(255, 255, 255), bg=(0, 0, 0))

    y = 2
    # Player HP
    hp_str = f"HP: {world.player.combat.hp} / {world.player.combat.max_hp}"
    console.print(x=panel_x + 1, y=y, string=hp_str)
    y += 2

    # Player Hunger and Thirst
    if world.player.physical.hunger_level_msg:
        console.print(x=panel_x + 1, y=y, string=world.player.physical.hunger_level_msg)
        y += 1
    if world.player.physical.thirst_level_msg:
        console.print(x=panel_x + 1, y=y, string=world.player.physical.thirst_level_msg)
        y += 1
    y += 1 # Spacer

    # Faction Reputations
    console.print(x=panel_x + 1, y=y, string="Reputation:")
    y += 1
    for faction, rep in world.player.social.reputation.items():
        console.print(x=panel_x + 2, y=y, string=f"- {faction.replace('_', ' ').title()}: {rep}")
        y += 1
    y += 1 # Spacer


    # Time and Season
    day = world.game_time // (24 * 60)
    hour = (world.game_time // 60) % 24
    minute = world.game_time % 60
    time_str = f"Day {day}, {hour:02d}:{minute:02d}"
    season = world.seasons[world.current_season_index]
    console.print(x=panel_x + 1, y=y, string=time_str)
    y += 1
    console.print(x=panel_x + 1, y=y, string=f"Season: {season}")
    y+= 2

    # Status Effects
    if world.player.physical.status_effects:
        console.print(x=panel_x + 1, y=y, string="Status:")
        y += 1
        for effect in world.player.physical.status_effects:
            color = (255, 255, 255) # Default white
            if effect == "Wet":
                color = COLOR_PLAYER_STATUS_WET
            elif effect == "Freezing":
                color = COLOR_PLAYER_STATUS_FREEZING
            console.print(x=panel_x + 2, y=y, string=f"- {effect}", fg=color)
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
    if not hasattr(world, 'player_fov_map') or not hasattr(world, 'fov_min_x') or not hasattr(world, 'fov_min_y'):
        # Fallback if FOV system isn't fully initialized
        return True

    fov_map = world.player_fov_map
    map_height, map_width = fov_map.shape

    local_x = x - world.fov_min_x
    local_y = y - world.fov_min_y

    if 0 <= local_x < map_width and 0 <= local_y < map_height:
        return fov_map[local_y, local_x]
    return False

def draw(console, world, camera_x, camera_y):
    """Draws the main game screen."""
    console.clear()

    # Draw the map
    for y in range(MAP_HEIGHT):
        for x in range(MAP_WIDTH):
            map_x, map_y = camera_x + x, camera_y + y
            tile = world.get_tile_at(map_x, map_y)
            if tile:
                is_in_fov = is_visible(world, map_x, map_y)
                if is_in_fov:
                    console.print(x=x, y=y, string=chr(tile.char), fg=tile.color)
                    world.explored_map[map_y, map_x] = True
                elif world.explored_map[map_y, map_x]:
                    console.print(x=x, y=y, string=chr(tile.char), fg=(100, 100, 100)) # Explored but not visible

    # Draw entities
    all_entities = world.npcs + world.village_npcs + [world.player]
    for entity in sorted(all_entities, key=lambda e: e.render_order.value if hasattr(e, 'render_order') else 0):
        if isinstance(entity, Player) and entity.state.is_riding:
            continue
        if is_visible(world, entity.x, entity.y):
            console.print(x=entity.x - camera_x, y=entity.y - camera_y,
                          string=chr(entity.char), fg=entity.color)

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

    if world.game_state == "BOOK_READING":
        draw_book_reading_ui(console, world)

    # Draw chat log at the bottom
    y = SCREEN_HEIGHT - 6
    console.draw_frame(x=0, y=y, width=MAP_WIDTH, height=6, title="Log",
                       clear=True, fg=(255, 255, 255), bg=(0, 0, 0))
    for i, message in enumerate(world.chat_log[-4:]):
        console.print(x=1, y=y + 1 + i, string=message)

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
            item_def = TILE_DEFINITIONS.get(mat_key, {}) # Assuming item definitions are accessible via this or separate import if needed.
            # Wait, TILE_DEFINITIONS contains tiles. ITEM_DEFINITIONS is in data/items.py but not imported here except TILE_DEFINITIONS?
            # render_console imports TILE_DEFINITIONS. engine imports ITEM_DEFINITIONS.
            # Let's trust that main passes world which has access, or just print key if def missing.
            # Actually, render_console doesn't import ITEM_DEFINITIONS. We should probably import it or just use keys/world.
            # Let's just use key for now or try to use TILE_DEFINITIONS if it happens to be there (some items are tiles)
            # Better: Import ITEM_DEFINITIONS in this file.

            # For now, let's just print the key formatted nicely.
            mat_name = mat_key.replace("_", " ").title()
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
        item_def = TILE_DEFINITIONS.get(item_key, {}) # Using TILE_DEFINITIONS.
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

    console.print_box(x=x + 2, y=y + 2, width=menu_width - 4, height=menu_height - 4,
                      string=f"by {book.author_name} ({book.year_written})\n\n{book.content}")
