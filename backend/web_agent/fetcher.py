# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Fetching, with the guards a fetcher inside a private network needs.

THREAT MODEL
This process can reach postgres:5432, qdrant:6333 and ollama:11434 on the docker
network, and whatever else the host can route to. A component that performs HTTP
requests is therefore an SSRF primitive unless it is constrained, and "we only
fetch from an allowlist" is necessary but NOT sufficient:

  * REDIRECTS. An allowlisted page can 302 to http://ollama:11434/ or to
    169.254.169.254 (cloud metadata). urllib follows redirects by default, so the
    allowlist check would pass and the fetch would still land somewhere else.
    -> redirects are followed manually, and every hop is re-checked.

  * DNS. An allowlisted hostname can resolve to a private address, whether by
    misconfiguration or deliberately (DNS rebinding).
    -> the resolved IP is checked, not just the name.

  * SIZE. A large or endless response would exhaust memory.
    -> capped, and read incrementally rather than all at once.

  * TIME. A slow endpoint holds a worker.
    -> connect and read timeouts, and a wall-clock budget across redirects.

Each of these has been closed deliberately; none is theoretical.
"""

import ipaddress
import logging
import os
import socket
import threading
import time
from urllib.parse import urlparse

import requests

from . import allowlist

logger = logging.getLogger("web_agent")

CONNECT_TIMEOUT = float(os.getenv("WEB_AGENT_CONNECT_TIMEOUT", "5"))
READ_TIMEOUT = float(os.getenv("WEB_AGENT_READ_TIMEOUT", "10"))
MAX_BYTES = int(os.getenv("WEB_AGENT_MAX_BYTES", str(2 * 1024 * 1024)))  # 2 MB
MAX_REDIRECTS = int(os.getenv("WEB_AGENT_MAX_REDIRECTS", "3"))
TOTAL_BUDGET_S = float(os.getenv("WEB_AGENT_TOTAL_TIMEOUT", "20"))

CACHE_TTL_SECONDS = int(os.getenv("WEB_AGENT_CACHE_TTL", "3600"))  # 1 hour

USER_AGENT = os.getenv(
    "WEB_AGENT_USER_AGENT",
    "CollegeAssistant/1.0 (+internal college information assistant)",
)

_cache = {}          # url -> {"body": str, "ctype": str, "ts": float}
_cache_lock = threading.Lock()


class FetchRefused(Exception):
    """Refused before any request was made. Not a network failure."""


class FetchFailed(Exception):
    """The request was permitted but did not produce usable content."""


def _is_public_ip(host):
    """Resolve `host` and require every answer to be a public address.

    ALL resolved addresses must be public: a name returning one public and one
    private address must not be reachable via the private one on a retry.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise FetchFailed(f"could not resolve {host}: {exc}") from exc

    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise FetchFailed(f"no addresses for {host}")

    for addr in addresses:
        ip = ipaddress.ip_address(addr)
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise FetchRefused(
                f"{host} resolves to non-public address {addr} — refusing. "
                f"This blocks SSRF into the internal docker network and cloud "
                f"metadata endpoints."
            )
    return sorted(addresses)


def _check_url(url, *, hop):
    """Every hop must be scheme-safe, allowlisted and publicly addressed."""
    parsed = urlparse(url)
    if parsed.scheme not in allowlist.ALLOWED_SCHEMES:
        raise FetchRefused(f"hop {hop}: scheme {parsed.scheme!r} not permitted")
    if not allowlist.is_allowed(url):
        raise FetchRefused(f"hop {hop}: {url} is not on the allowlist")
    _is_public_ip(parsed.hostname)


def _read_capped(response):
    """Read at most MAX_BYTES, streaming.

    Content-Length is advisory and can lie, so the cap is enforced on bytes
    actually read rather than on the declared length.
    """
    chunks, total = [], 0
    for chunk in response.iter_content(8192):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_BYTES:
            logger.warning("response exceeded %d bytes, truncating", MAX_BYTES)
            chunks.append(chunk[: max(0, MAX_BYTES - (total - len(chunk)))])
            break
        chunks.append(chunk)
    return b"".join(chunks)


def fetch(url, use_cache=True):
    """Fetch one ALLOWLISTED url. Returns (text, from_cache).

    Raises FetchRefused if not permitted, FetchFailed on a network/HTTP problem.
    """
    if not allowlist.is_allowed(url):
        # Checked here as well as per-hop: this is the entry point, and a caller
        # passing an arbitrary URL must be refused before any DNS lookup.
        raise FetchRefused(f"{url} is not on the allowlist")

    if use_cache:
        with _cache_lock:
            hit = _cache.get(url)
            if hit and (time.time() - hit["ts"]) < CACHE_TTL_SECONDS:
                return hit["body"], True

    deadline = time.monotonic() + TOTAL_BUDGET_S
    current = url
    body = None

    for hop in range(MAX_REDIRECTS + 1):
        if time.monotonic() > deadline:
            raise FetchFailed(f"exceeded {TOTAL_BUDGET_S:.0f}s total budget")

        _check_url(current, hop=hop)

        try:
            resp = requests.get(
                current,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                # Manual redirect handling — the whole point. requests would
                # otherwise follow to a host that was never allowlisted.
                allow_redirects=False,
                stream=True,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9"},
            )
        except requests.RequestException as exc:
            raise FetchFailed(f"request failed: {exc}") from exc

        try:
            if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
                target = resp.headers.get("Location")
                if not target:
                    raise FetchFailed(f"redirect with no Location from {current}")
                target = requests.compat.urljoin(current, target)
                logger.info("redirect %s -> %s (will be re-checked)", current, target)
                current = target
                continue

            if resp.status_code != 200:
                raise FetchFailed(f"HTTP {resp.status_code} from {current}")

            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype and not (ctype.startswith("text/") or ctype == "application/xhtml+xml"):
                # A PDF or image is not something this pipeline can read, and
                # decoding arbitrary binary into the prompt is a bad idea.
                raise FetchFailed(f"unsupported content type {ctype!r}")

            raw = _read_capped(resp)
            body = raw.decode(resp.encoding or "utf-8", errors="replace")
            break
        finally:
            resp.close()
    else:
        raise FetchFailed(f"more than {MAX_REDIRECTS} redirects starting at {url}")

    if body is None:
        raise FetchFailed(f"no body retrieved from {url}")

    with _cache_lock:
        _cache[url] = {"body": body, "ts": time.time()}
    return body, False


def cache_stats():
    now = time.time()
    with _cache_lock:
        return {
            "entries": len(_cache),
            "ttl_seconds": CACHE_TTL_SECONDS,
            "urls": [
                {"url": u, "age_seconds": round(now - v["ts"]), "bytes": len(v["body"])}
                for u, v in _cache.items()
            ],
        }


def clear_cache():
    with _cache_lock:
        n = len(_cache)
        _cache.clear()
    return n
