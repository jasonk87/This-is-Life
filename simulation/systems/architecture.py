from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import random

@dataclass
class FurnitureRole:
    id: str
    placement_type: str  # 'wall', 'center', 'corner', 'near_other', 'any'
    spacing_rules: int = 0
    adjacency_preferences: List[str] = field(default_factory=list)

@dataclass
class RoomArchetype:
    id: str
    min_size: int  # minimum area
    required_furniture_roles: List[str] = field(default_factory=list)
    optional_furniture_roles: List[str] = field(default_factory=list)
    placement_rules: Dict[str, str] = field(default_factory=dict)

@dataclass
class BlueprintVariant:
    id: str
    width: int
    height: int
    room_types: List[str] = field(default_factory=list)
    optional_room_types: List[str] = field(default_factory=list)
    fenced_yard_size: int = 0
    attachments: List[str] = field(default_factory=list)

@dataclass
class BuildingArchetype:
    id: str
    category: str
    size_range: Tuple[int, int]  # (min_footprint_area, max_footprint_area)
    room_types: List[str] = field(default_factory=list)  # required room types
    optional_room_types: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    variants: List[BlueprintVariant] = field(default_factory=list)

    def get_variant(self, wealth_tier: str) -> BlueprintVariant:
        if not self.variants:
            # Fallback to a default variant if none are defined
            width = int(self.size_range[0] ** 0.5)
            height = int(self.size_range[0] / width)
            return BlueprintVariant("default", width, height, self.room_types, self.optional_room_types)

        # Try to find a variant matching the wealth tier by ID
        for variant in self.variants:
            if wealth_tier in variant.id:
                return variant

        # If no specific variant matches, try to find a generic one, or return the first
        for variant in self.variants:
            if "default" in variant.id or "base" in variant.id:
                return variant
        return self.variants[0]

# Global Registry
FURNITURE_ROLES = {
    "bed": FurnitureRole("bed", "wall", spacing_rules=1),
    "wooden_bed": FurnitureRole("wooden_bed", "wall", spacing_rules=1),
    "table": FurnitureRole("table", "center", spacing_rules=1, adjacency_preferences=["chair"]),
    "chair": FurnitureRole("chair", "near_other", adjacency_preferences=["table", "desk"]),
    "dresser": FurnitureRole("dresser", "wall"),
    "shelf": FurnitureRole("shelf", "wall"),
    "bookshelf": FurnitureRole("bookshelf", "wall"),
    "desk": FurnitureRole("desk", "wall", adjacency_preferences=["chair"]),
    "workbench": FurnitureRole("workbench", "wall"),
    "stone_anvil": FurnitureRole("stone_anvil", "wall"),
    "storage": FurnitureRole("storage", "corner"),
    "counter": FurnitureRole("counter", "center"),
    "fireplace": FurnitureRole("fireplace", "wall")
}

ROOM_ARCHETYPES = {
    "bedroom": RoomArchetype("bedroom", 9, ["wooden_bed", "dresser"], ["chair", "bookshelf", "shelf"]),
    "shared_sleeping": RoomArchetype("shared_sleeping", 16, ["bed", "bed", "storage"], ["chair"]),
    "dining": RoomArchetype("dining", 12, ["table", "chair", "chair"], ["fireplace", "shelf"]),
    "workshop": RoomArchetype("workshop", 15, ["workbench", "storage"], ["chair", "stone_anvil", "shelf"]),
    "clinic_room": RoomArchetype("clinic_room", 12, ["wooden_bed", "desk", "storage"], ["chair"]),
    "office": RoomArchetype("office", 9, ["desk", "chair", "storage"], ["bookshelf"]),
    "storage": RoomArchetype("storage", 6, ["storage", "storage"], ["shelf"]),
    "tavern_floor": RoomArchetype("tavern_floor", 25, ["counter", "table", "table", "chair", "chair"], ["fireplace"])
}

