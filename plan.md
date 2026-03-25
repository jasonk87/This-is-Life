We have to be careful with `apply_conversation_topic` since it alters listener.
Wait, the simplest way is to find a group in `_continue_npc_conversation`, pick the *next speaker* and *next listener* from the group, apply the conversation topic, and then ensure that ALL members of the group receive the gossip/reflection.
Wait, if `A` talks to `B` (and `C`, `D` are nearby listeners):
`speaker = A`
`primary_listener = B`
`group_listeners = [C, D]`

We can modify `_continue_npc_conversation` in `engine.py` to:
1. Identify `nearby_participants` = `[p for p in self.village_npcs if not p.physical.is_dead and abs(p.x - speaker.x) + abs(p.y - speaker.y) <= 3 and (p.conversation_partner_id in (speaker.id, listener.id) or p.id == listener.id or (p.schedule.current_task in {"idle", "gathering_social", "socializing_at_focal_point", "following_target"} and random.random() < 0.3))]`
Wait, we need to limit to max 4 people (including speaker).
So `participants = [speaker, listener]`
`for p in self.village_npcs:`
  `if p not in participants and ...`
  `participants.append(p)`
  `if len(participants) == 4: break`

2. Then, pick the actual `speaker` and `listener` for this turn.
Wait, `_continue_npc_conversation` receives `speaker` and `listener` from the caller. The caller `update` loops over `conversing_npcs` and calls `_continue_npc_conversation(npc, partner)`. If it's `npc`'s turn, `npc` is the `speaker`. The `partner` is the `listener`.
BUT wait, what if `speaker` decides to talk to `C` instead of `listener`?
We can say:
```python
        # Select next listener from participants
        other_participants = [p for p in participants if p.id != speaker.id]
        if other_participants:
            listener = random.choice(other_participants)
```
Wait, if `listener` is changed, we need to update `apply_conversation_topic` to use the new `listener`.
And then we can apply gossip and reflections to EVERYONE in `other_participants`!
```python
        # In `_continue_npc_conversation` where it propagates:
        for p in other_participants:
            self.propagate_npc_harmful_incident_gossip(speaker, p)
            if goal == "reflection" or "reflection" in line (wait, we can just look at `topic_choice` if we have it):
                # Actually, in fallback, we don't have topic_choice.
```

Let's modify `select_conversation_topic` and `apply_conversation_topic` to accept `listeners: list[NPC]` instead of `listener`? No, "Do NOT create new dialogue framework. Only extend: existing conversation trigger logic, existing topic system."
Wait, if we pass a single `listener` to `select_conversation_topic`, it uses `shared_ticks = speaker.social.shared_experience_ticks.get(listener.id, 0)`.
What if we select the topic based on the max shared ticks among ALL `other_participants`?
"topic selection to consider: shared experiences between ANY participants, known incidents among the group, gossip propagation opportunities"

So we can modify `select_conversation_topic(world, speaker, listener, foundation_profile, group_listeners=None)`
```python
def select_conversation_topic(world, speaker, listener, foundation_profile, group_listeners=None) -> ConversationTopicChoice:
    group_listeners = group_listeners or []
    all_listeners = [listener] + [g for g in group_listeners if g.id != listener.id]

    relationship = float(getattr(getattr(speaker, "social", None), "relationships", {}).get(getattr(listener, "id", None), 50))
    for p in all_listeners:
        rel = float(getattr(getattr(speaker, "social", None), "relationships", {}).get(getattr(p, "id", None), 50))
        if rel > relationship: relationship = rel

    openness = float(getattr(foundation_profile, "openness", 0.5))
    shared_ticks = 0
    is_following = False
    for p in all_listeners:
        ticks = getattr(getattr(speaker, "social", None), "shared_experience_ticks", {}).get(getattr(p, "id", None), 0)
        if ticks > shared_ticks: shared_ticks = ticks
        if getattr(getattr(speaker, "social", None), "follow_target_id", None) == getattr(p, "id", None) or getattr(getattr(p, "social", None), "follow_target_id", None) == speaker.id:
            is_following = True

```
Wait, `apply_conversation_topic` can also take `group_listeners` to apply reflections to everyone!
```python
def apply_conversation_topic(world, speaker, listener, choice: ConversationTopicChoice, group_listeners=None) -> tuple[str, str]:
    group_listeners = group_listeners or []
    all_listeners = [listener] + [g for g in group_listeners if g.id != listener.id]
    # ...
    if topic in {"gossip", "report_incident"} and payload.get("incident_id"):
        for p in all_listeners:
            world.propagate_npc_harmful_incident_gossip(speaker, p)
        return ("Have you heard what happened recently?", "continue_conversation")
    if topic == "reflection":
        memory = payload.get("memory_text", "I've been thinking about old times.")
        for p in all_listeners:
            listener_memory = getattr(getattr(p, "knowledge", None), "long_term_memory", None)
            if isinstance(listener_memory, list):
                listener_memory.append(f"Heard from {speaker.name}: {memory}")
                if len(listener_memory) > 50:
                    del listener_memory[:-50]
            relationships = getattr(getattr(speaker, "social", None), "relationships", {})
            if getattr(p, "id", None) is not None:
                relationships[p.id] = min(100, relationships.get(p.id, 50) + 2)
        return (memory, "continue_conversation")
```
This requires minimal changes!

And for `_resolve_conversation_topic` in `engine.py`:
```python
    def _resolve_conversation_topic(self, speaker, listener, profile, group_listeners=None):
        topic_choice = self.select_conversation_topic(speaker, listener, profile, group_listeners=group_listeners)
        line, goal = apply_conversation_topic(self, speaker, listener, topic_choice, group_listeners=group_listeners)
        return line, (goal or topic_choice.goal or "continue_conversation"), topic_choice
```

