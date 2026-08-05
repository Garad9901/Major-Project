# Copyright (c) 2026 Yash Garad. All rights reserved.

import json
import os

import config


def append_changes(changes):
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(config.QUEUE_FILE, "a", encoding="utf-8") as f:
        for change in changes:
            f.write(json.dumps(change) + "\n")
