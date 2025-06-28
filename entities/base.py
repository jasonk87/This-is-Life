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

    def get_dialogue(self):
        return self.dialogue

    def take_damage(self, amount: int, world): # world is an instance of the World class from engine.py
        if self.is_dead:
            return

        self.hp -= amount
        # world.add_message_to_chat_log(f"{self.name} takes {amount} damage.") # This will be in the LLM narrative

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
            if not self.is_hostile_to_player:
                self.is_hostile_to_player = True
                world.add_message_to_chat_log(f"{self.name} becomes hostile!")