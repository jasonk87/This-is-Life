import unittest
from unittest.mock import MagicMock, patch
from runtime_compat import np
from engine import World, Event, NPC, Animal
from entities.base import DireWolf
from config import NPC_SCHEDULE_UPDATE_INTERVAL, WORLD_WIDTH, WORLD_HEIGHT, CHUNK_SIZE

class TestKnowledgeTravel(unittest.TestCase):
    def setUp(self):
        # Patch WorldGenerator to avoid noise generation which might be slow or inconsistent
        with patch('engine.WorldGenerator') as MockGenerator:
            MockGenerator.return_value.get_biome_at.return_value = "plains"
            MockGenerator.return_value.get_poi_at.return_value = None

            # Patch the chunk initialization to avoid complex world gen logic
            with patch.object(World, '_initialize_chunks') as mock_init_chunks:
                # Create a grid of mock chunks matching world dimensions
                mock_chunks = [[MagicMock() for _ in range(WORLD_WIDTH // CHUNK_SIZE)] for _ in range(WORLD_HEIGHT // CHUNK_SIZE)]
                for row in mock_chunks:
                    for chunk in row:
                        chunk.is_generated = True # Assume generated
                        chunk.is_terrain_generated = True # Assume terrain generated
                        chunk.village = None
                        chunk.biome = "plains"

                        # Create tiles with real dictionary properties to avoid MagicMock issues in .get()
                        tiles = []
                        for _ in range(CHUNK_SIZE):
                            row_tiles = []
                            for _ in range(CHUNK_SIZE):
                                tile = MagicMock()
                                tile.passable = True
                                tile.properties = {} # Real dict
                                tile.name = "Plains"
                                row_tiles.append(tile)
                            tiles.append(row_tiles)
                        chunk.tiles = tiles

                mock_init_chunks.return_value = mock_chunks

                self.world = World(seed=1)

        # Setup simplified FOV for testing
        self.world.transparency_map = np.full((WORLD_HEIGHT, WORLD_WIDTH), True)
        self.world.current_fov_radius = 50 # Large radius for testing

    def test_broadcast_news(self):
        # Create speaker and listener
        speaker = NPC(10, 10, name="Town Crier")
        listener_near = NPC(15, 10, name="Villager Near") # Dist 5
        listener_far = NPC(50, 50, name="Villager Far")   # Dist far

        self.world.village_npcs.extend([speaker, listener_near, listener_far])

        # Create an event
        event = Event("test_event", "Something happened!", speaker.id, self.world.game_time)

        # Broadcast
        self.world.broadcast_news(speaker, 20, event)

        # Check knowledge
        self.assertIn(event.id, listener_near.knowledge.known_events)
        self.assertNotIn(event.id, listener_far.knowledge.known_events)

    def test_hunter_warning(self):
        # Create Hunter
        hunter = NPC(10, 10, name="Hunter Bob")
        hunter.economic.profession = "Hunter"
        self.world.village_npcs.append(hunter)

        # Create Threat (Wolves) - Using Animal class
        wolf1 = Animal(15, 10, name="Wolf 1", animal_type="wolf")
        wolf2 = Animal(16, 10, name="Wolf 2", animal_type="wolf")
        self.world.npcs.extend([wolf1, wolf2])

        # Initialize FOV maps for the test
        hunter.id = 1
        # Use correct shape (H, W) for order='C' (which matches our refactor)
        # Note: If refactor to order='C' is done, indexing should be [y, x]
        self.world.npc_fov_maps[hunter.id] = np.full((WORLD_HEIGHT, WORLD_WIDTH), True)

        # Advance time to trigger schedule update
        self.world.game_time = 1000
        hunter.schedule.game_time_last_updated = 0

        # We must set hunter's _force_fov_update to True or just not patch it out if we want it to run.
        # But if we patch it out, it relies on our mock fov map, which is fine.
        # However, the logic also checks if threats are visible in self.world.npcs/self.world.village_npcs
        # Ensure wolf1 and wolf2 have proper positions and are in self.world.npcs (which they are)
        # Ensure they are not dead
        wolf1.physical.is_dead = False
        wolf2.physical.is_dead = False
        hunter.physical.is_dead = False
        hunter.combat.is_hostile_to_player = False

        # Manually ensure coordinates are correct so they aren't considered dead/out of bounds
        wolf1.x, wolf1.y = 15, 10
        wolf2.x, wolf2.y = 16, 10
        hunter.x, hunter.y = 10, 10

        # Create a boolean array where everything is True so the wolves are "visible"
        fake_fov = np.full((WORLD_HEIGHT, WORLD_WIDTH), True)
        self.world.npc_fov_maps[hunter.id] = fake_fov

        # Update entity positions so they can be found by spatial queries if needed (though FOV check just iterates them)
        self.world._rebuild_entity_positions()

        # Ensure we set _force_fov_update so the FEAR SYSTEM processes it properly if needed.
        hunter._force_fov_update = True

        # Mock _update_npc_fov to avoid re-calculating and overwriting our simple map
        with patch.object(self.world, '_update_npc_fov'):
            self.world._update_npc_schedules()

        self.assertTrue(getattr(hunter, 'is_frightened', False), "Hunter should be frightened")
        self.assertIn(wolf1.id, hunter.threat_source_ids)

        # Check if event was logged
        threat_events = [e for e in self.world.global_events if e.type == "threat_detected"]
        self.assertTrue(len(threat_events) > 0)
        self.assertEqual(threat_events[0].subject_id, hunter.id)

    def test_traveling_merchant_gossip(self):
        # Create two villages (conceptually)
        # Ensure they are in different chunks. If CHUNK_SIZE is 40 (from config), then 10 and 80 are different chunks.
        # But to be safe and robust against config changes, we use multipliers.
        village1_loc = (10, 10)
        village2_loc = (CHUNK_SIZE * 2 + 10, CHUNK_SIZE * 2 + 10)

        # Create Merchant at Village 1
        merchant = NPC(village1_loc[0], village1_loc[1], name="Traveling Merchant")
        merchant.economic.profession = "Traveling Merchant"
        merchant.schedule.current_task = "traveling_to_village"
        self.world.npcs.append(merchant)

        # Create an event in Village 1 (remote from Village 2)
        event_v1 = Event("village1_event", "Big news in Village 1!", 999, self.world.game_time, location=village1_loc)

        # Merchant learns about event_v1
        merchant.knowledge.known_events[event_v1.id] = event_v1

        # Create a recipient at Village 2
        recipient = NPC(village2_loc[0], village2_loc[1], name="Innkeeper")
        recipient.economic.profession = "Tavern Keeper"
        # Mock finding village for recipient (needed for logic)
        # We can just mock _get_village_for_npc to return a mock village object for the recipient
        mock_village2 = MagicMock()
        mock_village2.buildings = []

        # We need the merchant to arrive at Village 2.
        # The logic checks _get_village_for_npc(merchant, by_coords=True).
        # So if we move merchant to recipient's location and ensure world returns a village there.

        merchant.x, merchant.y = recipient.x, recipient.y

        # Ensure ONLY the recipient is in village_npcs to prevent random choice from picking another NPC
        # The setUp adds test NPCs to village_npcs, so we must clear it.
        self.world.village_npcs = [recipient]

        # Patch _get_village_for_npc to simulate arrival context
        with patch.object(self.world, '_get_village_for_npc') as mock_get_village:
            def get_village_side_effect(npc, by_coords=False):
                if npc == merchant and by_coords:
                    return mock_village2
                if npc == recipient:
                    return mock_village2
                return None
            mock_get_village.side_effect = get_village_side_effect

            # Trigger the arrival logic manually or by mocking path completion
            # The logic is inside _update_npc_movement when path is empty/done.
            # IMPORTANT: The logic block is inside `if npc.schedule.current_path:`.
            # So we need a path of length 1 (arrived) to enter the block.
            merchant.schedule.current_path = [(merchant.x, merchant.y)]

            # We need to make sure the "arrival" block runs. It runs if task is "traveling_to_village" and path empty.
            # And it selects a recipient from village_npcs. We only have one, so it should pick 'recipient'.

            self.world._update_npc_movement()

            # Debug print if assertion fails
            if event_v1.id not in recipient.knowledge.known_events:
                print(f"DEBUG FAILURE: Recipient known events: {recipient.knowledge.known_events.keys()}")
                print(f"DEBUG FAILURE: Merchant known events: {merchant.knowledge.known_events.keys()}")
                print(f"DEBUG FAILURE: Merchant task: {merchant.schedule.current_task}")

            # Assert recipient learned the news
            self.assertIn(event_v1.id, recipient.knowledge.known_events)

            # Assert merchant cleared old news and relearned local news (if any)
            # Since there are no global events near Village 2, merchant's known_events should be empty/cleared of v1
            self.assertNotIn(event_v1.id, merchant.knowledge.known_events)

if __name__ == '__main__':
    unittest.main()