Wait, `select_conversation_topic` is called from `world.select_conversation_topic`:
```python
    def select_conversation_topic(self, speaker, listener, foundation_profile, group_listeners=None):
        """Select structured conversation topic/content from simulation state."""
        return select_conversation_topic(self, speaker, listener, foundation_profile, group_listeners=group_listeners)
```

And where is `_continue_npc_conversation`?
```python
    def _continue_npc_conversation(self, speaker, listener):
        # Identify group
        group_participants = [speaker, listener]
        for p in self.village_npcs:
            if p.id not in (speaker.id, listener.id) and not p.physical.is_dead:
                if p.conversation_partner_id in (speaker.id, listener.id):
                    group_participants.append(p)
                elif abs(p.x - speaker.x) + abs(p.y - speaker.y) <= 3:
                    if p.schedule.current_task in {"idle", "gathering_social", "socializing_at_focal_point"}:
                        group_participants.append(p)
                    elif getattr(getattr(p, "social", None), "follow_target_id", None) in (speaker.id, listener.id):
                        group_participants.append(p)
            if len(group_participants) >= 4:
                break

        other_participants = [p for p in group_participants if p.id != speaker.id]
        if other_participants:
            # Rotate speaker/listener opportunistically
            # Guard may disengage if threat? Handled elsewhere, but let's just pick one
            # The speaker talks to one primary listener, but the whole group hears
            # We can optionally select a new listener randomly
            listener = random.choice(other_participants)

        profile = self.evaluate_conversation_foundation(speaker, listener)
        if not profile.can_start:
            # End for everyone
            for p in group_participants:
                p.conversation_partner_id = None
                p.current_conversation = []
            return

        if len(speaker.current_conversation) >= 6:
            if self._can_player_overhear(speaker):
                self.add_message_to_chat_log(f"You overhear {self.get_entity_display_name(speaker)} and the group wrap up their conversation.")
            for p in group_participants:
                p.conversation_partner_id = None
                p.current_conversation = []
                p.conversation_cooldown = random.randint(100, 200)
            return

        # LLM skip ...

        # update the fallback and resolution
            spoken_line, goal = self._fallback_npc_social_line(speaker, listener, group_listeners=other_participants)

            # update conversations
            speaker.current_conversation.append(f"{speaker.name}: {spoken_line}")
            for p in other_participants:
                if len(p.current_conversation) < len(speaker.current_conversation):
                    p.current_conversation.append(f"{speaker.name}: {spoken_line}")

            for p in other_participants:
                self.propagate_npc_harmful_incident_gossip(speaker, p)

            self._handle_npc_social_goal(speaker, listener, goal) # Wait, does this affect everyone?
            # actually we can let goal only affect speaker and listener.

            # Keep the group linked
            speaker.last_conversation_time = self.game_time
            for p in other_participants:
                p.last_conversation_time = self.game_time
                # Set their partner to speaker so next tick they might respond
                p.conversation_partner_id = speaker.id
            speaker.conversation_partner_id = listener.id
```

Wait, the LLM block also has fallback behavior if LLM fails, AND has `_can_player_overhear(speaker)`:
```python
        dialogue = self._poll_background_llm_task(task_key)
        ...
```
If we use LLM, `group_listeners` won't be in the prompt, but that's fine, we can just let LLM handle it as a 1-1, but broadcast the memory.
Wait! We also need to add `group_listeners` to `_fallback_npc_social_line`:
```python
    def _fallback_npc_social_line(self, speaker, listener, group_listeners=None) -> tuple[str, str]:
        profile = self.evaluate_conversation_foundation(speaker, listener)
        if not profile.can_start:
            ...
        line, topic_goal, _topic_choice = self._resolve_conversation_topic(speaker, listener, profile, group_listeners=group_listeners)
```
Wait, in `simulation/systems/conversation_topics.py`
```python
def select_conversation_topic(world, speaker, listener, foundation_profile, group_listeners=None) -> ConversationTopicChoice:
    group_listeners = group_listeners or []
    all_listeners = [listener] + [g for g in group_listeners if g.id != listener.id]

    relationship = float(getattr(getattr(speaker, "social", None), "relationships", {}).get(getattr(listener, "id", None), 50))
    openness = float(getattr(foundation_profile, "openness", 0.5))
    shared_ticks = getattr(getattr(speaker, "social", None), "shared_experience_ticks", {}).get(getattr(listener, "id", None), 0)
    is_following = getattr(getattr(speaker, "social", None), "follow_target_id", None) == getattr(listener, "id", None)

    for g in all_listeners:
        rel = float(getattr(getattr(speaker, "social", None), "relationships", {}).get(getattr(g, "id", None), 50))
        if rel > relationship: relationship = rel
        ticks = getattr(getattr(speaker, "social", None), "shared_experience_ticks", {}).get(getattr(g, "id", None), 0)
        if ticks > shared_ticks: shared_ticks = ticks
        if getattr(getattr(speaker, "social", None), "follow_target_id", None) == getattr(g, "id", None) or getattr(getattr(g, "social", None), "follow_target_id", None) == speaker.id:
            is_following = True
```
This is good!

