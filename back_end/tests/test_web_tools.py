"""web_tools SSRF guard + degrade-gracefully behavior — pure Python, no network.

The guard is split: `_check_public_url_syntax` is the sync, I/O-free core
(schemes, denylisted hosts, IP-literal ranges) and `_assert_public_http_url`
is the async wrapper that adds non-blocking DNS resolution. Every internal
shape must be rejected with 422. DNS is monkeypatched (on the running loop's
resolver) so the tests never resolve real hostnames.
"""

import asyncio
import socket

import pytest
from fastapi import HTTPException

from domains.platform_tools import web_tools
from domains.platform_tools.web_tools import (
    _assert_public_http_url,
    _check_public_url_syntax,
    _parse_trendshift_html,
    web_search,
)

REJECTED_URLS = [
    "file:///etc/passwd",
    "http://localhost",
    "http://127.0.0.1",
    "http://10.0.0.1",
    "http://192.168.1.1:8080",
    "http://[::1]",
    "http://169.254.169.254",  # cloud metadata endpoint (link-local)
    "http://opensweep_backend:8000",
    "http://foo.local",
]


@pytest.mark.parametrize("url", REJECTED_URLS)
def test_rejects_internal_urls(url):
    """String/IP-literal rejections need no DNS — the sync core catches them."""
    with pytest.raises(HTTPException) as exc:
        _check_public_url_syntax(url)
    assert exc.value.status_code == 422


def test_rejects_hosts_derived_from_settings(monkeypatch):
    """The deployment's own service hostnames (SEARXNG_URL /
    OPENSWEEP_BACKEND_INTERNAL_URL) are denied even when they don't match the
    opensweep_ prefix rule."""
    monkeypatch.setattr(
        web_tools.settings, "SEARXNG_URL", "http://searx.internal:8080", raising=False
    )
    monkeypatch.setattr(
        web_tools.settings,
        "OPENSWEEP_BACKEND_INTERNAL_URL",
        "http://backend.internal:8000",
        raising=False,
    )
    for url in ("http://searx.internal/search", "https://backend.internal/api"):
        with pytest.raises(HTTPException) as exc:
            _check_public_url_syntax(url)
        assert exc.value.status_code == 422


def test_empty_settings_urls_deny_nothing(monkeypatch):
    monkeypatch.setattr(web_tools.settings, "SEARXNG_URL", "", raising=False)
    monkeypatch.setattr(
        web_tools.settings, "OPENSWEEP_BACKEND_INTERNAL_URL", "", raising=False
    )
    assert _check_public_url_syntax("https://example.com/x") == "example.com"


def test_public_ip_literal_needs_no_resolution():
    assert _check_public_url_syntax("http://140.82.121.4/page") is None


def _fake_resolver(ip: str):
    async def fake(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return fake


@pytest.mark.parametrize(
    "url", ["https://github.com", "https://news.ycombinator.com"]
)
async def test_accepts_public_hosts(url, monkeypatch):
    monkeypatch.setattr(
        asyncio.get_running_loop(), "getaddrinfo", _fake_resolver("140.82.121.4")
    )
    await _assert_public_http_url(url)  # must not raise


async def test_rejects_hostname_resolving_to_loopback(monkeypatch):
    """DNS-rebinding baseline: a public-looking name that resolves to an
    internal address is refused."""
    monkeypatch.setattr(
        asyncio.get_running_loop(), "getaddrinfo", _fake_resolver("127.0.0.1")
    )
    with pytest.raises(HTTPException) as exc:
        await _assert_public_http_url("http://evil.example.com")
    assert exc.value.status_code == 422


async def test_rejects_unresolvable_hostname(monkeypatch):
    async def fail(host, port, *args, **kwargs):
        raise socket.gaierror(8, "nodename nor servname provided")

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fail)
    with pytest.raises(HTTPException) as exc:
        await _assert_public_http_url("http://no-such-host.example")
    assert exc.value.status_code == 422


async def test_web_search_unavailable_without_searxng(monkeypatch):
    monkeypatch.setattr(web_tools.settings, "SEARXNG_URL", "", raising=False)
    out = await web_search(query="anything", mode="web")
    assert out["status"] == "unavailable"
    assert out["results"] == []


# Mimics trendshift.io's server-rendered homepage: a marquee ticker entry
# (name only, no description paragraph) followed by the main trending list
# where each repo anchor is followed by a text-muted-foreground description.
TRENDSHIFT_HTML = """
<p class="text-[13px] leading-snug"><a href="/repositories/19761">OpenCut-app/OpenCut</a></p>
<div class="divide-border divide-y">
  <a class="text-foreground/80" href="/repositories/19761">OpenCut-app/OpenCut</a>
  <a aria-label="repo page" href="/repositories/19761"><svg></svg></a>
  <p class="text-muted-foreground text-sm leading-5">The open-source CapCut alternative</p>
  <a class="text-foreground/80" href="/repositories/14644">firecrawl/firecrawl</a>
  <p class="text-muted-foreground text-sm leading-5">Turn websites into LLM-ready data</p>
  <a class="text-foreground/80" href="/repositories/99999">someone/bare-repo</a>
</div>
"""


def test_parse_trendshift_dedupes_and_reads_descriptions():
    results = _parse_trendshift_html(TRENDSHIFT_HTML, "", 30)
    assert [r["title"] for r in results] == [
        "OpenCut-app/OpenCut",
        "firecrawl/firecrawl",
        "someone/bare-repo",
    ]
    by_title = {r["title"]: r for r in results}
    # ticker entry has no description; the main-list occurrence backfills it
    assert by_title["OpenCut-app/OpenCut"]["snippet"] == (
        "The open-source CapCut alternative"
    )
    assert by_title["OpenCut-app/OpenCut"]["url"] == (
        "https://github.com/OpenCut-app/OpenCut"
    )
    assert by_title["someone/bare-repo"]["snippet"] == (
        "Trending repository on trendshift.io"
    )
    assert all(r["source"] == "trendshift" for r in results)


def test_parse_trendshift_query_filters_and_limit_caps():
    results = _parse_trendshift_html(TRENDSHIFT_HTML, "firecrawl", 30)
    assert [r["title"] for r in results] == ["firecrawl/firecrawl"]
    # tokens also match against descriptions
    results = _parse_trendshift_html(TRENDSHIFT_HTML, "capcut", 30)
    assert [r["title"] for r in results] == ["OpenCut-app/OpenCut"]
    assert len(_parse_trendshift_html(TRENDSHIFT_HTML, "", 2)) == 2


async def test_web_search_trendshift_mode_degrades_on_upstream_failure(monkeypatch):
    async def boom(query, limit):
        raise RuntimeError("upstream down")

    monkeypatch.setitem(web_tools._SEARCH_MODES, "trendshift", boom)
    out = await web_search(query="", mode="trendshift")
    assert out["status"] == "error"
    assert out["results"] == []
