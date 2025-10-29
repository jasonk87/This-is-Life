"""
This module handles all the rendering and drawing functions for the game,
including the main world view, UI panels, menus, and overlays.
"""
import random
import numpy as np
import tcod
from config import SCREEN_WIDTH_TILES, SCREEN_HEIGHT_TILES, WORLD_WIDTH, WORLD_HEIGHT
from data.items import ITEM_DEFINITIONS
from data.environment import WEATHER_DEFINITIONS

def draw_weather_overlay(console: tcod.console.Console, world) -> None:
    """Draws a visual effect for the current weather, like rain."""
    current_weather_name = world.weather
    if current_weather_name != 'clear':
        weather_def = WEATHER_DEFINITIONS.get(current_weather_name)
        if weather_def:
            weather_char = weather_def.get("char", " ")
            weather_color = weather_def.get("color", (200, 200, 255))
            weather_chance = weather_def.get("chance", 0.1)

            map_view_width = console.width - (SCREEN_WIDTH_TILES // 4)

            for y in range(console.height):
                for x in range(map_view_width):
                    if random.random() < weather_chance:
                        if not np.array_equal(console.rgb[x, y]["bg"], np.array([0, 0, 0])) and console.rgb[x, y]["char"] not in [ord('#'), ord('+'), 177, 178]:
                            existing_fg = console.rgb[x, y]["fg"]
                            mixed_color = (
                                (weather_color[0] + existing_fg[0]) // 2,
                                (weather_color[1] + existing_fg[1]) // 2,
                                (weather_color[2] + existing_fg[2]) // 2,
                            )
                            console.rgb[x, y] = (weather_char, mixed_color,
                                                 console.rgb[x, y]["bg"])

def draw_status_panel(console: tcod.console.Console, world) -> None:
    """Draws a dedicated panel for player status."""
    panel_width = SCREEN_WIDTH_TILES // 4
    panel_height = SCREEN_HEIGHT_TILES
    panel_x = SCREEN_WIDTH_TILES - panel_width

    console.draw_frame(x=panel_x, y=0, width=panel_width, height=panel_height,
                       title="STATUS", clear=False)

    y_offset = 2
    console.print(x=panel_x + 2, y=y_offset,
                  string=f"HP: {world.player.combat.hp} / {world.player.combat.max_hp}")
    y_offset += 2

    console.print(x=panel_x + 2, y=y_offset,
                  string=f"Hunger: {world.player.physical.hunger_level_msg or 'Full'}")
    y_offset += 1
    console.print(x=panel_x + 2, y=y_offset,
                  string=f"Thirst: {world.player.physical.thirst_level_msg or 'Quenched'}")
    y_offset += 2

    console.print(x=panel_x + 2, y=y_offset, string=f"Time: {world.current_light_level_name}")
    y_offset += 2

    season_name = world.seasons[world.current_season_index]
    console.print(x=panel_x + 2, y=y_offset, string=f"Season: {season_name}")
    y_offset += 1
    console.print(x=panel_x + 2, y=y_offset,
                  string=f"Ambient: {world.ambient_temperature:.1f}C")
    y_offset += 1

    body_temp_color = (255, 255, 255)
    if "Freezing" in world.player.physical.status_effects:
        body_temp_color = (100, 100, 255)
    elif "Overheating" in world.player.physical.status_effects:
        body_temp_color = (255, 100, 100)
    console.print(x=panel_x + 2, y=y_offset,
                  string=f"Body Temp: {world.player.physical.temperature:.1f}C", fg=body_temp_color)
    y_offset += 1

    if world.player.physical.status_effects:
        status_str = ", ".join(world.player.physical.status_effects)
        console.print(x=panel_x + 3, y=y_offset,
                      string=f"({status_str})", fg=(255, 100, 100))
    y_offset += 2

    console.print(x=panel_x + 2, y=y_offset, string=f"Fame: {world.player.social.fame}")
    y_offset += 1
    console.print(x=panel_x + 2, y=y_offset, string=f"Infamy: {world.player.social.infamy}")
    y_offset += 2

    if world.player.social.title:
        console.print(x=panel_x + 2, y=y_offset, string=f"Title: {world.player.social.title}")

def draw(console: tcod.console.Console, world, camera_x: int, camera_y: int) -> None:
    """Draws the world on the given console using the given camera coordinates."""
    console.clear()

    game_state = world.game_state

    if game_state in ("PLAYING", "BUILD_MODE", "INFO_MENU"):
        map_view_width = console.width - (SCREEN_WIDTH_TILES // 4)
        for y_screen in range(console.height):
            for x_screen in range(map_view_width):
                x_world, y_world = camera_x + x_screen, camera_y + y_screen

                if not (0 <= x_world < WORLD_WIDTH and 0 <= y_world < WORLD_HEIGHT):
                    continue

                is_visible = world.player_fov_map[x_world, y_world]
                is_explored = world.explored_map[x_world, y_world]

                tile_char, tile_fg, tile_bg = None, None, (0, 0, 0)

                if is_visible:
                    tile = world.get_tile_at(x_world, y_world)
                    if tile:
                        tile_char, tile_fg = tile.char, tile.color
                elif is_explored:
                    tile = world.get_tile_at(x_world, y_world)
                    if tile:
                        tile_char, tile_fg = tile.char, tuple(c // 3 for c in tile.color)

                if tile_char is not None:
                    console.rgb[x_screen, y_screen] = (tile_char, tile_fg, tile_bg)

                if is_visible and (x_world, y_world) in world.items_on_map:
                    items_at_loc = world.items_on_map[(x_world, y_world)]
                    if items_at_loc:
                        top_item_key = items_at_loc[0]["item_key"]
                        item_def = ITEM_DEFINITIONS.get(top_item_key)
                        if item_def:
                            console.rgb[x_screen, y_screen]["char"] = ord(str(item_def.get("char", "?")))
                            console.rgb[x_screen, y_screen]["fg"] = item_def.get("color", (255, 0, 255))

        for npc in world.npcs + world.village_npcs:
            if world.player.is_riding and world.player.riding_animal_id == npc.id:
                continue
            if 0 <= npc.x < WORLD_WIDTH and 0 <= npc.y < WORLD_HEIGHT and world.player_fov_map[npc.x, npc.y]:
                npc_screen_x = npc.x - camera_x
                npc_screen_y = npc.y - camera_y
                if 0 <= npc_screen_x < console.width and 0 <= npc_screen_y < console.height:
                    console.rgb[npc_screen_x, npc_screen_y] = (npc.char, npc.color, (0, 0, 0))

        player_screen_x = world.player.x - camera_x
        player_screen_y = world.player.y - camera_y
        console.rgb[player_screen_x, player_screen_y] = (world.player.char, world.player.color, (0, 0, 0))

        draw_weather_overlay(console, world)

    if game_state == "INFO_MENU":
        draw_info_menu(console, world, camera_x, camera_y)
    elif game_state == "BUILD_MODE":
        draw_build_mode_ui(console, world)
    elif game_state == "DIALOGUE":
        draw_dialogue_ui(console, world)

    draw_chat_log(console, world)
    draw_interaction_menu(console, world)
    draw_trade_ui(console, world)
    draw_crafting_menu(console, world)
    draw_knowledge_menu(console, world)
    draw_book_reading_ui(console, world)
    draw_cursor_info(console, world, camera_x, camera_y)
    draw_status_panel(console, world)

def draw_book_reading_ui(console: tcod.console.Console, world) -> None:
    """Draws the book reading UI."""
    if world.game_state != "BOOK_READING":
        return

    menu_width = 60
    menu_height = 40
    menu_x = (SCREEN_WIDTH_TILES - menu_width) // 2
    menu_y = (SCREEN_HEIGHT_TILES - menu_height) // 2

    console.draw_frame(x=menu_x, y=menu_y, width=menu_width, height=menu_height,
                       title="Reading", clear=True)

    ctx = world.book_reading_context
    book_id = ctx.get("book_id")
    scroll_offset = ctx.get("scroll_offset", 0)

    if not book_id:
        console.print(x=menu_x + 2, y=menu_y + 2,
                      string="No book selected.", fg=(255, 0, 0))
        return

    book = next((b for b in world.books if b.id == book_id), None)

    if not book:
        console.print(x=menu_x + 2, y=menu_y + 2,
                      string=f"Error: Book with ID {book_id} not found.", fg=(255, 0, 0))
        return

    y_offset = menu_y + 2

    console.print_box(x=menu_x + 2, y=y_offset, width=menu_width - 4, height=2,
                      string=book.title, fg=(255, 255, 0), alignment=tcod.CENTER)
    y_offset += 2

    author_line = f"by {book.author_name}, Year {book.year_written}"
    console.print_box(x=menu_x + 2, y=y_offset, width=menu_width - 4, height=1,
                      string=author_line, fg=(200, 200, 200), alignment=tcod.CENTER)
    y_offset += 2

    console.print(x=menu_x + 1, y=y_offset, string="-" * (menu_width - 2))
    y_offset += 1

    content_width = menu_width - 4
    content_height = menu_height - (y_offset - menu_y) - 2

    wrapped_text = tcod.text.wrap(book.content, width=content_width, indent=0)
    lines = wrapped_text.split('\n')

    for i in range(content_height):
        line_index = scroll_offset + i
        if line_index < len(lines):
            console.print(x=menu_x + 2, y=y_offset + i, string=lines[line_index],
                          fg=(255, 255, 255))

    if scroll_offset > 0:
        console.print(x=menu_x + menu_width - 2, y=menu_y + 1, string="^", fg=(255, 255, 0))
    if scroll_offset + content_height < len(lines):
        console.print(x=menu_x + menu_width - 2, y=menu_y + menu_height - 2,
                      string="v", fg=(255, 255, 0))

def draw_knowledge_menu(console: tcod.console.Console, world) -> None:
    """Draws the knowledge menu UI."""
    if world.game_state != "KNOWLEDGE_MENU":
        return

    menu_width = 50
    menu_height = 30
    menu_x = (SCREEN_WIDTH_TILES - menu_width) // 2
    menu_y = (SCREEN_HEIGHT_TILES - menu_height) // 2

    console.draw_frame(x=menu_x, y=menu_y, width=menu_width, height=menu_height,
                       title="Knowledge", clear=True)

    ctx = world.knowledge_menu_context
    scroll_offset = ctx.get("scroll_offset", 0)

    y_offset = menu_y + 2

    known_books = [b for b in world.books if b.id in world.player.known_books]

    if not known_books:
        console.print(x=menu_x + 2, y=y_offset,
                      string="You haven't read any books yet.", fg=(128, 128, 128))
        return

    list_height = menu_height - 4
    for i in range(list_height):
        book_index = scroll_offset + i
        if book_index >= len(known_books):
            break

        book = known_books[book_index]
        console.print(x=menu_x + 2, y=y_offset + i,
                      string=f"- {book.title} by {book.author_name}", fg=(255, 255, 255))

def draw_cursor_info(console: tcod.console.Console, world, camera_x: int, camera_y: int) -> None:
    """Draws information about the tile under the mouse cursor."""
    cursor_world_x = camera_x + world.mouse_x
    cursor_world_y = camera_y + world.mouse_y

    season_name = world.seasons[world.current_season_index]
    weather_name = getattr(world, 'current_weather', 'clear').capitalize()

    tile_info = ""
    if 0 <= cursor_world_x < WORLD_WIDTH and 0 <= cursor_world_y < WORLD_HEIGHT:
        cursor_tile = world.get_tile_at(cursor_world_x, cursor_world_y)
        if cursor_tile:
            tile_info = f"| {cursor_tile.name}"

    cursor_info_text = f"({cursor_world_x}, {cursor_world_y}) | {season_name} | {weather_name} {tile_info}"

    text_width = len(cursor_info_text)
    border_width = text_width + 2
    border_height = 3

    console.draw_frame(x=0, y=0, width=border_width, height=border_height, clear=False,
                       fg=(255, 255, 255), bg=(0, 0, 0))
    console.print(x=1, y=1, string=cursor_info_text, fg=(255, 0, 0))

def draw_chat_log(console: tcod.console.Console, world) -> None:
    """Draws the chat log UI."""
    chat_width = console.width // 2
    chat_height = 10
    chat_x = 0
    chat_y = console.height - chat_height

    console.draw_frame(x=chat_x, y=chat_y, width=chat_width, height=chat_height,
                       title="Chat Log", clear=False, fg=(255, 255, 255), bg=(0, 0, 0))

    display_messages = world.chat_log[-(chat_height - 2):]
    for i, message in enumerate(display_messages):
        console.print(x=chat_x + 1, y=chat_y + 1 + i, string=message, fg=(200, 200, 200))

def draw_info_menu(main_console: tcod.console.Console, world, camera_x: int, camera_y: int) -> None:
    """Draws the information menu as a pop-up over the world view."""
    menu_width, menu_height = 40, 20
    menu_x = (main_console.width - menu_width) // 2
    menu_y = (main_console.height - menu_height) // 2

    main_console.draw_frame(x=menu_x, y=menu_y, width=menu_width, height=menu_height,
                            title="Info / Inspector", clear=True, fg=(255, 255, 0), bg=(0, 0, 0))

    ui_y = menu_y + 2
    main_console.print(x=menu_x + 2, y=ui_y, string="--- Player ---", fg=(170,170,220))
    ui_y += 1
    main_console.print(x=menu_x + 3, y=ui_y,
                       string=f"HP: {world.player.combat.hp} / {world.player.combat.max_hp}")
    ui_y +=1
    main_console.print(x=menu_x + 3, y=ui_y,
                       string=f"Hunger: {world.player.physical.hunger}/{world.player.physical.max_hunger} {world.player.physical.hunger_level_msg}")
    ui_y +=1
    main_console.print(x=menu_x + 3, y=ui_y,
                       string=f"Thirst: {world.player.physical.thirst}/{world.player.physical.max_thirst} {world.player.physical.thirst_level_msg}")
    ui_y += 2
    main_console.print(x=menu_x + 3, y=ui_y, string="Inventory:")
    ui_y += 1
    if not world.player.economic.inventory:
        main_console.print(x=menu_x + 4, y=ui_y, string="(Empty)", fg=(128, 128, 128))
        ui_y += 1
    else:
        inventory_summary = {}
        for item in world.player.economic.inventory:
            key = item["key"]
            inventory_summary[key] = inventory_summary.get(key, 0) + item.get("quantity", 1)

        for item_key, quantity in inventory_summary.items():
            item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
            main_console.print(x=menu_x + 4, y=ui_y,
                               string=f" - {item_name}: {quantity}")
            ui_y += 1
    ui_y += 1

    main_console.print(x=menu_x + 2, y=ui_y, string="--- Cursor Target ---", fg=(170,170,220))
    ui_y += 1

    cursor_world_x, cursor_world_y = camera_x + world.mouse_x, camera_y + world.mouse_y

    tile_name = "Void"
    if 0 <= cursor_world_x < WORLD_WIDTH and 0 <= cursor_world_y < WORLD_HEIGHT:
        tile_at_cursor = world.get_tile_at(cursor_world_x, cursor_world_y)
        tile_name = tile_at_cursor.name if tile_at_cursor else "Unknown"
    main_console.print(x=menu_x + 3, y=ui_y,
                       string=f"Tile: ({cursor_world_x},{cursor_world_y}) {tile_name}")
    ui_y += 1

    npc_at_cursor = None
    for npc_list in [world.village_npcs, world.npcs]:
        for npc_obj in npc_list:
            if npc_obj.x == cursor_world_x and npc_obj.y == cursor_world_y:
                npc_at_cursor = npc_obj
                break
        if npc_at_cursor:
            break

    if npc_at_cursor and 0 <= npc_at_cursor.x < WORLD_WIDTH and 0 <= npc_at_cursor.y < WORLD_HEIGHT and world.player_fov_map[npc_at_cursor.x, npc_at_cursor.y]:
        main_console.print(x=menu_x + 3, y=ui_y,
                           string=f"NPC: {npc_at_cursor.name}", fg=(180, 180, 255))

def draw_interaction_menu(console: tcod.console.Console, world) -> None:
    """Draws the interaction menu UI."""
    if not world.interaction_context["active"]:
        return

    ctx = world.interaction_context
    menu_x, menu_y = world.mouse_x + 1, world.mouse_y + 1

    max_entity_name_len = max(len(e["name"]) for e in ctx["target_entities"]) if ctx["target_entities"] else 10
    max_action_len = max(len(a) for a in ctx["available_actions"]) if ctx["available_actions"] else 10
    menu_width = max(max_entity_name_len, max_action_len) + 6
    menu_height = 1 + len(ctx["target_entities"]) + 1 + len(ctx["available_actions"]) + 2

    console.draw_frame(x=menu_x, y=menu_y, width=menu_width, height=menu_height,
                       title="Interact", clear=True)

    y_offset = menu_y + 1
    for i, entity in enumerate(ctx["target_entities"]):
        fg = (255, 255, 0) if i == ctx["selected_entity_index"] else (255, 255, 255)
        prefix = "> " if i == ctx["selected_entity_index"] else "  "
        console.print(x=menu_x + 1, y=y_offset, string=f"{prefix}{entity['name']}", fg=fg)
        y_offset += 1

    console.print(x=menu_x + 1, y=y_offset, string="-" * (menu_width - 2))
    y_offset += 1

    for i, action in enumerate(ctx["available_actions"]):
        fg = (255, 255, 0) if i == ctx["selected_action_index"] else (255, 255, 255)
        prefix = "* " if i == ctx["selected_action_index"] else "  "
        console.print(x=menu_x + 1, y=y_offset, string=f"{prefix}{action}", fg=fg)
        y_offset += 1

def draw_dialogue_ui(console: tcod.console.Console, world) -> None:
    """Draws the player-NPC dialogue UI."""
    if not world.chat_ui_active:
        return

    width = 60
    height = 20
    x = (SCREEN_WIDTH_TILES - width) // 2
    y = (SCREEN_HEIGHT_TILES - height) // 2

    title = f"Talking to {world.chat_ui_target_npc.name}" if world.chat_ui_target_npc else "Dialogue"
    console.draw_frame(x=x, y=y, width=width, height=height, title=title, clear=True)

    history_height = height - 4
    y_offset = y + 1

    # Display history from the bottom up
    for i in range(history_height):
        history_index = len(world.chat_ui_history) - 1 - i
        if history_index < 0:
            break

        speaker, text = world.chat_ui_history[history_index]
        line_y = y + height - 3 - i

        # Word wrap the text
        wrapped_lines = tcod.text.wrap(text, width=width - 4)

        # Display the wrapped lines, also from the bottom up
        for line in reversed(wrapped_lines.split('\n')):
            if line_y < y + 1:
                break

            fg_color = (255, 255, 0) if speaker == "Player" else (255, 255, 255)
            console.print(x=x + 2, y=line_y, string=f"{speaker}: {line}", fg=fg_color)
            line_y -= 1
            if line_y < y + 1:
                break

    # Draw the input line
    console.print(x=x + 1, y=y + height - 2, string="> " + world.chat_ui_input_line + "_", fg=(255, 255, 255))

def draw_trade_ui(console: tcod.console.Console, world) -> None:
    """Draws the trade UI."""

def draw_crafting_menu(console: tcod.console.Console, world) -> None:
    """Draws the crafting menu UI."""
    if world.game_state != "CRAFTING_MENU":
        return

    menu_width, menu_height = 50, 30
    menu_x = (SCREEN_WIDTH_TILES - menu_width) // 2
    menu_y = (SCREEN_HEIGHT_TILES - menu_height) // 2

    console.draw_frame(x=menu_x, y=menu_y, width=menu_width, height=menu_height,
                       title="Crafting", clear=True)

    ctx, recipes = world.crafting_menu_context, ctx["all_recipes"]
    selected_index, scroll_offset = ctx["selected_recipe_index"], ctx["scroll_offset"]

    list_height = menu_height - 4
    for i in range(list_height):
        recipe_index = scroll_offset + i
        if recipe_index >= len(recipes):
            break

        recipe_key = recipes[recipe_index]
        item_def = ITEM_DEFINITIONS.get(recipe_key, {})
        item_name = item_def.get("name", recipe_key)
        can_craft = world.player_can_craft(recipe_key)

        fg = (255, 255, 0) if recipe_index == selected_index else ((0, 255, 0) if can_craft else (255, 0, 0))
        prefix = "> " if recipe_index == selected_index else "  "
        console.print(x=menu_x + 2, y=menu_y + 2 + i, string=f"{prefix}{item_name}", fg=fg)

    details_x = menu_x + 25
    console.draw_rect(x=details_x - 1, y=menu_y + 1, width=1, height=menu_height - 2, ch=ord('|'))

    if 0 <= selected_index < len(recipes):
        selected_key = recipes[selected_index]
        selected_def = ITEM_DEFINITIONS.get(selected_key, {})
        selected_name = selected_def.get("name", selected_key)

        console.print(x=details_x + 1, y=menu_y + 2, string=selected_name)
        console.print(x=details_x + 1, y=menu_y + 4, string="Ingredients:")

        y_offset = menu_y + 5
        recipe = selected_def.get("crafting_recipe", {})
        if not recipe:
            console.print(x=details_x + 2, y=y_offset,
                          string="(No recipe)", fg=(128, 128, 128))
        else:
            for ingredient_key, required_qty in recipe.items():
                ingredient_name = ITEM_DEFINITIONS.get(ingredient_key, {}).get("name", ingredient_key)
                has_enough = world.player.has_item(ingredient_key, required_qty)
                fg = (0, 255, 0) if has_enough else (255, 0, 0)
                console.print(x=details_x + 2, y=y_offset,
                              string=f"- {ingredient_name}: {required_qty}", fg=fg)
                y_offset += 1

def draw_build_mode_ui(console: tcod.console.Console, world) -> None:
    """Draws the build mode UI."""
    if not world.ghost_furniture_tile:
        return
