# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Loads config/institution.json — the one file a college fills in.

WHY THIS EXISTS
The institution's identity used to live in frontend/src/institute.js, compiled
into the React bundle. Rebranding therefore meant editing JavaScript and
rebuilding, which is a reasonable thing to ask of the person who wrote it and an
unreasonable thing to ask of a college IT department that has been handed a
product. The same was true of the web-fetch allowlist, which lived in a third
place again.

One file, read at runtime, served from /api/institution/. Changing the name on
the sign-in page is now a file edit and a backend restart.

WHAT THIS MODULE WILL NOT DO
It will not invent a default institution name. `name` ships empty and
`is_configured()` reports False until someone sets it, which is what lets
first-run setup and the production entrypoint refuse to proceed. A product that
can go live still calling itself a placeholder will eventually go live still
calling itself a placeholder.

FAILURE POSTURE, AND WHY IT DIFFERS BY ENVIRONMENT
A malformed config file is an operator error, and the useful response is to say
so precisely rather than to serve a half-configured page. But this endpoint is
what the SIGN-IN SCREEN reads, so a hard failure here locks everyone out of a
system whose data is fine. So: parse errors are logged loudly and fall back to
the built-in defaults, keeping the service reachable, and `problems()` surfaces
them on the health dashboard and to first-run setup. Production start-up checks
that separately (see checks.py) so a broken config is caught at deploy time
rather than discovered by a user.
"""

import copy
import json
import logging
import os
import threading

logger = logging.getLogger("institution")

# Repo layout: backend/institution/config.py -> ../../config/institution.json
_DEFAULT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config", "institution.json")
)

CONFIG_PATH = os.getenv("INSTITUTION_CONFIG", _DEFAULT_PATH)

# The shape served when no file exists, so a fresh clone still runs. Every
# identity field a user would SEE is blank or neutral; nothing here names an
# institution, which is the point.
DEFAULTS = {
    "institution": {
        "name": "",
        "short_name": "",
        "descriptor": "Academic Information Service",
        "footnote": "Authorised users only",
        "initials": None,
        "logo_url": None,
        "contact_email": "",
        "contact_url": "",
    },
    "theme": {
        "accent": "#10a37f",
        "identity_ink": "#132A45",
        "identity_highlight": "#C98A2E",
    },
}

# Keys beginning with an underscore are documentation for whoever opens the
# file. They are stripped before the config is served so they never reach the
# browser or a caller's parser.
_DOC_PREFIX = "_"

_lock = threading.Lock()
_cache = None


class InstitutionConfigError(Exception):
    """Raised only by validate_file(); the runtime loader never raises."""


def _strip_docs(value):
    """Recursively drop _README / _comment / _field_notes keys."""
    if isinstance(value, dict):
        return {k: _strip_docs(v) for k, v in value.items() if not k.startswith(_DOC_PREFIX)}
    if isinstance(value, list):
        return [_strip_docs(v) for v in value]
    return value


def _merge(base, override):
    """Deep-merge `override` onto a copy of `base`.

    A partial config is legal and common: an operator who only wants to set the
    name should not have to restate the whole theme block, and an upgrade that
    adds a new field must not break a file written before that field existed.
    """
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _read_file(path):
    """Return (raw_dict, problems). Never raises."""
    if not os.path.exists(path):
        return {}, [
            f"No institution config at {path}. Serving built-in defaults; the "
            f"institution name is unset. Copy config/institution.example.json to "
            f"config/institution.json and fill it in."
        ]
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        # Line and column included: "invalid JSON" alone sends an operator
        # hunting through a 150-line file.
        return {}, [f"{path} is not valid JSON (line {exc.lineno}, column {exc.colno}): {exc.msg}"]
    except OSError as exc:
        return {}, [f"{path} could not be read: {exc}"]

    if not isinstance(data, dict):
        return {}, [f"{path} must contain a JSON object at the top level, not {type(data).__name__}"]
    return data, []


def _build():
    raw, problems = _read_file(CONFIG_PATH)
    merged = _merge(DEFAULTS, _strip_docs(raw))

    institution = merged.setdefault("institution", {})
    if not str(institution.get("name") or "").strip():
        problems.append(
            "institution.name is not set. The sign-in screen will show no "
            "institution name until it is."
        )

    # short_name is a convenience for narrow layouts; deriving it here means
    # every consumer does not have to implement the same fallback.
    if not str(institution.get("short_name") or "").strip():
        institution["short_name"] = institution.get("name") or ""

    for problem in problems:
        logger.warning("institution config: %s", problem)

    merged["_problems"] = problems
    return merged


def get(refresh=False):
    """The merged config. Cached, because this is read on every sign-in page load.

    `refresh=True` re-reads from disk — used by first-run setup, which writes the
    file and then immediately needs to see its own change.
    """
    global _cache
    with _lock:
        if _cache is None or refresh:
            _cache = _build()
        return _cache


def public():
    """The config as served to an UNAUTHENTICATED browser.

    Allowlisted, not blocklisted. A future field added to institution.json is
    absent from this dict until someone deliberately adds it here, so the
    default behaviour of a new setting is "not published to the internet"
    rather than "published unless we remembered".

    web_sources is deliberately excluded. The URLs are not secret, but they are
    an inventory of what the fetcher will reach, and there is no reason to hand
    that to an unauthenticated client.
    """
    config = get()
    institution = config.get("institution", {})
    theme = config.get("theme", {})
    return {
        "institution": {
            "name": institution.get("name") or "",
            "short_name": institution.get("short_name") or "",
            "descriptor": institution.get("descriptor") or "",
            "footnote": institution.get("footnote") or "",
            "initials": institution.get("initials"),
            "logo_url": institution.get("logo_url"),
            "contact_email": institution.get("contact_email") or "",
            "contact_url": institution.get("contact_url") or "",
        },
        "theme": {
            "accent": theme.get("accent") or DEFAULTS["theme"]["accent"],
            "identity_ink": theme.get("identity_ink") or DEFAULTS["theme"]["identity_ink"],
            "identity_highlight": (
                theme.get("identity_highlight") or DEFAULTS["theme"]["identity_highlight"]
            ),
        },
        "configured": is_configured(),
    }


def is_configured():
    """True once an institution name has been set.

    First-run setup and the production start-up check both gate on this.
    """
    return bool(str(get().get("institution", {}).get("name") or "").strip())


def problems():
    """Human-readable problems with the current config; empty when it is fine."""
    return list(get().get("_problems", []))
