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
            "deer_pelt": {
                "chance": 0.8,
                "quantity": 1
            }
        },
        "tameable": True,
        "taming_difficulty": 5,
        "favorite_food": "apple",
        "rideable": True
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
            "wolf_pelt": {
                "chance": 0.9,
                "quantity": 1
            }
        }
    }
}
