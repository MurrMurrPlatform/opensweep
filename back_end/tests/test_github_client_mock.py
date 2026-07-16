"""GitHubClient — httpx.MockTransport based tests, no network."""

import json

import httpx
import pytest

from infrastructure.github_client import GitHubClient


@pytest.mark.asyncio
async def test_inactive_when_token_unset():
    c = GitHubClient(token="")
    assert c.is_active is False
    with pytest.raises(RuntimeError):
        await c._get("/anything")
    await c.aclose()


@pytest.mark.asyncio
async def test_list_open_issues_parses_response(monkeypatch):
    body = [
        {"number": 1, "title": "First", "body": "b", "state": "open",
         "user": {"login": "alice"}, "labels": [{"name": "bug"}],
         "created_at": "2025-01-01T00:00:00Z"},
        # PRs should be filtered out by the service layer (this client returns raw).
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert "Authorization" in request.headers
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(handler)
    c = GitHubClient(token="x")
    c._client = httpx.AsyncClient(transport=transport, base_url="https://api.github.com",
                                   headers={"Authorization": "Bearer x", "Accept": "application/vnd.github+json"})
    out = await c.list_open_issues("acme", "repo")
    assert out[0]["number"] == 1
    await c.aclose()


@pytest.mark.asyncio
async def test_open_pull_request_posts_correct_body():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(201, json={"number": 42, "html_url": "https://github.com/x/y/pull/42"})

    transport = httpx.MockTransport(handler)
    c = GitHubClient(token="x")
    c._client = httpx.AsyncClient(transport=transport, base_url="https://api.github.com",
                                   headers={"Authorization": "Bearer x"})
    pr = await c.open_pull_request("acme", "repo", head="feat/x", base="main", title="t", body="b")
    assert pr["number"] == 42
    assert "/repos/acme/repo/pulls" in captured["url"]
    assert captured["json"] == {"head": "feat/x", "base": "main", "title": "t", "body": "b", "draft": False}
    await c.aclose()


# ── Check-run pagination (CI rollup must not truncate at 30) ────────────────


def _check_run_page(start: int, count: int) -> dict:
    return {
        "total_count": 130,
        "check_runs": [
            {"name": f"check-{i}", "status": "completed", "conclusion": "success"}
            for i in range(start, start + count)
        ],
    }


@pytest.mark.asyncio
async def test_list_check_runs_paginates_and_filters_latest():
    seen_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        if "page=2" in str(request.url):
            return httpx.Response(200, json=_check_run_page(100, 30))
        return httpx.Response(
            200,
            json=_check_run_page(0, 100),
            headers={
                "Link": '<https://api.github.com/repos/acme/repo/commits/abc/check-runs'
                '?per_page=100&filter=latest&page=2>; rel="next"'
            },
        )

    c = GitHubClient(token="x")
    c._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.github.com"
    )
    runs = await c.list_check_runs("acme", "repo", ref="abc")
    assert len(runs) == 130  # both pages, not just the first 30/100
    assert runs[0]["name"] == "check-0"
    assert runs[-1]["name"] == "check-129"
    # First request asks for big pages and only the latest check attempt.
    assert "per_page=100" in seen_urls[0]
    assert "filter=latest" in seen_urls[0]
    assert len(seen_urls) == 2
    await c.aclose()


@pytest.mark.asyncio
async def test_list_check_runs_caps_defensively():
    from infrastructure.github_client import MAX_CHECK_RUNS

    def handler(request: httpx.Request) -> httpx.Response:
        # Every page claims another next page — a pathological rollup.
        return httpx.Response(
            200,
            json=_check_run_page(0, 100),
            headers={
                "Link": '<https://api.github.com/repos/acme/repo/commits/abc/check-runs'
                '?per_page=100&page=99>; rel="next"'
            },
        )

    c = GitHubClient(token="x")
    c._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.github.com"
    )
    runs = await c.list_check_runs("acme", "repo", ref="abc")
    assert len(runs) == MAX_CHECK_RUNS  # capped, no infinite pagination
    await c.aclose()


# ── Loop-aware default client (Celery: fresh loop per asyncio.run) ──────────


def test_get_default_client_is_not_reused_across_event_loops():
    import asyncio

    from infrastructure.github_client import get_default_client

    async def grab():
        return get_default_client()

    first = asyncio.run(grab())
    second = asyncio.run(grab())
    # A client cached on a dead loop must never resurface on a new loop.
    assert first is not second


def test_get_default_client_is_cached_within_one_loop():
    import asyncio

    from infrastructure.github_client import get_default_client

    async def grab_twice():
        return get_default_client(), get_default_client()

    a, b = asyncio.run(grab_twice())
    assert a is b
