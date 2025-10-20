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

    draw_chat_log(console, world)
    draw_interaction_menu(console, world, camera_x, camera_y)
    # --- Weather Overlay ---
    draw_weather_overlay(console, world)

    draw_chat_ui(console, world)
    draw_trade_ui(console, world)
    draw_cursor_info(console, world, camera_x, camera_y)
    draw_status_panel(console, world)


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
    # ... (this function is full-screen overlay, no camera coords needed)

def draw_build_mode_ui(console: tcod.console.Console, world, camera_x: int, camera_y: int) -> None:
    if not world.ghost_furniture_tile: return
    # ... (rest of function is okay as it uses start_render_x which is now camera_x)