Then in `apply_conversation_topic`:
```python
def apply_conversation_topic(world, speaker, listener, choice: ConversationTopicChoice, group_listeners=None) -> tuple[str, str]:
    group_listeners = group_listeners or []
    all_listeners = [listener] + [g for g in group_listeners if g.id != listener.id]

    topic = choice.topic_type
    payload = choice.payload or {}
    if topic == "greeting":
        return (f"Good to see you, {listener.name}.", "continue_conversation")
    if topic == "small_talk":
        subject = payload.get("kind", "the day")
        return (f"Strange {subject}, isn't it?", "continue_conversation")
    if topic in {"gossip", "report_incident"} and payload.get("incident_id"):
        for g in all_listeners:
            world.propagate_npc_harmful_incident_gossip(speaker, g)
        return ("Have you heard what happened recently?", "continue_conversation")
    if topic == "reflection":
        memory = payload.get("memory_text", "I've been thinking about old times.")
        for g in all_listeners:
            listener_memory = getattr(getattr(g, "knowledge", None), "long_term_memory", None)
            if isinstance(listener_memory, list):
                listener_memory.append(f"Heard from {speaker.name}: {memory}")
                if len(listener_memory) > 50:
                    del listener_memory[:-50]
            relationships = getattr(getattr(speaker, "social", None), "relationships", {})
            if getattr(g, "id", None) is not None:
                relationships[g.id] = min(100, relationships.get(g.id, 50) + 2)
        return (memory, "continue_conversation")
    if topic == "ask_info":
        location_name = payload.get("location_name")
        location_coords = payload.get("location_coords")
        if location_name and location_coords and hasattr(speaker, "knowledge"):
            speaker.knowledge.known_locations[location_name] = location_coords
            return (f"Thanks for the tip about the {location_name}.", "continue_conversation")
    if topic == "ask_favor":
        need = payload.get("need", "a hand")
        return (f"I could use {need}, if you're willing.", "continue_conversation")
    return ("Let's keep talking.", "continue_conversation")
```

Wait, `_continue_npc_conversation` in `engine.py` is very long and handles LLM too. We can just add the logic there.

Let's look at `_continue_npc_conversation` and see how to add group logic.
```python
    def _continue_npc_conversation(self, speaker, listener):
        # FIND GROUP
        group_participants = [speaker, listener]
        for p in self.village_npcs:
            if p.id in (speaker.id, listener.id) or p.physical.is_dead:
                continue
            # Join if already in conversation
            if p.conversation_partner_id in (speaker.id, listener.id):
                group_participants.append(p)
            # Or randomly join if nearby and idle/social/following
            elif abs(p.x - speaker.x) + abs(p.y - speaker.y) <= 3:
                # Is following one of them
                if getattr(getattr(p, "social", None), "follow_target_id", None) in (speaker.id, listener.id):
                    group_participants.append(p)
                # Or idle and wants to join
                elif p.schedule.current_task in {"idle", "gathering_social", "socializing_at_focal_point"} and random.random() < 0.2:
                    group_participants.append(p)
            if len(group_participants) >= 4:
                break

        other_participants = [p for p in group_participants if p.id != speaker.id]
        if other_participants:
            # Rotate speaker/listener opportunistically
            if random.random() < 0.5:
                listener = random.choice(other_participants)
```
Wait, we need to update the history for ALL participants!
```python
        if len(speaker.current_conversation) >= 6:
            if self._can_player_overhear(speaker):
                self.add_message_to_chat_log(f"You overhear {self.get_entity_display_name(speaker)} wrap up their conversation.")
            for p in group_participants:
                p.conversation_partner_id = None
                p.current_conversation = []
                p.conversation_cooldown = random.randint(100, 200)
            return
```
And then in LLM fallback:
```python
        spoken_line, goal = self._fallback_npc_social_line(speaker, listener, group_listeners=other_participants)
```
Wait, in `_continue_npc_conversation`, it has both fallback and LLM branches. We need to make sure we sync `current_conversation` correctly!
In the original code:
```python
        if not self._is_npc_llm_relevant_to_player(speaker, listener):
            self._cancel_background_llm_task(task_key)
            spoken_line, goal = self._fallback_npc_social_line(speaker, listener, group_listeners=other_participants)
            line_formatted = f"{speaker.name}: {spoken_line}"
            speaker.current_conversation.append(line_formatted)
            for p in other_participants:
                p.current_conversation = list(speaker.current_conversation)
                # propagate gossip inside _fallback_npc_social_line / apply_conversation_topic handles memory!
                # actually, propagate_npc_harmful_incident_gossip was explicitly called here:
                # self.propagate_npc_harmful_incident_gossip(speaker, listener)
                self.propagate_npc_harmful_incident_gossip(speaker, p)

            self._handle_npc_social_goal(speaker, listener, goal)
            speaker.last_conversation_time = self.game_time
            speaker.conversation_partner_id = listener.id
            for p in other_participants:
                p.last_conversation_time = self.game_time
                p.conversation_partner_id = speaker.id
            return
```
Wait, if LLM is enabled, it uses LLM!
```python
            if not spoken_line:
                spoken_line, goal = self._fallback_npc_social_line(speaker, listener, group_listeners=other_participants)

            if self._can_player_overhear(speaker):
                self.add_message_to_chat_log(
                    f"You overhear {self.get_entity_display_name(speaker)} tell {self.get_entity_display_name(listener)}: {spoken_line}"
                )
            line_formatted = f"{speaker.name}: {spoken_line}"
            speaker.current_conversation.append(line_formatted)
            for p in other_participants:
                p.current_conversation = list(speaker.current_conversation)
                self.propagate_npc_harmful_incident_gossip(speaker, p)

            self._handle_npc_social_goal(speaker, listener, goal)

            speaker.last_conversation_time = self.game_time
            speaker.conversation_partner_id = listener.id
            for p in other_participants:
                p.last_conversation_time = self.game_time
                p.conversation_partner_id = speaker.id
            return
```
Let's make sure we update the signature of `_fallback_npc_social_line`:
```python
    def _fallback_npc_social_line(self, speaker, listener, group_listeners=None) -> tuple[str, str]:
        profile = self.evaluate_conversation_foundation(speaker, listener)
        # ...
        line, topic_goal, _topic_choice = self._resolve_conversation_topic(speaker, listener, profile, group_listeners=group_listeners)
```

