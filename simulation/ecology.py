"""
Ecology simulation module.

Tracks regional resources like timber, forageables, and animal populations.
"""

class EcologySystem:
    def __init__(self):
        # Maps region_id -> resource_dict
        self.regional_resources = {}

    def _initialize_region(self, region):
        """Set up initial resources based on the region's biome."""
        resources = {"wood": 0, "forage": 0, "game": 0}

        # Simple biome-based resource assignment
        biome = getattr(region, "primary_biome", "plains")
        if biome == "forest":
            resources["wood"] = 1000
            resources["forage"] = 500
            resources["game"] = 200
        elif biome == "plains":
            resources["wood"] = 100
            resources["forage"] = 800
            resources["game"] = 100
        elif biome == "mountains":
            resources["wood"] = 200
            resources["forage"] = 100
            resources["game"] = 50

        self.regional_resources[region.id] = resources

    def get_resource_availability(self, world, region_id: str, resource_type: str) -> int:
        if region_id not in self.regional_resources:
            if hasattr(world, "atlas") and region_id in world.atlas.regions_by_id:
                self._initialize_region(world.atlas.regions_by_id[region_id])
            else:
                return 0
        return self.regional_resources[region_id].get(resource_type, 0)

    def consume_resource(self, world, region_id: str, resource_type: str, amount: int) -> int:
        """Attempt to consume a resource. Returns the actual amount consumed."""
        if region_id not in self.regional_resources:
            if hasattr(world, "atlas") and region_id in world.atlas.regions_by_id:
                self._initialize_region(world.atlas.regions_by_id[region_id])
            else:
                return 0

        available = self.regional_resources[region_id].get(resource_type, 0)
        consumed = min(available, amount)
        self.regional_resources[region_id][resource_type] -= consumed
        return consumed

    def process_tick(self, world) -> None:
        """Handle regeneration of resources over time."""
        # Regenerate resources periodically.
        # Assume this is called once per game day or similar macro-tick.
        if world.game_time % 1000 == 0:  # Adjust this interval as needed
            for region_id, resources in self.regional_resources.items():
                # Regrow resources up to a soft cap
                # These caps should ideally be defined by the biome in _initialize_region
                resources["wood"] += 5
                resources["forage"] += 10
                resources["game"] += 2

                # Prevent unbounded growth (simple caps for now)
                resources["wood"] = min(resources["wood"], 2000)
                resources["forage"] = min(resources["forage"], 1000)
                resources["game"] = min(resources["game"], 500)
