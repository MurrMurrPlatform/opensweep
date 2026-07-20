"""Campaign planning — pure partition + part-list math, no DB.

`normalize_areas` sizes the docs' watch scopes against the repository's
real file tree (split oversized, merge tiny, sweep uncovered paths into a
remainder area); `build_plan` turns areas + lenses into the campaign's
part list per template. Both are pure so the whole planning surface is
unit-testable; campaign_service supplies the loaded docs/tree/lenses.
"""

from __future__ import annotations

from datetime import datetime

from domains.docs.services.doc_freshness import watches_path

# Target area size in files: areas above target_max are split by first-level
# subdirectory; adjacent areas below target_min are merged.
DEFAULT_TARGET_MIN = 50
DEFAULT_TARGET_MAX = 150

REMAINDER_TITLE = "Uncovered paths"


def _normalize(path: str) -> str:
    return (path or "").strip().replace("\\", "/").lstrip("./").rstrip("/")


def _area(
    title: str,
    scope_paths: list[str],
    doc_uids: list[str],
    file_count: int | None,
) -> dict:
    return {
        "title": title,
        "scope_paths": scope_paths,
        "doc_uids": doc_uids,
        "file_count": file_count,
    }


def _split_by_subdir(area: dict, matched: list[str]) -> list[dict]:
    """Split an oversized area by first-level subdirectory beneath each of
    its watch prefixes. Files sitting directly under a prefix stay grouped
    under the prefix itself."""
    groups: dict[str, list[str]] = {}
    order: list[str] = []
    for path in matched:
        prefix = next(
            (
                w
                for w in area["scope_paths"]
                if path == w or path.startswith(w + "/")
            ),
            "",
        )
        rest = path[len(prefix) :].lstrip("/") if prefix else path
        if prefix and "/" in rest:
            key = f"{prefix}/{rest.split('/', 1)[0]}"
        else:
            key = prefix or path.split("/", 1)[0]
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(path)
    return [
        _area(
            f"{area['title']} — {key.rsplit('/', 1)[-1]}",
            [key],
            list(area["doc_uids"]),
            len(groups[key]),
        )
        for key in sorted(order)
    ]


def _merge_tiny(areas: list[dict], *, target_min: int) -> list[dict]:
    """Merge runs of adjacent tiny areas (< target_min files) into one part.
    Areas without a file count (tree unavailable) are never merged."""
    out: list[dict] = []
    buffer: list[dict] = []

    def _flush() -> None:
        if not buffer:
            return
        if len(buffer) == 1:
            out.append(buffer[0])
        else:
            out.append(
                _area(
                    " + ".join(a["title"] for a in buffer),
                    [p for a in buffer for p in a["scope_paths"]],
                    list(dict.fromkeys(u for a in buffer for u in a["doc_uids"])),
                    sum(a["file_count"] or 0 for a in buffer),
                )
            )
        buffer.clear()

    for area in areas:
        count = area["file_count"]
        if count is None or count >= target_min:
            _flush()
            out.append(area)
            continue
        buffer.append(area)
        if sum(a["file_count"] or 0 for a in buffer) >= target_min:
            _flush()
    _flush()
    return out


def normalize_areas(
    docs: list[dict],
    file_paths: list[str],
    *,
    target_min: int = DEFAULT_TARGET_MIN,
    target_max: int = DEFAULT_TARGET_MAX,
) -> list[dict]:
    """Docs' watch scopes → right-sized area dicts against the real tree.

    `docs` are {uid, slug, title, watch_paths}; `file_paths` the repo's blob
    paths. Prefix matching reuses doc_freshness.watches_path. When the tree
    is unavailable (empty file_paths) every watched doc becomes one area
    with file_count=None and no remainder — sizing degrades, planning never
    fails.
    """
    watched = [d for d in docs if [p for p in (d.get("watch_paths") or []) if _normalize(p)]]

    if not file_paths:
        return [
            _area(
                str(d.get("title") or d.get("slug") or ""),
                [_normalize(p) for p in (d.get("watch_paths") or []) if _normalize(p)],
                [str(d["uid"])] if d.get("uid") else [],
                None,
            )
            for d in watched
        ]

    paths = [p for p in (_normalize(p) for p in file_paths) if p]
    areas: list[dict] = []
    covered: set[str] = set()
    for d in watched:
        watch = [_normalize(p) for p in (d.get("watch_paths") or []) if _normalize(p)]
        matched = [p for p in paths if watches_path(watch, p)]
        covered.update(matched)
        area = _area(
            str(d.get("title") or d.get("slug") or ""),
            watch,
            [str(d["uid"])] if d.get("uid") else [],
            len(matched),
        )
        if len(matched) > target_max:
            areas.extend(_split_by_subdir(area, matched))
        else:
            areas.append(area)
    areas = _merge_tiny(areas, target_min=target_min)

    uncovered = [p for p in paths if p not in covered]
    if uncovered:
        remainder = _area(
            REMAINDER_TITLE,
            sorted({p.split("/", 1)[0] for p in uncovered}),
            [],
            len(uncovered),
        )
        if len(uncovered) > target_max:
            areas.extend(
                _merge_tiny(
                    _split_by_subdir(
                        _area(REMAINDER_TITLE, remainder["scope_paths"], [], len(uncovered)),
                        uncovered,
                    ),
                    target_min=target_min,
                )
            )
        else:
            areas.append(remainder)
    return areas


