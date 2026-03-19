
import unittest
from unittest.mock import MagicMock, patch
from engine import World, NPC, Book, Event
from config import DAY_LENGTH_TICKS

class MockWorld(World):
    def __init__(self):
        self.game_time = 0
        self.village_npcs = []
        self.npcs = []
        self.buildings_by_id = {}
        self.add_message_to_chat_log = MagicMock()
        self.chunks = [[MagicMock() for _ in range(1)] for _ in range(1)]
        self.player = MagicMock()
        self.player.id = 1
        # Configure social stats for int comparisons
        self.player.social.fame = 0
        self.player.social.infamy = 0
        self.player.knowledge.known_events = {}
        self.player.knowledge.known_books = set()
        self.global_events = []
        self.books = []
        self.chunk_width = 1
        self.chunk_height = 1
        self._get_village_for_npc = MagicMock()
        # Mock LLM
        self._call_llm = MagicMock(return_value='{"title": "Life of Hero", "content": "A great story."}')
        self.book_reading_context = {}

class TestKnowledgeSystem(unittest.TestCase):
    def setUp(self):
        self.world = MockWorld()
        self.world.player.world_ref = self.world # Loopback for methods calling self.world_ref

    def test_scribe_writes_biography(self):
        scribe = NPC(x=0, y=0, name="Scribe")
        scribe.economic.profession = "Scribe"
        self.world.village_npcs.append(scribe)

        subject = NPC(x=0, y=0, name="Hero")
        subject.social.fame = 50
        self.world.village_npcs.append(subject)

        # Create some events for the subject
        event1 = Event("combat_attack", "Hero fought Wolf", subject.id, 100)
        self.world.global_events.append(event1)
        # The scribe must know about the event to write about it
        scribe.knowledge.known_events[event1.id] = event1

        # Mock building and inventory
        library = MagicMock()
        library.building_inventory = {}
        # Setup work zones so _find_target_coords_for_sub_task works without random.choice needing patch
        library.work_zone_tiles = {
            "writing_desk": [(0, 0)]
        }
        self.world.buildings_by_id["library_1"] = library
        scribe.schedule.work_building_id = "library_1"

        # To hit the "write_biography" block, we need `npc.current_sub_task` to be "write_biography"
        # and timer <= 0 and at target.
        scribe.current_sub_task = "write_biography"
        scribe.sub_task_target_coords = (0, 0)
        scribe.x, scribe.y = 0, 0
        scribe.sub_task_timer = 0

        # Run the method
        # The logic sorts candidates by fame, so 'Hero' (fame 50) should be picked over Scribe (fame 0)
        self.world._handle_npc_work_sub_tasks(scribe)

        # Check if book was created
        self.assertEqual(len(self.world.books), 1)
        book = self.world.books[0]
        self.assertEqual(book.book_type, "biography")
        self.assertIn(event1.id, book.referenced_event_ids)
        self.assertIn(f"book_{book.id}", library.building_inventory)

    def test_scribe_writes_generic_biography_without_known_events(self):
        scribe = NPC(x=0, y=0, name="Scribe")
        scribe.economic.profession = "Scribe"
        self.world.village_npcs.append(scribe)

        subject = NPC(x=0, y=0, name="Hero")
        subject.social.fame = 25
        self.world.village_npcs.append(subject)

        library = MagicMock()
        library.building_inventory = {}
        library.work_zone_tiles = {"writing_desk": [(0, 0)]}
        self.world.buildings_by_id["library_1"] = library
        scribe.schedule.work_building_id = "library_1"
        scribe.current_sub_task = "write_biography"
        scribe.sub_task_target_coords = (0, 0)
        scribe.x, scribe.y = 0, 0
        scribe.sub_task_timer = 0

        self.world._handle_npc_work_sub_tasks(scribe)

        self.assertEqual(len(self.world.books), 1)
        book = self.world.books[0]
        self.assertEqual(book.book_type, "biography")
        self.assertEqual(book.referenced_event_ids, [])
        self.assertIn("Biography: Hero", book.title)
        self.assertIn("fame 25", book.content)
        self.assertIn(f"book_{book.id}", library.building_inventory)


    def test_player_reads_book_and_learns(self):
        # Setup book with an event
        event1 = Event("historical_event", "Ancient Battle", 999, 10)
        self.world.global_events.append(event1)

        book = Book("History Book", 100, "Author", 200, "Content", "chronicle", referenced_event_ids=[event1.id])
        self.world.books.append(book)

        # Player reads book
        self.world.player_attempt_read_book(f"book_{book.id}")

        # Assert state change
        self.assertEqual(self.world.game_state, "BOOK_READING")
        self.assertEqual(self.world.book_reading_context["book_id"], book.id)

        # Assert knowledge gained
        self.assertIn(event1.id, self.world.player.knowledge.known_events)
        self.assertEqual(self.world.player.knowledge.known_events[event1.id], event1)

if __name__ == '__main__':
    unittest.main()
