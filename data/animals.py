"""
This file defines the properties of all animals in the game.
"""
ANIMAL_DEFINITIONS = {
    "deer": {
        "name": "Deer",
        "char": "d",
        "color": (205, 133, 63),
        "max_hp": 10,
        "behavior": "Wander-Flee",
        "hostile": False,
        "spawn_biomes": ["plains"],
        "spawn_chance": 0.001,
        "base_attack_name": "antlers",
        "base_attack_damage_dice": "1d4",
        "combat_behavior": "cowardly",
        "loot_drops": {
            "raw_venison": {
                "chance": 1.0,
                "quantity": [1, 3]
            },
            "animal_pelt": {
                "chance": 0.8,
                "quantity": 1
            }
        },
        "tameable": True,
        "taming_difficulty": 5,
        "favorite_food": "apple",
        "rideable": True,
        "can_mate": True,
        "mating_season": "Autumn",
        "gestation_period_days": 7,
        "predators": ["wolf", "dire_wolf", "bear"],
        "diet_type": "herbivore",
        "food_sources": ["Tall Grass", "Growing Wheat", "Flower"],
        "den_structure": "thicket"
    },
    "bear": {
        "name": "Bear",
        "char": "B",
        "color": (139, 69, 19),
        "max_hp": 30,
        "behavior": "Wander-Aggressive",
        "hostile": True,
        "spawn_biomes": ["plains", "mountain"],
        "spawn_chance": 0.0004,
        "base_attack_name": "maul",
        "base_attack_damage_dice": "2d6",
        "combat_behavior": "aggressive",
        "loot_drops": {
            "raw_meat": {
                "chance": 1.0,
                "quantity": [3, 6]
            },
            "animal_pelt": {
                "chance": 1.0,
                "quantity": [1, 2]
            }
        },
        "prey": ["deer", "sheep", "wolf"],
        "diet_type": "omnivore",
        "food_sources": ["raw_meat", "raw_fish", "raw_venison", "raw_mutton", "apple"],
        "den_structure": "bear_cave"
    },
    "fish": {
        "name": "Fish",
        "char": "f",
        "color": (0, 191, 255),
        "max_hp": 3,
        "behavior": "Wander-Water",
        "hostile": False,
        "spawn_biomes": ["water", "deep_water"],
        "spawn_chance": 0.002,
        "base_attack_name": "flop",
        "base_attack_damage_dice": "1d1",
        "combat_behavior": "cowardly",
        "loot_drops": {
            "raw_fish": {
                "chance": 1.0,
                "quantity": 1
            }
        },
        "diet_type": "herbivore",
        "food_sources": [] # Algae/insects implied
    },
    "wolf": {
        "name": "Wolf",
        "char": "w",
        "color": (169, 169, 169),
        "max_hp": 15,
        "hostile": True,
        "spawn_biomes": ["plains", "mountain"],
        "spawn_chance": 0.0005,
        "base_attack_name": "bite",
        "base_attack_damage_dice": "1d6",
        "combat_behavior": "aggressive",
        "loot_drops": {
            "animal_pelt": {
                "chance": 0.9,
                "quantity": 1
            },
            "raw_meat": {
                "chance": 0.5,
                "quantity": [1, 2]
            }
        },
        "prey": ["deer", "sheep", "rabbit"],
        "pack_animal": True,
        "diet_type": "carnivore",
        "food_sources": ["raw_meat", "raw_venison", "raw_mutton", "raw_fish"],
        "den_structure": "wolf_den"
    },
    "dire_wolf": {
        "name": "Dire Wolf",
        "char": "W",
        "color": (105, 105, 105),
        "max_hp": 25,
        "hostile": True,
        "spawn_biomes": ["mountain", "snow"],
        "spawn_chance": 0.00030000000000000003,
        "base_attack_name": "savage bite",
        "base_attack_damage_dice": "1d8",
        "combat_behavior": "aggressive",
        "prey": ["deer", "sheep", "wolf", "boar", "bison"],
        "fearless": True, # Will not flee from the player
        "loot_drops": {
            "animal_pelt": {
                "chance": 0.9,
                "quantity": [1, 2]
            },
            "raw_meat": {
                "chance": 0.7,
                "quantity": [2, 4]
            }
        },
        "diet_type": "carnivore",
        "food_sources": ["raw_meat", "raw_venison", "raw_mutton"],
        "den_structure": "wolf_den"
    },
    "sheep": {
        "name": "Sheep",
        "char": "s",
        "color": (255, 255, 240),
        "max_hp": 8,
        "behavior": "Wander-Flee",
        "hostile": False,
        "spawn_biomes": ["plains"],
        "spawn_chance": 0.001,
        "base_attack_name": "headbutt",
        "base_attack_damage_dice": "1d2",
        "combat_behavior": "cowardly",
        "loot_drops": {
            "raw_mutton": {
                "chance": 1.0,
                "quantity": [1, 2]
            }
        },
        "tameable": True,
        "taming_difficulty": 3,
        "favorite_food": "wheat",
        "rideable": False,
        "can_mate": True,
        "mating_season": "Spring",
        "gestation_period_days": 5,
        "shearable": {
            "item_yield": "raw_wool",
            "quantity": [1, 3],
            "regrowth_days": 7
        },
        "predators": ["wolf", "dire_wolf", "bear", "fox"],
        "diet_type": "herbivore",
        "food_sources": ["Tall Grass", "Growing Wheat", "Flower"],
        "den_structure": None # Domesticated/Wanders
    },
    "fox": {
        "name": "Fox",
        "char": "x",
        "color": (210, 105, 30),
        "max_hp": 8,
        "hostile": False,
        "behavior": "Wander-Flee",
        "spawn_biomes": ["plains"],
        "spawn_chance": 0.0008,
        "base_attack_name": "bite",
        "base_attack_damage_dice": "1d4",
        "combat_behavior": "cowardly",
        "loot_drops": {
            "animal_pelt": {
                "chance": 0.7,
                "quantity": 1
            }
        },
        "prey": ["sheep", "rabbit"],
        "diet_type": "carnivore",
        "food_sources": ["raw_meat", "raw_mutton", "raw_fish"],
        "den_structure": "fox_burrow"
    },
    "boar": {
        "name": "Boar",
        "char": "b",
        "color": (118, 85, 43),
        "max_hp": 12,
        "hostile": True,
        "behavior": "Wander-Aggressive",
        "spawn_biomes": ["plains"],
        "spawn_chance": 0.0006000000000000001,
        "base_attack_name": "tusk slash",
        "base_attack_damage_dice": "1d6",
        "combat_behavior": "aggressive",
        "loot_drops": {
            "raw_meat": {
                "chance": 1.0,
                "quantity": [2, 4]
            }
        },
        "diet_type": "omnivore",
        "food_sources": ["Tall Grass", "Growing Wheat", "Flower", "apple", "raw_meat"],
        "den_structure": "thicket"
    },
    "salmon": {
        "name": "Salmon",
        "char": "S",
        "color": (250, 128, 114),
        "max_hp": 4,
        "behavior": "Wander-Water",
        "hostile": False,
        "spawn_biomes": ["water", "deep_water"],
        "spawn_chance": 0.0015,
        "base_attack_name": "flop",
        "base_attack_damage_dice": "1d1",
        "combat_behavior": "cowardly",
        "loot_drops": {
            "raw_fish": {
                "chance": 1.0,
                "quantity": [1, 2]
            }
        }
    },
    "trout": {
        "name": "Trout",
        "char": "t",
        "color": (135, 206, 250),
        "max_hp": 3,
        "behavior": "Wander-Water",
        "hostile": False,
        "spawn_biomes": ["water"],
        "spawn_chance": 0.0018,
        "base_attack_name": "flop",
        "base_attack_damage_dice": "1d1",
        "combat_behavior": "cowardly",
        "loot_drops": {
            "raw_fish": {
                "chance": 1.0,
                "quantity": 1
            }
        }
    },
    "rabbit": {
        "name": "Rabbit",
        "char": "r",
        "color": (139, 119, 101),
        "max_hp": 4,
        "behavior": "Wander-Flee",
        "hostile": False,
        "spawn_biomes": ["plains"],
        "spawn_chance": 0.002,
        "base_attack_name": "bite",
        "base_attack_damage_dice": "1d1",
        "combat_behavior": "cowardly",
        "loot_drops": {
            "raw_meat": {
                "chance": 1.0,
                "quantity": 1
            }
        },
        "predators": ["fox", "wolf", "dire_wolf"],
        "diet_type": "herbivore",
        "food_sources": ["Tall Grass", "Growing Wheat", "Flower"],
        "den_structure": "rabbit_hole"
    },
    "bison": {
        "name": "Bison",
        "char": "O",
        "color": (160, 82, 45),
        "max_hp": 40,
        "behavior": "Wander-Neutral",
        "hostile": False,
        "spawn_biomes": ["plains"],
        "spawn_chance": 0.00030000000000000003,
        "base_attack_name": "gore",
        "base_attack_damage_dice": "2d6",
        "combat_behavior": "herd_defensive",
        "loot_drops": {
            "raw_meat": {
                "chance": 1.0,
                "quantity": [5, 10]
            },
            "animal_pelt": {
                "chance": 1.0,
                "quantity": [2, 3]
            }
        },
        "diet_type": "herbivore",
        "food_sources": ["Tall Grass", "Growing Wheat"],
        "den_structure": None # Migratory herd
    },
    "badger": {
        "name": "Badger",
        "char": "a",
        "color": (54, 54, 54),
        "max_hp": 15,
        "behavior": "Territorial",
        "hostile": False,
        "spawn_biomes": ["plains"],
        "spawn_chance": 0.0005,
        "base_attack_name": "claws",
        "base_attack_damage_dice": "1d6",
        "combat_behavior": "aggressive",
        "loot_drops": {
            "raw_meat": {
                "chance": 1.0,
                "quantity": [1, 2]
            },
            "animal_pelt": {
                "chance": 0.8,
                "quantity": 1
            }
        },
        "diet_type": "omnivore",
        "food_sources": ["raw_meat", "apple", "raw_fish"],
        "den_structure": "badger_sett"
    }
}
