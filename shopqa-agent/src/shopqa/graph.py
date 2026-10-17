"""Dựng đồ thị LangGraph cho ShopQA-Agent.

Luồng:
  generate_tests -> run_tests -> classify
  classify -> repair_test -> run_tests   (nếu có test_error và còn lượt sửa)
  classify -> report -> END              (trường hợp còn lại)

build_graph(self_repair=False) cho ra phiên bản A (không tự sửa),
build_graph(self_repair=True) cho ra phiên bản B (có vòng tự sửa),
để so sánh hai phiên bản trên cùng bộ lỗi cài sẵn.
"""
from langgraph.graph import END, START, StateGraph

from shopqa.nodes import classify, generate_tests, repair_test, report, run_tests
from shopqa.state import AgentState


def make_router(self_repair: bool):
    """Quyết định có chuyển sang vòng tự sửa hay không."""

    def route_after_classify(state: AgentState) -> str:
        has_test_error = any(
            finding["verdict"] == "test_error"
            for finding in state["findings"]
        )
        can_repair = (
            state["repair_attempts"] < state["max_repairs"]
        )

        if self_repair and has_test_error and can_repair:
            return "repair_test"

        return "report"

    return route_after_classify


def build_graph(self_repair: bool = True):
    g = StateGraph(AgentState)

    g.add_node("generate_tests", generate_tests)
    g.add_node("run_tests", run_tests)
    g.add_node("classify", classify)
    g.add_node("repair_test", repair_test)
    g.add_node("report", report)

    g.add_edge(START, "generate_tests")
    g.add_edge("generate_tests", "run_tests")
    g.add_edge("run_tests", "classify")
    g.add_conditional_edges(
        "classify",
        make_router(self_repair),
        {"repair_test": "repair_test", "report": "report"},
    )
    g.add_edge("repair_test", "run_tests")   # vòng lặp tự sửa
    g.add_edge("report", END)

    return g.compile()

