The code review found a critical functional failure:
In `_continue_npc_conversation`, the `listener` is randomly reassigned (50% chance) at the very top of the function.
Because this function is polled on every game tick while waiting for an asynchronous LLM task (via `_poll_background_llm_task`), the `listener` will continuously change mid-turn!
This modifies the `task_key = ("npc_conversation", speaker.id, listener.id)` and forces it to repeatedly submit new LLM tasks.

Ah! The function `_continue_npc_conversation` is called repeatedly if `last_conversation_time + 10 < game_time`.
If an LLM task is pending, `_poll_background_llm_task(task_key)` returns `BACKGROUND_LLM_PENDING` and the function returns.
Next tick, it is called AGAIN!
If `listener` is randomized at the top, `task_key` changes, and we submit a NEW task!

How to fix this?
We should ONLY randomize the `listener` if we are NOT currently waiting on an LLM task for the current speaker, OR we can just use `speaker.conversation_partner_id` which IS stable!
Wait, `speaker.conversation_partner_id` points to the PREVIOUS speaker (now the listener).
If we want to rotate the listener, we should update `speaker.conversation_partner_id` so it's stable!
But if we do it at the top of the function, we change the partner ID. But we only want to rotate the listener ONCE per conversational turn.
When does a turn start? A turn starts when `_continue_npc_conversation` is first called after the cooldown.
Wait, `_continue_npc_conversation` doesn't know if it's the "first" call of the turn or a "polling" call, EXCEPT by checking if there's already a pending LLM task!
Actually, `task_key` in the original code was `("npc_conversation", speaker.id, listener.id)`.
If we want to see if a task is pending for this speaker, we can check if *any* task is pending for this speaker? No, `_background_llm_tasks` is a dict keyed by `task_key`.

What if we store the chosen listener for the current turn?
Where? On the speaker!
`speaker.conversation_partner_id` ALREADY stores the listener!
When `_continue_npc_conversation` is called, `listener` is passed in as `partner = world.get_entity_by_id(npc.conversation_partner_id)`.
If we randomize `listener` at the top of `_continue_npc_conversation`, we could just do:
```python
        # Only rotate if we haven't already started a task for this turn.
        # But how do we know?
```
Wait, if we only randomize the listener *after* the turn completes?
At the END of `_continue_npc_conversation` (when `spoken_line` is added), we set:
```python
            speaker.last_conversation_time = self.game_time
            speaker.conversation_partner_id = next_listener.id
            for p in other_participants:
                p.last_conversation_time = self.game_time
                if p.id != next_listener.id:
                    p.conversation_partner_id = speaker.id
```
YES! We can select the `next_listener` for the NEXT turn at the end of the current turn!
Then `speaker.conversation_partner_id` will naturally point to the chosen next listener.
And when `update()` loop runs, it uses `npc.conversation_partner_id` to pass `listener` to `_continue_npc_conversation`.
So `listener` will be stable during the polling!
Wait, if `speaker` is A, and `listener` is B.
A talks to B. At the end of the turn, A becomes the listener for the next turn, and B becomes the speaker?
Wait, if A talks to B, next turn, B's `last_conversation_time` expires. `B` becomes the `speaker`. Who is B's listener?
At the end of A's turn, we set:
`B.conversation_partner_id = C.id` (randomly chosen from participants)!
Let's look at the original code at the end of the turn:
```python
            speaker.last_conversation_time = self.game_time
            speaker.conversation_partner_id = listener.id
            for p in other_participants:
                p.last_conversation_time = self.game_time
                if p.id != listener.id:
                    p.conversation_partner_id = speaker.id
```
Here, `other_participants` includes `listener` and others.
Wait, `other_participants = [p for p in group_participants if p.id != speaker.id]`.
If we do:
```python
            # Pick the NEXT speaker (who is currently one of the other_participants)
            # Actually, the "next speaker" is just anyone whose timer expires.
            # But they all expire at the same time. The first one processed in `update()` will speak.
            # But we can dictate who they speak TO.
```
Wait, in the original code, `p.conversation_partner_id = speaker.id` means ALL other participants will try to speak to `speaker` next time.
If we want to rotate, instead of having everyone point to `speaker`, they could point to someone else?
No, the problem is we did this at the top of `_continue_npc_conversation`:
```python
        other_participants = [p for p in group_participants if p.id != speaker.id]
        if other_participants and random.random() < 0.5:
            listener = random.choice(other_participants)
```
If we simply remove this rotation from the top, and instead do it at the END of the function, how does it work?
Wait, if `update()` calls `_continue_npc_conversation(npc, partner)`, `npc` is the speaker, `partner` is the listener.
The `partner` is determined by `npc.conversation_partner_id`.
If we want `npc` to speak to a random group member, we should set `npc.conversation_partner_id` to that random member BEFORE the turn starts!
When does the turn finish?
At the end of `_continue_npc_conversation`, when the text is generated and appended.
At this point, we set up the `conversation_partner_id` for everyone for the NEXT turn.
So:
```python
            next_speaker_candidates = other_participants # Anyone else could speak next
            # We don't know who will speak next, because `update()` iterates in random order.
            # So for each person `p` in `other_participants`, we can randomly pick THEIR next target!
            for p in other_participants:
                p.last_conversation_time = self.game_time
                # 50% chance to reply to the current speaker, 50% chance to talk to someone else in the group
                possible_targets = [g for g in group_participants if g.id != p.id]
                if possible_targets and random.random() < 0.5:
                    p.conversation_partner_id = random.choice(possible_targets).id
                else:
                    p.conversation_partner_id = speaker.id

            speaker.last_conversation_time = self.game_time
            # The current speaker might also speak again next time if they are processed first?
            # Sure, set their partner too
            possible_targets_for_speaker = [g for g in group_participants if g.id != speaker.id]
            if possible_targets_for_speaker:
                speaker.conversation_partner_id = random.choice(possible_targets_for_speaker).id
            else:
                speaker.conversation_partner_id = listener.id
```
YES! This sets up the `conversation_partner_id`s for the NEXT turn, which are stable until the next turn completes!
This completely avoids modifying `listener` mid-turn, keeps `task_key` stable, and still achieves opportunistic rotation!

Let's modify `engine.py` to remove the mid-turn rotation and instead rotate the `conversation_partner_id` at the end of the turn!
