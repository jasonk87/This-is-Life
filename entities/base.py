from config import DEFAULT_SPEECH_VOLUME
from data.items import ITEM_DEFINITIONS # For accessing armor properties

class NPC:
    def __init__(self, x, y, name="NPC", dialogue=None, personality="normal", family_ties="none", attitude_to_player="indifferent"):
        self.x = x
        self.y = y
        self.name = name
        self.char = ord('N') # Default character for NPC
        self.color = (0, 255, 0) # Green color for NPC
        self.dialogue = dialogue if dialogue is not None else ["Hello!"] # List of dialogue options
        self.personality = personality
        self.family_ties = family_ties
        self.attitude_to_player = attitude_to_player
        self.last_speech_time = 0

        # Scheduling attributes from Phase 1
        self.home_building_id = None
        self.work_building_id = None
        self.current_destination_coords = None
        self.current_path = []
        self.current_task = "idle"
        self.game_time_last_updated = 0

        # Contextual attributes for Phase 6
        self.wealth_level = "average"
        self.profession = "unemployed"
        self.original_char_before_sleep = self.char
        self.npc_inventory = {}

        # Combat Attributes (Phase 5.3)
        self.max_hp = 20  # Default max HP
        self.hp = self.max_hp
        self.toughness = "average"  # Descriptors: "frail", "average", "sturdy", "tough"
        self.is_hostile_to_player = False
        self.is_dead = False
        self.id = id(self) # Simple unique ID for now, can be replaced by uuid later if needed

        # Combat AI Attributes (Extending from Phase 5.3)
        self.combat_behavior = "defensive" # e.g., 'aggressive', 'defensive', 'cowardly', 'opportunist'
        self.base_attack_name = "fists"    # e.g., "claws", "bite", "rusty dagger"
        self.base_attack_damage_dice = "1d3" # e.g., "1d4", "1d6+1" (simple for now, can expand parsing later)
        self.attack_range = 1              # Typically 1 for melee
        self.target_entity_id = None       # ID of the entity this NPC is currently targeting (e.g., player's ID)

        # Auditory property
        self.speech_volume: int = DEFAULT_SPEECH_VOLUME

        # Equipment Slots (Usually None for simple creatures)
        self.equipped_weapon: str | None = None
        self.equipped_armor_body: str | None = None
        self.equipped_armor_head: str | None = None

        # Perception
        self.perceived_item_tiles: list[tuple[int,int]] = [] # Coords of tiles with items seen this tick
        self.task_target_item_details: dict | None = None # For tasks like picking up a specific item

        # Sub-Task State (for multi-step actions like professions)
        self.current_sub_task: str | None = None # e.g., "chop_trees", "haul_logs"
        self.sub_task_target_coords: tuple[int, int] | None = None # Specific global coords for the sub-task action
        self.sub_task_timer: int = 0 # Ticks remaining for the current sub-task's action phase
        self.sub_task_zone_target: str | None = None # General zone tag for pathing, e.g., "log_pile_area"
        self.current_sub_task_sequence_index: int = 0 # Index for current profession's sub-task sequence

        # Auditory Perception
        self.hearing_radius: int = DEFAULT_HEARING_RADIUS # Standard hearing range for NPCs

        # Note: self.current_task will be updated to include "attacking", "fleeing" as needed by the engine.

    def get_dialogue(self):
        return self.dialogue

    def take_damage(self, amount: int, world):
        if self.is_dead:
            return

        total_defense_bonus = 0
        # Check body armor
        if self.equipped_armor_body and self.equipped_armor_body in ITEM_DEFINITIONS:
            armor_def = ITEM_DEFINITIONS[self.equipped_armor_body]
            total_defense_bonus += armor_def.get("properties", {}).get("defense_bonus", 0)

        # Check head armor
        if self.equipped_armor_head and self.equipped_armor_head in ITEM_DEFINITIONS:
            armor_def = ITEM_DEFINITIONS[self.equipped_armor_head]
            total_defense_bonus += armor_def.get("properties", {}).get("defense_bonus", 0)

        effective_damage = max(0, amount - total_defense_bonus) # Ensure damage doesn't go below 0

        # world.add_message_to_chat_log(f"Debug: {self.name} incoming damage {amount}, defense {total_defense_bonus}, effective {effective_damage}")

        self.hp -= effective_damage

        if self.hp <= 0:
            self.hp = 0
            self.is_dead = True
            # The world.handle_npc_death(self) call will be made from where take_damage is called,
            # typically after the LLM has provided its narrative.
            # This keeps the NPC class from needing a direct 'world' reference for this specific action,
            # though for other interactions it might be useful.
            # For now, the death processing is handled by the World class after this method.
            # world.add_message_to_chat_log(f"{self.name} has died!") # This will also be part of LLM narrative or game logic
        else:
            # Non-fatal hit, NPC becomes hostile if not already
            if not self.is_hostile_to_player: # Only make non-hostiles hostile. Creatures might already be.
                self.is_hostile_to_player = True
                # Avoid "becomes hostile" message for creatures that are always hostile
                if self.profession != "Creature": # Assuming Creature profession for always-hostile
                    world.add_message_to_chat_log(f"{self.name} becomes hostile!")

class DireWolf(NPC):
    def __init__(self, x, y, name="Dire Wolf"):
        super().__init__(x, y, name=name)
        self.char = ord('w')
        self.color = (160, 160, 160) # Dark grey
        self.max_hp = 15
        self.hp = self.max_hp
        self.toughness = "average"
        self.is_hostile_to_player = True # Hostile by default
        self.combat_behavior = "aggressive"
        self.base_attack_name = "bite"
        self.base_attack_damage_dice = "1d6"
        self.attack_range = 1
        self.profession = "Creature" # To differentiate from villagers for AI/scheduling
        self.dialogue = ["*Growl*", "*Snarl*"] # Simple "dialogue"
        self.speech_volume = 5 # Quieter than human speech
        self.hearing_radius = DEFAULT_HEARING_RADIUS + 2 # Slightly better hearing