import json
import os
import pickle
import time

SAVE_DIR = "saves"
SAVE_FORMAT_VERSION = 1


def _save_path(filename: str) -> str:
    return os.path.join(SAVE_DIR, filename)


def _metadata_path(filename: str) -> str:
    """Sidecar path holding a save's summary.

    The summary lives beside the .sav rather than inside it because the save
    itself is one pickled World: reading a field out of it means
    deserializing the entire world, and the load menu wants to list a dozen
    saves at once without paying that for each.
    """
    base = filename[:-4] if filename.endswith(".sav") else filename
    return _save_path(f"{base}.meta.json")


def _build_save_metadata(world) -> dict:
    """Summarize a world for display in the load menu."""
    player = getattr(world, "player", None)
    seasons = getattr(world, "seasons", None) or []
    season_index = getattr(world, "current_season_index", 0)
    season = seasons[season_index] if 0 <= season_index < len(seasons) else ""
    return {
        "player_name": str(getattr(player, "name", "") or "Unknown"),
        "game_time": int(getattr(world, "game_time", 0)),
        "season": str(season),
        "weather": str(getattr(world, "weather", "") or ""),
        "saved_at": time.time(),
    }


def load_save_metadata(filename: str):
    """Read a save's summary sidecar, or None if it has none.

    Saves written before summaries existed simply have no sidecar; callers
    fall back to showing the bare filename.
    """
    path = _metadata_path(filename)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _build_save_envelope(world) -> dict:
    """Wrap the world in explicit save metadata before serialization."""
    return {
        "version": SAVE_FORMAT_VERSION,
        "world": world,
    }


def _extract_world_from_envelope(save_data):
    """Validate a save envelope and return its world payload."""
    if not isinstance(save_data, dict):
        raise ValueError("Save file does not contain a versioned save envelope.")

    version = save_data.get("version")
    if version != SAVE_FORMAT_VERSION:
        raise ValueError(f"Unsupported save format version: {version!r}")

    if "world" not in save_data:
        raise ValueError("Save file is missing its world payload.")

    return save_data["world"]


def save_game(world, filename="savegame.sav"):
    """Saves the game world to a versioned save file."""
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)

    filepath = _save_path(filename)
    try:
        with open(filepath, "wb") as f:
            pickle.dump(_build_save_envelope(world), f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"Game saved to {filepath}")
    except Exception as e:
        print(f"Error saving game: {e}")
        return False

    # The summary is a convenience for the load menu; failing to write it
    # must not report the save itself as failed.
    try:
        with open(_metadata_path(filename), "w", encoding="utf-8") as f:
            json.dump(_build_save_metadata(world), f)
    except (OSError, TypeError, ValueError) as e:
        print(f"Warning: could not write save summary: {e}")
    return True


def load_game(filename="savegame.sav"):
    """Loads the game world from a versioned save file."""
    filepath = _save_path(filename)
    if not os.path.exists(filepath):
        print(f"Save file {filepath} not found.")
        return None

    try:
        with open(filepath, "rb") as f:
            save_data = pickle.load(f)
        world = _extract_world_from_envelope(save_data)
        print(f"Game loaded from {filepath}")
        return world
    except Exception as e:
        print(f"Error loading game: {e}")
        return None
