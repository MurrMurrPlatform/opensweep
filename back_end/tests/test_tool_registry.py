"""Platform-tool registry contract — every registered tool carries a
non-empty one-line description (the prompt kit renders tool lists from
`tool_descriptions()`, so a missing description would ship a broken prompt)."""

from domains.platform_tools.dispatcher import _TOOLS, tool_descriptions, tool_names


def test_every_registered_tool_has_a_nonempty_description():
    descriptions = tool_descriptions()
    assert set(descriptions) == set(tool_names())
    for name, desc in descriptions.items():
        assert isinstance(desc, str) and desc.strip(), f"tool {name!r} has no description"


def test_registry_entries_are_callable_fn_description_pairs():
    for name, (fn, desc) in _TOOLS.items():
        assert callable(fn), f"tool {name!r} entry is not callable"
        assert desc.strip(), f"tool {name!r} has an empty description"


def test_prompt_kit_groups_only_name_registered_tools():
    from domains.executors import prompt_kit

    grouped = {
        *prompt_kit.PLATFORM_WRITE_TOOLS,
        *prompt_kit.PLATFORM_READ_TOOLS,
        *prompt_kit.ANALYSIS_TOOLS,
        *prompt_kit.NEWS_READ_TOOLS,
        *prompt_kit.NEWS_WRITE_TOOLS,
    }
    assert grouped <= set(tool_names())
