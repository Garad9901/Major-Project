# Copyright (c) 2026 Yash Garad. All rights reserved.

import json
import logging
import os
import time

import config

logger = logging.getLogger("sync_worker")

# Sentinel watermark used the first time a table is ever polled — everything
# currently in the table is >= this, so the first cycle reports a full
# initial sync rather than silently skipping pre-existing rows.
EPOCH = "1970-01-01T00:00:00+00:00"


def load_state():
    """The saved watermarks, or {} if there are none that can be read.

    A CORRUPT STATE FILE MUST NOT BE FATAL, AND IT USED TO BE.
    This function is called once, from main(), BEFORE the `while True` loop that
    catches everything else. An unreadable file therefore raised straight out of
    main(), the container exited, `restart: always` started it again, and it
    raised again — a permanent crash loop.

    Verified, not theorised: truncating this file to a half-written line (what an
    unclean shutdown or a full disk leaves behind) put the worker into exactly
    that loop, 4 restarts and climbing, with JSONDecodeError each time.

    What made it worse is that nothing would have told anyone. The backend, the
    database and Qdrant all stay healthy, so /api/health/status/ shows every
    component green while the index quietly stops being updated. The first
    symptom is a user being given last week's answer, with no error anywhere.

    Starting from an empty state is the right recovery. It re-polls everything
    from the epoch, which is a full re-embed — slower, but SAFE, because point
    IDs are a deterministic uuid5 of (table, pk), so re-embedding overwrites
    rather than duplicates. That was measured during the audit: a forced
    re-embed of all 55 profile rows left the collection at 81 points, unchanged.

    The unreadable file is moved aside rather than deleted, so whatever went
    wrong can still be looked at.
    """
    if not os.path.exists(config.STATE_FILE):
        return {}
    try:
        with open(config.STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        quarantine = f"{config.STATE_FILE}.corrupt.{int(time.time())}"
        try:
            os.replace(config.STATE_FILE, quarantine)
        except OSError:
            quarantine = "(could not be preserved)"
        logger.error(
            "STATE FILE UNREADABLE (%s): %s. Moved to %s and starting from an "
            "empty state — this cycle will re-poll and re-embed EVERY table from "
            "scratch, which is safe (upserts are idempotent) but slow. If this "
            "recurs, the data volume is probably failing writes.",
            config.STATE_FILE, exc, quarantine,
        )
        return {}

    if not isinstance(state, dict):
        logger.error(
            "state file contained %s, not an object — ignoring it and starting "
            "from an empty state.", type(state).__name__,
        )
        return {}
    return state


def save_state(state):
    """Write the watermarks atomically.

    os.replace() is atomic, so a reader never sees a half-written file and a
    process killed mid-write leaves the previous state intact — confirmed by
    SIGKILLing the worker mid-cycle during the audit; the file stayed valid.

    The flush + fsync before the replace close the remaining gap: without them
    the rename can reach the disk before the DATA does, so a machine-level crash
    (power loss, not a process kill) can leave a zero-length or truncated file
    under the real name. That is precisely the corruption load_state() now has
    to recover from, so it is worth the cost — this runs a handful of times a
    minute, not in a hot path.
    """
    os.makedirs(config.DATA_DIR, exist_ok=True)
    tmp_path = config.STATE_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, config.STATE_FILE)
