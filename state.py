import json
import os

import config


def load_state():
    """Returns None if this is the first run — that's the "do initial
    clustering" signal, same role state["cluster_centers"] is None used to
    play in the single-genre version."""
    if os.path.exists(config.STATE_FILE):
        with open(config.STATE_FILE) as f:
            return json.load(f)
    return None


def save_state(state):
    with open(config.STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