BUILDING_ARCHETYPES = {
    "shack": BuildingArchetype("shack", "residential", (16, 25), ["shared_sleeping"], [], ["poor"], [
        BlueprintVariant("shack_poor", 4, 4, ["shared_sleeping"], [], 1, [])
    ]),
    "house": BuildingArchetype("house", "residential", (36, 49), ["bedroom", "dining"], ["storage"], ["middle"], [
        BlueprintVariant("house_poor", 6, 6, ["bedroom", "dining"], [], 2, []),
        BlueprintVariant("house_middle", 7, 7, ["bedroom", "dining"], ["storage"], 3, []),
        BlueprintVariant("house_rich", 8, 8, ["bedroom", "dining"], ["storage"], 4, []),
    ]),
    "common_house": BuildingArchetype("common_house", "residential", (25, 49), ["shared_sleeping"], ["dining", "storage"], ["middle"], [
        BlueprintVariant("common_house_base", 6, 6, ["shared_sleeping"], ["dining", "storage"], 2, [])
    ]),
    "large_house": BuildingArchetype("large_house", "residential", (49, 81), ["bedroom", "bedroom", "dining"], ["storage", "office"], ["rich"], [
        BlueprintVariant("large_house_middle", 8, 8, ["bedroom", "bedroom", "dining"], ["storage"], 4, []),
        BlueprintVariant("large_house_rich", 10, 10, ["bedroom", "bedroom", "dining"], ["storage", "office"], 5, [])
    ]),
    "tavern": BuildingArchetype("tavern", "commercial", (49, 100), ["tavern_floor"], ["storage", "bedroom"], ["middle"], [
        BlueprintVariant("tavern_poor", 7, 7, ["tavern_floor"], ["storage"], 2, []),
        BlueprintVariant("tavern_middle", 9, 9, ["tavern_floor"], ["storage", "bedroom"], 3, []),
        BlueprintVariant("tavern_rich", 11, 11, ["tavern_floor"], ["storage", "bedroom"], 4, [])
    ]),
    "city_hall": BuildingArchetype("city_hall", "civic", (49, 81), ["office", "dining"], ["storage"], ["rich"], [
        BlueprintVariant("city_hall_base", 9, 9, ["office", "dining"], ["storage"], 5, [])
    ]),
    "guard_post": BuildingArchetype("guard_post", "civic", (25, 49), ["office"], ["storage"], ["middle"], [
        BlueprintVariant("guard_post_base", 6, 6, ["office"], ["storage"], 2, [])
    ]),
    "barracks": BuildingArchetype("barracks", "civic", (36, 64), ["shared_sleeping", "storage"], [], ["middle"], [
        BlueprintVariant("barracks_base", 8, 8, ["shared_sleeping", "storage"], [], 3, [])
    ]),
    "storage_building": BuildingArchetype("storage_building", "industrial", (25, 49), ["storage"], [], ["poor"], [
        BlueprintVariant("storage_building_base", 6, 6, ["storage"], [], 1, [])
    ]),
    "lumber_shed": BuildingArchetype("lumber_shed", "industrial", (25, 49), ["workshop"], ["storage"], ["poor"], [
        BlueprintVariant("lumber_shed_base", 6, 6, ["workshop"], ["storage"], 2, ["logs"])
    ]),
    "carpenter_shop": BuildingArchetype("carpenter_shop", "industrial", (36, 64), ["workshop"], ["storage"], ["middle"], [
        BlueprintVariant("carpenter_shop_base", 7, 7, ["workshop"], ["storage"], 3, ["lumber"])
    ]),
    "clinic": BuildingArchetype("clinic", "medical", (36, 64), ["clinic_room", "office"], ["storage"], ["middle"], [
        BlueprintVariant("clinic_base", 7, 7, ["clinic_room", "office"], ["storage"], 2, [])
    ])
}

FURNITURE_ANCHORS = {
    "bed": "sleep",
    "wooden_bed": "sleep",
    "chair": "eat", # social could also fit, but eat is common. Let's make sure it handles both or pick one primary. Let's stick to the prompt's suggestions if possible.
    "table": "eat",
    "workbench": "work",
    "stone_anvil": "work",
    "desk": "work",
    "storage": "storage",
    "bookshelf": "read",
    "counter": "social",
    "fireplace": "social"
}

ROOM_FALLBACK_ANCHORS = {
    "shared_sleeping": "sleep",
    "tavern_floor": "social",
    "dining": "eat",
    "workshop": "work",
    "clinic_room": "service"
}

@dataclass
class Room:
    x: int
    y: int
    w: int
    h: int
    room_type: str

@dataclass
class FunctionalAnchor:
    type: str
    x: int
    y: int
    tags: Dict[str, str] = field(default_factory=dict)

@dataclass
class GeneratedBuilding:
    footprint: Tuple[int, int, int, int]  # x, y, w, h
    rooms: List[Room]
    placed_furniture: List[Tuple[int, int, str]]  # (x, y, role_id)
    anchors: List[FunctionalAnchor] = field(default_factory=list)

def _is_occupied(x: int, y: int, occupied_tiles: set) -> bool:
    return (x, y) in occupied_tiles