def _area_recency(
    area: dict, path_recency: dict[str, datetime | None]
) -> datetime | None:
    """The area's coverage age: for each scope path, the latest covered
    stamp under it; the area scores by its STALEST scope path. None = some
    scope path was never covered (ranks first for rotation)."""
    per_scope: list[datetime | None] = []
    for scope in area.get("scope_paths") or []:
        latest: datetime | None = None
        for path, at in path_recency.items():
            if at is None or not (path == scope or path.startswith(scope + "/")):
                continue
            if latest is None or at > latest:
                latest = at
        per_scope.append(latest)
    if not per_scope or any(v is None for v in per_scope):
        return None
    return min(v for v in per_scope if v is not None)


def _part(idx: int, kind: str, title: str, area: dict | None, lens_keys: list[str]) -> dict:
    return {
        "idx": idx,
        "kind": kind,
        "title": title,
        "scope_paths": list((area or {}).get("scope_paths") or []),
        "doc_uids": list((area or {}).get("doc_uids") or []),
        "lens_keys": list(lens_keys),
        "run_uid": "",
        "state": "pending",
        "file_count": (area or {}).get("file_count"),
    }


def build_plan(
    template: str,
    areas: list[dict],
    lenses: list[dict],
    *,
    k: int = 3,
    path_recency: dict[str, datetime | None] | None = None,
    focus_lens: str | None = None,
) -> list[dict]:
    """Areas + lenses → the campaign's ordered part list.

    - full:     every area (all enabled local lenses) + one global part per
                enabled global lens.
    - rotation: the k least-recently-covered areas (never-covered first,
                scored by `path_recency` over their scope paths); no globals.
    - focused:  every area with just `focus_lens`, plus that lens's global
                sweep when it names a global agent.

    Parts get idx assigned sequentially, areas before globals.
    """
    enabled = [dict(lens) for lens in lenses if lens.get("enabled", True)]
    local = [lens for lens in enabled if (lens.get("scope") or "local") == "local"]
    global_ = [lens for lens in enabled if lens.get("scope") == "global"]
    local_keys = [str(lens["key"]) for lens in local]

    def _global_part(lens: dict) -> dict:
        return _part(0, "global", f"Global sweep — {lens['key']}", None, [str(lens["key"])])

    picked: list[dict]
    globals_out: list[dict]
    if template == "rotation":
        recency = path_recency or {}
        scored = [(i, _area_recency(a, recency)) for i, a in enumerate(areas)]
        _EPOCH = datetime.min
        scored.sort(key=lambda pair: (pair[1] is not None, pair[1] or _EPOCH, pair[0]))
        picked = [
            _part(0, "area", areas[i]["title"], areas[i], local_keys)
            for i, _ in scored[: max(k, 0)]
        ]
        globals_out = []
    elif template == "focused":
        focus = str(focus_lens or "")
        picked = [_part(0, "area", a["title"], a, [focus]) for a in areas]
        lens = next((lens for lens in enabled if str(lens.get("key")) == focus), None)
        globals_out = (
            [_global_part(lens)] if lens is not None and lens.get("global_agent_key") else []
        )
    else:  # full
        picked = [_part(0, "area", a["title"], a, local_keys) for a in areas]
        globals_out = [_global_part(lens) for lens in global_]

    parts = picked + globals_out
    for idx, part in enumerate(parts):
        part["idx"] = idx
    return parts
