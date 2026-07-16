"""Provider fallback-chain selection (pure — llm_provider_service.choose_provider)."""

from types import SimpleNamespace

from domains.llm_providers.services.llm_provider_service import choose_provider


def provider(
    uid,
    *,
    label="",
    active=False,
    enabled=True,
    health="unknown",
    priority=100,
):
    return SimpleNamespace(
        uid=uid,
        label=label or uid,
        active=active,
        enabled=enabled,
        last_health_status=health,
        fallback_priority=priority,
    )


class TestActiveFirst:
    def test_active_provider_wins(self):
        ps = [provider("a", priority=1), provider("b", active=True, priority=99)]
        assert choose_provider(ps).uid == "b"

    def test_active_ok_health_wins_over_lower_priority_fallback(self):
        ps = [provider("fallback", priority=0), provider("act", active=True, health="ok")]
        assert choose_provider(ps).uid == "act"


class TestExclusion:
    def test_excluded_active_falls_back(self):
        ps = [provider("act", active=True), provider("next", priority=10)]
        assert choose_provider(ps, exclude_uids={"act"}).uid == "next"

    def test_excluded_fallbacks_are_skipped(self):
        ps = [
            provider("act", active=True),
            provider("p1", priority=1),
            provider("p2", priority=2),
        ]
        assert choose_provider(ps, exclude_uids={"act", "p1"}).uid == "p2"

    def test_all_excluded_returns_none(self):
        ps = [provider("act", active=True), provider("p1")]
        assert choose_provider(ps, exclude_uids={"act", "p1"}) is None


class TestFallbackOrdering:
    def test_ordered_by_fallback_priority(self):
        ps = [provider("high", priority=200), provider("low", priority=5)]
        assert choose_provider(ps).uid == "low"

    def test_priority_ties_break_by_label(self):
        ps = [
            provider("z", label="zeta", priority=50),
            provider("a", label="alpha", priority=50),
        ]
        assert choose_provider(ps).uid == "a"

    def test_missing_priority_defaults_to_100(self):
        no_priority = SimpleNamespace(
            uid="np", label="np", active=False, enabled=True,
            last_health_status="unknown", fallback_priority=None,
        )
        ps = [no_priority, provider("early", priority=99), provider("late", priority=101)]
        assert choose_provider(ps).uid == "early"
        assert choose_provider(ps, exclude_uids={"early"}).uid == "np"


class TestHealthAndEnabled:
    def test_disabled_providers_are_never_chosen(self):
        ps = [provider("off", enabled=False, priority=1), provider("on", priority=2)]
        assert choose_provider(ps).uid == "on"

    def test_unreachable_providers_are_never_chosen(self):
        ps = [provider("down", health="unreachable", priority=1), provider("up", priority=2)]
        assert choose_provider(ps).uid == "up"

    def test_unreachable_active_falls_back(self):
        ps = [provider("act", active=True, health="unreachable"), provider("next")]
        assert choose_provider(ps).uid == "next"

    def test_disabled_active_falls_back(self):
        ps = [provider("act", active=True, enabled=False), provider("next")]
        assert choose_provider(ps).uid == "next"

    def test_no_usable_provider_returns_none(self):
        ps = [provider("off", enabled=False), provider("down", health="unreachable")]
        assert choose_provider(ps) is None

    def test_empty_list_returns_none(self):
        assert choose_provider([]) is None
