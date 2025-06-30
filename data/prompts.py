# data/prompts.py

# --- LLM Settings ---
OLLAMA_ENDPOINT = "http://192.168.86.30:11434"
OLLAMA_MODEL = "llama3.2:latest"

# --- LLM Prompts ---
LLM_PROMPTS = {
    "village_lore": "Generate a brief, atmospheric lore description for a fantasy village. Include its name, a unique characteristic, and a hint of its history or current struggles. Respond in a single paragraph.",
    "building_interior": """\
Generate a JSON object describing the interior decoration for a {building_type} of size {width}x{height} tiles.
The building is located in a village with the following characteristics:
Village Lore Summary: {village_lore_summary}

The primary inhabitants of this building are:
{inhabitant_details}
(Note: Inhabitant details include name, personality, wealth level (poor, average, wealthy), and profession.)

Available decoration items (choose from this list for the 'type' field): {decoration_items}.

Task:
Based on the building type, village lore, and especially the inhabitants' wealth, profession, and personality, generate a list of decorations.
- Wealth: 'Poor' inhabitants should have sparse, simple, possibly worn items. 'Wealthy' inhabitants can have more numerous, finer, or specialized items. 'Average' is in between.
- Profession: A blacksmith might have a small anvil or tool rack, a farmer might have sacks of grain or farming tools stored, a scholar might have more bookshelves.
- Personality: A 'grumpy' NPC might have a spartan, unkempt interior. A 'jovial' one might have a more welcoming, perhaps slightly cluttered space. A 'vain' one might have a mirror.
- Village Lore: If the lore mentions specific local crafts, dangers, or beliefs, try to subtly reflect that if an appropriate item exists (e.g., extra sturdy doors if lore mentions monsters, specific religious symbols if relevant and items exist).

For each decoration item, specify its:
- 'type': (must be one of the item names from the provided list)
- 'x': (integer, x-coordinate relative to building origin, from 0 to width-1)
- 'y': (integer, y-coordinate relative to building origin, from 0 to height-1)

Constraints:
- Ensure items do not overlap (occupy the same x,y coordinate).
- Ensure all item coordinates fit within the {width}x{height} bounds of the building's interior.
- Be realistic. A small hut for a poor farmer shouldn't be filled with lavish furniture.
- Do not place items on the exact border (x=0, x=width-1, y=0, y=height-1) if these are typically walls, unless the item is explicitly a wall-mounted item like a 'Wall Shelf' (which can be on y=1 to height-2, and x=1 to width-2, assuming it's not on the direct edge). Generally, keep items within the inner area.

Example Output:
{
  "decorations": [
    {"type": "bed_simple", "x": 1, "y": 1},
    {"type": "wooden_table", "x": 3, "y": 2},
    {"type": "wooden_chair", "x": 2, "y": 2}
  ]
}

JSON Output:
""",
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
  ],
  "combat_behavior": "defensive",
  "base_attack_name": "fists"
}

NPC Data:
Provide the following fields for the NPC:
- 'name'
- 'personality' (e.g., 'grumpy', 'jovial', 'shy', 'lawful', 'greedy')
- 'family_ties' (e.g., 'married to John', 'orphan', 'sibling of Jane')
- 'attitude_to_player' (e.g., 'friendly', 'suspicious', 'indifferent', 'hostile', 'admiring') - this should be influenced by player reputation.
- 'dialogue' (3-5 lines reflecting personality, attitude, and possibly reacting to player reputation)
- 'combat_behavior' (How they generally act in a fight: 'aggressive', 'defensive', 'cowardly', 'opportunist', 'avoids_combat') - should be consistent with personality.
- 'base_attack_name' (Their primary unarmed or simple attack name if forced into combat: e.g., 'fists', 'teeth', 'claws', 'kick', 'old rusty dagger', 'farming tool')

The player's current reputation is:
- Criminal Points: {player_criminal_points}
- Hero Points: {player_hero_points}

Hints for generation (use if provided, otherwise generate freely):
- Name Hint: {name_hint}
- Personality Hint: {personality_hint}
- Family Ties Hint: {family_ties_hint}
- Attitude Hint: {attitude_to_player_hint}

