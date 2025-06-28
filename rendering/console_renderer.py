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

    draw_chat_log(console, world) # Draw chat log

    # --- Interaction Menu (if active) ---
    # Must be drawn after main map and entities, but before cursor info if we want cursor over it
    # Or drawn last to be on top of everything. Let's try drawing it quite late.
    draw_interaction_menu(console, world, start_x, start_y)

    # --- Chat UI (if active) ---
    # Drawn very late to be on top of almost everything.
    draw_chat_ui(console, world)


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
        title="Info / Inspector", # Changed title
        clear=True,
        fg=(255, 255, 0),
        bg=(0, 0, 0)
    )

    ui_y = menu_y + 2 # Starting y for content

    # --- Player Info ---
    main_console.print(x=menu_x + 2, y=ui_y, string="--- Player ---", fg=(170,170,220))
    ui_y += 1
    hp_text = f"HP: {world.player.hp} / {world.player.max_hp}"
    main_console.print(x=menu_x + 3, y=ui_y, string=hp_text, fg=(255, 255, 255))
    ui_y += 2
    main_console.print(x=menu_x + 3, y=ui_y, string="Inventory:", fg=(255, 255, 255))
    ui_y += 1
    if not world.player.inventory:
        main_console.print(x=menu_x + 4, y=ui_y, string="(Empty)", fg=(128, 128, 128))
        ui_y += 1
    else:
        for item, quantity in world.player.inventory.items():
            item_name = ITEM_DEFINITIONS.get(item, {}).get("name", item)
            text = f" - {item_name}: {quantity}"
            main_console.print(x=menu_x + 4, y=ui_y, string=text, fg=(255, 255, 255))
            ui_y += 1
    ui_y += 1 # Spacer

    # --- Cursor / NPC Info ---
    main_console.print(x=menu_x + 2, y=ui_y, string="--- Cursor Target ---", fg=(170,170,220))
    ui_y += 1

    # Calculate world coordinates of the mouse cursor
    # This needs the same start_x, start_y logic as in draw() if map is offset
    # Assuming info_menu is full screen or mouse_x, mouse_y are screen coords
    # For simplicity, let's assume world.mouse_x and world.mouse_y are already global world coords
    # if they are tile coords from the event. If they are screen coords, conversion is needed.
    # The main draw loop sets world.mouse_x/y to tile coordinates.
    # However, those are screen tile coordinates. We need to map them to world coordinates.

    # Re-calculate map offset to find true world coords of mouse
    start_render_x = world.player.x - main_console.width // 2
    start_render_y = world.player.y - main_console.height // 2
    start_render_x = max(0, min(start_render_x, WORLD_WIDTH - main_console.width))
    start_render_y = max(0, min(start_render_y, WORLD_HEIGHT - main_console.height))

    cursor_world_x = start_render_x + world.mouse_x
    cursor_world_y = start_render_y + world.mouse_y

    cursor_world_x = max(0, min(cursor_world_x, WORLD_WIDTH - 1))
    cursor_world_y = max(0, min(cursor_world_y, WORLD_HEIGHT - 1))

    tile_at_cursor = world.get_tile_at(cursor_world_x, cursor_world_y)
    tile_name = tile_at_cursor.name if tile_at_cursor else "Unknown"
    main_console.print(x=menu_x + 3, y=ui_y, string=f"Tile: ({cursor_world_x},{cursor_world_y}) {tile_name}", fg=(200,200,200))
    ui_y += 1

    npc_at_cursor = None
    for npc_list in [world.village_npcs, world.npcs]: # Check both lists
        for npc_obj in npc_list:
            if npc_obj.x == cursor_world_x and npc_obj.y == cursor_world_y:
                npc_at_cursor = npc_obj
                break
        if npc_at_cursor: break

    if npc_at_cursor:
        main_console.print(x=menu_x + 3, y=ui_y, string=f"NPC: {npc_at_cursor.name}", fg=(180, 180, 255))
        ui_y += 1
        main_console.print(x=menu_x + 4, y=ui_y, string=f"Task: {npc_at_cursor.current_task}", fg=(200,200,200))
        ui_y += 1
        if npc_at_cursor.current_destination_coords:
            main_console.print(x=menu_x + 4, y=ui_y, string=f"Dest: {npc_at_cursor.current_destination_coords}", fg=(200,200,200))
            ui_y += 1
        main_console.print(x=menu_x + 4, y=ui_y, string=f"Personality: {npc_at_cursor.personality}", fg=(200,200,200))
        ui_y += 1
        if npc_at_cursor.home_building_id:
            home_b = world.buildings_by_id.get(npc_at_cursor.home_building_id)
            home_type = home_b.building_type if home_b else "ID Unknown"
            main_console.print(x=menu_x + 4, y=ui_y, string=f"Home: {home_type} ({npc_at_cursor.home_building_id[:6]}..)", fg=(200,200,200))
            ui_y += 1
        if npc_at_cursor.work_building_id:
            work_b = world.buildings_by_id.get(npc_at_cursor.work_building_id)
            work_type = work_b.building_type if work_b else "ID Unknown"
            main_console.print(x=menu_x + 4, y=ui_y, string=f"Work: {work_type} ({npc_at_cursor.work_building_id[:6]}..)", fg=(200,200,200))
            ui_y += 1
    else:
        main_console.print(x=menu_x + 3, y=ui_y, string="No NPC at cursor.", fg=(128,128,128))
        ui_y +=1

