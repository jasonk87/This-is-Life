import tcod
from config import SCREEN_WIDTH_TILES, SCREEN_HEIGHT_TILES, WORLD_WIDTH, WORLD_HEIGHT
from data.items import ITEM_DEFINITIONS
from data.environment import WEATHER_TYPES
from data.factions import FACTIONS

def draw_status_panel(console: tcod.console.Console, world) -> None:
    """Draws a dedicated panel for player status."""
    panel_width = SCREEN_WIDTH_TILES // 4
    panel_height = SCREEN_HEIGHT_TILES
    panel_x = SCREEN_WIDTH_TILES - panel_width

    console.draw_frame(x=panel_x, y=0, width=panel_width, height=panel_height, title="STATUS", clear=False)

    y_offset = 2
    # Health
    console.print(x=panel_x + 2, y=y_offset, string=f"HP: {world.player.hp} / {world.player.max_hp}")
    y_offset += 2

    # Hunger and Thirst
    console.print(x=panel_x + 2, y=y_offset, string=f"Hunger: {world.player.hunger_level_msg if world.player.hunger_level_msg else 'Full'}")
    y_offset += 1
    console.print(x=panel_x + 2, y=y_offset, string=f"Thirst: {world.player.thirst_level_msg if world.player.thirst_level_msg else 'Quenched'}")
    y_offset += 2

    # Reputation
    console.print(x=panel_x + 2, y=y_offset, string="Reputation:")
    y_offset += 1
    for faction_id, score in world.player.reputation.items():
        faction_name = FACTIONS.get(faction_id, {}).get("name", faction_id)
        console.print(x=panel_x + 3, y=y_offset, string=f"- {faction_name}: {score}")
        y_offset += 1
    y_offset += 2

    # Time of Day
    console.print(x=panel_x + 2, y=y_offset, string=f"Time: {world.current_light_level_name}")


