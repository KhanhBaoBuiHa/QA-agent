"""Node 1: sinh test case từ mô tả tính năng bằng LLM."""
import json
import os
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from shopqa.llm import get_llm, response_text
from shopqa.prompts import GENERATE_SYSTEM, build_generate_user_prompt
from shopqa.schemas import TestSuiteModel
from shopqa.state import AgentState, TestCase

MAX_ATTEMPTS = 3  # số lần thử lại nếu LLM trả JSON sai


def _extract_json(text: str) -> dict:
    """Lấy object JSON từ phản hồi, kể cả khi LLM bọc trong ```json ... ```."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("không tìm thấy JSON trong phản hồi")
    return json.loads(text[start : end + 1])


def parse_suite(text: str) -> TestSuiteModel:
    """Phân tích + kiểm tra schema. Lỗi nào cũng là ValueError."""
    return TestSuiteModel.model_validate(_extract_json(text))


def generate_tests(state: AgentState, llm=None, max_tests: int | None = None) -> dict:
    llm = llm or get_llm()
    max_tests = max_tests or int(os.getenv("SHOPQA_MAX_TESTS", "6"))

    messages = [
        SystemMessage(content=GENERATE_SYSTEM),
        HumanMessage(content=build_generate_user_prompt(
            state["spec"], state["base_url"], state["app_context"], max_tests)),
    ]

    suite, last_error = None, None
    for _ in range(MAX_ATTEMPTS):
        reply = response_text(llm.invoke(messages))
        try:
            suite = parse_suite(reply)
            break
        except ValueError as e:
            last_error = e
            messages += [
                AIMessage(content=reply),
                HumanMessage(content=(
                    f"Your previous output was invalid: {str(e)[:1500]}\n"
                    "Return the corrected JSON object only.")),
            ]
    if suite is None:
        raise ValueError(f"LLM không trả JSON hợp lệ sau {MAX_ATTEMPTS} lần thử: {last_error}")

    tests: list[TestCase] = [
        TestCase(
            id=t.id,
            title=t.title,
            steps=t.steps,
            expected=t.expected,
            actions=[a.model_dump(exclude_none=True) for a in t.actions],
        )
        for t in suite.tests[:max_tests]
    ]
    return {"test_cases": tests}
