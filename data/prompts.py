# data/prompts.py

# --- LLM Settings ---
OLLAMA_ENDPOINT = "http://192.168.86.30:11434"
OLLAMA_MODEL = "llama3.2:latest"

# --- LLM Prompts ---
LLM_PROMPTS = {
    "village_lore": "Generate a brief, atmospheric lore description for a fantasy village. Include its name, a unique characteristic, and a hint of its history or current struggles. Respond in a single paragraph.",
    # Updated list of decoration items for the building_interior prompt
    "building_interior": "Generate a JSON object describing the interior decoration of a {building_type} of size {width}x{height}. "
                         "Include items from the following list: {decoration_items}. "
                         "For each item, specify its 'type' (which must be one of the provided item names), "
                         "'x' (relative to building origin, 0 to width-1), "
                         "'y' (relative to building origin, 0 to height-1). "
                         "Ensure items do not overlap and fit within the {width}x{height} bounds. "
                         "Focus on common items appropriate for the building type. "
                         "Example: {\"decorations\": [{\"type\": \"wooden_chair\", \"x\": 1, \"y\": 1}, {\"type\": \"wooden_table\", \"x\": 3, \"y\": 2}]}.",
    "npc_personality": """\
Generate a JSON object for a fantasy NPC.
The NPC should have:
- 'name'
- 'personality' (e.g., 'grumpy', 'jovial', 'shy', 'lawful', 'greedy')
- 'family_ties' (e.g., 'married to John', 'orphan', 'sibling of Jane')
- 'attitude_to_player' (e.g., 'friendly', 'suspicious', 'indifferent', 'hostile', 'admiring')
- 3-5 lines of 'dialogue' that reflect their personality and attitude.

Consider the following information about the player when determining attitude and dialogue:
- Player Criminal Points: {player_criminal_points} (Higher means more notorious for crimes)
- Player Hero Points: {player_hero_points} (Higher means more renowned for heroic deeds)

A lawful or good-natured NPC might have a negative attitude towards a player with high criminal points.
A greedy or criminal NPC might be friendly or indifferent to a player with high criminal points.
Most NPCs would have a positive attitude towards a player with high hero points.
Incorporate any provided hints: name_hint, personality_hint, family_ties_hint, attitude_to_player_hint.

Example Output:
{
  "name": "Elara",
  "personality": "wise and lawful",
  "family_ties": "elder of the village",
  "attitude_to_player": "cautiously respectful",
  "dialogue": [
    "We've heard tales of your deeds, traveler. Some good, some... less so.",
    "Justice always finds its course.",
    "May your path be clear, provided it aligns with the village's well-being."
  ]
}

NPC Data:
""",
    "npc_daily_goal": """\
You are an AI simulating the behavior of an NPC in a village.
NPC Name: {npc_name}
Personality: {npc_personality}
Current Task/State: {npc_current_task}
Current Location: Is the NPC at their home? {is_at_home}. Is the NPC at their workplace? {is_at_work}.
Job: Does the NPC have a job? {has_job}. If so, what kind of job? (e.g., Sheriff, Blacksmith, Farmer, Unemployed) {job_type}.
Time of Day: {time_of_day_str} (e.g., Early Morning, Morning, Midday, Afternoon, Evening, Night)
Available Goals:
1.  "Go to work" (If they have a job and are not there during work hours)
2.  "Go home" (If it's late or they are done with work)
3.  "Wander the village" (For leisure or if no specific task)
4.  "Stay put" (If currently busy or content)
5.  "Socialize" (If near other NPCs, future feature)
6.  "Seek food/resources" (Future feature)

Based on all this context, what is the MOST LIKELY high-level goal for {npc_name} right now?
Respond with a JSON object containing the chosen goal, like: {"goal": "Chosen Goal"}
Example: {"goal": "Go to work"}
If the NPC should stay put or has no other pressing task, use "Stay put".
If the NPC has a job and it's working hours, they should prioritize "Go to work" unless already there.
If it's evening/night, they should prioritize "Go home" unless already there.
Consider their personality: a lazy NPC might avoid work, a social one might wander more.
---
Chosen Goal JSON:
""",
}
