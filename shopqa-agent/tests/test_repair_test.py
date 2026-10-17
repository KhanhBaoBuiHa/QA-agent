
from unittest.mock import MagicMock

from shopqa.nodes.stubs import repair_test


def make_state(verdict="test_error"):
    return {
        "spec": "Product page should display the product name.",
        "base_url": "http://localhost:8000",
        "app_context": "Product link uses selector text=Product",
        "run_id": "test-run",
        "test_cases": [
            {
                "id": "TC01",
                "title": "Open product page",
                "steps": ["Click the product link"],
                "expected": "Product name is displayed",
                "actions": [
                    {"action": "click", "target": "#old-selector"}
                ],
            }
        ],
        "results": [
            {
                "test_id": "TC01",
                "passed": False,
                "log": "Locator timed out",
                "screenshots": [],
                "failed_step": "Click product",
                "error_type": "element_not_found",
            }
        ],
        "findings": [
            {
                "test_id": "TC01",
                "verdict": verdict,
                "reason": "The selector may be incorrect",
            }
        ],
        "repair_attempts": 0,
        "max_repairs": 3,
        "report": "",
    }


def test_repair_updates_test_case():
    state = make_state()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = MagicMock(
        content=(
            '{"steps":["Click the product link"],'
            '"actions":[{"action":"click","target":"text=Product"}]}'
        )
    )

    result = repair_test(state, llm=fake_llm)

    assert result["repair_attempts"] == 1
    assert result["test_cases"][0]["actions"][0]["target"] == "text=Product"
    assert state["test_cases"][0]["actions"][0]["target"] == "#old-selector"


def test_repair_does_not_change_real_bug():
    state = make_state(verdict="real_bug")
    fake_llm = MagicMock()

    result = repair_test(state, llm=fake_llm)

    assert result["repair_attempts"] == 1
    assert "test_cases" not in result
    fake_llm.invoke.assert_not_called()


def test_invalid_llm_response_keeps_original_test():
    state = make_state()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = MagicMock(
        content="not valid JSON"
    )

    result = repair_test(state, llm=fake_llm)

    assert result["repair_attempts"] == 1
    assert result["test_cases"][0]["actions"] == state["test_cases"][0]["actions"]
