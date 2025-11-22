import pickle
import os

def save_game(world, filename="savegame.sav"):
    """Saves the game world to a file."""
    if not os.path.exists("saves"):
        os.makedirs("saves")

    filepath = os.path.join("saves", filename)
    try:
        # We need to be careful with what we pickle.
        # tcod objects might not be picklable.
        # Specifically tcod.noise.Noise and numpy arrays are usually fine, but C-structs might be issues.
        # Let's try simple pickle first.

        # Temporarily remove unpicklable objects if any (e.g. tcod context if stored in world, but it shouldn't be)
        # The generator has tcod.noise.Noise. Let's see if that pickles.

        with open(filepath, "wb") as f:
            pickle.dump(world, f)
        print(f"Game saved to {filepath}")
        return True
    except Exception as e:
        print(f"Error saving game: {e}")
        return False

def load_game(filename="savegame.sav"):
    """Loads the game world from a file."""
    filepath = os.path.join("saves", filename)
    if not os.path.exists(filepath):
        print(f"Save file {filepath} not found.")
        return None

    try:
        with open(filepath, "rb") as f:
            world = pickle.load(f)
        print(f"Game loaded from {filepath}")
        return world
    except Exception as e:
        print(f"Error loading game: {e}")
        return None
