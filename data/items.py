# data/items.py

# --- Item Definitions ---
ITEM_DEFINITIONS = {
    "healing_salve": {
        "name": "Healing Salve",
        "description": "A simple paste that heals minor wounds.",
        "crafting_recipe": {
            "flower": 3  # Requires 3 flowers to craft
        },
        "on_use": {
            "heal_amount": 10
        }
    }
}
