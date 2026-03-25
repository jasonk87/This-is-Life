Let's see the current `_continue_npc_conversation`:
```python
    def _continue_npc_conversation(self, speaker, listener):
        group_participants = [speaker, listener]
        for p in self.village_npcs:
            if p.id in (speaker.id, listener.id) or p.physical.is_dead:
                continue

            # socially available check: urgent threat, flee, medical, higher-priority states
            if p.combat.is_hostile_to_player or getattr(p, "is_frightened", False):
                continue
            if p.schedule.current_task in {"fleeing_from_player", "avoiding_social_threat", "combat_action_flee_from_player", "attacking_player", "going_to_report_crime", "seeking_healer", "resting_in_bed"}:
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
                if p.conversation_partner_id == speaker.id or p.conversation_partner_id == listener.id or p.id in (speaker.id, listener.id):
                    p.conversation_partner_id = None
                    p.current_conversation = []
            return

        if len(speaker.current_conversation) >= 6:
            if self._can_player_overhear(speaker):
                self.add_message_to_chat_log(f"You overhear {self.get_entity_display_name(speaker)} and the group wrap up their conversation.")
            for p in group_participants:
                if p.conversation_partner_id == speaker.id or p.conversation_partner_id == listener.id or p.id in (speaker.id, listener.id):
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
                if len(p.current_conversation) < len(speaker.current_conversation):
                    p.current_conversation = list(speaker.current_conversation)
                self.propagate_npc_harmful_incident_gossip(speaker, p)

            self._handle_npc_social_goal(speaker, listener, goal)

            speaker.last_conversation_time = self.game_time
            speaker.conversation_partner_id = listener.id
            for p in other_participants:
                p.last_conversation_time = self.game_time
                if p.id != listener.id:
                    # Point to speaker or listener to stay in group
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
                if len(p.current_conversation) < len(speaker.current_conversation):
                    p.current_conversation = list(speaker.current_conversation)
                self.propagate_npc_harmful_incident_gossip(speaker, p)

            self._handle_npc_social_goal(speaker, listener, goal)

            speaker.last_conversation_time = self.game_time
            speaker.conversation_partner_id = listener.id
            for p in other_participants:
                p.last_conversation_time = self.game_time
                if p.id != listener.id:
                    p.conversation_partner_id = speaker.id
            return
