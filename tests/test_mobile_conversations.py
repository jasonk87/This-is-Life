import pytest
from unittest.mock import patch
from engine import World
from entities.base import NPC


def test_mobile_conversation_follow():
    """NPC A follows NPC B when within follow range, with random always succeeding."""
    world = World(seed=42)

    # NPC A and B
    a = NPC(x=10, y=10, name="A")
    a.schedule.current_task = "idle"
    b = NPC(x=12, y=10, name="B")
    b.schedule.current_task = "idle"

    world.village_npcs.extend([a, b])

    # Set conversation state
    a.conversation_partner_id = b.id
    b.conversation_partner_id = a.id

    # B moves away a bit (distance = 3, which is > 2 so keep-up triggers)
    b.x = 13
    b.y = 10

    from simulation.systems.scheduling import run_npc_mobile_conversation_policy

    # Mock random.random() to always return 0.0, so keep_up_chance always passes.
    # This avoids seed-ordering issues from World(seed=42) consuming random state.
    with patch("random.random", return_value=0.0):
        result = run_npc_mobile_conversation_policy(world, a)

    assert result is True
    assert a.schedule.current_task == "mobile_conversation_follow"
    assert a.schedule.current_path is not None
    assert len(a.schedule.current_path) > 0


def test_mobile_conversation_drop_when_far():
    """NPC A gives up following when partner is too far (> 6 tiles)."""
    world = World(seed=42)

    a = NPC(x=10, y=10, name="A")
    b = NPC(x=20, y=20, name="B")

    world.village_npcs.extend([a, b])

    a.conversation_partner_id = b.id
    b.conversation_partner_id = a.id

    # Distance is ~14, which is > 6
    from simulation.systems.scheduling import run_npc_mobile_conversation_policy

    with patch("random.random", return_value=0.0):
        result = run_npc_mobile_conversation_policy(world, a)

    # Policy returns false (does not attempt to follow)
    assert result is False
    assert a.schedule.current_task != "mobile_conversation_follow"


def test_urgent_tasks_override_mobile_conversations():
    """NPC stuck in urgent task (e.g. fleeing) does not switch to follow."""
    world = World(seed=42)

    a = NPC(x=10, y=10, name="A")
    a.schedule.current_task = "fleeing_from_player"
    b = NPC(x=13, y=10, name="B")
    b.schedule.current_task = "idle"

    world.village_npcs.extend([a, b])
    a.conversation_partner_id = b.id

    from simulation.systems.scheduling import run_npc_mobile_conversation_policy

    with patch("random.random", return_value=0.0):
        result = run_npc_mobile_conversation_policy(world, a)

    assert result is False
    assert a.schedule.current_task == "fleeing_from_player"