def draw_minimap(console: tcod.console.Console, world) -> None:
    """Draws a minimap in the corner of the screen."""
    from config import MINIMAP_WIDTH, MINIMAP_HEIGHT, MINIMAP_X, MINIMAP_Y, MINIMAP_COLORS

    minimap_console = tcod.console.Console(MINIMAP_WIDTH, MINIMAP_HEIGHT, order="F")
    minimap_console.draw_frame(0, 0, MINIMAP_WIDTH, MINIMAP_HEIGHT, title="Minimap", fg=(255, 255, 255))

    map_center_x = world.player.x
    map_center_y = world.player.y

    for y_minimap in range(1, MINIMAP_HEIGHT - 1):
        for x_minimap in range(1, MINIMAP_WIDTH - 1):
            x_world = map_center_x - (MINIMAP_WIDTH // 2) + x_minimap
            y_world = map_center_y - (MINIMAP_HEIGHT // 2) + y_minimap

            if 0 <= x_world < WORLD_WIDTH and 0 <= y_world < WORLD_HEIGHT and world.explored_map[x_world, y_world]:
                tile = world.get_tile_at(x_world, y_world)
                if tile:
                    color = MINIMAP_COLORS["default"]
                    if "wall" in tile.name.lower():
                        color = MINIMAP_COLORS["wall"]
                    elif "road" in tile.name.lower():
                        color = MINIMAP_COLORS["road"]
                    elif "water" in tile.name.lower():
                        color = MINIMAP_COLORS["water"]
                    elif "plains" in tile.name.lower() or "grass" in tile.name.lower():
                        color = MINIMAP_COLORS["grass"]
                    minimap_console.bg[x_minimap, y_minimap] = color

    # Draw NPCs
    for npc in world.npcs + world.village_npcs:
        if world.player_fov_map[npc.x, npc.y]:
            x_minimap = npc.x - map_center_x + (MINIMAP_WIDTH // 2)
            y_minimap = npc.y - map_center_y + (MINIMAP_HEIGHT // 2)
            if 1 <= x_minimap < MINIMAP_WIDTH -1 and 1 <= y_minimap < MINIMAP_HEIGHT -1:
                minimap_console.bg[x_minimap, y_minimap] = MINIMAP_COLORS["npc"]

    # Draw player
    player_x_minimap = MINIMAP_WIDTH // 2
    player_y_minimap = MINIMAP_HEIGHT // 2
    minimap_console.bg[player_x_minimap, player_y_minimap] = MINIMAP_COLORS["player"]

    minimap_console.blit(console, MINIMAP_X, MINIMAP_Y, 0, 0, MINIMAP_WIDTH, MINIMAP_HEIGHT)


def draw(console: tcod.console.Console, world, camera_x: int, camera_y: int) -> None:
    """Draws the world on the given console using the given camera coordinates."""
    console.clear()

    game_state = world.game_state

    # --- World Rendering (if not in a full-screen menu) ---
    if game_state == "PLAYING" or game_state == "BUILD_MODE" or game_state == "INFO_MENU":
        map_view_width = console.width - (SCREEN_WIDTH_TILES // 4)
        # --- Draw Map Tiles and Items ---
        for y_screen in range(console.height):
            for x_screen in range(map_view_width):
                x_world, y_world = camera_x + x_screen, camera_y + y_screen

                # Skip drawing if the coordinate is outside the world bounds
                if not (0 <= x_world < WORLD_WIDTH and 0 <= y_world < WORLD_HEIGHT):
                    continue

                is_visible = world.player_fov_map[x_world, y_world]
                is_explored = world.explored_map[x_world, y_world]

                tile_char, tile_fg, tile_bg = None, None, (0, 0, 0)

                # Get tile appearance
                if is_visible:
                    tile = world.get_tile_at(x_world, y_world)
                    if tile:
                        tile_char, tile_fg = tile.char, tile.color
                elif is_explored:
                    tile = world.get_tile_at(x_world, y_world)
                    if tile:
                        tile_char, tile_fg = tile.char, tuple(c // 3 for c in tile.color)

                # Draw the tile if it's determined to be visible or explored
                if tile_char is not None:
                    console.rgb[x_screen, y_screen] = (tile_char, tile_fg, tile_bg)

                # Draw items on top of tiles if visible
                if is_visible and (x_world, y_world) in world.items_on_map:
                    items_at_loc = world.items_on_map[(x_world, y_world)]
                    if items_at_loc:
                        top_item_key = items_at_loc[0]["item_key"]
                        item_def = ITEM_DEFINITIONS.get(top_item_key)
                        if item_def:
                            console.rgb[x_screen, y_screen]["char"] = ord(str(item_def.get("char", "?")))
                            console.rgb[x_screen, y_screen]["fg"] = item_def.get("color", (255, 0, 255))

        # --- Draw NPCs ---
        for npc in world.npcs + world.village_npcs:
            if 0 <= npc.x < WORLD_WIDTH and 0 <= npc.y < WORLD_HEIGHT and world.player_fov_map[npc.x, npc.y]:
                npc_screen_x = npc.x - camera_x
                npc_screen_y = npc.y - camera_y
                if 0 <= npc_screen_x < console.width and 0 <= npc_screen_y < console.height:
                    console.rgb[npc_screen_x, npc_screen_y] = (npc.char, npc.color, (0, 0, 0))

        # --- Draw Player (always in the center) ---
        player_screen_x = world.player.x - camera_x
        player_screen_y = world.player.y - camera_y
        console.rgb[player_screen_x, player_screen_y] = (world.player.char, world.player.color, (0, 0, 0))

    # --- UI Overlays ---
    if game_state == "INFO_MENU":
        draw_info_menu(console, world, camera_x, camera_y)
    elif game_state == "BUILD_MODE":
        draw_build_mode_ui(console, world, camera_x, camera_y)
    elif game_state == "INVENTORY_MENU":
        draw_inventory_menu(console, world)
    elif game_state == "CRAFTING_MENU":
        draw_crafting_menu(console, world)

    draw_chat_log(console, world)
    draw_interaction_menu(console, world, camera_x, camera_y)
    # --- Weather Overlay ---
    draw_weather_overlay(console, world)

    draw_chat_ui(console, world)
    draw_trade_ui(console, world)
    draw_cursor_info(console, world, camera_x, camera_y)
    draw_status_panel(console, world)
    draw_minimap(console, world)


def draw_weather_overlay(console: tcod.console.Console, world) -> None:
    """Draws a visual effect over the screen for the current weather."""
    from data.environment import WEATHER_TYPES
    import random

    weather_key = world.current_weather
    if weather_key == "clear":
        return

    weather_def = WEATHER_TYPES.get(weather_key)
    if not weather_def:
        return

    # A simple particle effect: sprinkle a number of weather characters randomly.
    # The number of particles can be tied to the game time to create a sense of movement.
    num_particles = 50
    char_to_draw = ord(str(weather_def["overlay_char"]))
    color_to_draw = weather_def["overlay_color"]

    for _ in range(num_particles):
        # Add a time-based offset to the y-coordinate to simulate falling
        x = random.randint(0, console.width - 1)
        y_offset = (world.game_time + random.randint(0, console.height)) % console.height
        y = y_offset

        # Check if console coordinates are valid (they should be)
        if 0 <= x < console.width and 0 <= y < console.height:
            # Only draw if the background is empty (black), to avoid drawing over UI frames.
            # This is a simple way to keep weather behind UI.
            if console.rgb[x, y]["bg"] == (0, 0, 0):
                 console.rgb[x, y] = (char_to_draw, color_to_draw, console.rgb[x, y]["bg"])


def draw_cursor_info(console: tcod.console.Console, world, camera_x: int, camera_y: int) -> None:
    """Draws information about the tile under the mouse cursor."""
    cursor_world_x = camera_x + world.mouse_x
    cursor_world_y = camera_y + world.mouse_y

    season_name = world.current_season['name']
    weather_name = WEATHER_TYPES[world.current_weather]['name']

    tile_info = ""
    if 0 <= cursor_world_x < WORLD_WIDTH and 0 <= cursor_world_y < WORLD_HEIGHT:
        cursor_tile = world.get_tile_at(cursor_world_x, cursor_world_y)
        if cursor_tile:
            tile_info = f"| {cursor_tile.name}"

    cursor_info_text = f"({cursor_world_x}, {cursor_world_y}) | {season_name}, {weather_name} {tile_info}"

    text_width = len(cursor_info_text)
    border_width = text_width + 2
    border_height = 3

    console.draw_frame(x=0, y=0, width=border_width, height=border_height, clear=False, fg=(255, 255, 255), bg=(0, 0, 0))
    console.print(x=1, y=1, string=cursor_info_text, fg=(255, 0, 0))

def draw_chat_log(console: tcod.console.Console, world) -> None:
    chat_width = console.width // 2
    chat_height = 10
    chat_x = 0
    chat_y = console.height - chat_height

    console.draw_frame(x=chat_x, y=chat_y, width=chat_width, height=chat_height, title="Chat Log", clear=False, fg=(255, 255, 255), bg=(0, 0, 0))

    display_messages = world.chat_log[-(chat_height - 2):]
    for i, message in enumerate(display_messages):
        console.print(x=chat_x + 1, y=chat_y + 1 + i, string=message, fg=(200, 200, 200))

def draw_info_menu(main_console: tcod.console.Console, world, camera_x: int, camera_y: int) -> None:
    """Draws the information menu as a pop-up over the world view."""
    menu_width = 40
    menu_height = 20
    menu_x = (main_console.width - menu_width) // 2
    menu_y = (main_console.height - menu_height) // 2

    main_console.draw_frame(x=menu_x, y=menu_y, width=menu_width, height=menu_height, title="Info / Inspector", clear=True, fg=(255, 255, 0), bg=(0, 0, 0))

    ui_y = menu_y + 2
    main_console.print(x=menu_x + 2, y=ui_y, string="--- Player ---", fg=(170,170,220))
    ui_y += 1
    main_console.print(x=menu_x + 3, y=ui_y, string=f"HP: {world.player.hp} / {world.player.max_hp}", fg=(255, 255, 255))
    ui_y +=1
    main_console.print(x=menu_x + 3, y=ui_y, string=f"Hunger: {world.player.hunger}/{world.player.max_hunger} {world.player.hunger_level_msg}", fg=(255,165,0) if world.player.hunger_level_msg else (200,200,200))
    ui_y +=1
    main_console.print(x=menu_x + 3, y=ui_y, string=f"Thirst: {world.player.thirst}/{world.player.max_thirst} {world.player.thirst_level_msg}", fg=(100,149,237) if world.player.thirst_level_msg else (200,200,200))
    ui_y += 2
    main_console.print(x=menu_x + 3, y=ui_y, string="Inventory:", fg=(255, 255, 255))
    ui_y += 1
    if not world.player.inventory:
        main_console.print(x=menu_x + 4, y=ui_y, string="(Empty)", fg=(128, 128, 128))
        ui_y += 1
    else:
        # This needs to be updated to handle the new list-of-dicts inventory
        inventory_summary = {}
        for item in world.player.inventory:
            key = item["key"]
            inventory_summary[key] = inventory_summary.get(key, 0) + item.get("quantity", 1)

        for item_key, quantity in inventory_summary.items():
            item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
            main_console.print(x=menu_x + 4, y=ui_y, string=f" - {item_name}: {quantity}", fg=(255, 255, 255))
            ui_y += 1
    ui_y += 1

    main_console.print(x=menu_x + 2, y=ui_y, string="--- Cursor Target ---", fg=(170,170,220))
    ui_y += 1

    cursor_world_x = camera_x + world.mouse_x
    cursor_world_y = camera_y + world.mouse_y

    tile_name = "Void"
    if 0 <= cursor_world_x < WORLD_WIDTH and 0 <= cursor_world_y < WORLD_HEIGHT:
        tile_at_cursor = world.get_tile_at(cursor_world_x, cursor_world_y)
        tile_name = tile_at_cursor.name if tile_at_cursor else "Unknown"
    main_console.print(x=menu_x + 3, y=ui_y, string=f"Tile: ({cursor_world_x},{cursor_world_y}) {tile_name}", fg=(200,200,200))
    ui_y += 1

    # ... (rest of NPC info logic is fine as it uses world coordinates)
    npc_at_cursor = None
    for npc_list in [world.village_npcs, world.npcs]: # Check both lists
        for npc_obj in npc_list:
            if npc_obj.x == cursor_world_x and npc_obj.y == cursor_world_y:
                npc_at_cursor = npc_obj
                break
        if npc_at_cursor: break

    if npc_at_cursor:
        if 0 <= npc_at_cursor.x < WORLD_WIDTH and 0 <= npc_at_cursor.y < WORLD_HEIGHT and world.player_fov_map[npc_at_cursor.x, npc_at_cursor.y]:
             main_console.print(x=menu_x + 3, y=ui_y, string=f"NPC: {npc_at_cursor.name}", fg=(180, 180, 255))
             # ... (the rest of the NPC info is okay)


def draw_inventory_menu(console: tcod.console.Console, world) -> None:
    """Draws a full-screen, interactive inventory menu."""
    menu_width = SCREEN_WIDTH_TILES - 10
    menu_height = SCREEN_HEIGHT_TILES - 6
    menu_x = (SCREEN_WIDTH_TILES - menu_width) // 2
    menu_y = (SCREEN_HEIGHT_TILES - menu_height) // 2

    console.draw_frame(x=menu_x, y=menu_y, width=menu_width, height=menu_height, title="INVENTORY", clear=True)

    # Split the menu into two panels: item list and details
    list_panel_width = menu_width // 2
    detail_panel_width = menu_width - list_panel_width - 1

    # Draw vertical separator
    for i in range(1, menu_height - 1):
        console.print(x=menu_x + list_panel_width, y=menu_y + i, string="│")

    # --- Item List Panel ---
    inv_context = world.inventory_menu_context
    inventory = world.player.inventory

    list_height = menu_height - 4 # Top/bottom border + padding

    # Handle scrolling
    if inv_context["selected_item_index"] < inv_context["scroll_offset"]:
        inv_context["scroll_offset"] = inv_context["selected_item_index"]
    elif inv_context["selected_item_index"] >= inv_context["scroll_offset"] + list_height:
        inv_context["scroll_offset"] = inv_context["selected_item_index"] - list_height + 1

    y_offset = menu_y + 2
    for i, item in enumerate(inventory[inv_context["scroll_offset"] : inv_context["scroll_offset"] + list_height]):
        item_def = ITEM_DEFINITIONS.get(item["key"], {})
        display_name = item_def.get("name", item["key"])

        # Format name with quantity or durability
        if "quantity" in item:
            display_str = f"{display_name} (x{item['quantity']})"
        elif "durability" in item:
            display_str = f"{display_name} ({item['durability']}/{item['max_durability']})"
        else:
            display_str = display_name

        fg_color = (255, 255, 0) if i + inv_context["scroll_offset"] == inv_context["selected_item_index"] else (255, 255, 255)

        console.print(x=menu_x + 2, y=y_offset + i, string=display_str, fg=fg_color)

    # --- Item Detail Panel ---
    if inventory:
        selected_item = inventory[inv_context["selected_item_index"]]
        item_def = ITEM_DEFINITIONS.get(selected_item["key"], {})

        detail_x = menu_x + list_panel_width + 2
        detail_y = menu_y + 2

        # Item Name
        console.print(x=detail_x, y=detail_y, string=item_def.get("name", "Unknown Item"), fg=(200, 200, 255))
        detail_y += 2

        # Description
        desc = item_def.get("description", "No details available.")
        console.print_box(x=detail_x, y=detail_y, width=detail_panel_width - 4, height=10, string=desc)
        detail_y += 5

        # Properties
        if "properties" in item_def:
            for prop, val in item_def["properties"].items():
                console.print(x=detail_x, y=detail_y, string=f"{prop.replace('_', ' ').title()}: {val}")
                detail_y += 1

        # Usable effects
        if "on_use" in item_def:
            detail_y +=1
            console.print(x=detail_x, y=detail_y, string="[Usable]", fg=(0, 255, 0))
            for effect, val in item_def["on_use"].items():
                 detail_y += 1
                 console.print(x=detail_x + 1, y=detail_y, string=f"- {effect.replace('_', ' ').title()}: {val}")


def draw_crafting_menu(console: tcod.console.Console, world) -> None:
    """Draws a full-screen, interactive crafting menu."""
    menu_width = SCREEN_WIDTH_TILES - 10
    menu_height = SCREEN_HEIGHT_TILES - 6
    menu_x = (SCREEN_WIDTH_TILES - menu_width) // 2
    menu_y = (SCREEN_HEIGHT_TILES - menu_height) // 2

    console.draw_frame(x=menu_x, y=menu_y, width=menu_width, height=menu_height, title="CRAFTING", clear=True)

    # Panels: Recipe List | Recipe Details & Player Inventory
    list_panel_width = menu_width // 3
    detail_panel_width = menu_width - list_panel_width - 1

    # Separator
    for i in range(1, menu_height - 1):
        console.print(x=menu_x + list_panel_width, y=menu_y + i, string="│")

    craft_context = world.crafting_menu_context
    recipes = craft_context.get("craftable_recipes", [])

    # --- Recipe List Panel ---
    list_height = menu_height - 4

    if craft_context["selected_recipe_index"] < craft_context["scroll_offset"]:
        craft_context["scroll_offset"] = craft_context["selected_recipe_index"]
    elif craft_context["selected_recipe_index"] >= craft_context["scroll_offset"] + list_height:
        craft_context["scroll_offset"] = craft_context["selected_recipe_index"] - list_height + 1

    y_offset = menu_y + 2
    for i, recipe_info in enumerate(recipes[craft_context["scroll_offset"] : craft_context["scroll_offset"] + list_height]):
        item_key = recipe_info["item_key"]
        item_def = ITEM_DEFINITIONS.get(item_key, {})
        display_name = item_def.get("name", item_key)

        can_craft, _ = world.player_can_craft(item_key) # Use helper

        fg_color = (255, 255, 0) if i + craft_context["scroll_offset"] == craft_context["selected_recipe_index"] else ((255, 255, 255) if can_craft else (128, 128, 128))

        console.print(x=menu_x + 2, y=y_offset + i, string=display_name, fg=fg_color)

    # --- Recipe Detail Panel ---
    if recipes:
        selected_recipe_info = recipes[craft_context["selected_recipe_index"]]
        item_key = selected_recipe_info["item_key"]
        item_def = ITEM_DEFINITIONS.get(item_key, {})
        recipe_reqs = selected_recipe_info.get("recipe", {})

        detail_x = menu_x + list_panel_width + 2
        detail_y = menu_y + 2

        # Item Name & Description
        console.print(x=detail_x, y=detail_y, string=item_def.get("name", "Unknown"), fg=(200, 200, 255))
        detail_y += 2
        console.print_box(x=detail_x, y=detail_y, width=detail_panel_width - 4, height=5, string=item_def.get("description", "No description."))
        detail_y += 6

        # Required Ingredients
        console.print(x=detail_x, y=detail_y, string="Ingredients:")
        detail_y += 1
        for res_key, qty_needed in recipe_reqs.items():
            res_name = ITEM_DEFINITIONS.get(res_key, {}).get("name", res_key)
            player_has_qty = world.player.get_item_quantity(res_key)
            has_enough = player_has_qty >= qty_needed
            res_color = (255, 255, 255) if has_enough else (255, 100, 100)
            console.print(x=detail_x + 1, y=detail_y, string=f"- {res_name}: {player_has_qty}/{qty_needed}", fg=res_color)
            detail_y += 1

        # Workstation Requirement
        workstation_key = selected_recipe_info.get("workstation")
        if workstation_key:
            detail_y += 1
            workstation_name = ITEM_DEFINITIONS.get(workstation_key, {}).get("name", workstation_key)
            player_is_near_station = world.player_is_near_workstation(workstation_key)
            station_color = (0, 255, 0) if player_is_near_station else (255, 100, 100)
            console.print(x=detail_x, y=detail_y, string=f"Requires: {workstation_name}", fg=station_color)
            if not player_is_near_station:
                console.print(x=detail_x, y=detail_y + 1, string="(You are not near one)", fg=station_color)


    # --- Player Resources Panel (Bottom right) ---
    res_panel_height = menu_height // 2
    res_panel_y = menu_y + menu_height - res_panel_height -1
    console.draw_frame(x=menu_x + list_panel_width + 1, y=res_panel_y, width=detail_panel_width, height=res_panel_height, title="Materials", clear=False)

    res_y = res_panel_y + 2
    res_x = menu_x + list_panel_width + 2

    # Aggregate player inventory for display
    inventory_summary = world.player.get_inventory_summary()

    # Collect all unique resources needed by all craftable recipes
    all_needed_resources = set()
    for recipe_info in recipes:
        for res_key in recipe_info.get("recipe", {}).keys():
            all_needed_resources.add(res_key)

    sorted_resources = sorted(list(all_needed_resources), key=lambda r: ITEM_DEFINITIONS.get(r, {}).get("name", r))

    max_res_lines = res_panel_height - 4
    for i, res_key in enumerate(sorted_resources[:max_res_lines]):
        res_name = ITEM_DEFINITIONS.get(res_key, {}).get("name", res_key)
        qty_owned = inventory_summary.get(res_key, 0)
        console.print(x=res_x, y=res_y + i, string=f"{res_name}: {qty_owned}")


def draw_interaction_menu(console: tcod.console.Console, world, camera_x: int, camera_y: int) -> None:
    if not world.interaction_context["active"]:
        return

    ctx = world.interaction_context
    menu_x = world.mouse_x + 1
    menu_y = world.mouse_y + 1

    # Basic dynamic width, more complex logic can be added
    max_entity_name_len = max(len(e["name"]) for e in ctx["target_entities"]) if ctx["target_entities"] else 10
    max_action_len = max(len(a) for a in ctx["available_actions"]) if ctx["available_actions"] else 10
    menu_width = max(max_entity_name_len, max_action_len) + 6 # Padding

    # Total height: 1 for title, len(entities), 1 for separator, len(actions), 2 for borders
    menu_height = 1 + len(ctx["target_entities"]) + 1 + len(ctx["available_actions"]) + 2

    console.draw_frame(x=menu_x, y=menu_y, width=menu_width, height=menu_height, title="Interact", clear=True)

    y_offset = menu_y + 1
    # Draw entities list
    for i, entity in enumerate(ctx["target_entities"]):
        fg = (255, 255, 0) if i == ctx["selected_entity_index"] else (255, 255, 255)
        prefix = "> " if i == ctx["selected_entity_index"] else "  "
        console.print(x=menu_x + 1, y=y_offset, string=f"{prefix}{entity['name']}", fg=fg)
        y_offset += 1

    # Separator
    console.print(x=menu_x + 1, y=y_offset, string="-" * (menu_width - 2))
    y_offset += 1

    # Draw actions for selected entity
    for i, action in enumerate(ctx["available_actions"]):
        fg = (255, 255, 0) if i == ctx["selected_action_index"] else (255, 255, 255)
        prefix = "* " if i == ctx["selected_action_index"] else "  "
        console.print(x=menu_x + 1, y=y_offset, string=f"{prefix}{action}", fg=fg)
        y_offset += 1


def draw_chat_ui(console: tcod.console.Console, world) -> None:
    if not world.chat_ui_active: return
    # ... (this function is full-screen overlay, no camera coords needed)

def draw_trade_ui(console: tcod.console.Console, world) -> None:
    if not world.trade_ui_active: return

    menu_width = SCREEN_WIDTH_TILES - 6
    menu_height = SCREEN_HEIGHT_TILES - 4
    menu_x = (SCREEN_WIDTH_TILES - menu_width) // 2
    menu_y = (SCREEN_HEIGHT_TILES - menu_height) // 2

    console.draw_frame(x=menu_x, y=menu_y, width=menu_width, height=menu_height, title="TRADE", clear=True)

    trade_context = world.trade_ui_context
    merchant_name = trade_context.get("npc_target_name", "Merchant")

    # --- Layout Definitions ---
    half_width = menu_width // 2
    player_panel_x = menu_x + 1
    merchant_panel_x = menu_x + half_width

    info_panel_height = 8
    info_panel_y = menu_y + menu_height - info_panel_height - 1

    list_height = menu_height - info_panel_height - 3

    # --- Draw Headers and Money ---
    player_header_color = (255, 255, 0) if trade_context["active_panel"] == "PLAYER" else (255, 255, 255)
    merchant_header_color = (255, 255, 0) if trade_context["active_panel"] == "MERCHANT" else (255, 255, 255)

    console.print(x=player_panel_x, y=menu_y + 1, string=f"Your Items (Sell)", fg=player_header_color)
    console.print(x=merchant_panel_x, y=menu_y + 1, string=f"{merchant_name}'s Wares (Buy)", fg=merchant_header_color)

    money_str = f"Your Money: {world.player.money}"
    console.print(x=menu_x + menu_width - len(money_str) - 2, y=menu_y + 1, string=money_str, fg=(255, 223, 0))

    # --- Draw Item Lists ---
    def draw_item_list(panel_x, panel_width, items, selected_index, scroll_offset):
        y_pos = menu_y + 3
        for i, item_data in enumerate(items[scroll_offset : scroll_offset + list_height]):
            item_key, quantity, price = item_data
            item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
            display_str = f"{item_name} (x{quantity}) - ${price}"

            fg = (0, 255, 255) if i + scroll_offset == selected_index else (255, 255, 255)
            console.print(x=panel_x, y=y_pos + i, string=display_str, fg=fg)

    # Player's items
    draw_item_list(player_panel_x, half_width, trade_context["player_inventory_snapshot"],
                   trade_context["player_item_index"], trade_context["player_scroll_offset"])

    # Merchant's items
    draw_item_list(merchant_panel_x, half_width, trade_context["merchant_inventory_snapshot"],
                   trade_context["merchant_item_index"], trade_context["merchant_scroll_offset"])

    # --- Draw Info Panel ---
    console.draw_frame(x=menu_x, y=info_panel_y, width=menu_width, height=info_panel_height, title="Item Info", clear=False)

    selected_item_key = None
    if trade_context["active_panel"] == "PLAYER" and trade_context["player_inventory_snapshot"]:
        selected_item_key = trade_context["player_inventory_snapshot"][trade_context["player_item_index"]][0]
    elif trade_context["active_panel"] == "MERCHANT" and trade_context["merchant_inventory_snapshot"]:
        selected_item_key = trade_context["merchant_inventory_snapshot"][trade_context["merchant_item_index"]][0]

    if selected_item_key:
        item_def = ITEM_DEFINITIONS.get(selected_item_key, {})
        console.print_box(x=menu_x + 2, y=info_panel_y + 2,
                          width=menu_width - 4, height=info_panel_height - 4,
                          string=item_def.get("description", "No description available."))


def draw_build_mode_ui(console: tcod.console.Console, world, camera_x: int, camera_y: int) -> None:
    if not world.ghost_furniture_tile: return
    # ... (rest of function is okay as it uses start_render_x which is now camera_x)
