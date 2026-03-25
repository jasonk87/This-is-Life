import pytest
from engine import World
from entities.base import NPC

def test_mobile_conversation_follow():
    # Force a specific seed so that random chances pass
    import random
    random.seed(42)

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

    # B moves away a bit
    b.x = 13
    b.y = 10

    # Now distance is 3. A's policy should trigger and follow B.
    from simulation.systems.scheduling import run_npc_mobile_conversation_policy
    result = run_npc_mobile_conversation_policy(world, a)

    assert result is True
    assert a.schedule.current_task == "mobile_conversation_follow"
    assert a.schedule.current_path is not None
    assert len(a.schedule.current_path) > 0

def test_mobile_conversation_drop_when_far():
    import random
    random.seed(42)

    world = World(seed=42)

    a = NPC(x=10, y=10, name="A")
    b = NPC(x=20, y=20, name="B")

    world.village_npcs.extend([a, b])

    a.conversation_partner_id = b.id
    b.conversation_partner_id = a.id

    # Distance is 20, which is > 6
    from simulation.systems.scheduling import run_npc_mobile_conversation_policy
    result = run_npc_mobile_conversation_policy(world, a)

    # Policy returns false (does not attempt to follow)
    assert result is False
    assert a.schedule.current_task != "mobile_conversation_follow"


def test_urgent_tasks_override_mobile_conversations():
    import random
    random.seed(42)

    world = World(seed=42)

    a = NPC(x=10, y=10, name="A")
    a.schedule.current_task = "fleeing_from_player"
    b = NPC(x=13, y=10, name="B")
    b.schedule.current_task = "idle"

    world.village_npcs.extend([a, b])
    a.conversation_partner_id = b.id

    from simulation.systems.scheduling import run_npc_mobile_conversation_policy
    result = run_npc_mobile_conversation_policy(world, a)

    assert result is False
    assert a.schedule.current_task == "fleeing_from_player"
