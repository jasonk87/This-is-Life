"""One-time possessions for newly generated villagers, not renderer costumes.

Only World.__init__ calls this. Loading a save, drawing, and ordinary ticks
must never manufacture replacement clothes. Existing equipment wins.
"""

import hashlib


def seed_starting_wardrobes(world):
    for actor in world.all_npcs:
        if getattr(actor, "animal_type", None) or getattr(
            actor, "_starting_wardrobe_seeded", False
        ):
            continue
        actor._starting_wardrobe_seeded = True
        seed = hashlib.blake2b(f"wardrobe:{actor.id}".encode(), digest_size=4).digest()
        wealth = getattr(actor.economic, "wealth_level", "average")
        poor = wealth in {"poor", "destitute"}
        choices = {
            "body": "cloth_tunic" if poor or seed[0] % 2 == 0 else "wool_shirt",
            "legs": "linen_trousers" if poor or seed[1] % 2 == 0 else "wool_trousers",
            "feet": "leather_shoes" if poor or seed[2] % 2 == 0 else "leather_boots",
        }
        if not poor and seed[3] % 4 == 0:
            choices["head"] = "wool_cap"
        for slot, key in choices.items():
            if actor.get_equipped_item_reference(slot) is not None:
                continue
            # Prefer something already owned. New possessions are made only
            # for this generation loadout, just like the existing guard gear.
            owned = [
                item
                for item in actor.economic.npc_inventory.iter_item_references()
                if item.equip_slot == slot
            ]
            item = max(owned, key=lambda candidate: candidate.evaluate_utility(), default=None)
            if item is None:
                actor.add_item(key, 1)
                item = actor.economic.npc_inventory.get_item_reference(key)
            actor.equip_item_reference(slot, item)
