import os
from datetime import datetime

STATE_FILE = "sync_state.txt"


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}

    with open(STATE_FILE, "r") as f:
        lines = f.readlines()

    state = {}
    for line in lines:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            state[k] = v

    return state


def save_state(state):
    with open(STATE_FILE, "w") as f:
        for k, v in state.items():
            f.write(f"{k}={v}\n")


def get_last_sync(key):
    state = load_state()
    val = state.get(key)
    if not val:
        return None
    return datetime.fromisoformat(val)


def set_last_sync(key, dt):
    state = load_state()
    state[key] = dt.isoformat()
    save_state(state)