# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Writes config/institution.json back to disk, safely.

WHY THIS IS NOT JUST json.dump()
This file is the one thing standing between a working deployment and a sign-in
page with no name on it. Three things can go wrong when a web request rewrites a
config file, and all three have to be closed or the admin UI is a liability
rather than a feature:

  1. A CRASH MID-WRITE leaves a truncated file. Opening the real path with "w"
     truncates it before a single byte is written, so a process killed at that
     instant destroys the configuration. Written to a temporary file in the same
     directory and then os.replace()d, which is atomic on POSIX and on Windows:
     readers see either the whole old file or the whole new one, never a
     fragment.

  2. A BAD EDIT is unrecoverable. Every write keeps the previous contents as
     institution.json.bak, so an operator who breaks the allowlist has something
     to copy back that does not require us.

  3. THE RUNNING PROCESS DOES NOT NOTICE. Both the institution config and the
     web allowlist are cached in memory for the life of the process. Writing the
     file without invalidating them means the operator changes a setting, sees
     no effect, and changes it again. Both caches are dropped here, so a save
     takes effect on the next request rather than the next restart.

WHAT IT REFUSES TO DO
Write a payload that does not parse back, and write a payload with no
institution name once one has been set. Neither is a hypothetical: the second is
what a half-filled form submission looks like.
"""

import json
import logging
import os
import shutil
import tempfile

from . import config

logger = logging.getLogger("institution")


class ConfigWriteError(Exception):
    pass


def _current_raw():
    """The file as it is on disk, documentation keys and all.

    Read raw rather than through config.get(), because config.get() strips the
    _README and _comment blocks. Writing back what that returns would silently
    delete the documentation an operator relies on the next time they open the
    file by hand.
    """
    if not os.path.exists(config.CONFIG_PATH):
        return {}
    try:
        with open(config.CONFIG_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        # A file too broken to read is a file we must not merge into, or we
        # would quietly discard whatever else was in it.
        raise ConfigWriteError(
            "the existing config file could not be read, so it cannot be "
            "updated safely. Fix or remove it and try again."
        )


def update_section(section, value, validate=None):
    """Replace one top-level section and persist. Returns the new merged config.

    Only the named section is touched; everything else in the file — including
    the documentation blocks — is preserved byte-for-byte through the round
    trip.
    """
    raw = _current_raw()

    if validate is not None:
        problem = validate(value)
        if problem:
            raise ConfigWriteError(problem)

    # Preserve any documentation keys that lived inside the section being
    # replaced, so editing the allowlist through the UI does not strip the
    # explanation of how the allowlist works.
    existing = raw.get(section)
    if isinstance(existing, dict) and isinstance(value, dict):
        preserved = {k: v for k, v in existing.items() if k.startswith("_")}
        value = {**preserved, **value}

    raw[section] = value

    # Serialise BEFORE touching the real file. A payload that cannot be encoded
    # must not take the existing configuration with it.
    try:
        body = json.dumps(raw, indent=2, ensure_ascii=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise ConfigWriteError(f"the new configuration could not be encoded: {exc}")

    # Parse it back. Cheap, and it means a corrupt write is impossible rather
    # than merely unlikely.
    try:
        json.loads(body)
    except json.JSONDecodeError as exc:
        raise ConfigWriteError(f"the new configuration did not round-trip: {exc}")

    _atomic_write(body)

    # Drop both caches so the change is live on the next request. Deferred
    # imports: web_agent imports institution nowhere, and importing it at module
    # scope here would create a cycle through the app registry.
    fresh = config.get(refresh=True)
    try:
        from web_agent import allowlist
        allowlist.load(force=True)
    except Exception as exc:  # noqa: BLE001 - a bad allowlist must not 500 the save
        logger.warning("config saved, but the allowlist did not reload: %s", exc)

    logger.info("institution config section %r updated", section)
    return fresh


def _atomic_write(body):
    directory = os.path.dirname(config.CONFIG_PATH) or "."
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as exc:
        raise ConfigWriteError(f"could not create {directory}: {exc}")

    # Keep the previous version. An operator who breaks something needs a way
    # back that does not involve us.
    if os.path.exists(config.CONFIG_PATH):
        try:
            shutil.copy2(config.CONFIG_PATH, config.CONFIG_PATH + ".bak")
        except OSError as exc:
            logger.warning("could not write a .bak alongside the config: %s", exc)

    # Same directory as the target: os.replace is only atomic within one
    # filesystem, and /tmp is frequently a different one.
    handle = None
    try:
        fd, temp_path = tempfile.mkstemp(
            prefix=".institution.", suffix=".tmp", dir=directory,
        )
        handle = os.fdopen(fd, "w", encoding="utf-8")
        handle.write(body)
        handle.flush()
        # fsync before replace: without it a power loss can leave the directory
        # entry pointing at a file whose contents never reached the disk.
        os.fsync(handle.fileno())
        handle.close()
        handle = None
        os.replace(temp_path, config.CONFIG_PATH)
    except OSError as exc:
        raise ConfigWriteError(f"could not write {config.CONFIG_PATH}: {exc}")
    finally:
        if handle is not None:
            handle.close()


def validate_web_sources(value):
    """Reject an allowlist the fetcher would refuse, BEFORE it reaches disk.

    Deliberately duplicates part of web_agent.allowlist._validate rather than
    calling it: that function raises on the first problem, and a form wants to
    tell the operator everything that is wrong at once. The fetcher's copy stays
    the authority — this one only decides whether the save is accepted.
    """
    from urllib.parse import urlparse

    if not isinstance(value, dict) or not isinstance(value.get("urls"), list):
        return "web_sources must be an object with a 'urls' list."

    problems = []
    seen = set()
    for index, entry in enumerate(value["urls"], start=1):
        where = f"entry {index}"
        if not isinstance(entry, dict):
            problems.append(f"{where}: must be an object")
            continue
        for field in ("id", "url", "label"):
            if not str(entry.get(field) or "").strip():
                problems.append(f"{where}: '{field}' is required")
        entry_id = str(entry.get("id") or "").strip()
        if entry_id and entry_id in seen:
            problems.append(f"{where}: duplicate id {entry_id!r}")
        seen.add(entry_id)

        url = str(entry.get("url") or "").strip()
        if url:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                problems.append(
                    f"{where}: scheme {parsed.scheme or '(none)'!r} is not allowed; "
                    f"only http and https. file:, ftp: and data: are ways to turn "
                    f"a fetcher into something else entirely."
                )
            if not parsed.hostname:
                problems.append(f"{where}: no hostname in {url!r}")
            if parsed.username or parsed.password:
                problems.append(f"{where}: URL embeds credentials, which would be logged")
    return "; ".join(problems) if problems else None


def validate_institution(value):
    if not isinstance(value, dict):
        return "institution must be an object."
    if not str(value.get("name") or "").strip():
        return "The institution name cannot be blank once it has been set."
    return None
