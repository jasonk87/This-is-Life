import tcod
from config import SCREEN_WIDTH_TILES, SCREEN_HEIGHT_TILES, WORLD_WIDTH, WORLD_HEIGHT
from data.items import ITEM_DEFINITIONS

def draw(console: tcod.console.Console, world) -> None:
    """Draws the world on the given console."""
    console.clear()

    # --- MAP DRAWING OFFSET CALCULATION ---
    start_x = world.player.x - console.width // 2
    start_y = world.player.y - console.height // 2
    start_x = max(0, min(start_x, WORLD_WIDTH - console.width))
    start_y = max(0, min(start_y, WORLD_HEIGHT - console.height))

    if world.game_state == "PLAYING":
        for y_offset in range(console.height):
            for x_offset in range(console.width):
                map_x, map_y = start_x + x_offset, start_y + y_offset
                tile = world.get_tile_at(map_x, map_y)
                if tile:
                    console.rgb[x_offset, y_offset] = (tile.char, tile.color, (0, 0, 0))

        # --- PLAYER DRAWING ---
        player_screen_x = world.player.x - start_x
        player_screen_y = world.player.y - start_y
        if 0 <= player_screen_x < console.width and 0 <= player_screen_y < console.height:
            console.rgb[player_screen_x, player_screen_y] = (world.player.char, world.player.color, (0, 0, 0))

        # --- NPC DRAWING ---
        for npc in world.npcs + world.village_npcs:
            npc_screen_x = npc.x - start_x
            npc_screen_y = npc.y - start_y
            if 0 <= npc_screen_x < console.width and 0 <= npc_screen_y < console.height:
                console.rgb[npc_screen_x, npc_screen_y] = (npc.char, npc.color, (0, 0, 0))

    elif world.game_state == "INFO_MENU":
        draw_info_menu(console, world)

    draw_chat_log(console, world)

    # --- Cursor Info (Top Left) - Always draw last to be on top ---
    cursor_world_x = start_x + world.mouse_x
    cursor_world_y = start_y + world.mouse_y
    
    # Clamp cursor world coordinates to world boundaries
    cursor_world_x = max(0, min(cursor_world_x, WORLD_WIDTH - 1))
    cursor_world_y = max(0, min(cursor_world_y, WORLD_HEIGHT - 1))

    cursor_tile = world.get_tile_at(cursor_world_x, cursor_world_y)
    
    cursor_info_text = f"({cursor_world_x}, {cursor_world_y}) "
    if cursor_tile:
        cursor_info_text += f"{cursor_tile.name}"
    else:
        cursor_info_text += "Out of Bounds"

    # Calculate dimensions for the border
    text_width = len(cursor_info_text)
    border_width = text_width + 2  # 1 char padding on each side
    border_height = 3             # 1 char padding on top/bottom, plus text line

    # Draw the border
    console.draw_frame(
        x=0,
        y=0,
        width=border_width,
        height=border_height,
        title="",
        clear=False, # Don't clear the background, just draw the frame
        fg=(255, 255, 255), # White border
        bg=(0, 0, 0) # Black background for the frame itself
    )
    # Print the text inside the border
    console.print(x=1, y=1, string=cursor_info_text, fg=(255, 0, 0)) # Bright Red text, no background as frame handles it

def draw_chat_log(console: tcod.console.Console, world) -> None:
    chat_width = console.width // 2
    chat_height = 10
    chat_x = 0
    chat_y = console.height - chat_height

    console.draw_frame(
        x=chat_x,
        y=chat_y,
        width=chat_width,
        height=chat_height,
        title="Chat Log",
        clear=False,
        fg=(255, 255, 255),
        bg=(0, 0, 0)
    )

    # Display last few messages
    display_messages = world.chat_log[- (chat_height - 2):] # -2 for border
    for i, message in enumerate(display_messages):
        console.print(x=chat_x + 1, y=chat_y + 1 + i, string=message, fg=(200, 200, 200))

def draw_info_menu(main_console: tcod.console.Console, world) -> None:
    """Draws the information menu as a pop-up."""
    menu_width = 40
    menu_height = 20
    menu_x = (main_console.width - menu_width) // 2
    menu_y = (main_console.height - menu_height) // 2

    # Draw border
    main_console.draw_frame(
        x=menu_x,
        y=menu_y,
        width=menu_width,
        height=menu_height,
        title="Inventory",
        clear=True,
        fg=(255, 255, 0), # Yellow border
        bg=(0, 0, 0) # Black background for the frame itself
    )

    # Draw HP
    ui_y = menu_y + 2
    hp_text = f"HP: {world.player.hp} / {world.player.max_hp}"
    main_console.print(x=menu_x + 2, y=ui_y, string=hp_text, fg=(255, 255, 255))
    ui_y += 2

    # Draw Inventory
    main_console.print(x=menu_x + 2, y=ui_y, string="Inventory:", fg=(255, 255, 255))
    ui_y += 1

    if not world.player.inventory:
        main_console.print(x=menu_x + 2, y=ui_y, string=" (Empty)", fg=(128, 128, 128))
    else:
        for item, quantity in world.player.inventory.items():
            item_name = ITEM_DEFINITIONS.get(item, {}).get("name", item)
            text = f" - {item_name}: {quantity}"
            main_console.print(x=menu_x + 2, y=ui_y, string=text, fg=(255, 255, 255))
            ui_y += 1
