"""Shared helpers for engine-emitted UI requests."""

OPEN_DIALOGUE = "open_dialogue"
CLOSE_DIALOGUE = "close_dialogue"
OPEN_TRADE = "open_trade"
CLOSE_TRADE = "close_trade"


def open_dialogue_request(npc, mode: str = "talk") -> dict:
    return {"type": OPEN_DIALOGUE, "npc": npc, "mode": mode}


def close_dialogue_request(target_npc=None) -> dict:
    return {"type": CLOSE_DIALOGUE, "npc": target_npc}


def open_trade_request(npc) -> dict:
    return {"type": OPEN_TRADE, "npc": npc}


def close_trade_request(target_npc=None) -> dict:
    return {"type": CLOSE_TRADE, "npc": target_npc}


def apply_ui_requests(world, context_handler=None):
    """Apply UI requests emitted by the simulation layer."""
    while world.ui_requests:
        request = world.ui_requests.pop(0)
        request_type = request.get("type")
        npc = request.get("npc")

        if request_type == OPEN_DIALOGUE:
            world.game_state = "DIALOGUE"
            world.chat_ui_target_npc = npc
            world.chat_ui_mode = request.get("mode", "talk")
            world.chat_ui_active = True
            world.trade_ui_active = False
            world.trade_ui_npc_target = None
            world.needs_text_input = context_handler is None
            if context_handler is not None:
                context_handler.start_text_input()
        elif request_type == CLOSE_DIALOGUE:
            if npc is None or world.chat_ui_target_npc == npc:
                world.chat_ui_active = False
                world.chat_ui_target_npc = None
                world.game_state = "PLAYING"
                world.needs_text_input = False
                if context_handler is not None:
                    context_handler.stop_text_input()
        elif request_type == OPEN_TRADE:
            world.chat_ui_active = False
            world.chat_ui_target_npc = None
            world.game_state = "TRADE_MENU"
            world.trade_ui_active = True
            world.trade_ui_npc_target = npc
            world.initialize_trade_session()
            world.needs_text_input = False
            if context_handler is not None:
                context_handler.stop_text_input()
        elif request_type == CLOSE_TRADE:
            if npc is None or world.trade_ui_npc_target == npc:
                world.trade_ui_active = False
                world.trade_ui_npc_target = None
                world.needs_text_input = False
                if context_handler is not None:
                    context_handler.stop_text_input()
                if world.game_state == "TRADE_MENU":
                    world.game_state = "PLAYING"
