
    def _get_witnesses_to_action(self, x: int, y: int, action_type: str) -> list[NPC]:
        """Finds NPCs who can see a location and would consider the action a crime."""
        witnesses = []
        for npc in self.village_npcs:
            if npc.is_dead:
                continue

            # Check if the NPC can see the location of the crime
            if npc.id in self.npc_fov_maps and self.npc_fov_maps[npc.id][x, y]:
                # Simple logic for now: most villagers will witness most crimes.
                # Future: More nuanced logic based on NPC personality, relationship to player, etc.
                if action_type in ["assault", "lockpicking", "theft"]:
                    # Guards and Sheriffs will always be witnesses
                    if npc.profession in ["Guard", "Sheriff"]:
                        witnesses.append(npc)
                    # For other NPCs, maybe a chance based on personality
                    elif npc.personality not in ["careless", "fearful"]: # Example personalities who might not report
                        witnesses.append(npc)
        return witnesses
