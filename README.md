# This-is-Life

"This is Life" is a 2D tile-based sandbox RPG where you navigate a procedurally generated world, interacting with NPCs, taking on tasks, and shaping your story. The game leverages a Large Language Model (LLM) to create dynamic NPC personalities, dialogues, and even some world events.

## Key Features:

*   **Procedurally Generated World**: Explore a unique world every time you play, with diverse biomes, villages, and points of interest.
*   **Dynamic NPCs**: Interact with NPCs whose personalities, schedules, and dialogues are driven by an LLM. They have homes, jobs, and react to your reputation.
*   **LLM-Powered Interactions**: Experience unique dialogues, persuasion attempts, and combat resolutions adjudicated by an LLM.
*   **Day/Night Cycle**: Time passes, affecting visibility (FOV) and NPC schedules.
*   **Reputation System**: Your actions can earn you hero or criminal points, influencing how NPCs perceive you.
*   **Basic Combat**: Engage in combat with NPCs, with outcomes determined by LLM-based adjudication.
*   **Crafting and Item Usage**: Gather resources and craft items. Use items like torches to light your way.
*   **Interactive World**: Chop trees, open doors, pick locks, sit on furniture, and sleep in beds.
*   **Trading**: Buy and sell items with merchant NPCs.
*   **Contracts**: Take on simple delivery contracts from NPCs.
*   **Exploration and Survival**: Manage your health and navigate the environment.

## Requirements:

*   Python 3.10+
*   An accessible Ollama server with a model like `llama3.2` (or compatible) running.
    *   The game is configured to use `http://192.168.86.30:11434` by default (see `data/prompts.py`). You may need to change this.
*   Python libraries: `tcod`, `requests`, `numpy`. Install them using:
    ```bash
    pip install -r requirements.txt
    ```
*   A font file: `dejavu10x10_gs_tc.png` (or any other tcod-compatible tilesheet) in the root project directory.

## How to Run:

1.  **Ensure Ollama is running and accessible.**
2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Run the game**:
    ```bash
    python main.py
    ```

## Basic Controls (Partial List - see `main.py` for more):

*   **Arrow Keys**: Move
*   **E**: Interact with the tile you are facing (e.g., open doors, talk to NPCs, chop trees, sit, sleep, pick locks).
*   **I**: Toggle Info Menu.
*   **C**: Craft a healing salve (example).
*   **H**: Use a healing salve (example).
*   **Q**: Quit the game.