import unittest
from unittest.mock import patch
from types import SimpleNamespace

import config
import engine
from engine import NPC, World
from simulation.world_model import Village


class TestVillageDirectionDescription(unittest.TestCase):
    """Bug-hunt/ideation audit item: village war/raid/diplomacy events were
    real (village_relationships, at_war_with, raiding parties, dynamic
    per-village pricing) but never surfaced to the player - log_event only
    reaches the player if they happen to be physically witnessing the exact
    location, which is never true for this distance-gated abstract
    simulation. _describe_village_direction_from_player is the shared
    helper used to make these events legible without inventing a village
    naming system (villages have no name field anywhere in this codebase)."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=3001)
        self.player_chunk_x = self.world.player.x // config.CHUNK_SIZE
        self.player_chunk_y = self.world.player.y // config.CHUNK_SIZE

    def test_none_chunk_coords_falls_back_gracefully(self):
        self.assertEqual(
            self.world._describe_village_direction_from_player(None),
            "somewhere in the region",
        )

    def test_within_abstract_simulation_distance_is_nearby(self):
        near = (self.player_chunk_x + 1, self.player_chunk_y - 1)
        self.assertEqual(self.world._describe_village_direction_from_player(near), "nearby")

    def test_directly_east_and_far_is_east(self):
        far = config.ABSTRACT_SIMULATION_DISTANCE_CHUNKS + 5
        coords = (self.player_chunk_x + far, self.player_chunk_y)
        self.assertEqual(self.world._describe_village_direction_from_player(coords), "to the east")

    def test_directly_north_and_far_is_north(self):
        # chunk_y increases southward, so "north" is a smaller y.
        far = config.ABSTRACT_SIMULATION_DISTANCE_CHUNKS + 5
        coords = (self.player_chunk_x, self.player_chunk_y - far)
        self.assertEqual(self.world._describe_village_direction_from_player(coords), "to the north")

    def test_directly_south_and_far_is_south(self):
        far = config.ABSTRACT_SIMULATION_DISTANCE_CHUNKS + 5
        coords = (self.player_chunk_x, self.player_chunk_y + far)
        self.assertEqual(self.world._describe_village_direction_from_player(coords), "to the south")

    def test_directly_west_and_far_is_west(self):
        far = config.ABSTRACT_SIMULATION_DISTANCE_CHUNKS + 5
        coords = (self.player_chunk_x - far, self.player_chunk_y)
        self.assertEqual(self.world._describe_village_direction_from_player(coords), "to the west")

    def test_northeast_diagonal(self):
        far = config.ABSTRACT_SIMULATION_DISTANCE_CHUNKS + 5
        coords = (self.player_chunk_x + far, self.player_chunk_y - far)
        self.assertEqual(self.world._describe_village_direction_from_player(coords), "to the northeast")

    def test_southwest_diagonal(self):
        far = config.ABSTRACT_SIMULATION_DISTANCE_CHUNKS + 5
        coords = (self.player_chunk_x - far, self.player_chunk_y + far)
        self.assertEqual(self.world._describe_village_direction_from_player(coords), "to the southwest")

    def test_direction_is_recomputed_fresh_not_cached(self):
        """Move the player and confirm the same village coords now describe
        differently - proves this isn't cached/stale."""
        far = config.ABSTRACT_SIMULATION_DISTANCE_CHUNKS + 5
        coords = (self.player_chunk_x + far, self.player_chunk_y)
        self.assertEqual(self.world._describe_village_direction_from_player(coords), "to the east")

        # Move the player to be right next to those same coords now.
        self.world.player.x = coords[0] * config.CHUNK_SIZE
        self.world.player.y = coords[1] * config.CHUNK_SIZE
        self.assertEqual(self.world._describe_village_direction_from_player(coords), "nearby")


