"""Shared typed UI requests emitted by the simulation layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, TypeAlias

_LEGACY_OPEN_DIALOGUE = "open_dialogue"
_LEGACY_CLOSE_DIALOGUE = "close_dialogue"
_LEGACY_OPEN_TRADE = "open_trade"
_LEGACY_CLOSE_TRADE = "close_trade"


@dataclass(frozen=True)
class OpenDialogueRequest:
    """Request for the UI layer to open dialogue with an NPC."""

    npc: object
    mode: str = "talk"


@dataclass(frozen=True)
class CloseDialogueRequest:
    """Request for the UI layer to close dialogue with an optional target NPC."""

    npc: object | None = None


@dataclass(frozen=True)
class OpenTradeRequest:
    """Request for the UI layer to open a trade session with an NPC."""

    npc: object


@dataclass(frozen=True)
class CloseTradeRequest:
    """Request for the UI layer to close a trade session with an optional target NPC."""

    npc: object | None = None


UIRequest: TypeAlias = OpenDialogueRequest | CloseDialogueRequest | OpenTradeRequest | CloseTradeRequest
LegacyUIRequest: TypeAlias = Mapping[str, object]


def open_dialogue_request(npc, mode: str = "talk") -> OpenDialogueRequest:
    return OpenDialogueRequest(npc=npc, mode=mode)


def close_dialogue_request(target_npc=None) -> CloseDialogueRequest:
    return CloseDialogueRequest(npc=target_npc)


def open_trade_request(npc) -> OpenTradeRequest:
    return OpenTradeRequest(npc=npc)


def close_trade_request(target_npc=None) -> CloseTradeRequest:
    return CloseTradeRequest(npc=target_npc)


def coerce_ui_request(request: UIRequest | LegacyUIRequest) -> UIRequest:
    """Return a typed UI request, accepting old dict payloads at the boundary.

    The simulation layer should emit typed request objects.  This compatibility
    shim keeps older queued/pickled UI request dictionaries from crashing the UI
    loop while still centralizing the legacy string mapping outside the core
    dispatcher branches.
    """
    if isinstance(
        request,
        (
            OpenDialogueRequest,
            CloseDialogueRequest,
            OpenTradeRequest,
            CloseTradeRequest,
        ),
    ):
        return request

    if not isinstance(request, Mapping):
        raise TypeError(f"Unsupported UI request: {request!r}")

    request_type = request.get("type")
    npc = request.get("npc")
    if request_type == _LEGACY_OPEN_DIALOGUE:
        mode = request.get("mode", "talk")
        return OpenDialogueRequest(npc=npc, mode=str(mode))
    if request_type == _LEGACY_CLOSE_DIALOGUE:
        return CloseDialogueRequest(npc=npc)
    if request_type == _LEGACY_OPEN_TRADE:
        return OpenTradeRequest(npc=npc)
    if request_type == _LEGACY_CLOSE_TRADE:
        return CloseTradeRequest(npc=npc)

    raise TypeError(f"Unsupported UI request: {request!r}")


def apply_ui_requests(world, context_handler=None):
    """Apply UI requests emitted by the simulation layer."""
    while world.ui_requests:
        request = coerce_ui_request(world.ui_requests.pop(0))

        if isinstance(request, OpenDialogueRequest):
            world.game_state = "DIALOGUE"
            world.chat_ui_target_npc = request.npc
            world.chat_ui_mode = request.mode
            world.chat_ui_active = True
            if hasattr(world, "interaction_context") and isinstance(world.interaction_context, dict):
                world.interaction_context["active"] = False
            world.trade_ui_active = False
            world.trade_ui_npc_target = None
            world.needs_text_input = context_handler is None
            if context_handler is not None and hasattr(context_handler, "start_text_input"):
                context_handler.start_text_input()
        elif isinstance(request, CloseDialogueRequest):
            if request.npc is None or world.chat_ui_target_npc == request.npc:
                world.chat_ui_active = False
                world.chat_ui_target_npc = None
                world.game_state = "PLAYING"
                world.needs_text_input = False
                if context_handler is not None and hasattr(context_handler, "stop_text_input"):
                    context_handler.stop_text_input()
        elif isinstance(request, OpenTradeRequest):
            world.chat_ui_active = False
            world.chat_ui_target_npc = None
            world.game_state = "TRADE_MENU"
            world.trade_ui_active = True
            if hasattr(world, "interaction_context") and isinstance(world.interaction_context, dict):
                world.interaction_context["active"] = False
            world.trade_ui_npc_target = request.npc
            world.initialize_trade_session()
            world.needs_text_input = False
            if context_handler is not None and hasattr(context_handler, "stop_text_input"):
                context_handler.stop_text_input()
        elif isinstance(request, CloseTradeRequest):
            if request.npc is None or world.trade_ui_npc_target == request.npc:
                world.trade_ui_active = False
                world.trade_ui_npc_target = None
                world.needs_text_input = False
                if context_handler is not None and hasattr(context_handler, "stop_text_input"):
                    context_handler.stop_text_input()
                if world.game_state == "TRADE_MENU":
                    world.game_state = "PLAYING"
