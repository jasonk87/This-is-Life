from unittest.mock import patch

import engine
from entities.base import CombatStats, Equipment, PhysicalState, SocialState


def test_player_uses_shared_simulation_components():
    player = engine.Player(5, 6)

    assert isinstance(player.physical, PhysicalState)
    assert isinstance(player.combat, CombatStats)
    assert isinstance(player.social, SocialState)
    assert isinstance(player.equipment, Equipment)

    player.add_item("apple", 2)
    assert player.has_item("apple", 2)


def test_world_update_delegates_to_tick_system():
    world = engine.World(seed=1)

    with patch("engine.run_world_tick") as run_world_tick:
        world.update()

    run_world_tick.assert_called_once_with(world)
