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
        self.last_speech_time = 0 # Timestamp of last speech

        # --- New attributes for Phase 1 Plan ---
        self.home_building_id = None
        self.work_building_id = None
        self.current_destination_coords = None  # (x, y) tuple
        self.current_path = []  # List of (x, y) tuples
        self.current_task = "idle"  # e.g., "idle", "going to work", "working", "going home"
        self.game_time_last_updated = 0 # To track in-game time for scheduling

    def get_dialogue(self):
        return self.dialogue