# data/prompts.py

# --- LLM Settings ---
OLLAMA_ENDPOINT = "http://192.168.86.30:11434"
OLLAMA_MODEL = "llama3.2:latest"

# --- LLM Prompts ---
LLM_PROMPTS = {
    "village_lore": "Generate a brief, atmospheric lore description for a fantasy village. Include its name, a unique characteristic, and a hint of its history or current struggles. Respond in a single paragraph.",
    "building_interior": "Generate a JSON object describing the interior decoration of a {building_type} of size {width}x{height}. Include items from the following list: {decoration_items}. For each item, specify its 'type', 'x' (relative to building origin), 'y' (relative to building origin). Ensure items do not overlap and fit within the {width}x{height} bounds. Example: {\"decorations\": [{\"type\": \"bed\", \"x\": 1, \"y\": 1}, {\"type\": \"table\", \"x\": 3, \"y\": 2}]}.",
    "npc_personality": "Generate a JSON object for a fantasy NPC. Include 'name', 'personality' (e.g., 'grumpy', 'jovial', 'shy'), 'family_ties' (e.g., 'married to John', 'orphan', 'sibling of Jane'), 'attitude_to_player' (e.g., 'friendly', 'suspicious', 'indifferent'), and 3-5 lines of 'dialogue' that reflect their personality and attitude. If a name_hint, personality_hint, family_ties_hint, or attitude_to_player_hint is provided, incorporate it into the generation. Example: {\"name\": \"Elara\", \"personality\": \"wise\", \"family_ties\": \"elder of the village\", \"attitude_to_player\": \"helpful\", \"dialogue\": [\"Welcome, traveler. May your path be clear.\", \"The ancient trees whisper secrets to those who listen.\"]}.",
}