Make sure the entire output is a single JSON object.
Example of a full JSON structure to output (after filling in the values):
{
  "name": "Borin",
  "personality": "gruff but fair",
  "family_ties": "widower",
  "attitude_to_player": "neutral",
  "dialogue": [
    "What do you want?",
    "This village has seen better days, and worse.",
    "Don't cause trouble, and we'll get along fine."
  ],
  "combat_behavior": "defensive",
  "base_attack_name": "work hammer"
}
""",
    "npc_daily_goal": """\
You are an AI simulating the behavior of an NPC in a village.
NPC Name: {npc_name}
Personality: {npc_personality}
Current Task/State: {npc_current_task}
Current Location: Is the NPC at their home? {is_at_home}. Is the NPC at their workplace? {is_at_work}.
Job: Does the NPC have a job? {has_job}. If so, what kind of job? (e.g., Sheriff, Blacksmith, Farmer, Unemployed) {job_type}.
Time of Day: {time_of_day_str} (e.g., Early Morning, Morning, Midday, Afternoon, Evening, Night)
Current Light Level: {current_light_level_name} (e.g., DAY, NIGHT, DUSK, DAWN, DEEP_NIGHT)
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
If the NPC has a job and it's working hours (typically during DAY or DAWN/DUSK), they should prioritize "Go to work" unless already there.
If it's evening/night (especially DEEP_NIGHT or NIGHT light levels), they should prioritize "Go home" unless already there.
During dark light levels (NIGHT, DEEP_NIGHT), NPCs might be less inclined to "Wander the village" unless their job (e.g., Guard) or personality (e.g., restless, nefarious) suggests it. They might prefer "Stay put" if at a safe location like home.
Consider their personality: a lazy NPC might avoid work, a social one might wander more (but perhaps less so in pitch darkness).
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
    "npc_job_offer_lumber": """\
You are {npc_name}, the {npc_profession} of this village. Your personality is {npc_personality}.
Your current attitude towards the player is: {npc_attitude}.
Player Reputation: Criminal Points: {player_criminal_points}, Hero Points: {player_hero_points}.

The player is talking to you, and you have a job opportunity for them.
The job is to collect {quantity_needed} {item_name_plural}. You are offering {reward_amount} money for this task.

Based on your personality and attitude to the player, generate a short, in-character dialogue line offering this job.
Make it clear what is needed and what the reward is. End by asking if they accept (implicitly or explicitly).

Example: "Say, you look like you could use some work. I need {quantity_needed} {item_name_plural}. Bring them to me, and I'll pay you {reward_amount} coins. What do you say?"
Another Example (grumpy): "Don't just stand there. If you want to make yourself useful, fetch me {quantity_needed} {item_name_plural}. I'll give you {reward_amount}. Take it or leave it."

Job Offer Dialogue:
""",
    "action_lockpick_check": """\
You are an AI adjudicating a lockpicking attempt in a fantasy role-playing game.

Player's Lockpicking Skill (1-10, higher is better): {player_lockpicking_skill}
Lock's Difficulty (1-10, higher is harder): {lock_difficulty}

Task:
Determine if the lockpicking attempt is successful.
- Higher player skill relative to lock difficulty increases success chance.
- Lower player skill relative to lock difficulty decreases success chance.
- A skill much lower than difficulty should likely fail. A skill much higher should likely succeed.
- There should always be a small chance of failure even with high skill (e.g., a critical fumble, pick breaking) and a small chance of success even with low skill (beginner's luck), unless skill vs difficulty is extremely disparate.

Output Format (JSON):
Return a JSON object with the following fields:
- "success": boolean (true if the lock is picked, false otherwise)
- "narrative_feedback": string (A short, vivid description of the lockpicking attempt and its outcome. E.g., "With a soft *click*, the tumblers align and the lock springs open!", or "The tension is too much, and your lockpick snaps with a disheartening *twang*!", or "You jiggle the pick, but the lock remains stubbornly shut.")
- "lockpick_broken": boolean (true if the lockpick used for the attempt breaks, false otherwise. A pick might break on failure, or rarely even on success if the lock was particularly stubborn/rusty.)

Example Success:
{
  "success": true,
  "narrative_feedback": "You carefully manipulate the tumblers, feeling them give way one by one. With a final satisfying *thunk*, the lock opens!",
  "lockpick_broken": false
}

Example Failure (pick breaks):
{
  "success": false,
  "narrative_feedback": "You apply a bit too much pressure, and the delicate lockpick snaps in two! The lock remains closed.",
  "lockpick_broken": true
}

Example Failure (no break):
{
  "success": false,
  "narrative_feedback": "Despite your efforts, the intricate mechanism of the lock resists your attempts. It remains firmly shut.",
  "lockpick_broken": false
}

Adjudication:
""",
    "adjudicate_player_attack": """\
You are an AI adjudicating a player's melee attack in a fantasy role-playing game.

**Attacker (Player):**
- Weapon Used: {player_weapon_name} (e.g., "Stone Axe", "Fists", "Dagger")
- (Conceptual) Player's Melee Skill (1-10, higher is better): {player_melee_skill}

**Target (NPC):**
- Name: {npc_name}
- Toughness: {npc_toughness} (e.g., "frail", "average", "sturdy", "armored", "tough as nails")

**Task:**
Based on the attacker's weapon, conceptual skill, and the target's toughness, determine the outcome of the attack.
- A better weapon and higher skill should increase the chance to hit and the potential damage.
- Higher NPC toughness should decrease the chance to hit (if it implies agility/defense) or reduce damage taken.
- Fists should do minimal damage, a proper weapon more.
- Consider a degree of randomness in outcomes.

**Output Format (JSON):**
Return a JSON object with the following fields:
- "hit": boolean (true if the attack connects, false if it's a miss, dodge, or parry)
- "damage_dealt": integer (The amount of HP damage dealt. Can be 0 even on a hit if, for example, armor absorbs it all or it's a glancing blow. Should be 0 if "hit" is false.)
- "narrative_feedback": string (A short, vivid, in-character description of the attack action and its immediate result. Examples: "Your Stone Axe connects solidly with {npc_name}'s side, drawing a pained grunt!", "You swing your fists, but {npc_name} easily sidesteps the clumsy blow.", "The {player_weapon_name} glances off {npc_name}'s tough hide, doing little harm.")
- "target_status_change": string (For now, usually "none". Future options: "staggered", "bleeding", "knocked_down")

Example - Successful Hit:
{
  "hit": true,
  "damage_dealt": 7,
  "narrative_feedback": "Your Stone Axe bites deeply into {npc_name}'s shoulder!",
  "target_status_change": "none"
}

Example - Miss:
{
  "hit": false,
  "damage_dealt": 0,
  "narrative_feedback": "{npc_name} nimbly dodges your wild swing with the {player_weapon_name}.",
  "target_status_change": "none"
}

Example - Glancing Hit (low damage):
{
  "hit": true,
  "damage_dealt": 1,
  "narrative_feedback": "Your {player_weapon_name} skitters across {npc_name}'s defenses, barely scratching them.",
  "target_status_change": "none"
}

Adjudication Output:
""",
    "npc_combat_decision": """\
You are an AI determining an NPC's combat action in a fantasy game.

**NPC State:**
- Name: {npc_name}
- Personality: {npc_personality} (e.g., brave, cowardly, aggressive, defensive, tactical)
- Combat Behavior Trait: {npc_combat_behavior} (e.g., aggressive, defensive, cowardly, opportunist)
- Current Health: {npc_hp} out of {npc_max_hp} (e.g., 5/20)
- Has Healing Item: {has_healing_item} (boolean, e.g., true if has 'healing_salve')
- Current Task/Status: {npc_current_task}
- Base Attack Name: {npc_attack_name} (e.g., fists, rusty dagger, claws)
- Attack Range: {npc_attack_range} (e.g., 1 for melee)

**Target (Player) State:**
- Player is at ({player_x}, {player_y}). NPC is at ({npc_x}, {npc_y}).
- Distance to Player: {distance_to_player} (Manhattan distance for simplicity)
- Is Player within NPC's attack range? {player_in_attack_range} (boolean)
- Can the NPC currently see the Player? {can_see_player} (boolean)
- Player's Last Known Action (optional, if available): {player_last_action_desc} (e.g., "attacked me", "approached", "used item", "disappeared from sight")

**Available Actions for NPC:**
1.  "attack_player": If player is in range and NPC intends to fight.
2.  "move_to_attack_player": If player is not in range, but NPC intends to engage.
3.  "flee_from_player": If NPC wants to disengage and run away.
4.  "hold_position": If NPC is waiting, assessing, or being defensive without immediate action. (e.g., a guard holding a chokepoint, or a cautious NPC waiting for an opening).
5.  "move_to_cover": If NPC wants to find and move to a nearby position that offers better protection from the player.
6.  "use_healing_item": If NPC health is low and they possess a healing item.
7.  "use_ability": (Future placeholder - e.g., "cast_defensive_spell") - For now, default to other actions.

**Task:**
Based on the NPC's personality, combat behavior, health, possession of healing items, current situation relative to the player, and their attack capabilities, decide the MOST appropriate combat action.
- **Cowardly/Low Health:** More likely to "flee_from_player".
- **Aggressive/Brave:** More likely to "attack_player" or "move_to_attack_player".
- **Defensive:** Might "hold_position" or "attack_player" if a good opportunity arises.
- **Opportunist:** Might "flee_from_player" if outnumbered or low health, or "attack_player" if player is weak or distracted.
- If "attack_player" is chosen, the NPC must be able to make an attack (e.g., player in range AND can_see_player is true).
- If "move_to_attack_player" is chosen, the NPC should not already be in attack range AND can_see_player is true. If can_see_player is false, consider "hold_position" or "move_to_last_known_position" (if LKP available) or "search_area".
- If "flee_from_player", distance should ideally increase. This can be chosen even if player is not visible but threat is perceived.
- If "move_to_cover" is chosen, it implies the NPC is aware of potential cover (game will verify actual spots).
- If `has_healing_item` is true and NPC health is low (e.g., <40% of max_hp), "use_healing_item" is a strong candidate unless immediate danger prevents it (e.g., player right next to a frail NPC). It might be preferable to "move_to_cover" first, then "use_healing_item".
- If can_see_player is false, and the NPC is not fleeing or taking cover, "hold_position" or "search_area" (if available) are good defaults. An aggressive NPC might move towards where they last saw the player.

Respond with a JSON object containing the chosen action and a brief narrative for the NPC's thought process or intent.
Example: {"action": "move_to_attack_player", "narrative": "{npc_name} growls and charges towards the player!"}
Example: {"action": "flee_from_player", "narrative": "Seeing their injuries, {npc_name} decides to retreat!"}
Example: {"action": "attack_player", "narrative": "{npc_name} lashes out with their {npc_attack_name}!"}

JSON Output:
"""
,
    "adjudicate_npc_attack": """\
You are an AI adjudicating an NPC's melee attack against the player in a fantasy role-playing game.

**Attacker (NPC):**
- Name: {npc_name}
- Weapon Used: {weapon_name} (e.g., "Rusty Sword", "Fists", "Claws")
- Weapon Damage Info: {weapon_damage_description} (e.g., "1d6+1", "1d3")
- (Conceptual) NPC's Melee Skill/Ferocity (1-10, higher is better, derived from personality/role): {npc_melee_skill}

**Target (Player):**
- Player Health: {player_hp}/{player_max_hp}
- (Conceptual) Player's Defensive Capability (e.g., armor, agility - simplified as a general toughness for now): {player_toughness_desc} (e.g., "unarmored", "wearing leather", "heavily armored", "agile")

**Task:**
Based on the NPC's attack type, conceptual skill, and the player's current state/defense, determine the outcome of the attack.
- The specific {weapon_name} and its {weapon_damage_description} should heavily influence damage if the attack hits.
- Higher NPC skill/ferocity ({npc_melee_skill}) should increase hit chance and potentially damage.
- Higher player defense/toughness ({player_toughness_desc}) should decrease hit chance or reduce damage.
- Consider a degree of randomness in outcomes.

**Output Format (JSON):**
Return a JSON object with the following fields:
- "hit": boolean (true if the attack connects, false if it's a miss, dodge, or parry by the player)
- "damage_dealt": integer (The amount of HP damage dealt to the player. Can be 0 even on a hit. Should be 0 if "hit" is false.)
- "narrative_feedback": string (A short, vivid, in-character description of the NPC's attack action using {weapon_name} and its immediate result on the player. Examples: "{npc_name} lunges with their {weapon_name}, landing a solid blow on you!", "You deftly sidestep {npc_name}'s clumsy swing with their {weapon_name}.", "The {weapon_name} from {npc_name} scrapes against your armor, doing minimal damage.")
- "attacker_status_change": string (For now, usually "none". Future options for NPC: "overextended", "enraged")

Example - Successful Hit:
{
  "hit": true,
  "damage_dealt": 5,
  "narrative_feedback": "{npc_name} strikes you hard with their {weapon_name}!",
  "attacker_status_change": "none"
}

Example - Miss:
{
  "hit": false,
  "damage_dealt": 0,
  "narrative_feedback": "You manage to avoid {npc_name}'s telegraphed attack with their {weapon_name}.",
  "attacker_status_change": "none"
}

Adjudication Output:
"""
,
    "npc_item_pickup_decision": """\
You are an AI determining if an NPC should pick up a nearby item.

**NPC State:**
- Name: {npc_name}
- Personality: {npc_personality} (e.g., greedy, practical, curious, cautious, indifferent)
- Current Task: {npc_current_task}
- Current Inventory (summary): {npc_inventory_summary} (e.g., "Rusty Sword, 2 Healing Salves, 5 Gold")
- Currently Equipped Weapon: {npc_equipped_weapon_name}
- Currently Equipped Armor: {npc_equipped_armor_name}

**Perceived Items Nearby:**
A list of items the NPC can see on the ground. Each item is a dictionary:
{perceived_items_list_str}
Example for one item in the list:
  {{ "item_key": "rusty_sword", "name": "Rusty Sword", "quantity": 1, "distance": 3, "coords": [x,y] }}
  {{ "item_key": "healing_salve", "name": "Healing Salve", "quantity": 1, "distance": 2, "coords": [x,y] }}

**Task:**
Based on the NPC's personality, current inventory/equipment, and the perceived items, decide if the NPC should attempt to pick up ONE of the items.
- **Greedy/Opportunistic:** More likely to pick up valuable items or any usable gear.
- **Practical/Resourceful:** Might pick up useful tools, weapons if unarmed/under-equipped, or resources they need (if needs were tracked).
- **Cautious:** Might ignore items in dangerous areas or if already well-equipped.
- **Well-Equipped:** Less likely to pick up items worse than what they have.
- **Needs:** If the NPC needs a healing item (low health) and sees one, they should strongly consider it. (Assume low health implies a need for healing items if not directly stated).
- Prioritize items that are better than current equipment, or useful items like healing salves if low on them or injured.
- For now, the NPC will only decide to pick up *one item per decision cycle*. Choose the most compelling one if multiple are good.

**Output Format (JSON):**
If deciding to pick up an item:
  {{"action": "pickup_item", "target_coords": [x, y], "item_key_to_pickup": "item_key_string", "reasoning": "brief in-character thought"}}
If deciding to ignore all items for now:
  {{"action": "ignore_items", "reasoning": "brief in-character thought"}}

Example - Pickup:
{
  "action": "pickup_item",
  "target_coords": [15, 22],
  "item_key_to_pickup": "rusty_sword",
  "reasoning": "{npc_name} spots a sword. 'This could be useful,' they think."
}
Example - Ignore:
{
  "action": "ignore_items",
  "reasoning": "{npc_name} glances at the items but decides they have no need for them right now."
}

JSON Decision:
"""
}
