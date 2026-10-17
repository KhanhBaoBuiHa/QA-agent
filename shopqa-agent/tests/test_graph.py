
from unittest.mock import MagicMock

from shopqa.graph import build_graph, make_router


def make_state(verdict="test_error", repair_attempts=0, max_repairs=3):
    return {
        "spec": "Product page should display the product name.",
        "base_url": "http://localhost:8000",
        "app_context": "Product link uses selector text=Product",
        "run_id": "test-graph",
        "test_cases": [],
        "results": [],
        "findings": [
            {
                "test_id": "TC01",
                "verdict": verdict,
                "reason": "Test finding",
            }
        ],
        "repair_attempts": repair_attempts,
        "max_repairs": max_repairs,
        "report": "",
    }


def test_router_sends_test_error_to_repair_when_attempts_remain():
    router = make_router(self_repair=True)
    state = make_state(verdict="test_error")

    assert router(state) == "repair_test"


def test_router_sends_real_bug_to_report():
    router = make_router(self_repair=True)
    state = make_state(verdict="real_bug")

    assert router(state) == "report"


def test_router_stops_when_max_repairs_reached():
    router = make_router(self_repair=True)
    state = make_state(
        verdict="test_error",
        repair_attempts=3,
        max_repairs=3,
    )

    assert router(state) == "report"


def test_router_skips_repair_when_self_repair_disabled():
    router = make_router(self_repair=False)
    state = make_state(verdict="test_error")

    assert router(state) == "report"


def test_build_graph_returns_compiled_graph():
    graph = build_graph(self_repair=True)

    assert graph is not None
    assert hasattr(graph, "invoke")