And `_resolve_conversation_topic`:
```python
    def _resolve_conversation_topic(self, speaker, listener, profile, group_listeners=None):
        topic_choice = self.select_conversation_topic(speaker, listener, profile, group_listeners=group_listeners)
        line, goal = apply_conversation_topic(self, speaker, listener, topic_choice, group_listeners=group_listeners)
        return line, (goal or topic_choice.goal or "continue_conversation"), topic_choice
```

Wait, `select_conversation_topic` uses `world.select_conversation_topic`, which calls `select_conversation_topic` in `conversation_topics.py`.
So we update `world.select_conversation_topic`:
```python
    def select_conversation_topic(self, speaker, listener, foundation_profile, group_listeners=None):
        return select_conversation_topic(self, speaker, listener, foundation_profile, group_listeners=group_listeners)
```

Also `apply_conversation_topic` requires `group_listeners=group_listeners`.

Let's do this carefully!
Wait, what if `speaker` is talking, and `listener` is chosen from `other_participants`.
What about `conversation_partner_id` assignments?
```python
        speaker.conversation_partner_id = listener.id
        for p in other_participants:
            p.conversation_partner_id = speaker.id
```
This forms a star! Everyone points to the speaker.
Then next tick, `update()` loops over `conversing_npcs` (`conversation_partner_id is not None`).
Wait! If `C.conversation_partner_id == speaker.id`, and `C`'s `last_conversation_time + 10 < game_time`, `C` will call `_continue_npc_conversation(C, speaker)`.
So `C` becomes the new speaker, and `speaker` becomes the listener.
BUT what about the others (like `B`, who was `listener`)?
`B`'s `conversation_partner_id == speaker.id`.
`B` might also trigger!
If `B` and `C` both trigger at the same time, we have a race condition where both speak.
But wait! `C.last_conversation_time` is updated when `speaker` talks!
```python
            speaker.last_conversation_time = self.game_time
            for p in other_participants:
                p.last_conversation_time = self.game_time
```
So their `last_conversation_time` is EXACTLY the same!
Next time, they all become eligible at the exact same tick!
If `B` is processed first in the `for npc in conversing_npcs` loop, `B` will talk to `A` (speaker).
When `B` talks, it updates `A` and `C`'s `last_conversation_time`!
So when the loop reaches `C` in the same tick, `C`'s `last_conversation_time` is NO LONGER `< game_time - 10`. It was just updated to `game_time`!
So `C` won't talk!
This naturally guarantees only ONE person talks next, rotating opportunistically based on list order.
Is this correct?
Let's trace:
1. `update()` loop: `conversing_npcs` = `[A, B, C]`.
2. `A` is processed. `A.last_conversation_time` is old. `A` talks. Updates `A, B, C` `last_conversation_time` to `T`.
3. `B` is processed. `B.last_conversation_time` is `T`. Does NOT talk.
4. `C` is processed. `C.last_conversation_time` is `T`. Does NOT talk.
Wait! In the FIRST place, `A` talks to `B`. Next time (at `T+11`), `update()` loop over `[A, B, C]`. Who is processed first?
If `conversing_npcs` is ordered, it might always be `A`!
Wait! `A`'s `conversation_partner_id` is `B`. `B`'s is `A`. `C`'s is `A`.
If `A` is processed first:
`A` calls `_continue_npc_conversation(A, B)`.
`A` rotates listener from `[B, C]`. Maybe `A` talks to `C`. Updates all to `T+11`.
If `A` is ALWAYS processed first, then `A` will ALWAYS be the speaker! That's not good. "rotate speakers opportunistically".
How to rotate?
If we want them to take turns, we can add a cooldown, or shuffle `conversing_npcs`!
```python
        conversing_npcs = [npc for npc in self.village_npcs if npc.conversation_partner_id is not None]
        random.shuffle(conversing_npcs) # Rotate naturally
        for npc in conversing_npcs:
```
Yes! If we shuffle `conversing_npcs` before iterating, anyone whose time is up might speak.
Wait, if `B` is processed first, `B` calls `_continue_npc_conversation(B, A)` (since `B`'s partner is `A`).
`B` becomes speaker, talks to `A` (or `C`). Everyone updates.
This works PERFECTLY and naturally!

Let's review the required changes:
1. `engine.py:World.update`:
In `engine.py`, find the block:
```python
        conversing_npcs = [npc for npc in self.village_npcs if npc.conversation_partner_id is not None]
        for npc in conversing_npcs:
```
Add `import random` if needed, and `random.shuffle(conversing_npcs)`. But wait, does `World.update()` have `random`? Yes, `import random` is at the top of `engine.py`.

2. `engine.py:World._continue_npc_conversation`:
Modify it to dynamically form groups, select a listener, propagate to all.

3. `simulation/systems/conversation_topics.py:select_conversation_topic` and `apply_conversation_topic`:
Add `group_listeners` and adjust max logic.

Let's check `_start_npc_socialization` in `engine.py`. Does it need changes?
```python
        partner = random.choice(weighted_partners or potential_partners)
        npc.conversation_partner_id = partner.id
        partner.conversation_partner_id = npc.id
```
If we leave it as is, it creates a 2-person group. Then when `_continue_npc_conversation` runs, others can join. This perfectly satisfies "allow 2-person conversations to expand".

Are there other places we need to touch?
Let's check `_resolve_conversation_topic` in `engine.py`:
```python
    def _resolve_conversation_topic(self, speaker, listener, profile, group_listeners=None):
        topic_choice = self.select_conversation_topic(speaker, listener, profile, group_listeners=group_listeners)
        line, goal = apply_conversation_topic(self, speaker, listener, topic_choice, group_listeners=group_listeners)
        return line, (goal or topic_choice.goal or "continue_conversation"), topic_choice
```

Wait, `apply_conversation_topic` also modifies `relationships` and `long_term_memory` for all participants.
Let's review how it's implemented.

```python
<<<<<<< SEARCH
def apply_conversation_topic(world, speaker, listener, choice: ConversationTopicChoice) -> tuple[str, str]:
    topic = choice.topic_type
    payload = choice.payload or {}
    if topic == "greeting":
        return (f"Good to see you, {listener.name}.", "continue_conversation")
    if topic == "small_talk":
        subject = payload.get("kind", "the day")
        return (f"Strange {subject}, isn't it?", "continue_conversation")
    if topic in {"gossip", "report_incident"} and payload.get("incident_id"):
        world.propagate_npc_harmful_incident_gossip(speaker, listener)
        return ("Have you heard what happened recently?", "continue_conversation")
    if topic == "reflection":
        memory = payload.get("memory_text", "I've been thinking about old times.")
        listener_memory = getattr(getattr(listener, "knowledge", None), "long_term_memory", None)
        if isinstance(listener_memory, list):
            listener_memory.append(f"Heard from {speaker.name}: {memory}")
            if len(listener_memory) > 50:
                del listener_memory[:-50]
        relationships = getattr(getattr(speaker, "social", None), "relationships", {})
        if getattr(listener, "id", None) is not None:
            relationships[listener.id] = min(100, relationships.get(listener.id, 50) + 2)
        return (memory, "continue_conversation")
    if topic == "ask_info":
        location_name = payload.get("location_name")
        location_coords = payload.get("location_coords")
        if location_name and location_coords and hasattr(speaker, "knowledge"):
            speaker.knowledge.known_locations[location_name] = location_coords
            return (f"Thanks for the tip about the {location_name}.", "continue_conversation")
    if topic == "ask_favor":
        need = payload.get("need", "a hand")
        return (f"I could use {need}, if you're willing.", "continue_conversation")
    return ("Let's keep talking.", "continue_conversation")
=======
def apply_conversation_topic(world, speaker, listener, choice: ConversationTopicChoice, group_listeners=None) -> tuple[str, str]:
    group_listeners = group_listeners or []
    all_listeners = [listener] + [g for g in group_listeners if g.id != getattr(listener, "id", None)]

    topic = choice.topic_type
    payload = choice.payload or {}
    if topic == "greeting":
        return (f"Good to see you, {listener.name}.", "continue_conversation")
    if topic == "small_talk":
        subject = payload.get("kind", "the day")
        return (f"Strange {subject}, isn't it?", "continue_conversation")
    if topic in {"gossip", "report_incident"} and payload.get("incident_id"):
        for g in all_listeners:
            world.propagate_npc_harmful_incident_gossip(speaker, g)
        return ("Have you heard what happened recently?", "continue_conversation")
    if topic == "reflection":
        memory = payload.get("memory_text", "I've been thinking about old times.")
        relationships = getattr(getattr(speaker, "social", None), "relationships", {})
        for g in all_listeners:
            listener_memory = getattr(getattr(g, "knowledge", None), "long_term_memory", None)
            if isinstance(listener_memory, list):
                listener_memory.append(f"Heard from {speaker.name}: {memory}")
                if len(listener_memory) > 50:
                    del listener_memory[:-50]
            if getattr(g, "id", None) is not None:
                relationships[g.id] = min(100, relationships.get(g.id, 50) + 2)
        return (memory, "continue_conversation")
    if topic == "ask_info":
        location_name = payload.get("location_name")
        location_coords = payload.get("location_coords")
        if location_name and location_coords and hasattr(speaker, "knowledge"):
            speaker.knowledge.known_locations[location_name] = location_coords
            return (f"Thanks for the tip about the {location_name}.", "continue_conversation")
    if topic == "ask_favor":
        need = payload.get("need", "a hand")
        return (f"I could use {need}, if you're willing.", "continue_conversation")
    return ("Let's keep talking.", "continue_conversation")
>>>>>>> REPLACE
```
This is perfect.

Next is `select_conversation_topic`:
```python
<<<<<<< SEARCH
def select_conversation_topic(world, speaker, listener, foundation_profile) -> ConversationTopicChoice:
    relationship = float(getattr(getattr(speaker, "social", None), "relationships", {}).get(getattr(listener, "id", None), 50))
    openness = float(getattr(foundation_profile, "openness", 0.5))
    shared_ticks = getattr(getattr(speaker, "social", None), "shared_experience_ticks", {}).get(getattr(listener, "id", None), 0)
    is_following = getattr(getattr(speaker, "social", None), "follow_target_id", None) == getattr(listener, "id", None)
=======
def select_conversation_topic(world, speaker, listener, foundation_profile, group_listeners=None) -> ConversationTopicChoice:
    group_listeners = group_listeners or []
    all_listeners = [listener] + [g for g in group_listeners if g.id != getattr(listener, "id", None)]

    relationship = 50.0
    shared_ticks = 0
    is_following = False

    for g in all_listeners:
        g_id = getattr(g, "id", None)
        rel = float(getattr(getattr(speaker, "social", None), "relationships", {}).get(g_id, 50))
        if rel > relationship:
            relationship = rel

        ticks = getattr(getattr(speaker, "social", None), "shared_experience_ticks", {}).get(g_id, 0)
        if ticks > shared_ticks:
            shared_ticks = ticks

        if getattr(getattr(speaker, "social", None), "follow_target_id", None) == g_id or \
           getattr(getattr(g, "social", None), "follow_target_id", None) == speaker.id:
            is_following = True

    openness = float(getattr(foundation_profile, "openness", 0.5))
>>>>>>> REPLACE
```
Next is `engine.py`.

In `update`:
```python
<<<<<<< SEARCH
        conversing_npcs = [npc for npc in self.village_npcs if npc.conversation_partner_id is not None]
        for npc in conversing_npcs:
            if npc.last_conversation_time + 10 < self.game_time:
=======
        conversing_npcs = [npc for npc in self.village_npcs if npc.conversation_partner_id is not None]
        random.shuffle(conversing_npcs)
        for npc in conversing_npcs:
            if npc.last_conversation_time + 10 < self.game_time:
>>>>>>> REPLACE
```

Then `_continue_npc_conversation` and `_fallback_npc_social_line`:

```python
<<<<<<< SEARCH
    def _fallback_npc_social_line(self, speaker, listener) -> tuple[str, str]:
        profile = self.evaluate_conversation_foundation(speaker, listener)
        if not profile.can_start:
            if profile.stance in {"fearful", "hostile"}:
                return ("I'd rather keep my distance.", "end_conversation")
            return ("Now isn't a good time.", "end_conversation")

        line, topic_goal, _topic_choice = self._resolve_conversation_topic(speaker, listener, profile)
=======
    def _fallback_npc_social_line(self, speaker, listener, group_listeners=None) -> tuple[str, str]:
        profile = self.evaluate_conversation_foundation(speaker, listener)
        if not profile.can_start:
            if profile.stance in {"fearful", "hostile"}:
                return ("I'd rather keep my distance.", "end_conversation")
            return ("Now isn't a good time.", "end_conversation")

        line, topic_goal, _topic_choice = self._resolve_conversation_topic(speaker, listener, profile, group_listeners=group_listeners)
>>>>>>> REPLACE

<<<<<<< SEARCH
    def _resolve_conversation_topic(self, speaker, listener, profile):
        """Select and apply a structured conversation topic payload."""
        topic_choice = self.select_conversation_topic(speaker, listener, profile)
        line, goal = apply_conversation_topic(self, speaker, listener, topic_choice)
        return line, (goal or topic_choice.goal or "continue_conversation"), topic_choice
=======
    def _resolve_conversation_topic(self, speaker, listener, profile, group_listeners=None):
        """Select and apply a structured conversation topic payload."""
        topic_choice = self.select_conversation_topic(speaker, listener, profile, group_listeners=group_listeners)
        line, goal = apply_conversation_topic(self, speaker, listener, topic_choice, group_listeners=group_listeners)
        return line, (goal or topic_choice.goal or "continue_conversation"), topic_choice
>>>>>>> REPLACE

<<<<<<< SEARCH
    def select_conversation_topic(self, speaker, listener, foundation_profile):
        """Select structured conversation topic/content from simulation state."""
        return select_conversation_topic(self, speaker, listener, foundation_profile)
=======
    def select_conversation_topic(self, speaker, listener, foundation_profile, group_listeners=None):
        """Select structured conversation topic/content from simulation state."""
        return select_conversation_topic(self, speaker, listener, foundation_profile, group_listeners=group_listeners)
>>>>>>> REPLACE
```

In `_continue_npc_conversation`:
```python
<<<<<<< SEARCH
    def _continue_npc_conversation(self, speaker, listener):
        profile = self.evaluate_conversation_foundation(speaker, listener)
        if not profile.can_start:
            speaker.conversation_partner_id = None
            listener.conversation_partner_id = None
            speaker.current_conversation = []
            listener.current_conversation = []
            return
        if len(speaker.current_conversation) >= 6:
            if self._can_player_overhear(speaker):
                self.add_message_to_chat_log(f"You overhear {self.get_entity_display_name(speaker)} and {self.get_entity_display_name(listener)} wrap up their conversation.")
            speaker.conversation_partner_id = None
            listener.conversation_partner_id = None
            speaker.current_conversation = []
            listener.current_conversation = []
            speaker.conversation_cooldown = random.randint(100, 200)
            listener.conversation_cooldown = random.randint(100, 200)
            return

        event_summary = "the weather"
        if speaker.knowledge.known_events:
            event = random.choice(list(speaker.knowledge.known_events.values()))
            event_summary = event.description

        history = "\n".join(speaker.current_conversation)
        task_key = ("npc_conversation", speaker.id, listener.id)
        if not self._is_npc_llm_relevant_to_player(speaker, listener):
            self._cancel_background_llm_task(task_key)
            spoken_line, goal = self._fallback_npc_social_line(speaker, listener)
            speaker.current_conversation.append(f"{speaker.name}: {spoken_line}")
            listener.current_conversation.append(f"{speaker.name}: {spoken_line}")
            self.propagate_npc_harmful_incident_gossip(speaker, listener)
            self._handle_npc_social_goal(speaker, listener, goal)
            speaker.last_conversation_time = self.game_time
            listener.last_conversation_time = self.game_time
            listener.conversation_partner_id = speaker.id
            speaker.conversation_partner_id = listener.id
            return

        dialogue = self._poll_background_llm_task(task_key)
        if dialogue is BACKGROUND_LLM_PENDING:
            return
        if dialogue is not None:
            spoken_line = ""
            goal = "continue_conversation"
            if dialogue:
                response_json = self._parse_llm_json_object(dialogue)
                if response_json is not None:
                    spoken_line = response_json.get("response", "").strip()
                    goal = self._coerce_dialogue_goal_by_profile(profile, response_json.get("goal", "continue_conversation"))
                else:
                    spoken_line = dialogue.strip()

            if not spoken_line:
                spoken_line, goal = self._fallback_npc_social_line(speaker, listener)

            if self._can_player_overhear(speaker):
                self.add_message_to_chat_log(
                    f"You overhear {self.get_entity_display_name(speaker)} tell {self.get_entity_display_name(listener)}: {spoken_line}"
                )
            speaker.current_conversation.append(f"{speaker.name}: {spoken_line}")
            listener.current_conversation.append(f"{speaker.name}: {spoken_line}")
            self.propagate_npc_harmful_incident_gossip(speaker, listener)
            self._handle_npc_social_goal(speaker, listener, goal)

            speaker.last_conversation_time = self.game_time
            listener.last_conversation_time = self.game_time
            listener.conversation_partner_id = speaker.id
            speaker.conversation_partner_id = listener.id
            return

        prompt = LLM_PROMPTS["npc_npc_conversation"].format(
            speaker_name=speaker.name,
            speaker_personality=speaker.social.personality,
            speaker_profession=speaker.economic.profession,
            listener_name=listener.name,
            relationship_score=speaker.social.relationships.get(listener.id, 50),
            recent_event_summary=event_summary,
            conversation_history=history
        )
        self._submit_background_llm_task(task_key, prompt)
=======
    def _continue_npc_conversation(self, speaker, listener):
        group_participants = [speaker, listener]
        for p in self.village_npcs:
            if p.id in (speaker.id, listener.id) or p.physical.is_dead:
                continue
            if p.conversation_partner_id in (speaker.id, listener.id):
                group_participants.append(p)
            elif abs(p.x - speaker.x) + abs(p.y - speaker.y) <= 3:
                is_following = getattr(getattr(p, "social", None), "follow_target_id", None) in (speaker.id, listener.id)
                if is_following or (p.schedule.current_task in {"idle", "gathering_social", "socializing_at_focal_point"} and random.random() < 0.2):
                    group_participants.append(p)
            if len(group_participants) >= 4:
                break

        other_participants = [p for p in group_participants if p.id != speaker.id]
        if other_participants and random.random() < 0.5:
            listener = random.choice(other_participants)

        profile = self.evaluate_conversation_foundation(speaker, listener)
        if not profile.can_start:
            for p in group_participants:
                p.conversation_partner_id = None
                p.current_conversation = []
            return

        if len(speaker.current_conversation) >= 6:
            if self._can_player_overhear(speaker):
                self.add_message_to_chat_log(f"You overhear {self.get_entity_display_name(speaker)} and the group wrap up their conversation.")
            for p in group_participants:
                p.conversation_partner_id = None
                p.current_conversation = []
                p.conversation_cooldown = random.randint(100, 200)
            return

        event_summary = "the weather"
        if speaker.knowledge.known_events:
            event = random.choice(list(speaker.knowledge.known_events.values()))
            event_summary = event.description

        history = "\n".join(speaker.current_conversation)
        task_key = ("npc_conversation", speaker.id, listener.id)
        if not self._is_npc_llm_relevant_to_player(speaker, listener):
            self._cancel_background_llm_task(task_key)
            spoken_line, goal = self._fallback_npc_social_line(speaker, listener, group_listeners=other_participants)
            line_formatted = f"{speaker.name}: {spoken_line}"
            speaker.current_conversation.append(line_formatted)
            for p in other_participants:
                p.current_conversation = list(speaker.current_conversation)

            self._handle_npc_social_goal(speaker, listener, goal)

            speaker.last_conversation_time = self.game_time
            speaker.conversation_partner_id = listener.id
            for p in other_participants:
                p.last_conversation_time = self.game_time
                p.conversation_partner_id = speaker.id
            return

        dialogue = self._poll_background_llm_task(task_key)
        if dialogue is BACKGROUND_LLM_PENDING:
            return
        if dialogue is not None:
            spoken_line = ""
            goal = "continue_conversation"
            if dialogue:
                response_json = self._parse_llm_json_object(dialogue)
                if response_json is not None:
                    spoken_line = response_json.get("response", "").strip()
                    goal = self._coerce_dialogue_goal_by_profile(profile, response_json.get("goal", "continue_conversation"))
                else:
                    spoken_line = dialogue.strip()

            if not spoken_line:
                spoken_line, goal = self._fallback_npc_social_line(speaker, listener, group_listeners=other_participants)

            if self._can_player_overhear(speaker):
                self.add_message_to_chat_log(
                    f"You overhear {self.get_entity_display_name(speaker)} tell {self.get_entity_display_name(listener)}: {spoken_line}"
                )
            line_formatted = f"{speaker.name}: {spoken_line}"
            speaker.current_conversation.append(line_formatted)
            for p in other_participants:
                p.current_conversation = list(speaker.current_conversation)

            self._handle_npc_social_goal(speaker, listener, goal)

            speaker.last_conversation_time = self.game_time
            speaker.conversation_partner_id = listener.id
            for p in other_participants:
                p.last_conversation_time = self.game_time
                p.conversation_partner_id = speaker.id
            return

        prompt = LLM_PROMPTS["npc_npc_conversation"].format(
            speaker_name=speaker.name,
            speaker_personality=speaker.social.personality,
            speaker_profession=speaker.economic.profession,
            listener_name=listener.name,
            relationship_score=speaker.social.relationships.get(listener.id, 50),
            recent_event_summary=event_summary,
            conversation_history=history
        )
        self._submit_background_llm_task(task_key, prompt)
>>>>>>> REPLACE
```
Wait, in LLM fallback logic, `self.propagate_npc_harmful_incident_gossip(speaker, listener)` is missing now in `_continue_npc_conversation`?
Ah, if I removed `self.propagate_npc_harmful_incident_gossip(speaker, listener)` from `_continue_npc_conversation`, it is because it is already handled inside `apply_conversation_topic`!
Let's double check `apply_conversation_topic`:
```python
    if topic in {"gossip", "report_incident"} and payload.get("incident_id"):
        for g in all_listeners:
            world.propagate_npc_harmful_incident_gossip(speaker, g)
```
Yes, `apply_conversation_topic` handles it!
BUT wait! The LLM path DOES NOT call `_resolve_conversation_topic`!
In the LLM path, if `spoken_line` is from LLM, it DOES NOT call `apply_conversation_topic`!
If the LLM responds, it parses `spoken_line` and `goal`. It doesn't pick a `topic_choice` and apply it!
So in the LLM path, `propagate_npc_harmful_incident_gossip` is NOT CALLED!
Wait! In the original code, the LLM path explicitly called `self.propagate_npc_harmful_incident_gossip(speaker, listener)`!
```python
            speaker.current_conversation.append(f"{speaker.name}: {spoken_line}")
            listener.current_conversation.append(f"{speaker.name}: {spoken_line}")
            self.propagate_npc_harmful_incident_gossip(speaker, listener)
            self._handle_npc_social_goal(speaker, listener, goal)
```
So I DO NEED to add it back to the LLM path AND the non-LLM path (because if LLM is offline, `_fallback_npc_social_line` handles the memory, but `propagate_npc_harmful_incident_gossip` was previously still called explicitly)!
Wait, `apply_conversation_topic` handles `propagate_npc_harmful_incident_gossip` AND `long_term_memory` for `reflection`!
If `apply_conversation_topic` handles gossip propagation, why did the original code explicitly call `self.propagate_npc_harmful_incident_gossip(speaker, listener)`?
Let's check `_fallback_npc_social_line`:
```python
    def _fallback_npc_social_line(self, speaker, listener) -> tuple[str, str]:
        # ...
        line, topic_goal, _topic_choice = self._resolve_conversation_topic(speaker, listener, profile)
        return line, topic_goal
```
So `_fallback_npc_social_line` triggers `apply_conversation_topic` which DOES propagate gossip!
And then the caller `_continue_npc_conversation` ALSO propagated gossip!
```python
            spoken_line, goal = self._fallback_npc_social_line(speaker, listener)
            # ...
            self.propagate_npc_harmful_incident_gossip(speaker, listener)
```
This means it was propagated TWICE in the fallback case!
Wait, `propagate_npc_harmful_incident_gossip` in `world` (engine.py) is:
```python
    def propagate_npc_harmful_incident_gossip(self, speaker, listener, *, overhear_radius: int = 3) -> bool:
        """Let one NPC tell another about one incident, with nearby NPC overhearing."""
        return propagate_harmful_incident_gossip(self, speaker, listener, overhear_radius=overhear_radius)
```
It takes a single `speaker` and `listener` and uses an `overhear_radius`!
Ah! If it has an `overhear_radius`, it already broadcasts to nearby NPCs!
```python
def propagate_harmful_incident_gossip(world, speaker, listener, *, overhear_radius: int = 3) -> bool:
```
So `propagate_npc_harmful_incident_gossip` already broadcasts to `group_listeners` because they are within `overhear_radius` (which is 3, and group is distance <= 3)!
BUT `apply_conversation_topic` handles `reflection` memories too! Does `reflection` have an overhear radius? No!
```python
    if topic == "reflection":
        memory = payload.get("memory_text", "I've been thinking about old times.")
        listener_memory = getattr(getattr(listener, "knowledge", None), "long_term_memory", None)
        if isinstance(listener_memory, list):
            listener_memory.append(f"Heard from {speaker.name}: {memory}")
```
So modifying `apply_conversation_topic` to loop over `all_listeners` is STILL strictly better for `reflection` and other topics!
For `propagate_npc_harmful_incident_gossip`, since it already does an overhear check, calling it per listener is fine (it might be slightly redundant, but the inner logic of `propagate_harmful_incident_gossip` probably checks if they already know).

So to be safe, in `_continue_npc_conversation`, I SHOULD STILL call `propagate_npc_harmful_incident_gossip(speaker, p)` for the LLM path (since LLM path doesn't call `apply_conversation_topic`):
```python
            for p in other_participants:
                self.propagate_npc_harmful_incident_gossip(speaker, p)
```
And I will add this loop to BOTH the `_is_npc_llm_relevant_to_player` False branch AND the dialogue parsing branch!

So the plan is:
1. Modify `engine.py`: `World.update` to `random.shuffle(conversing_npcs)`
2. Modify `engine.py`: `World._continue_npc_conversation` to collect `group_participants` (up to 4), optionally rotate `listener` from them, and update state/conversations/propagation for ALL `other_participants`.
3. Modify `engine.py`: `_fallback_npc_social_line`, `_resolve_conversation_topic`, `select_conversation_topic` to accept `group_listeners=None`.
4. Modify `simulation/systems/conversation_topics.py`: `select_conversation_topic`, `apply_conversation_topic` to accept `group_listeners=None` and apply max stats and group wide knowledge propagation!

This exactly aligns with the prompt!

Let's do the execution via set_plan!