def _is_wall(x: int, y: int, rx: int, ry: int, rw: int, rh: int) -> bool:
    # True if on the boundary of the room
    return x == rx or x == rx + rw - 1 or y == ry or y == ry + rh - 1

def _is_corner(x: int, y: int, rx: int, ry: int, rw: int, rh: int) -> bool:
    return (x == rx and y == ry) or \
           (x == rx and y == ry + rh - 1) or \
           (x == rx + rw - 1 and y == ry) or \
           (x == rx + rw - 1 and y == ry + rh - 1)

def _get_wealth_tier(tags: List[str]) -> str:
    if "poor" in tags:
        return "low"
    if "rich" in tags:
        return "high"
    return "mid"

def _get_building_identity_profile(building_type: str, category: str) -> Dict:
    """Returns a lightweight preference profile for visual identity."""
    # Defaults
    profile = {
        "room_bias": [],
        "furniture_bias": [],
        "density_bias": "mid",
        "clustering": "light"
    }

    if building_type == "tavern" or category == "commercial":
        profile["room_bias"] = ["tavern_floor", "dining"]
        profile["furniture_bias"] = ["table", "chair", "counter", "fireplace"]
        profile["density_bias"] = "high"
        profile["clustering"] = "tight"
    elif building_type == "clinic" or category == "medical":
        profile["room_bias"] = ["clinic_room", "office"]
        profile["furniture_bias"] = ["bed", "desk", "storage"]
        profile["density_bias"] = "low"
        profile["clustering"] = "spaced"
    elif category == "industrial":
        profile["room_bias"] = ["workshop", "storage"]
        profile["furniture_bias"] = ["workbench", "storage"]
        profile["density_bias"] = "mid"
        profile["clustering"] = "functional"
    elif category == "civic":
        profile["room_bias"] = ["office", "dining"]
        profile["furniture_bias"] = ["desk", "chair", "storage"]
        profile["density_bias"] = "mid"
        profile["clustering"] = "functional"
    elif category == "residential":
        profile["room_bias"] = ["bedroom", "dining"]
        profile["furniture_bias"] = ["bed", "table", "chair", "fireplace"]
        profile["density_bias"] = "mid"
        profile["clustering"] = "light"

    return profile

