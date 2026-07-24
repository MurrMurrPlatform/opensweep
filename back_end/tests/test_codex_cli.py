"""codex_cli is the single home for launching codex — both orchestrators use it.

These tests lock in the consolidation: the interactive turn path (turn_cli) and
the one-shot run path (executors/cli_tracking → llm_executor) must resolve their
codex helpers to the SAME objects in codex_cli, so a codex fix lands once. If a
path grows its own copy again, the identity assertions here fail.
"""

from domains.llm_providers.services import codex_cli


def test_run_and_turn_paths_share_one_codex_implementation():
    from domains.executors import cli_tracking
    from domains.llm_providers.services import llm_executor
    from domains.runs.services import turn_cli

    # Sandbox bypass, exec-stream parsing, and the running-total reducer are all
    # single-source in codex_cli — the historical names are thin re-exports.
    assert llm_executor.with_codex_sandbox_bypass is codex_cli.with_sandbox_bypass
    assert turn_cli.parse_codex_deltas is codex_cli.parse_deltas
    assert cli_tracking._codex_delta_feeder is codex_cli.delta_feeder


def test_base_exec_argv_is_the_invariant_head():
    assert codex_cli.base_exec_argv() == ["codex", "exec", "--skip-git-repo-check", "--json"]


def test_model_inserts_after_exec_and_defers_to_existing_flag():
    argv = codex_cli.with_model(["codex", "exec", "--json", "p"], model="gpt-5-codex")
    assert argv == ["codex", "exec", "--model", "gpt-5-codex", "--json", "p"]
    # Existing model flag wins; empty model is a no-op.
    assert codex_cli.with_model(["codex", "exec", "-m", "x", "p"], model="y") == [
        "codex", "exec", "-m", "x", "p",
    ]
    assert codex_cli.with_model(["codex", "exec", "p"], model="  ") == ["codex", "exec", "p"]
