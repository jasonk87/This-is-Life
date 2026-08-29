"""Inter-village diplomacy, conflict notices, and regional player awareness."""

from __future__ import annotations
import math
from typing import Any
from config import CHUNK_SIZE, ABSTRACT_SIMULATION_DISTANCE_CHUNKS


def describe_village_direction_from_player(player: Any, chunk_coords: tuple[int, int] | None) -> str:
    """Return a short player-relative direction string (e.g. 'to the northeast', 'nearby')."""
    if not chunk_coords or player is None:
        return "somewhere in the region"

    player_chunk_x = player.x // CHUNK_SIZE
    player_chunk_y = player.y // CHUNK_SIZE
    dx = chunk_coords[0] - player_chunk_x
    dy = chunk_coords[1] - player_chunk_y

    if abs(dx) <= ABSTRACT_SIMULATION_DISTANCE_CHUNKS and abs(dy) <= ABSTRACT_SIMULATION_DISTANCE_CHUNKS:
        return "nearby"

    # atan2 with -dy since chunk_y increases southward
    angle = math.degrees(math.atan2(-dy, dx)) % 360
    directions = ["east", "northeast", "north", "northwest", "west", "southwest", "south", "southeast"]
    direction = directions[round(angle / 45) % 8]
    return f"to the {direction}"


def notify_war_declared(world: Any, village: Any, other_village: Any) -> None:
    """Broadcast a distant or nearby war declaration notice to the player's message feed."""
    dir_a = describe_village_direction_from_player(getattr(world, "player", None), getattr(village, "chunk_coords", None))
    dir_b = describe_village_direction_from_player(getattr(world, "player", None), getattr(other_village, "chunk_coords", None))

    msg = f"War has broken out between a village {dir_a} and a village {dir_b}!"
    if hasattr(world, "add_message_to_chat_log"):
        world.add_message_to_chat_log(msg)


def notify_peace_treaty(world: Any, village: Any, other_village: Any) -> None:
    """Broadcast a peace treaty notification to the player's message feed."""
    dir_a = describe_village_direction_from_player(getattr(world, "player", None), getattr(village, "chunk_coords", None))
    dir_b = describe_village_direction_from_player(getattr(world, "player", None), getattr(other_village, "chunk_coords", None))

    msg = f"A peace treaty has been signed between a village {dir_a} and a village {dir_b}."
    if hasattr(world, "add_message_to_chat_log"):
        world.add_message_to_chat_log(msg)


def notify_raid_sighted(world: Any, source_village: Any, target_village: Any) -> None:
    """Broadcast a raid alert if moving near the player or across the region."""
    dir_target = describe_village_direction_from_player(getattr(world, "player", None), getattr(target_village, "chunk_coords", None))
    if dir_target == "nearby":
        msg = "URGENT: A hostile raiding party has been spotted approaching this settlement!"
    else:
        dir_source = describe_village_direction_from_player(getattr(world, "player", None), getattr(source_village, "chunk_coords", None))
        msg = f"Word arrives that raiders from {dir_source} were seen marching towards a village {dir_target}."

    if hasattr(world, "add_message_to_chat_log"):
        world.add_message_to_chat_log(msg)