def place_furniture(room: Room, occupied_tiles: set, wealth_tier: str = "mid", profile: Dict = None) -> List[Tuple[int, int, str]]:
    placed = []
    archetype = ROOM_ARCHETYPES.get(room.room_type)
    if not archetype:
        return placed

    if profile is None:
        profile = {
            "furniture_bias": [],
            "density_bias": "mid",
            "clustering": "light"
        }

    # We need to preserve door access. Assume door is at center of one wall or just reserve inner boundary middle tiles.
    inner_doors = [
        (room.x + room.w // 2, room.y + 1),
        (room.x + 1, room.y + room.h // 2),
        (room.x + room.w // 2, room.y + room.h - 2),
        (room.x + room.w - 2, room.y + room.h // 2)
    ]
    for dx, dy in inner_doors:
        occupied_tiles.add((dx, dy))

    optional_furniture = archetype.optional_furniture_roles.copy()

    # Sort optional furniture based on profile bias
    optional_furniture.sort(key=lambda f: 0 if f in profile.get("furniture_bias", []) else 1)

    # Base wealth logic for slicing optional furniture
    slice_idx = len(optional_furniture)
    if wealth_tier == "low":
        slice_idx = 1 if optional_furniture else 0
    elif wealth_tier == "mid":
        slice_idx = len(optional_furniture) // 2 + 1

    # Density bias nudge (keep it strictly bounded)
    density_bias = profile.get("density_bias", "mid")
    if density_bias == "high" and wealth_tier != "high":
        slice_idx = min(len(optional_furniture), slice_idx + 1)
    elif density_bias == "low" and wealth_tier != "low":
        slice_idx = max(0, slice_idx - 1)

    optional_furniture = optional_furniture[:slice_idx]

    all_roles_to_place = archetype.required_furniture_roles + optional_furniture

    for role_id in all_roles_to_place:
        role = FURNITURE_ROLES.get(role_id)
        if not role:
            continue

        placed_pos = None
        candidates = []

        for y in range(room.y + 1, room.y + room.h - 1):
            for x in range(room.x + 1, room.x + room.w - 1):
                if _is_occupied(x, y, occupied_tiles):
                    continue

                # Check placement rules
                is_wall = _is_wall(x, y, room.x + 1, room.y + 1, room.w - 2, room.h - 2) # Inner wall
                is_corner = _is_corner(x, y, room.x + 1, room.y + 1, room.w - 2, room.h - 2)

                score = 0

                if role.placement_type == "wall" and is_wall:
                    score += 10
                elif role.placement_type == "center" and not is_wall:
                    score += 10
                    # Distance to center
                    cx, cy = room.x + room.w // 2, room.y + room.h // 2
                    score -= abs(cx - x) + abs(cy - y)
                elif role.placement_type == "center" and is_wall:
                    score += 1 # allow fallback
                elif role.placement_type == "corner" and is_corner:
                    score += 10
                elif role.placement_type == "near_other":
                    # Find nearest placed item of preference
                    min_dist = 999
                    for px, py, prole in placed:
                        if prole in role.adjacency_preferences:
                            dist = abs(px - x) + abs(py - y)
                            if dist < min_dist:
                                min_dist = dist

                    if wealth_tier == "high" and min_dist < 4:
                        score += 20 - min_dist
                    elif wealth_tier != "high" and min_dist < 3:
                        score += 15 - min_dist
                    else:
                        score += 1 # allow fallback
                else:
                    if role.placement_type == "any":
                        score += 1

                if score > 0:
                    # Apply clustering adjustments
                    clustering = profile.get("clustering", "light")
                    if placed:
                        # Distance to identical or related items
                        min_sim_dist = 999
                        for px, py, prole in placed:
                            # Related if same role, or both in the identity's biased furniture
                            if prole == role_id or (prole in profile.get("furniture_bias", []) and role_id in profile.get("furniture_bias", [])):
                                dist = abs(px - x) + abs(py - y)
                                if dist < min_sim_dist:
                                    min_sim_dist = dist

                        if min_sim_dist != 999:
                            if clustering == "tight":
                                if min_sim_dist < 3:
                                    score += 2  # Encourage clustering
                            elif clustering == "spaced":
                                if min_sim_dist < 3:
                                    score -= 3  # Discourage clustering
                                elif min_sim_dist >= 3:
                                    score += 1  # Encourage spacing
                            elif clustering == "functional":
                                # Group work/storage items
                                if role_id in ["workbench", "storage", "desk"] and min_sim_dist < 6:
                                    score += 3

                    # Minor coordinate-based deterministic tie-breaker or scatter
                    tie_breaker = ((x * 7 + y * 3) % 5) / 10.0
                    if wealth_tier == "low":
                        score -= tie_breaker # slightly looser
                    elif wealth_tier == "high":
                        score += tie_breaker # slightly different tie-breaker behavior

                    candidates.append((score, x, y))

        if candidates:
            # Sort by score descending and take the best
            candidates.sort(key=lambda c: c[0], reverse=True)
            _, best_x, best_y = candidates[0]
            placed_pos = (best_x, best_y)
            placed.append((best_x, best_y, role_id))
            occupied_tiles.add((best_x, best_y))
            # Reserve spacing if any
            for dy in range(-role.spacing_rules, role.spacing_rules + 1):
                for dx in range(-role.spacing_rules, role.spacing_rules + 1):
                    occupied_tiles.add((best_x + dx, best_y + dy))

    return placed

def generate_building(building_type: str, x: int, y: int, w: int, h: int) -> GeneratedBuilding:
    archetype = BUILDING_ARCHETYPES.get(building_type)
    if not archetype:
        return GeneratedBuilding((x, y, w, h), [], [])

    # Determine wealth tier
    wealth_tier = _get_wealth_tier(archetype.tags)

    # Get identity profile
    profile = _get_building_identity_profile(building_type, archetype.category)

    # Bias and filter optional rooms
    optional_rooms = archetype.optional_room_types.copy()

    # Sort optional rooms based on profile bias
    optional_rooms.sort(key=lambda r: 0 if r in profile["room_bias"] else 1)

    if wealth_tier == "low":
        optional_rooms = [] # Skip optional rooms
    elif wealth_tier == "mid":
        optional_rooms = optional_rooms[:max(1, len(optional_rooms) // 2)]
    # high: try to fit all optional rooms

    all_rooms_to_place = archetype.room_types + optional_rooms

    # Partition into Rooms
    rooms = []
    available_space = [(x, y, w, h)]

    # Simple BSP-like generation prioritizing required rooms
    # We should make sure we only attempt to place required rooms if possible,
    # and not use up all the space with tiny fragments for optional rooms.
    for i, r_type in enumerate(all_rooms_to_place):
        room_arch = ROOM_ARCHETYPES.get(r_type)
        if not room_arch:
            continue

        space_idx = -1
        for j, space in enumerate(available_space):
            sx, sy, sw, sh = space
            if sw * sh >= room_arch.min_size and sw >= 3 and sh >= 3:
                space_idx = j
                break

        if space_idx != -1:
            sx, sy, sw, sh = available_space.pop(space_idx)

            # For the last required room (or if we don't have enough space to split), we might just take the whole space
            # Let's check how many rooms are left to place
            rooms_left = len(archetype.room_types) - i - 1
            if rooms_left <= 0:
                # We can just take the remaining space, no need to split if it's the last required or an optional room
                # (actually optional rooms might still want to split, but let's keep it simple for now)
                # Actually, better: if this is the only room left or space is too small to split into another min_size room
                pass

            # We want to make sure the remaining space can actually fit another room if we need one
            split_w, split_h = sw, sh

            # Determine split ratio based on wealth
            split_ratio = 0.5
            if wealth_tier == "low":
                # Deterministic uneven split based on coordinates
                split_ratio = 0.4 if (sx + sy) % 2 == 0 else 0.6
            elif wealth_tier == "high":
                split_ratio = 0.5 # Strictly balanced

            if sw >= sh and sw >= 6:
                # Split vertically
                split_w = max(3, int(sw * split_ratio))
                if split_w * sh < room_arch.min_size:
                    split_w = min(sw, max(3, int(room_arch.min_size / max(1, sh)) + 1))
            elif sh > sw and sh >= 6:
                # Split horizontally
                split_h = max(3, int(sh * split_ratio))
                if sw * split_h < room_arch.min_size:
                    split_h = min(sh, max(3, int(room_arch.min_size / max(1, sw)) + 1))

            if rooms_left <= 0:
                split_w, split_h = sw, sh

            # Force the dimensions if we didn't meet min size
            if split_w * split_h < room_arch.min_size:
                split_w, split_h = sw, sh # Give up and use the whole chunk

            rooms.append(Room(sx, sy, split_w, split_h, r_type))

            if sw - split_w >= 3:
                available_space.append((sx + split_w, sy, sw - split_w, sh))
            if sh - split_h >= 3:
                available_space.append((sx, sy + split_h, sw, sh - split_h))

    # Place Furniture
    placed_furniture = []
    occupied_tiles = set()

    for room in rooms:
        placed_furniture.extend(place_furniture(room, occupied_tiles, wealth_tier, profile))

    # Generate Anchors
    anchors = []
    anchors_per_room_instance: Dict[Tuple[int, int, int, int], set[str]] = {(r.x, r.y, r.w, r.h): set() for r in rooms}
    anchor_tile_counts: Dict[Tuple[int, int], Dict[str, int]] = {}

    for furn_x, furn_y, role_id in placed_furniture:
        anchor_type = FURNITURE_ANCHORS.get(role_id)
        if not anchor_type:
            continue

        # Find which room this furniture is in
        parent_room = None
        for r in rooms:
            if r.x <= furn_x < r.x + r.w and r.y <= furn_y < r.y + r.h:
                parent_room = r
                break

        # Prevent excessive duplicate anchors of the same type on the same tile
        tile_pos = (furn_x, furn_y)
        if tile_pos not in anchor_tile_counts:
            anchor_tile_counts[tile_pos] = {}

        if anchor_tile_counts[tile_pos].get(anchor_type, 0) < 1: # Max 1 per type per tile
            tags = {"role": role_id}
            if parent_room:
                tags["room_type"] = parent_room.room_type
                anchors_per_room_instance[(parent_room.x, parent_room.y, parent_room.w, parent_room.h)].add(anchor_type)

            anchors.append(FunctionalAnchor(type=anchor_type, x=furn_x, y=furn_y, tags=tags))
            anchor_tile_counts[tile_pos][anchor_type] = anchor_tile_counts[tile_pos].get(anchor_type, 0) + 1

    # Fallback Anchors for rooms
    for room in rooms:
        fallback_type = ROOM_FALLBACK_ANCHORS.get(room.room_type)
        if not fallback_type:
            continue

        room_instance_key = (room.x, room.y, room.w, room.h)
        if fallback_type not in anchors_per_room_instance[room_instance_key]:
            # No furniture anchor of this type in this room, place a fallback at the center
            center_x = room.x + room.w // 2
            center_y = room.y + room.h // 2

            # Simple bounds check just in case, though center should be inside
            if room.x <= center_x < room.x + room.w and room.y <= center_y < room.y + room.h:
                tags = {"room_type": room.room_type, "fallback": "true"}
                anchors.append(FunctionalAnchor(type=fallback_type, x=center_x, y=center_y, tags=tags))

    return GeneratedBuilding((x, y, w, h), rooms, placed_furniture, anchors)
