import json

import pytest

from shopqa.nodes.generate_tests import generate_tests
from shopqa.state import initial_state


class FakeLLM:
    """LLM giả: trả lần lượt các phản hồi đã định sẵn, ghi lại những gì được hỏi."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)

        class Msg:
            pass

        m = Msg()
        m.content = self.replies.pop(0)
        return m


VALID = {"tests": [{
    "id": "t1", "title": "Thêm vào giỏ", "steps": ["bấm thêm"], "expected": "giỏ có 1 món",
    "actions": [
        {"action": "goto", "target": "/"},
        {"action": "click", "target": '[data-testid="add-p1"]'},
        {"action": "expect_text", "target": '[data-testid="cart-count"]', "value": "1"},
    ]}]}


def _state():
    return initial_state("spec", "http://localhost:8000", "- <button> [data-testid=\"add-p1\"]")


def test_parses_fenced_json_and_returns_test_cases():
    llm = FakeLLM(["```json\n" + json.dumps(VALID) + "\n```"])
    out = generate_tests(_state(), llm=llm)
    assert out["test_cases"][0]["id"] == "t1"
    assert out["test_cases"][0]["actions"][1] == {"action": "click", "target": '[data-testid="add-p1"]'}


def test_retries_after_invalid_json():
    llm = FakeLLM(["xin chào, đây không phải JSON", json.dumps(VALID)])
    out = generate_tests(_state(), llm=llm)
    assert len(llm.calls) == 2
    assert len(out["test_cases"]) == 1
    # lần thử lại phải kèm lý do lỗi để LLM sửa
    assert "invalid" in llm.calls[1][-1].content


def test_rejects_action_missing_value_then_gives_up():
    bad = {"tests": [{"id": "t1", "title": "x", "expected": "y", "actions": [
        {"action": "goto", "target": "/"},
        {"action": "fill", "target": "#a"},           # thiếu value
        {"action": "expect_visible", "target": "#a"}]}]}
    llm = FakeLLM([json.dumps(bad)] * 3)
    with pytest.raises(ValueError, match="sau 3 lần"):
        generate_tests(_state(), llm=llm)


def test_rejects_test_without_assertion():
    bad = {"tests": [{"id": "t1", "title": "x", "expected": "y", "actions": [
        {"action": "goto", "target": "/"}, {"action": "click", "target": "#a"}]}]}
    llm = FakeLLM([json.dumps(bad), json.dumps(VALID)])
    out = generate_tests(_state(), llm=llm)
    assert len(llm.calls) == 2 and out["test_cases"][0]["id"] == "t1"


def test_prompt_includes_spec_and_ui_elements():
    llm = FakeLLM([json.dumps(VALID)])
    generate_tests(_state(), llm=llm)
    user_prompt = llm.calls[0][1].content
    assert "spec" in user_prompt and 'data-testid="add-p1"' in user_prompt
