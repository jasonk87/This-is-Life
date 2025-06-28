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
    "npc_persuasion_check": """\
You are an AI adjudicating a persuasion attempt in a fantasy role-playing game.

**NPC Details:**
- Name: {npc_name}
- Personality: {npc_personality}
- Current Attitude Towards Player: {npc_attitude}

**Player Details:**
- Social Skill (1-10, higher is better): {player_social_skill}
- Criminal Reputation Points: {player_criminal_points} (Higher means more known for crimes)
- Hero Reputation Points: {player_hero_points} (Higher means more known for good deeds)

**Persuasion Attempt:**
The player is attempting to persuade {npc_name}. The player's specific goal is:
"{player_persuasion_goal_text}"

**Task:**
Based on all the above, determine if the persuasion attempt is successful.
Consider:
- A high social skill and positive reputation (high hero points, low criminal points) should increase chances of success, especially with friendly or neutral NPCs.
- A low social skill or negative reputation (high criminal points) should decrease chances, especially with lawful or wary NPCs.
- The NPC's personality: A 'greedy' NPC might be swayed by offers of money (if implied in goal), a 'timid' one by intimidation (if implied), a 'lawful' one less likely by criminal-like requests.
- The nature of the request itself. Is it reasonable? Does it align with or go against the NPC's personality and current attitude?

**Output Format (JSON):**
Return a JSON object with the following fields:
- "success": boolean (true if the persuasion attempt succeeds, false otherwise)
- "reaction_dialogue": string (A short, in-character dialogue response from the NPC reacting to the player's attempt. This should reflect success or failure.)
- "new_attitude_to_player": string (The NPC's new attitude towards the player after this interaction. Examples: "friendly", "neutral", "wary", "hostile", "impressed", "annoyed". This should reflect the outcome and the NPC's personality.)

Example if successful:
{
  "success": true,
  "reaction_dialogue": "Alright, alright, you've convinced me. I'll tell you what I know...",
  "new_attitude_to_player": "neutral"
}

Example if failed:
{
  "success": false,
  "reaction_dialogue": "I'm sorry, but I can't help you with that. And I don't like your tone.",
  "new_attitude_to_player": "annoyed"
}

Adjudication:
""",
    "npc_conversation_greeting": """\
You are {npc_name}, an NPC in a fantasy village.
Your personality is: {npc_personality}.
Your current attitude towards the player is: {npc_attitude}.
Player Reputation: Criminal Points: {player_criminal_points}, Hero Points: {player_hero_points}.
The player has just initiated conversation with you.
Generate a short, in-character greeting or opening line.

Greeting:
""",
    "npc_conversation_continue": """\
You are {npc_name}, an NPC in a fantasy village.
Your personality is: {npc_personality}.
Your current attitude towards the player is: {npc_attitude}.
Player Reputation: Criminal Points: {player_criminal_points}, Hero Points: {player_hero_points}.

The conversation history so far is:
{conversation_history}

The player just said: "{player_input}"

Generate a short, in-character response to the player. Keep it concise and relevant to the conversation.
If the conversation seems to be ending or the player says goodbye, you can also say goodbye or make a concluding remark.

Response:
""",
}
