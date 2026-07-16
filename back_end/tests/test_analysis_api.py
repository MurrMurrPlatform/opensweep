"""Analysis API surface — read + interactive routes are registered."""

import inspect

from domains.analysis.services.analysis_service import AnalysisService


def test_read_and_interactive_routes_exist():
    import api.v1.analysis as m

    paths = {r.path for r in m.router.routes}
    assert "/api/v1/analyses" in paths
    assert "/api/v1/analyses/latest" in paths
    assert "/api/v1/analyses/{uid}" in paths
    assert "/api/v1/analyses/{uid}/questions/{qid}/answer" in paths
    assert "/api/v1/analyses/{uid}/questions/{qid}/dismiss" in paths
    assert "/api/v1/analyses/{uid}/refine" in paths


def test_latest_declared_before_uid_so_static_path_wins():
    # /latest must be matched before /{uid} or it'd be swallowed as a uid.
    import api.v1.analysis as m

    order = [r.path for r in m.router.routes if r.path.startswith("/api/v1/analyses/")]
    assert order.index("/api/v1/analyses/latest") < order.index("/api/v1/analyses/{uid}")


def test_service_exposes_interactive_methods():
    for name in ("answer_question", "dismiss_question", "refine_with_answers"):
        assert callable(getattr(AnalysisService, name))
    # refine takes the analysis uid + who triggered it.
    params = set(inspect.signature(AnalysisService.refine_with_answers).parameters)
    assert {"uid", "triggered_by"} <= params
