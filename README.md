# This-is-Life

"This is Life" is a 2D tile-based sandbox RPG where you navigate a procedurally generated world, interacting with NPCs, taking on tasks, and shaping your story. The game leverages a Large Language Model (LLM) to create dynamic NPC personalities, dialogues, and even some world events.

For implementation direction and non-negotiable simulation rules, read [`docs/SIMULATION_DOCTRINE.md`](docs/SIMULATION_DOCTRINE.md). Player actions and NPC actions are routed through a unified interaction layer described in [`docs/INTERACTION_LAYER.md`](docs/INTERACTION_LAYER.md).

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


## Developer Headless Simulation Sandbox

For developer and agent validation of actual simulation behavior, use the headless sandbox. It runs deterministic scenarios without graphics or LLM/Ollama calls and emits readable summaries plus optional JSON reports.

```bash
python tools/run_simulation_sandbox.py --scenario construction_basic --ticks 500 --seed 123
python tools/run_simulation_sandbox.py --scenario delivery_basic --ticks 500 --seed 123 --report out/sim_reports/delivery_basic.json --log out/sim_reports/delivery_basic.log
python tools/run_simulation_sandbox.py --scenario construction_basic --ticks 500 --seed 123 --snapshot out/sim_reports/construction_basic.png --overlay claims,paths,buildings,npcs,blueprints,chunks,interactions
python tools/asset_workbench.py --preview-character --gender female --profession Blacksmith
```

Available scenarios include `construction_basic`, `delivery_basic`, `hunting_food_chain`, and `settlement_growth`. See [`docs/SIMULATION_SANDBOX.md`](docs/SIMULATION_SANDBOX.md) for report format, usage guidance for Codex/Jules, and instructions for adding scenarios.

## Basic Controls (Partial List - see `main.py` for more):

*   **Arrow Keys**: Move
*   **E**: Interact with the tile you are facing (e.g., open doors, talk to NPCs, chop trees, sit, sleep, pick locks).
*   **I**: Toggle Info Menu.
*   **C**: Craft a healing salve (example).
*   **H**: Use a healing salve (example).
*   **Q**: Quit the game.