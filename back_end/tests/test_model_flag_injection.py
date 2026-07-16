"""with_model_flag — the provider's model (incl. per-stage workflow override)
must reach claude/codex CLIs whose templates have no {{model}} placeholder.

The workflow override is applied in-memory to `provider.model` before argv
construction, so injecting `provider.model` covers both the provider's own
model and the per-stage override.
"""

from domains.llm_providers.services.llm_executor import with_model_flag


def test_claude_gets_model_appended_when_template_lacks_placeholder():
    argv = ["claude", "-p", "hi", "--output-format", "stream-json"]
    out = with_model_flag(
        argv, kind="claude_subscription", model="claude-sonnet-4-6", template="claude -p {{instruction_q}}"
    )
    assert out[-2:] == ["--model", "claude-sonnet-4-6"]


def test_template_with_model_placeholder_is_left_alone():
    argv = ["claude", "-p", "hi", "--model", "claude-opus-4-8"]
    out = with_model_flag(
        argv,
        kind="claude_subscription",
        model="claude-opus-4-8",
        template="claude -p {{instruction_q}} --model {{model_q}}",
    )
    assert out == argv


def test_explicit_model_flag_in_argv_is_not_duplicated():
    argv = ["claude", "-p", "hi", "--model", "claude-opus-4-8"]
    out = with_model_flag(
        argv, kind="claude_subscription", model="claude-sonnet-4-6", template="claude -p {{instruction_q}} --model claude-opus-4-8"
    )
    assert out == argv


def test_empty_model_injects_nothing():
    argv = ["claude", "-p", "hi"]
    assert with_model_flag(argv, kind="claude_subscription", model="  ", template="claude -p x") == argv


def test_codex_model_lands_after_exec_subcommand():
    argv = ["codex", "exec", "--skip-git-repo-check", "--json", "prompt"]
    out = with_model_flag(
        argv, kind="codex_subscription", model="gpt-5-codex", template="codex exec --skip-git-repo-check --json {{instruction_q}}"
    )
    assert out[:4] == ["codex", "exec", "--model", "gpt-5-codex"]
    assert out[4:] == ["--skip-git-repo-check", "--json", "prompt"]


def test_codex_short_model_flag_is_respected():
    argv = ["codex", "exec", "-m", "gpt-5-codex", "prompt"]
    out = with_model_flag(
        argv, kind="codex_subscription", model="other", template="codex exec -m gpt-5-codex {{instruction_q}}"
    )
    assert out == argv


def test_other_kinds_pass_through():
    argv = ["opencode", "run", "hi"]
    assert with_model_flag(argv, kind="opencode", model="x", template="opencode run {{instruction_q}}") == argv
