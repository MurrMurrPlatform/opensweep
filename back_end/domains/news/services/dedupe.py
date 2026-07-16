"""Stable dedupe-key generation for NewsItems.

A NewsItem's dedupe_key collapses repeat filings of the same story across
scout runs. Keyed on the normalized URL when one is present (the same
article found via different searches must collide), falling back to the
normalized title for URL-less items.

URL normalisation strips the parts that vary without changing identity:
scheme, www., fragments, trailing slashes, and tracking query params.
"""

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from domains.findings.services.dedupe import _normalise_title

# Exact-match semantics: utm_* is a family (utm_source, utm_medium, …) but
# the bare names must match EXACTLY — prefixed lookalikes (ref_id, gclidx)
# are legitimate identity-bearing params and must survive normalisation.
_UTM_PARAM_RE = re.compile(r"^utm_[a-z0-9_]+$")
_TRACKING_PARAMS = {"ref", "fbclid", "gclid"}


def _is_tracking_param(name: str) -> bool:
    n = name.lower()
    return n in _TRACKING_PARAMS or bool(_UTM_PARAM_RE.fullmatch(n))


def _normalise_url(url: str) -> str:
    parts = urlsplit((url or "").strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/")
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking_param(k)
    ]
    qs = urlencode(sorted(query))
    return f"{host}{path}" + (f"?{qs}" if qs else "")


def build_news_dedupe_key(
    *,
    repository_uid: str,
    url: str,
    title: str,
) -> str:
    anchor = _normalise_url(url) if (url or "").strip() else _normalise_title(title)
    raw = "|".join([(repository_uid or ""), anchor])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]
