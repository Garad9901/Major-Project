# Copyright (c) 2026 Yash Garad. All rights reserved.

"""The web fetch agent: question -> allowlisted pages -> sanitised text.

Shaped like the SQL and RAG agents so the orchestrator treats all three the
same: a callable that takes a question and returns evidence, degrading to
"nothing useful" rather than raising when a source is unavailable.
"""

import logging
import time

from . import allowlist, extract, fetcher

logger = logging.getLogger("web_agent")


class WebPage:
    """One fetched page. Mirrors rag_agent.RetrievedChunk's shape."""

    def __init__(self, url, label, text, from_cache=False, meta=None):
        self.url = url
        self.label = label
        self.text = text
        self.from_cache = from_cache
        self.meta = meta or {}

    def to_dict(self):
        return {
            "url": self.url,
            "label": self.label,
            "from_cache": self.from_cache,
            "chars": len(self.text),
            **{k: v for k, v in self.meta.items() if k != "injection_samples"},
        }


def _log(**kwargs):
    """Write an audit row. Never let logging break a request."""
    try:
        from .models import WebFetchLog
        WebFetchLog.objects.create(**kwargs)
    except Exception:
        logger.exception("could not write web fetch log for %s", kwargs.get("url"))


def fetch_for_question(question, limit=2):
    """Pages relevant to `question`, or [] if none apply.

    The question NEVER becomes a URL. It only selects entries from the
    allowlist by keyword — see allowlist.select_for_question.
    """
    entries = allowlist.select_for_question(question, limit=limit)
    if not entries:
        logger.info("no allowlisted page matches question=%r", question[:60])
        return []

    pages = []
    for entry in entries:
        started = time.perf_counter()
        try:
            html, from_cache = fetcher.fetch(entry["url"])
        except fetcher.FetchRefused as exc:
            # Should be unreachable for an entry that came OUT of the allowlist,
            # so reaching it means a guard fired — an unsafe redirect target or a
            # hostname now resolving to a private address. Recorded loudly.
            logger.warning("REFUSED %s: %s", entry["url"], exc)
            _log(url=entry["url"], allowlist_id=entry["id"], outcome="refused",
                 detail=str(exc)[:500], question=question[:500],
                 duration_ms=round((time.perf_counter() - started) * 1000, 1))
            continue
        except fetcher.FetchFailed as exc:
            logger.warning("FAILED %s: %s", entry["url"], exc)
            _log(url=entry["url"], allowlist_id=entry["id"], outcome="failed",
                 detail=str(exc)[:500], question=question[:500],
                 duration_ms=round((time.perf_counter() - started) * 1000, 1))
            continue

        text, meta = extract.extract(html)
        duration = round((time.perf_counter() - started) * 1000, 1)

        _log(url=entry["url"], allowlist_id=entry["id"],
             outcome="cached" if from_cache else "ok",
             http_status=200 if not from_cache else None,
             bytes_returned=len(html), duration_ms=duration,
             injection_lines_removed=meta["injection_lines_removed"],
             detail=("truncated" if meta["truncated"] else ""),
             question=question[:500])

        if not text.strip():
            logger.info("no usable text from %s", entry["url"])
            continue

        pages.append(WebPage(entry["url"], entry["label"], text,
                             from_cache=from_cache, meta=meta))
        logger.info(
            "fetched %s (%s) %d chars in %.0fms%s",
            entry["id"], "cache" if from_cache else "network",
            len(text), duration,
            f", stripped {meta['injection_lines_removed']} injection line(s)"
            if meta["injection_lines_removed"] else "",
        )

    return pages


def fetch_url_directly(url, question=""):
    """Fetch ONE explicit URL, subject to the same allowlist.

    Exists for operators and tests only. Nothing on the request path calls it,
    and it is NOT exposed through any API — a URL parameter reachable from
    outside would be exactly the open-proxy design this agent avoids.
    """
    started = time.perf_counter()
    try:
        html, from_cache = fetcher.fetch(url)
    except fetcher.FetchRefused as exc:
        _log(url=url, allowlist_id="", outcome="refused", detail=str(exc)[:500],
             question=question[:500],
             duration_ms=round((time.perf_counter() - started) * 1000, 1))
        raise
    except fetcher.FetchFailed as exc:
        _log(url=url, allowlist_id="", outcome="failed", detail=str(exc)[:500],
             question=question[:500],
             duration_ms=round((time.perf_counter() - started) * 1000, 1))
        raise

    entry = allowlist.entry_for_url(url)
    text, meta = extract.extract(html)
    _log(url=url, allowlist_id=(entry or {}).get("id", ""),
         outcome="cached" if from_cache else "ok",
         bytes_returned=len(html),
         duration_ms=round((time.perf_counter() - started) * 1000, 1),
         injection_lines_removed=meta["injection_lines_removed"],
         question=question[:500])
    return WebPage(url, (entry or {}).get("label", url), text,
                   from_cache=from_cache, meta=meta)
