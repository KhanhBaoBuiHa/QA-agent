
from shopqa.nodes.stubs import classify
from unittest.mock import MagicMock


def make_state(error_type="element_not_found"):
    return {
        "spec": "The product page should display the product name.",
        "app_context": "E-commerce website",
        "test_cases": [
            {
                "id": "TC04",
                "steps": [{"action": "click", "target": "product"}],
                "expected": "Product name is displayed",
            }
        ],
        "results": [
            {
                "test_id": "TC04",
                "passed": False,
                "error_type": error_type,
                "log": "Locator timed out",
                "failed_step": "Click product",
                "screenshots": [],
            }
        ],
    }


def test_llm_classifies_real_bug():
    state = make_state()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = MagicMock(
        content='{"verdict": "real_bug", "reason": "Product name is missing"}'
    )

    result = classify(state, llm=fake_llm)

    assert result["findings"][0]["verdict"] == "real_bug"
    fake_llm.invoke.assert_called_once()


def test_llm_classifies_test_error():
    state = make_state()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = MagicMock(
        content='{"verdict": "test_error", "reason": "The locator is incorrect"}'
    )

    result = classify(state, llm=fake_llm)

    assert result["findings"][0]["verdict"] == "test_error"


def test_llm_invalid_json_falls_back_to_inconclusive():
    state = make_state()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = MagicMock(
        content="This is not valid JSON"
    )

    result = classify(state, llm=fake_llm)

    assert result["findings"][0]["verdict"] == "inconclusive"
    

def test_pass_result_is_classified_as_pass():
    state = {
        "results": [{
            "test_id": "TC01",
            "passed": True,
            "error_type": "",
            "log": "All steps passed",
        }]
    }

    result = classify(state)

    assert result["findings"][0]["verdict"] == "pass"


def test_invalid_action_is_classified_as_test_error():
    state = {
        "results": [{
            "test_id": "TC02",
            "passed": False,
            "error_type": "invalid_action",
            "log": "Unsupported action: hover",
        }]
    }

    result = classify(state)

    assert result["findings"][0]["verdict"] == "test_error"


def test_missing_element_is_inconclusive():
    state = {
        "results": [{
            "test_id": "TC03",
            "passed": False,
            "error_type": "element_not_found",
            "log": "Locator timed out",
        }]
    }

    result = classify(state)

    assert result["findings"][0]["verdict"] == "inconclusive"