class TestAbstractSimulationDiplomacyNotifications(unittest.TestCase):
    """Integration-level tests driving the real _update_abstract_simulation
    daily tick, following the established pattern from
    tests/test_population_lifecycle.py (real World(seed=...), pick a real
    generated village pair by distance, force game_time to a day boundary)."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=3002)
        self.world.game_time = config.DAY_LENGTH_TICKS

    def _make_npc(self, name):
        npc = NPC(
            self.world.player.x,
            self.world.player.y,
            name=name,
            dialogue=["Hello."],
            personality="villager",
            player_id=self.world.player.id,
        )
        return npc

    def _distant_village_with_resident(self):
        """Finds a real generated village beyond ABSTRACT_SIMULATION_DISTANCE_CHUNKS
        of the player (required for _update_abstract_simulation's
        diplomacy/warfare block to run at all for that village as the
        source) and gives it a resident NPC tied to a real building, mirroring
        test_population_lifecycle.py's test_death_runs_for_players_nearby_village_not_just_distant_ones."""
        player_chunk_x = self.world.player.x // config.CHUNK_SIZE
        player_chunk_y = self.world.player.y // config.CHUNK_SIZE
        for y in range(self.world.chunk_height):
            for x in range(self.world.chunk_width):
                chunk = self.world.chunks[y][x]
                if not chunk.village or not chunk.village.buildings:
                    continue
                dist = max(abs(x - player_chunk_x), abs(y - player_chunk_y))
                if dist > config.ABSTRACT_SIMULATION_DISTANCE_CHUNKS:
                    village = chunk.village
                    home = village.buildings[0]
                    resident = self._make_npc(f"Resident of {village.id[:4]}")
                    resident.x, resident.y = home.global_center_x, home.global_center_y
                    resident.schedule.home_building_id = home.id
                    self.world.village_npcs.append(resident)
                    self.world.npcs.append(resident)
                    self.world._mark_entity_positions_dirty()
                    return village
        return None

    def _any_other_village(self, exclude_id):
        for v in self.world.villages:
            if v.id != exclude_id:
                return v
        return None

    def test_war_declared_notifies_player_via_chat_log(self):
        source_village = self._distant_village_with_resident()
        self.assertIsNotNone(source_village, "test requires a village beyond ABSTRACT_SIMULATION_DISTANCE_CHUNKS")
        target_village = self._any_other_village(source_village.id)
        self.assertIsNotNone(target_village, "test requires at least 2 villages")

        # Preset relationship well below the -50 war threshold so war
        # declares deterministically on this call regardless of the 5%
        # random relationship-decay branch. Mock random.random to a value
        # that fails both the 5% decay check and the 10% raid-dispatch
        # check, isolating the war-declared message from this test.
        source_village.village_relationships[target_village.id] = -80
        target_village.village_relationships[source_village.id] = -80

        with patch("random.random", return_value=0.9):
            self.world._update_abstract_simulation()

        self.assertIn(target_village.id, source_village.at_war_with)
        chat_text = " ".join(self.world.chat_log)
        self.assertIn("War has broken out between a village", chat_text)

    def test_peace_declared_notifies_player_via_chat_log(self):
        source_village = self._distant_village_with_resident()
        self.assertIsNotNone(source_village)
        target_village = self._any_other_village(source_village.id)
        self.assertIsNotNone(target_village)

        source_village.at_war_with.add(target_village.id)
        target_village.at_war_with.add(source_village.id)
        # Relationship already recovered above the -10 peace threshold.
        source_village.village_relationships[target_village.id] = 0
        target_village.village_relationships[source_village.id] = 0

        with patch("random.random", return_value=0.9):
            self.world._update_abstract_simulation()

        self.assertNotIn(target_village.id, source_village.at_war_with)
        chat_text = " ".join(self.world.chat_log)
        self.assertIn("peace treaty has been signed", chat_text)

    def test_raid_message_is_urgent_when_target_village_is_near_player(self):
        source_village = self._distant_village_with_resident()
        self.assertIsNotNone(source_village)

        # Build a synthetic target village positioned exactly at the
        # player's own chunk, so it's guaranteed "nearby" regardless of
        # what the world generator actually placed near the player.
        player_chunk_x = self.world.player.x // config.CHUNK_SIZE
        player_chunk_y = self.world.player.y // config.CHUNK_SIZE
        target_village = Village(chunk_coords=(player_chunk_x, player_chunk_y))
        # interaction_points values are lists of coordinates (see the
        # "well"/"noticeboard" generation in _generate_village_structure);
        # readers take [0].
        target_village.interaction_points["town_square_center"] = [(self.world.player.x, self.world.player.y)]
        self.world.villages.append(target_village)

        source_village.at_war_with.add(target_village.id)
        target_village.at_war_with.add(source_village.id)
        source_village.village_relationships[target_village.id] = -80
        target_village.village_relationships[source_village.id] = -80

        # random.random() < 0.1 must succeed to dispatch the raid; also
        # comfortably fails the 5% decay branch's own random check since
        # both branches share the same mocked low value here deliberately -
        # a decay this small can't move -80 back above the war/peace
        # thresholds, so it doesn't interfere with staying "at war".
        with patch("random.random", return_value=0.0):
            self.world._update_abstract_simulation()

        chat_text = " ".join(self.world.chat_log)
        self.assertIn("trouble may be close at hand", chat_text)

    def test_raid_message_uses_directions_when_target_is_far(self):
        source_village = self._distant_village_with_resident()
        self.assertIsNotNone(source_village)
        target_village = self._any_other_village(source_village.id)
        self.assertIsNotNone(target_village)
        player_chunk_x = self.world.player.x // config.CHUNK_SIZE
        player_chunk_y = self.world.player.y // config.CHUNK_SIZE
        far = config.ABSTRACT_SIMULATION_DISTANCE_CHUNKS + 10
        target_village.chunk_coords = (player_chunk_x + far, player_chunk_y)
        target_village.interaction_points["town_square_center"] = [
            (self.world.player.x + far * config.CHUNK_SIZE, self.world.player.y)
        ]

        source_village.at_war_with.add(target_village.id)
        target_village.at_war_with.add(source_village.id)
        source_village.village_relationships[target_village.id] = -80
        target_village.village_relationships[source_village.id] = -80

        with patch("random.random", return_value=0.0):
            self.world._update_abstract_simulation()

        chat_text = " ".join(self.world.chat_log)
        self.assertIn("marching toward a village to the east", chat_text)
        self.assertNotIn("trouble may be close at hand", chat_text)


