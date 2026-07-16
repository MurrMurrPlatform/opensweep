"""Pure-Python test: NewsItem dedupe_key stability + URL-identity collisions."""

import string

from domains.news.services.dedupe import build_news_dedupe_key


def _key(url: str = "", title: str = "", repo: str = "r1") -> str:
    return build_news_dedupe_key(repository_uid=repo, url=url, title=title)


def test_url_identity_variants_collide():
    """Scheme, www., trailing slash, tracking params and fragments all vary
    without changing story identity — every variant must produce one key."""
    canonical = _key(url="http://example.com/post")
    variants = [
        "https://example.com/post",
        "https://www.example.com/post",
        "https://www.example.com/post/",
        "https://example.com/post?utm_source=hn&utm_medium=social",
        "https://example.com/post?ref=homepage",
        "https://example.com/post?fbclid=abc123",
        "https://example.com/post?gclid=xyz",
        "https://example.com/post/#comments",
    ]
    for v in variants:
        assert _key(url=v) == canonical, v


def test_tracking_lookalike_params_are_meaningful():
    """Only EXACT tracking params are stripped: ref_id/ref_src/gclidx-style
    prefixed lookalikes carry identity and must differentiate URLs."""
    canonical = _key(url="https://example.com/post")
    for lookalike in (
        "https://example.com/post?ref_id=42",
        "https://example.com/post?ref_src=twsrc",
        "https://example.com/post?gclidx=abc",
        "https://example.com/post?fbclid2=abc",
    ):
        assert _key(url=lookalike) != canonical, lookalike


def test_query_param_order_does_not_matter():
    a = _key(url="https://example.com/search?a=1&b=2")
    b = _key(url="https://example.com/search?b=2&a=1")
    assert a == b


def test_meaningful_query_params_differ():
    a = _key(url="https://example.com/item?id=1")
    b = _key(url="https://example.com/item?id=2")
    assert a != b


def test_repository_separates_keys():
    a = _key(url="https://example.com/post", repo="r1")
    b = _key(url="https://example.com/post", repo="r2")
    assert a != b


def test_title_fallback_when_url_empty():
    a = _key(title="Rust 1.80 Released!")
    b = _key(title="rust 199 released")  # case/digit/punctuation-insensitive
    assert a == b


def test_title_fallback_different_titles_differ():
    assert _key(title="Rust released") != _key(title="Zig released")


def test_key_is_24_hex_chars():
    for k in (_key(url="https://example.com/x"), _key(title="t"), _key()):
        assert isinstance(k, str)
        assert len(k) == 24
        assert set(k) <= set(string.hexdigits.lower())


def test_url_present_ignores_title():
    a = _key(url="https://example.com/post", title="Headline A")
    b = _key(url="https://example.com/post", title="Completely different headline")
    assert a == b
