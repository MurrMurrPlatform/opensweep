"""Per-repo analyzer config normalization (§E) — pure."""

from domains.repositories.services.analyzer_config import _normalize


def test_defaults_to_auto_with_no_tools():
    assert _normalize(None) == {"mode": "auto", "tools": []}
    assert _normalize({}) == {"mode": "auto", "tools": []}


def test_junk_mode_falls_back_to_auto():
    assert _normalize({"mode": "yolo"})["mode"] == "auto"
    assert _normalize({"mode": "off"})["mode"] == "off"


def test_unknown_tools_are_dropped_and_shapes_coerced():
    config = _normalize(
        {
            "mode": "custom",
            "tools": [
                {"tool": "semgrep", "args": ["--config", "p/ci"], "paths": ["back_end/"], "junk": 1},
                {"tool": "bogus"},
                {"tool": "ruff"},
            ],
        }
    )
    assert config["mode"] == "custom"
    assert config["tools"] == [
        {"tool": "semgrep", "args": ["--config", "p/ci"], "paths": ["back_end/"]},
        {"tool": "ruff", "args": [], "paths": []},
    ]
