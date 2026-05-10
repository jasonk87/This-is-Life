import os
import pickle

SAVE_DIR = "saves"
SAVE_FORMAT_VERSION = 1


def _save_path(filename: str) -> str:
    return os.path.join(SAVE_DIR, filename)


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
        return True
    except Exception as e:
        print(f"Error saving game: {e}")
        return False


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
