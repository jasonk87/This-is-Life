ANIMAL_DEFINITIONS = {
    "deer": {
        "name": "Deer",
        "char": "d",
        "color": (205, 133, 63),
        "max_hp": 10,
        "behavior": "Wander-Flee",
        "hostile": False,
        "spawn_biomes": ["plains"],
        "spawn_chance": 0.01,
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
        "gestation_period_days": 7
    },
    "wolf": {
        "name": "Wolf",
        "char": "w",
        "color": (169, 169, 169),
        "max_hp": 15,
        "hostile": True,
        "spawn_biomes": ["plains", "mountain"],
        "spawn_chance": 0.005,
        "base_attack_name": "bite",
        "base_attack_damage_dice": "1d6",
        "combat_behavior": "aggressive",
        "loot_drops": {
            "animal_pelt": {
                "chance": 0.9,
                "quantity": 1
            },
            "raw_meat_scrap": {
                "chance": 0.5,
                "quantity": [1, 2]
            }
        }
    },
    "sheep": {
        "name": "Sheep",
        "char": "s",
        "color": (255, 255, 240),
        "max_hp": 8,
        "behavior": "Wander-Flee",
        "hostile": False,
        "spawn_biomes": ["plains"],
        "spawn_chance": 0.01,
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
        }
    }
}
