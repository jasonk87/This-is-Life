# data/culture.py

CULTURES = {
    "default": {
        "name": "Commonwealth",
        "description": "A generic, balanced culture representing a fusion of different traditions.",
        "naming_scheme": {
            "village_prefixes": ["Green", "North", "West", "South", "East", "Clear", "Stag", "Elk", "Crow"],
            "village_suffixes": ["wood", "creek", "meadow", "field", "ford", "town", "stead", "brook", "vale"],
            "npc_male_first_names": ["John", "Mark", "Peter", "Paul", "James", "David", "Daniel", "Michael", "William"],
            "npc_female_first_names": ["Mary", "Sarah", "Jennifer", "Elizabeth", "Susan", "Linda", "Karen", "Nancy"],
            "npc_last_names": ["Smith", "Jones", "Williams", "Brown", "Davis", "Miller", "Wilson", "Moore", "Taylor"]
        },
        "building_styles": {
            "residential": {"wall": "wood_wall", "floor": "wood_floor", "roof": "thatch_roof"},
            "commercial": {"wall": "wood_wall", "floor": "stone_floor", "roof": "shingle_roof"},
            "industrial": {"wall": "stone_wall", "floor": "dirt_floor", "roof": "shingle_roof"},
            "civic": {"wall": "stone_wall", "floor": "stone_floor", "roof": "shingle_roof"},
        },
        "professions": {
            # Weights determine the likelihood of a profession appearing in a village
            "Farmer": 1.0,
            "Woodcutter": 1.0,
            "Miner": 0.5,
            "Blacksmith": 0.5,
            "Merchant": 0.7,
            "Guard": 0.3,
            "Sheriff": 0.1,
            "Tavern Keeper": 0.5
        },
        "lore_elements": {
            "origin_stories": [
                "Founded by settlers seeking fertile land, this village has a strong agricultural tradition.",
                "This village grew around a crossroads, becoming a hub for trade and travelers.",
                "Fleeing a distant war, the founders of this village sought a peaceful, secluded life."
            ],
            "struggles": [
                "harsh winters",
                "bandit raids",
                "a lingering plague",
                "a tyrannical local lord",
                "a rival neighboring village"
            ],
            "unique_characteristics": [
                "its unusually large marketplace",
                "a mysterious ancient ruin nearby",
                "a local legend about a hidden treasure",
                "its annual harvest festival",
                "the exceptionally potent ale brewed in its tavern"
            ]
        },
        "unique_buildings": []
    },
    "forest_folk": {
        "name": "Forest Folk",
        "description": "A reclusive, nature-worshipping culture that lives in harmony with the woods.",
        "naming_scheme": {
            "village_prefixes": ["Green", "Mossy", "Shadow", "Whisper", "Briar", "Oaken"],
            "village_suffixes": ["dell", "glade", "wood", "thicket", "grove", "copse"],
            "npc_male_first_names": ["Faelan", "Cassian", "Peregrin", "Ronan", "Silas", "Orion"],
            "npc_female_first_names": ["Elara", "Moira", "Seraphina", "Bronwyn", "Astrid", "Rowan"],
            "npc_last_names": ["Greenhand", "Swiftbow", "Oakenshield", "Shadowalker", "Whisperwind", "Thornfield"]
        },
        "building_styles": {
            "residential": {"wall": "log_wall", "floor": "wood_floor", "roof": "thatch_roof"},
            "commercial": {"wall": "log_wall", "floor": "wood_floor", "roof": "thatch_roof"},
            "industrial": {"wall": "wattle_and_daub_wall", "floor": "dirt_floor", "roof": "thatch_roof"},
            "civic": {"wall": "living_wood_wall", "floor": "mossy_stone_floor", "roof": "living_leaf_roof"},
        },
        "professions": {
            "Farmer": 0.3,
            "Woodcutter": 1.0,
            "Miner": 0.1,
            "Blacksmith": 0.2,
            "Merchant": 0.4,
            "Guard": 0.5,
            "Sheriff": 0.05,
            "Tavern Keeper": 0.6,
            "Herbalist": 0.8,
            "Hunter": 0.9
        },
        "lore_elements": {
            "origin_stories": [
                "Descended from ancient guardians of the forest, this village is hidden from the outside world.",
                "This village was founded by a druidic circle seeking to protect a sacred grove.",
                "The villagers made a pact with the spirits of the forest for protection and prosperity."
            ],
            "struggles": [
                "encroaching civilization",
                "a corruption spreading through the forest",
                "the wrath of a powerful forest spirit",
                "a rival tribe of beastmen",
                "a dwindling supply of rare herbs"
            ],
            "unique_characteristics": [
                "its houses built into the living trees",
                "a massive, ancient tree at the village center",
                "the eerie silence that pervades the area",
                "the glowing flora that illuminates the village at night",
                "the strange, musical language of the villagers"
            ]
        },
        "unique_buildings": ["moon_well", "herbalist_hut"]
    },
    "mountain_clan": {
        "name": "Mountain Clan",
        "description": "A hardy, resilient culture that carves its existence from the stone of the mountains.",
        "naming_scheme": {
            "village_prefixes": ["Stone", "Iron", "Glimmer", "Crag", "Boulder", "Peak"],
            "village_suffixes": ["hold", "fast", "breach", "delve", "heim", "gard"],
            "npc_male_first_names": ["Durin", "Borin", "Grom", "Thorin", "Balin", "Kili"],
            "npc_female_first_names": ["Helga", "Astrid", "Brunhilda", "Sigrid", "Ingrid", "Freya"],
            "npc_last_names": ["Stonehand", "Ironfist", "Deepdelver", "Axebreaker", "Hammerfall", "Grimgar"]
        },
        "building_styles": {
            "residential": {"wall": "stone_wall", "floor": "stone_floor", "roof": "shingle_roof"},
            "commercial": {"wall": "stone_wall", "floor": "stone_floor", "roof": "shingle_roof"},
            "industrial": {"wall": "hewn_stone_wall", "floor": "dirt_floor", "roof": "shingle_roof"},
            "civic": {"wall": "fortress_stone_wall", "floor": "polished_stone_floor", "roof": "slate_roof"},
        },
        "professions": {
            "Farmer": 0.1, # Limited farming in the mountains
            "Woodcutter": 0.3,
            "Miner": 1.0,
            "Blacksmith": 0.9,
            "Merchant": 0.4,
            "Guard": 0.8,
            "Sheriff": 0.2,
            "Tavern Keeper": 0.7,
            "Jeweler": 0.6,
            "Stonemason": 0.9
        },
        "lore_elements": {
            "origin_stories": [
                "Exiled from their ancestral mountain home, this clan seeks to reclaim their lost glory.",
                "This village was built around a rich vein of ore, its fortunes tied to the mountain's bounty.",
                "The clan claims descent from a mythical hero who tamed a dragon in these very mountains."
            ],
            "struggles": [
                "frequent monster attacks from deep tunnels",
                "a dwindling supply of food",
                "a bitter feud with a rival clan",
                "the constant threat of avalanches",
                "the greed of a powerful dragon"
            ],
            "unique_characteristics": [
                "its masterful stone carvings and architecture",
                "the constant echo of hammers from the forges",
                "a massive gate guarding the entrance to their mountain home",
                "the shimmering gems that adorn their halls",
                "the stoic, and untrusting nature of the clansfolk"
            ]
        },
        "unique_buildings": ["great_hall", "clan_forge"]
    }
}