class TestTradeSessionPriceConditionsNote(unittest.TestCase):
    """Bug-hunt/ideation audit item: villages already have genuinely
    different, fluctuating supply/demand-driven prices via get_dynamic_price,
    but nothing ever told the player. initialize_trade_session now adds a
    one-time note when a village's conditions are notably one-sided."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=3003)
        self.merchant = NPC(0, 0, name="Merchant", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        self.merchant.economic.profession = "Merchant"
        self.merchant.schedule.work_building_id = "shop_1"
        self.world.trade_ui_active = True
        self.world.trade_ui_npc_target = self.merchant

    def _shop(self, inventory):
        return SimpleNamespace(building_type="general_store", building_inventory=dict(inventory))

    def test_scarce_goods_produce_high_price_note(self):
        village = Village()
        village.supply = {"bread": 1}
        village.demand = {"bread": 10}  # modifier = clamp(10/1) = 5.0, well above 1.5
        self.world.buildings_by_id = {"shop_1": self._shop({"bread": 3})}

        with patch.object(self.world, "_get_village_for_npc", return_value=village):
            self.world.initialize_trade_session()

        chat_text = " ".join(self.world.chat_log)
        self.assertIn("prices are running high", chat_text)

    def test_surplus_goods_produce_low_price_note(self):
        village = Village()
        village.supply = {"bread": 50}
        village.demand = {"bread": 1}  # modifier = clamp(1/50) = 0.2, well below 0.6
        self.world.buildings_by_id = {"shop_1": self._shop({"bread": 3})}

        with patch.object(self.world, "_get_village_for_npc", return_value=village):
            self.world.initialize_trade_session()

        chat_text = " ".join(self.world.chat_log)
        self.assertIn("surplus stock", chat_text)

    def test_balanced_conditions_produce_no_note(self):
        village = Village()
        village.supply = {"bread": 5}
        village.demand = {"bread": 5}  # modifier = 1.0, unremarkable
        self.world.buildings_by_id = {"shop_1": self._shop({"bread": 3})}

        with patch.object(self.world, "_get_village_for_npc", return_value=village):
            self.world.initialize_trade_session()

        chat_text = " ".join(self.world.chat_log)
        self.assertNotIn("prices are running high", chat_text)
        self.assertNotIn("surplus stock", chat_text)

    def test_no_village_does_not_crash(self):
        self.world.buildings_by_id = {"shop_1": self._shop({"bread": 3})}
        with patch.object(self.world, "_get_village_for_npc", return_value=None):
            self.world.initialize_trade_session()  # should not raise
        self.assertIn(("bread", 3, self.world.get_dynamic_price("bread", None, merchant=self.merchant)), self.world.trade_ui_merchant_inventory_snapshot)


if __name__ == "__main__":
    unittest.main()
