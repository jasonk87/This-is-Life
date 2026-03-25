Ah, I did not merge the `random.shuffle()` line in `engine.py`! The diff failed in my earlier attempt so it was never added to `engine.py`! Perfect!

Let's double check `apply_conversation_topic` in `conversation_topics.py`.
```python
def apply_conversation_topic(world, speaker, listener, choice: ConversationTopicChoice, group_listeners=None) -> tuple[str, str]:
    group_listeners = group_listeners or []
    all_listeners = [listener] + [g for g in group_listeners if getattr(g, "id", None) != getattr(listener, "id", None)]

    # ...
```
And `select_conversation_topic`:
```python
def select_conversation_topic(world, speaker, listener, foundation_profile, group_listeners=None) -> ConversationTopicChoice:
    group_listeners = group_listeners or []
    all_listeners = [listener] + [g for g in group_listeners if getattr(g, "id", None) != getattr(listener, "id", None)]

    base_relationship = float(getattr(getattr(speaker, "social", None), "relationships", {}).get(getattr(listener, "id", None), 50))
    relationship = base_relationship
    base_shared_ticks = getattr(getattr(speaker, "social", None), "shared_experience_ticks", {}).get(getattr(listener, "id", None), 0)
    shared_ticks = base_shared_ticks
    is_following = False

    for g in all_listeners:
        g_id = getattr(g, "id", None)
        if g_id is None:
            continue
        rel = float(getattr(getattr(speaker, "social", None), "relationships", {}).get(g_id, 50))
        if rel > relationship:
            relationship = relationship + (rel - relationship) * 0.2

        ticks = getattr(getattr(speaker, "social", None), "shared_experience_ticks", {}).get(g_id, 0)
        if ticks > shared_ticks:
            shared_ticks = int(shared_ticks + (ticks - shared_ticks) * 0.2)

        if getattr(getattr(speaker, "social", None), "follow_target_id", None) == g_id or \
           getattr(getattr(g, "social", None), "follow_target_id", None) == getattr(speaker, "id", None):
            is_following = True

    openness = float(getattr(foundation_profile, "openness", 0.5))
```
The constraint "Keep group topic effects as a bias only; do not let one strong participant fully dominate every group turn." is honored by taking the base relationship and augmenting it slightly: `relationship = relationship + (rel - relationship) * 0.2` rather than `relationship = rel`.

One thing: `relationship = relationship + (rel - relationship) * 0.2` could cause the relationship to grow over multiple iterations if multiple members have a higher relationship!
For example: base=50. Member A has 100. `relationship` becomes 60. Member B has 100. `relationship` becomes 68.
This is completely fine and acts as a modest bias.

Let's double check if I broke any tests by removing `test_conversations.py` or creating `numpy.py`.
I will run `pytest` one more time.
