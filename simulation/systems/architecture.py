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
class BuildingArchetype:
    id: str
    category: str
    size_range: Tuple[int, int]  # (min_footprint_area, max_footprint_area)
    room_types: List[str] = field(default_factory=list)  # required room types
    optional_room_types: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

# Global Registry
FURNITURE_ROLES = {
    "bed": FurnitureRole("bed", "wall", spacing_rules=1),
    "table": FurnitureRole("table", "center", spacing_rules=1, adjacency_preferences=["chair"]),
    "chair": FurnitureRole("chair", "near_other", adjacency_preferences=["table", "desk"]),
    "dresser": FurnitureRole("dresser", "wall"),
    "shelf": FurnitureRole("shelf", "wall"),
    "desk": FurnitureRole("desk", "wall", adjacency_preferences=["chair"]),
    "workbench": FurnitureRole("workbench", "wall"),
    "storage": FurnitureRole("storage", "corner"),
    "counter": FurnitureRole("counter", "center"),
    "fireplace": FurnitureRole("fireplace", "wall")
}

ROOM_ARCHETYPES = {
    "bedroom": RoomArchetype("bedroom", 9, ["bed", "dresser"], ["chair", "shelf"]),
    "shared_sleeping": RoomArchetype("shared_sleeping", 16, ["bed", "bed", "storage"], ["chair"]),
    "dining": RoomArchetype("dining", 12, ["table", "chair", "chair"], ["fireplace", "shelf"]),
    "workshop": RoomArchetype("workshop", 15, ["workbench", "storage"], ["chair", "shelf"]),
    "clinic_room": RoomArchetype("clinic_room", 12, ["bed", "desk", "storage"], ["chair"]),
    "office": RoomArchetype("office", 9, ["desk", "chair", "storage"], ["shelf"]),
    "storage": RoomArchetype("storage", 6, ["storage", "storage"], ["shelf"]),
    "tavern_floor": RoomArchetype("tavern_floor", 25, ["counter", "table", "table", "chair", "chair"], ["fireplace"])
}

BUILDING_ARCHETYPES = {
    "shack": BuildingArchetype("shack", "residential", (16, 25), ["shared_sleeping"], [], ["poor"]),
    "house": BuildingArchetype("house", "residential", (36, 49), ["bedroom", "dining"], ["storage"], ["middle"]),
    "common_house": BuildingArchetype("common_house", "residential", (25, 49), ["shared_sleeping"], ["dining", "storage"], ["middle"]),
    "large_house": BuildingArchetype("large_house", "residential", (49, 81), ["bedroom", "bedroom", "dining"], ["storage", "office"], ["rich"]),
    "tavern": BuildingArchetype("tavern", "commercial", (49, 100), ["tavern_floor"], ["storage", "bedroom"], ["middle"]),
    "city_hall": BuildingArchetype("city_hall", "civic", (49, 81), ["office", "dining"], ["storage"], ["rich"]),
    "guard_post": BuildingArchetype("guard_post", "civic", (25, 49), ["office"], ["storage"], ["middle"]),
    "barracks": BuildingArchetype("barracks", "civic", (36, 64), ["shared_sleeping", "storage"], [], ["middle"]),
    "storage_building": BuildingArchetype("storage_building", "industrial", (25, 49), ["storage"], [], ["poor"]),
    "lumber_shed": BuildingArchetype("lumber_shed", "industrial", (25, 49), ["workshop"], ["storage"], ["poor"]),
    "carpenter_shop": BuildingArchetype("carpenter_shop", "industrial", (36, 64), ["workshop"], ["storage"], ["middle"]),
    "clinic": BuildingArchetype("clinic", "medical", (36, 64), ["clinic_room", "office"], ["storage"], ["middle"])
}

FURNITURE_ANCHORS = {
    "bed": "sleep",
    "chair": "eat", # social could also fit, but eat is common. Let's make sure it handles both or pick one primary. Let's stick to the prompt's suggestions if possible.
    "table": "eat",
    "workbench": "work",
    "desk": "work",
    "storage": "storage",
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

def place_furniture(room: Room, occupied_tiles: set, wealth_tier: str = "mid") -> List[Tuple[int, int, str]]:
    placed = []
    archetype = ROOM_ARCHETYPES.get(room.room_type)
    if not archetype:
        return placed

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
    if wealth_tier == "low":
        optional_furniture = optional_furniture[:1] if optional_furniture else []
    elif wealth_tier == "mid":
        optional_furniture = optional_furniture[:len(optional_furniture) // 2 + 1]
    # high: place all optional

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

    # Filter optional rooms by wealth tier
    optional_rooms = archetype.optional_room_types.copy()
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
        placed_furniture.extend(place_furniture(room, occupied_tiles, wealth_tier))

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
