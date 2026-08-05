# Copyright (c) 2026 Yash Garad. All rights reserved.

import json
import os

import config

# Sentinel watermark used the first time a table is ever polled — everything
# currently in the table is >= this, so the first cycle reports a full
# initial sync rather than silently skipping pre-existing rows.
EPOCH = "1970-01-01T00:00:00+00:00"


def load_state():
    if not os.path.exists(config.STATE_FILE):
        return {}
    with open(config.STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    os.makedirs(config.DATA_DIR, exist_ok=True)
    tmp_path = config.STATE_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp_path, config.STATE_FILE)
