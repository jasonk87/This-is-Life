
import unittest
from engine import World

class TestGame(unittest.TestCase):
    def test_world_initialization(self):
        try:
            world = World()
            self.assertIsNotNone(world)
            self.assertIsNotNone(world.player)
        except Exception as e:
            self.fail(f"World initialization failed with an exception: {e}")

if __name__ == '__main__':
    unittest.main()
