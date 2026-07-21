"""Pure tests for codex auth.json document helpers — no Neo4j, no I/O."""

import json

from domains.llm_providers.services import codex_auth


def _doc(access="a1", refresh="r1", idt="i1", account="acct-1", last="2026-07-20T01:00:00Z", **extra):
    d = {
        "OPENAI_API_KEY": None,
        "auth_mode": "chatgpt",
        "tokens": {
            "id_token": idt,
            "access_token": access,
            "refresh_token": refresh,
            "account_id": account,
        },
        "last_refresh": last,
    }
    d.update(extra)
    return json.dumps(d)


def test_is_valid_true_for_access_token():
    assert codex_auth.is_valid(_doc()) is True


def test_is_valid_false_for_garbage_or_missing_token():
    assert codex_auth.is_valid("not json") is False
    assert codex_auth.is_valid("") is False
    assert codex_auth.is_valid(_doc(access="")) is False
    assert codex_auth.is_valid(json.dumps({"tokens": {}})) is False


def test_account_id_extraction():
    assert codex_auth.account_id(_doc(account="acct-9")) == "acct-9"
    assert codex_auth.account_id("nope") == ""


def test_same_account_matches_and_blocks_mismatch():
    assert codex_auth.same_account(_doc(account="x"), _doc(account="x")) is True
    assert codex_auth.same_account(_doc(account="x"), _doc(account="y")) is False


def test_same_account_permits_when_seed_has_no_account():
    seed = json.dumps({"tokens": {"access_token": "a"}})
    assert codex_auth.same_account(seed, _doc(account="y")) is True


def test_changed_detects_rotated_tokens_and_last_refresh():
    seed = _doc(access="a1", refresh="r1", last="t1")
    assert codex_auth.changed(seed, _doc(access="a2", refresh="r1", last="t1")) is True
    assert codex_auth.changed(seed, _doc(access="a1", refresh="r2", last="t1")) is True
    assert codex_auth.changed(seed, _doc(access="a1", refresh="r1", last="t2")) is True


def test_changed_false_for_reformatted_identical_tokens():
    seed = _doc()
    # Same fields, different whitespace/key order → not a real change.
    reserialized = json.dumps(json.loads(seed), indent=2, sort_keys=True)
    assert codex_auth.changed(seed, reserialized) is False


def test_looks_like_reauth_signatures():
    assert codex_auth.looks_like_reauth("Your access token could not be refreshed.")
    assert codex_auth.looks_like_reauth("Please log out and sign in again")
    assert codex_auth.looks_like_reauth("error: not logged in")
    assert codex_auth.looks_like_reauth("codex exited 1: some transient network blip") is False


def test_decide_write_back_persist_on_valid_rotation():
    seed = _doc(access="a1")
    rotated = _doc(access="a2")
    assert codex_auth.decide_write_back(seed, rotated) == codex_auth.PERSIST


def test_decide_write_back_noop_when_unchanged_or_absent():
    seed = _doc()
    assert codex_auth.decide_write_back(seed, seed) == codex_auth.NOOP
    assert codex_auth.decide_write_back(seed, None) == codex_auth.NOOP


def test_decide_write_back_uncertain_on_changed_but_invalid():
    seed = _doc()
    # A truncated/partial file that differs from the seed and does not parse to
    # a usable credential → codex may have died mid-rotation.
    assert codex_auth.decide_write_back(seed, '{"tokens": {"access_token": ') == codex_auth.UNCERTAIN


def test_decide_write_back_rejects_account_swap():
    seed = _doc(account="acct-1", access="a1")
    other = _doc(account="acct-2", access="a2")
    assert codex_auth.decide_write_back(seed, other) == codex_auth.REJECT_ACCOUNT