def draw_interaction_menu(console: tcod.console.Console, world, start_render_x: int, start_render_y: int) -> None:
    """Draws the NPC interaction menu if active."""
    if not world.interaction_menu_active:
        return

    menu_options = world.interaction_menu_options
    if not menu_options:
        return

    # Determine menu width based on longest option
    menu_title = f"Interact: {world.interaction_menu_target_npc.name if world.interaction_menu_target_npc else 'NPC'}"
    max_option_width = len(menu_title)
    for option in menu_options:
        if len(option) > max_option_width:
            max_option_width = len(option)

    menu_width = max_option_width + 4  # Padding
    menu_height = len(menu_options) + 4 # Padding + title

    # Position the menu: Try to place it near the player on screen.
    # Player's world coordinates: world.player.x, world.player.y
    # Player's screen coordinates:
    player_screen_x = world.player.x - start_render_x
    player_screen_y = world.player.y - start_render_y

    # Tentative menu screen position (top-left corner of the menu)
    # Try to place it to the right of the player, or left if too close to edge.
    menu_screen_x = player_screen_x + 2
    menu_screen_y = player_screen_y - menu_height // 2

    # Clamp menu position to be within console boundaries
    if menu_screen_x + menu_width > console.width:
        menu_screen_x = player_screen_x - menu_width - 1
    if menu_screen_x < 0:
        menu_screen_x = 0

    menu_screen_y = max(0, min(menu_screen_y, console.height - menu_height))


    console.draw_frame(
        x=menu_screen_x,
        y=menu_screen_y,
        width=menu_width,
        height=menu_height,
        title=menu_title,
        clear=True, # Clear background behind menu
        fg=(255, 255, 255), # White border
        bg=(20, 20, 40)    # Dark blue background
    )

    for i, option_text in enumerate(menu_options):
        text_color = (200, 200, 200) # Default text color (greyish)
        bg_color = (20, 20, 40) # Default background (same as menu frame)
        if i == world.interaction_menu_selected_index:
            text_color = (255, 255, 50) # Highlighted text color (yellow)
            bg_color = (50, 50, 80)   # Highlighted background color (darker purple/blue)

        console.print_box( # Use print_box for auto-wrap and alignment if needed, or simple print
            x=menu_screen_x + 1,
            y=menu_screen_y + 2 + i,
            width=menu_width - 2,
            height=1,
            string=option_text,
            fg=text_color,
            bg=bg_color,
            alignment=tcod.constants.LEFT
            )

def draw_chat_ui(console: tcod.console.Console, world) -> None:
    """Draws the dedicated pop-up chat UI if active."""
    if not world.chat_ui_active:
        return

    # Define chat window dimensions and position
    # Let's make it cover the bottom half of the screen for now
    chat_width = console.width - 4 # Some padding
    chat_height = console.height // 2 - 2
    chat_x = 2
    chat_y = console.height - chat_height - 1 # Positioned at the bottom

    # Frame
    title = f"Chat with: {world.chat_ui_target_npc.name if world.chat_ui_target_npc else 'System'}"
    if world.chat_ui_mode == "persuade_goal_input":
        title = f"Persuade {world.chat_ui_target_npc.name if world.chat_ui_target_npc else 'NPC'}: Enter Goal"

    console.draw_frame(
        x=chat_x, y=chat_y, width=chat_width, height=chat_height,
        title=title,
        clear=True, fg=(255, 255, 255), bg=(10, 10, 20) # Dark background
    )

    # History display area
    history_display_x = chat_x + 1
    history_display_y = chat_y + 1
    history_display_width = chat_width - 2
    history_display_height = chat_height - 4 # Reserve 1 for border, 1 for input line, 1 for top title/border

    # Display chat history (newest at the bottom)
    # Simple scrolling: show last N lines that fit. world.chat_ui_scroll_offset can be used later.
    displayable_lines = history_display_height

    # Get the relevant portion of history
    # For now, no complex scrolling, just show the last `displayable_lines`
    start_index = max(0, len(world.chat_ui_history) - displayable_lines)
    visible_history = world.chat_ui_history[start_index:]

    for i, (speaker, text) in enumerate(visible_history):
        line_y = history_display_y + i
        prefix = ""
        line_color = (200, 200, 200) # Default

        if speaker == "Player":
            prefix = "You: "
            line_color = (150, 255, 150) # Light green for player
        elif speaker == "System":
            prefix = "[System]: "
            line_color = (255, 255, 100) # Yellow for system
        else: # NPC
            prefix = f"{speaker}: "
            line_color = (150, 150, 255) # Light blue for NPC

        full_line = prefix + text
        # Simple wrap for long lines (manual)
        wrapped_lines = tcod.console.wrap_rect(full_line, history_display_width, tcod. उठा हुआ) # Use tcod. उठा हुआ for default font

        current_line_in_chunk = 0
        for wrapped_segment in wrapped_lines:
            if i + current_line_in_chunk < displayable_lines: # Check if still within visible area
                 console.print(x=history_display_x, y=line_y + current_line_in_chunk, string=wrapped_segment, fg=line_color)
            current_line_in_chunk +=1
            if current_line_in_chunk > 1 and i + current_line_in_chunk -1 >= displayable_lines : # if wrapped text overflows
                break
        # This simple wrap assumes each original history entry fits or wraps without complex multi-line draw for single entry.
        # A proper scrollable text box is more complex.

    # Input line
    input_line_y = chat_y + chat_height - 2 # Second to last line
    input_prefix = "> "
    console.print(x=history_display_x, y=input_line_y, string=input_prefix + world.chat_ui_input_line, fg=(255,255,255))

    # Blinking cursor (simple version: just an underscore)
    if int(world.game_time * 2) % 2 == 0: # Blink roughly every half second (assuming game_time increments often)
        cursor_x = history_display_x + len(input_prefix) + len(world.chat_ui_input_line)
        if cursor_x < history_display_x + history_display_width:
             console.print(x=cursor_x, y=input_line_y, string="_", fg=(255,255,255))
