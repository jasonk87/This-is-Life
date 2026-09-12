# This-is-Life

"This is Life" is a 2D tile-based living-world simulation. Its inhabitants have persistent identities, possessions, homes, jobs, relationships and memories. Player actions and NPC decisions leave consequences in the same world.

**LLMs are currently disabled.** World generation, dialogue fallbacks, combat and background simulation run locally without model requests. No Ollama server or API key is required to play. Optional model integrations remain in the code but require explicit re-enabling in `config.py`.

For implementation direction and non-negotiable simulation rules, read [`docs/SIMULATION_DOCTRINE.md`](docs/SIMULATION_DOCTRINE.md). Player actions and NPC actions are routed through a unified interaction layer described in [`docs/INTERACTION_LAYER.md`](docs/INTERACTION_LAYER.md).

## Key Features:

*   **Procedurally Generated World**: Explore a unique world every time you play, with diverse biomes, villages, and points of interest.
*   **Persistent People**: Individual appearance and actual worn equipment, local needs-driven schedules, homes, jobs, relationships and remembered events.
*   **Witnessed Consequences**: Incidents, knowledge, reputation, grievances and law connect what happens to how other people respond.
*   **Day/Night Cycle**: Time passes, affecting visibility (FOV) and NPC schedules.
*   **Reputation System**: Your actions can earn you hero or criminal points, influencing how NPCs perceive you.
*   **Body-Based Combat**: Humans and wolves share connected body regions, layered tissue wounds, bleeding, pain, fractures and functional impairment. Equipped weapons and regional armor matter; treatment consumes supplies and recovery takes time.
*   **Crafting and Item Usage**: Gather resources and craft items. Use items like torches to light your way.
*   **Interactive World**: Chop trees, open doors, pick locks, sit on furniture, and sleep in beds.
*   **Trading**: Buy and sell items with merchant NPCs.
*   **Contracts**: Take on simple delivery contracts from NPCs.
*   **Exploration and Survival**: Manage your health and navigate the environment.

## Requirements:

*   Python 3.11+ (GitHub tests use 3.11).
*   Python dependencies, including `tcod`, `numpy`, `Pillow` and `pygame`. Install them using:
    ```bash
    pip install -r requirements.txt
    ```
*   A font file: `dejavu10x10_gs_tc.png` (or any other tcod-compatible tilesheet) in the root project directory.

## How to Run:

1.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Run the game**:
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
*   **F**: Select a visible combat target. **Tab** cycles targets, arrows choose an action, **Enter/F** commits it.
*   **U**: Inventory: equip owned weapons/clothing or use supplies.
*   **I**, then **B**: Inspect your body and wounds; **T** treats using owned supplies.
*   **C**: Crafting menu. **B** while playing: building menu.
*   **Q**: Journal. **L**: Look mode. **T** while playing: talk.
*   **Space**: Pause/resume. **1/2/3**: simulation speed. **.**: step.
*   **Esc** while playing: save. **?**: help.

See [the body model](docs/body-combat-slice.md) and [combat gameplay/stabilization](docs/combat-gameplay-stabilization.md) for controls, measured behavior, verification and current limitations.
