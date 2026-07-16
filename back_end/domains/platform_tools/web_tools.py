"""Platform tools: web_search + fetch_url — the news-scout's open-web window.

Both tools are read-only against the internet and never mutate OpenSweep or the
source repository. They are deliberately forgiving: upstream failures return
`{"status": "error", ...}` instead of raising, so a flaky search engine never
kills an agent run mid-flight.

`fetch_url` carries an SSRF guard (`_assert_public_http_url`): agents feed it
URLs harvested from the open web, so it must never be usable to probe the
compose network (opensweep_* services), localhost, or private/link-local ranges —
including via DNS records that resolve to internal addresses.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import xml.etree.ElementTree as ET
from html import unescape
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import httpx
from fastapi import HTTPException

from config import settings

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")


def _timeout() -> float:
    return float(settings.OPENSWEEP_WEB_TOOL_TIMEOUT_SECONDS)


# ---------------------------------------------------------------------------
# web_search
# ---------------------------------------------------------------------------


async def _search_web(query: str, limit: int) -> list[dict[str, Any]]:
    base = settings.SEARXNG_URL.rstrip("/")
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await client.get(
            f"{base}/search", params={"q": query, "format": "json"}
        )
        resp.raise_for_status()
    return [
        {
            "title": r.get("title") or "",
            "url": r.get("url") or "",
            "snippet": r.get("content") or "",
            "source": "searxng",
            "published_at": r.get("publishedDate") or "",
        }
        for r in (resp.json().get("results") or [])[:limit]
    ]


async def _search_github(query: str, limit: int) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await client.get(
            "https://api.github.com/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc", "per_page": limit},
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "opensweep-platform",
            },
        )
        resp.raise_for_status()
    return [
        {
            "title": r.get("full_name") or "",
            "url": r.get("html_url") or "",
            "snippet": r.get("description") or "",
            "source": "github",
            "published_at": r.get("pushed_at") or "",
        }
        for r in (resp.json().get("items") or [])[:limit]
    ]


async def _search_hackernews(query: str, limit: int) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await client.get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": query, "hitsPerPage": limit},
        )
        resp.raise_for_status()
    out: list[dict[str, Any]] = []
    for h in (resp.json().get("hits") or [])[:limit]:
        out.append(
            {
                "title": h.get("title") or h.get("story_title") or "",
                "url": h.get("url")
                or f"https://news.ycombinator.com/item?id={h.get('objectID', '')}",
                "snippet": h.get("story_text") or "",
                "source": "hackernews",
                "published_at": h.get("created_at") or "",
            }
        )
    return out


async def _search_arxiv(query: str, limit: int) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await client.get(
            "http://export.arxiv.org/api/query",
            params={"search_query": f"all:{query}", "start": 0, "max_results": limit},
        )
        resp.raise_for_status()
    out: list[dict[str, Any]] = []
    root = ET.fromstring(resp.text)
    for entry in root.findall("atom:entry", _ATOM_NS)[:limit]:
        summary = " ".join(
            (entry.findtext("atom:summary", default="", namespaces=_ATOM_NS) or "").split()
        )
        out.append(
            {
                "title": " ".join(
                    (entry.findtext("atom:title", default="", namespaces=_ATOM_NS) or "").split()
                ),
                "url": (entry.findtext("atom:id", default="", namespaces=_ATOM_NS) or "").strip(),
                "snippet": summary[:300],
                "source": "arxiv",
                "published_at": (
                    entry.findtext("atom:published", default="", namespaces=_ATOM_NS) or ""
                ).strip(),
            }
        )
    return out


_TRENDSHIFT_URL = "https://trendshift.io/"

_TRENDSHIFT_REPO_RE = re.compile(r'href="/repositories/(\d+)"[^>]*>([^<]+)</a>')
# The repo description paragraph in the main trending list. Keyed on the
# text-muted-foreground class so the marquee ticker at the top of the page
# (which repeats the same repos without a description) never matches.
_TRENDSHIFT_DESC_RE = re.compile(
    r'<p class="[^"]*text-muted-foreground[^"]*"[^>]*>([^<]{3,400})</p>'
)


def _parse_trendshift_html(page: str, query: str, limit: int) -> list[dict[str, Any]]:
    """Extract the trending leaderboard from trendshift.io's homepage.

    Trendshift has no JSON API, but the Next.js page server-renders every
    trending repository as `<a href="/repositories/{id}">owner/name</a>`
    followed (in the main list) by a description paragraph. Entries are
    deduped by trendshift id in order of first appearance; a description
    found on a later occurrence backfills an entry filed without one. If
    trendshift restyles the description paragraph we degrade to bare repo
    names rather than breaking.
    """
    entries: dict[str, dict[str, Any]] = {}
    for m in _TRENDSHIFT_REPO_RE.finditer(page):
        name = unescape(m.group(2)).strip()
        if "/" not in name:  # icon/aria anchors to the same repo page
            continue
        # Window sized for the inline-SVG icon soup between name and
        # description (~2-4k chars); the different-repo guard below keeps a
        # too-large window from stealing the next card's description.
        desc_m = _TRENDSHIFT_DESC_RE.search(page, m.end(), m.end() + 8000)
        if desc_m:
            # A description only belongs to this repo if no OTHER repo's
            # anchor sits between the name and the paragraph (same-repo
            # anchors — icon/aria links inside the card — are fine).
            between = page[m.end() : desc_m.start()]
            if any(
                other.group(1) != m.group(1)
                for other in _TRENDSHIFT_REPO_RE.finditer(between)
            ):
                desc_m = None
        desc = unescape(desc_m.group(1)).strip() if desc_m else ""
        entry = entries.setdefault(
            m.group(1),
            {
                "title": name,
                "url": f"https://github.com/{name}",
                "snippet": "",
                "source": "trendshift",
                "published_at": "",
            },
        )
        if desc and not entry["snippet"]:
            entry["snippet"] = desc
    results = list(entries.values())
    tokens = (query or "").lower().split()
    if tokens:
        results = [
            r
            for r in results
            if any(t in f"{r['title']} {r['snippet']}".lower() for t in tokens)
        ]
    for r in results:
        r["snippet"] = r["snippet"] or "Trending repository on trendshift.io"
    return results[:limit]


async def _search_trendshift(query: str, limit: int) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=_timeout(), follow_redirects=True) as client:
        resp = await client.get(
            _TRENDSHIFT_URL, headers={"User-Agent": "opensweep-platform"}
        )
        resp.raise_for_status()
    return _parse_trendshift_html(resp.text, query, limit)


_SEARCH_MODES: dict[str, Callable[..., Any]] = {
    "web": _search_web,
    "github": _search_github,
    "hackernews": _search_hackernews,
    "arxiv": _search_arxiv,
    "trendshift": _search_trendshift,
}


async def web_search(
    *,
    query: str,
    mode: str = "web",
    limit: int = 8,
    **_: Any,
) -> dict[str, Any]:
    """Search the open web. Read-only; results are leads, not facts.

    Modes:
      - "web" — general metasearch via the deployment's SearXNG instance.
      - "github" — GitHub repository search, ordered by stars (trending /
        popular projects for a topic).
      - "hackernews" — Hacker News stories via Algolia (community signal).
      - "arxiv" — arXiv papers (research).
      - "trendshift" — trendshift.io's GitHub trending leaderboard (today's
        rising repositories). The query does not search: it only FILTERS the
        leaderboard by substring; pass an empty query to get the full list.

    Returns `{"status": "ok", "results": [{title, url, snippet, source,
    published_at}, ...]}`. When the upstream engine is down or misconfigured
    the call returns `{"status": "error"|"unavailable", "detail": ...,
    "results": []}` instead of failing the run — check `status` before using
    the results. Follow up on promising hits with `fetch_url`.
    """
    if mode not in _SEARCH_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"invalid mode={mode!r}; expected one of {sorted(_SEARCH_MODES)}",
        )
    if mode == "web" and not (settings.SEARXNG_URL or "").strip():
        return {
            "status": "unavailable",
            "detail": "SEARXNG_URL not configured",
            "results": [],
        }
    try:
        results = await _SEARCH_MODES[mode](query, max(int(limit), 0))
    except Exception as exc:  # keep agent runs alive on upstream failure
        return {"status": "error", "detail": str(exc), "results": []}
    return {"status": "ok", "results": results}


# ---------------------------------------------------------------------------
# fetch_url
# ---------------------------------------------------------------------------


def _ip_forbidden(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
    )


def _denied_hosts() -> frozenset[str]:
    """Hostnames of the deployment's own internal services, derived from
    settings. opensweep_*/opensweep-* names are caught by the prefix rule; this covers
    deployments whose SearXNG / internal-backend URLs use other names."""
    hosts: set[str] = set()
    for raw in (settings.SEARXNG_URL, settings.OPENSWEEP_BACKEND_INTERNAL_URL):
        h = (urlsplit((raw or "").strip()).hostname or "").strip().lower()
        if h:
            hosts.add(h)
    return frozenset(hosts)


def _check_public_url_syntax(url: str) -> str | None:
    """Pure-string/IP-literal SSRF checks — no I/O, unit-testable sync.

    Rejects non-http(s) schemes, empty hosts, localhost/.local/opensweep_* hosts,
    the deployment's own service hostnames (SEARXNG_URL /
    OPENSWEEP_BACKEND_INTERNAL_URL), and IP literals in
    private/loopback/link-local/reserved/unspecified ranges.

    Returns the hostname that still needs DNS validation, or None when the
    host was an IP literal already fully validated. Raises HTTPException 422
    on rejection.
    """
    parts = urlsplit(url or "")
    if parts.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=422,
            detail=f"unsupported URL scheme {parts.scheme!r}; only http/https allowed",
        )
    host = (parts.hostname or "").strip().lower()
    if not host:
        raise HTTPException(status_code=422, detail="URL has no hostname")
    if (
        host == "localhost"
        or host.endswith(".local")
        or host.startswith("opensweep_")
        or host.startswith("opensweep-")
        or host in _denied_hosts()
    ):
        raise HTTPException(
            status_code=422, detail=f"refusing to fetch internal host {host!r}"
        )
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if _ip_forbidden(literal):
            raise HTTPException(
                status_code=422,
                detail=f"refusing to fetch non-public address {host!r}",
            )
        return None
    return host


async def _assert_public_http_url(url: str) -> None:
    """SSRF guard: only public http(s) URLs pass.

    Runs the sync string/IP-literal checks, then resolves the hostname on the
    event loop's resolver (non-blocking) and rejects names whose DNS
    resolution includes ANY internal address (DNS-rebinding baseline).
    Raises HTTPException 422 on rejection.
    """
    host = _check_public_url_syntax(url)
    if host is None:
        return
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, None, proto=socket.IPPROTO_TCP
        )
    except socket.gaierror as exc:
        raise HTTPException(
            status_code=422, detail=f"hostname {host!r} does not resolve: {exc}"
        ) from None
    for info in infos:
        try:
            resolved = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if _ip_forbidden(resolved):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"refusing to fetch {host!r}: resolves to non-public "
                    f"address {info[4][0]}"
                ),
            )


def _strip_html(text: str) -> str:
    text = _SCRIPT_STYLE_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


_MAX_REDIRECTS = 3
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


async def fetch_url(
    *,
    url: str,
    max_chars: int = 40_000,
    **_: Any,
) -> dict[str, Any]:
    """Fetch a public web page and return its readable text.

    Read-only. HTML responses are reduced to plain text (scripts, styles,
    and tags stripped; whitespace collapsed); other content types are
    returned as-is. The body is capped at the deployment's byte limit and
    the returned text at `max_chars` — `truncated` tells you when either
    cap hit.

    Only PUBLIC http(s) URLs are allowed: internal hosts (localhost,
    opensweep_* services, private/link-local addresses — including via DNS)
    are rejected with 422. Upstream failures return `{"status": "error",
    "detail": ...}` instead of failing the run.

    Success shape: `{"status": "ok", "url": <final URL after redirects>,
    "content_type": ..., "text": ..., "truncated": bool}`.
    """
    max_bytes = int(settings.OPENSWEEP_WEB_FETCH_MAX_BYTES)
    # Redirects are followed MANUALLY so every hop's URL is validated BEFORE
    # its request is sent — httpx's follow_redirects would issue the request
    # first and only let us inspect resp.history after the fact (TOCTOU).
    current = url
    body = b""
    content_type = ""
    encoding = "utf-8"
    final_url = url
    truncated = False
    try:
        async with httpx.AsyncClient(
            follow_redirects=False, timeout=_timeout()
        ) as client:
            for _hop in range(_MAX_REDIRECTS + 1):
                await _assert_public_http_url(current)
                async with client.stream(
                    "GET", current, headers={"User-Agent": "opensweep-platform"}
                ) as resp:
                    if resp.status_code in _REDIRECT_STATUSES:
                        location = (resp.headers.get("location") or "").strip()
                        if not location:
                            return {
                                "status": "error",
                                "detail": f"redirect from {current} has no Location header",
                            }
                        current = urljoin(current, location)
                        continue
                    resp.raise_for_status()

                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in resp.aiter_bytes():
                        chunks.append(chunk)
                        total += len(chunk)
                        if total >= max_bytes:
                            truncated = True
                            break
                    body = b"".join(chunks)[:max_bytes]
                    content_type = resp.headers.get("content-type", "")
                    encoding = resp.charset_encoding or "utf-8"
                    final_url = str(resp.url)
                    break
            else:
                return {
                    "status": "error",
                    "detail": f"too many redirects (max {_MAX_REDIRECTS})",
                }
    except HTTPException:
        raise
    except Exception as exc:  # keep agent runs alive on upstream failure
        return {"status": "error", "detail": str(exc)}

    text = body.decode(encoding, errors="replace")
    if "html" in content_type.lower():
        text = _strip_html(text)
    if len(text) > max_chars:
        truncated = True
    return {
        "status": "ok",
        "url": final_url,
        "content_type": content_type,
        "text": text[:max_chars],
        "truncated": truncated,
    }
