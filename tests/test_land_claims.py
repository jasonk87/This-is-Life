import unittest
from types import SimpleNamespace
from unittest.mock import patch

from engine import World, Building, ItemReference
from simulation.world_model import Village, TownEconomicNeed
from tile_types import Tile


class TestTerritorialLandClaims(unittest.TestCase):
    def setUp(self):
        import engine
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=77)
        self.world.chunk_width = 1
        self.world.chunk_height = 1
        self.village = Village()
        self.village.interaction_points = {"town_square_center": [(30, 30)]}
        self.world.chunks[0][0].village = self.village
        self.world.villages = [self.village]

    def test_settlement_claim_creation_tracks_jurisdiction_tiles(self):
        house = Building(28, 28, 5, 5, building_type="house", category="residential")
        self.village.add_building(house)

        claim = self.world.ensure_settlement_territory(self.village)

        self.assertIsNotNone(claim)
        self.assertEqual(claim.claim_type, "settlement_core")
        self.assertEqual(claim.settlement_id, self.village.id)
        self.assertTrue(claim.metadata.get("jurisdiction"))
        self.assertIn((30, 30), claim.claimed_tiles)
        self.assertIn(claim.id, self.village.territory_claim_ids)
        self.assertIsNotNone(house.territory_claim_id)

    def test_nearby_settlement_claims_do_not_overlap(self):
        other = Village()
        other.interaction_points = {"town_square_center": [(34, 30)]}
        self.world.villages.append(other)

        first_claim = self.world.ensure_settlement_territory(self.village)
        second_claim = self.world.ensure_settlement_territory(other)

        self.assertTrue(first_claim.claimed_tiles)
        first_tiles = set().union(*(claim.all_tiles() for claim in self.world.land_claims_by_id.values() if claim.settlement_id == self.village.id))
        other_tiles = set().union(*(claim.all_tiles() for claim in self.world.land_claims_by_id.values() if claim.settlement_id == other.id))
        self.assertFalse(first_tiles & other_tiles)

    def test_farmland_reservation_blocks_house_construction(self):
        farm = Building(20, 20, 8, 6, building_type="farm", category="agricultural_workplace")
        self.village.add_building(farm)
        self.world.buildings_by_id[farm.id] = farm
        self.world.ensure_settlement_territory(self.village)

        farm_claim = self.world.land_claims_by_id[farm.territory_claim_id]
        self.assertEqual(farm_claim.claim_type, "farm")
        self.assertIn((24, 24), farm_claim.claimed_tiles)

        blocked = self.world.place_construction_blueprint("house", 22, 22)
        self.assertIsNone(blocked)
        self.assertIsNone(self.world.get_blueprint_at(22, 22))

    def test_reserved_expansion_allows_future_construction_reservation(self):
        self.world.ensure_settlement_territory(self.village)
        reserved = self.world._expand_settlement_reserved_land(self.village, "house")
        tile = next(iter(reserved.reserved_tiles))

        blueprint = self.world.place_construction_blueprint("wooden_chair", tile[0], tile[1])

        self.assertIsNotNone(blueprint)
        claims = self.world.get_land_claims_at(tile[0], tile[1])
        self.assertTrue(any(claim.claim_type == "reserved_expansion" for claim in claims))
        self.assertTrue(any(claim.claim_type == "construction_reservation" for claim in claims))

    def test_farm_ranch_hunting_and_logging_claim_types_stay_distinct(self):
        farm = Building(5, 5, 8, 6, building_type="farm", category="agricultural_workplace")
        ranch = Building(27, 5, 8, 6, building_type="ranch", category="agricultural_workplace")
        lodge = Building(5, 27, 6, 5, building_type="hunting_lodge", category="commercial_workplace")
        mill = Building(27, 27, 6, 5, building_type="lumber_mill", category="commercial_workplace")
        for building in [farm, ranch, lodge, mill]:
            self.village.add_building(building)
            self.world.buildings_by_id[building.id] = building

        self.world.ensure_settlement_territory(self.village)

        claim_types = {
            self.world.land_claims_by_id[building.territory_claim_id].claim_type
            for building in [farm, ranch, lodge, mill]
        }
        self.assertIn("farm", claim_types)
        self.assertIn("ranch", claim_types)
        self.assertIn("hunting", claim_types)
        self.assertIn("logging", claim_types)

    def test_settlement_growth_pressure_creates_reserved_expansion(self):
        house = Building(28, 28, 5, 5, building_type="house", category="residential")
        house.residents = [SimpleNamespace(), SimpleNamespace()]
        self.village.add_building(house)

        self.world.ensure_settlement_territory(self.village)
        reserved = self.world._expand_settlement_reserved_land(self.village, "house")

        self.assertIsNotNone(reserved)
        self.assertEqual(reserved.claim_type, "reserved_expansion")
        self.assertGreater(reserved.expansion_pressure, 0)
        self.assertTrue(reserved.reserved_tiles)

    def test_construction_planning_seeks_claim_valid_land_not_farm(self):
        farm = Building(20, 20, 8, 6, building_type="farm", category="agricultural_workplace")
        house = Building(28, 28, 5, 5, building_type="house", category="residential")
        house.residents = [SimpleNamespace(), SimpleNamespace()]
        self.village.add_building(farm)
        self.village.add_building(house)
        self.world.ensure_settlement_territory(self.village)

        with patch.object(self.world, "_get_village_anchor_coords", return_value=(24, 24)):
            spot = self.world._find_valid_building_spot(self.village, 7, 7)

        self.assertIsNotNone(spot)
        footprint = self.world._claim_rect_tiles(spot[0], spot[1], 7, 7)
        farm_claim = self.world.land_claims_by_id[farm.territory_claim_id]
        self.assertFalse(footprint & farm_claim.claimed_tiles)

    def test_completed_building_keeps_territory_association(self):
        blueprint = self.world.place_construction_blueprint("workshop", 30, 30)
        blueprint.required_work = 10
        for item_key, qty in blueprint.required_materials.items():
            for _ in range(qty):
                blueprint.deposit_item_reference(ItemReference(item_key))
        blueprint.apply_work(10)
        self.world._complete_construction_blueprint(blueprint)

        workshop = next(building for building in self.village.buildings if building.building_type == "workshop")
        claim = self.world.land_claims_by_id[workshop.territory_claim_id]
        self.assertEqual(claim.claim_type, "business")
        self.assertEqual(claim.owner_id, workshop.id)
        self.assertEqual(workshop.settlement_id, self.village.id)

    def test_service_need_pressure_selects_workshop_and_reserves_land(self):
        vacant_house = Building(28, 28, 5, 5, building_type="house", category="residential")
        self.village.add_building(vacant_house)
        self.world.town_board.economic_needs.append(
            TownEconomicNeed(type="service", target_key="Blacksmith", settlement_id=self.village.id)
        )

        with patch.object(self.world, "_find_valid_building_spot", return_value=(15, 35)):
            self.world._plan_village_expansion(self.village)

        blueprint = self.world.get_blueprint_at(15, 35)
        self.assertIsNotNone(blueprint)
        self.assertEqual(blueprint.target_build, "workshop")
        claim = self.world.land_claims_by_id[blueprint.territory_claim_id]
        self.assertEqual(claim.claim_type, "construction_reservation")

    def test_claim_hover_summary_reports_territory_type(self):
        claim = self.world.create_land_claim(
            "ranch",
            {(12, 12)},
            owner_type="building",
            owner_id="ranch-1",
            settlement_id=self.village.id,
        )

        self.assertIsNotNone(claim)
        self.assertEqual(self.world.get_land_claim_summary(12, 12), "Pasture claim")


if __name__ == "__main__":
    unittest.main()
