"""Các node CHƯA LÀM THẬT (bước 3, 4, 5 sau này): classify, repair_test, report.

Mỗi hàm giữ nguyên chữ ký để thay thế dần bằng file riêng (classify.py, ...).
"""

import json

from langchain_core.messages import HumanMessage, SystemMessage

from shopqa.llm import get_llm, response_text
from shopqa.state import AgentState, Finding




def classify(state: AgentState, llm=None) -> dict:
    """Kết hợp rule-based classification với LLM cho lỗi chưa rõ nguyên nhân."""
    import json

    from langchain_core.messages import HumanMessage, SystemMessage
    from shopqa.llm import get_llm, response_text

    findings: list[Finding] = []
    test_cases = {
        test["id"]: test
        for test in state.get("test_cases", [])
    }

    for result in state["results"]:
        test_id = result["test_id"]
        error_type = result["error_type"]
        log = result["log"].strip()

        if result["passed"]:
            findings.append(Finding(
                test_id=test_id,
                verdict="pass",
                reason="Tất cả các bước của test đã chạy thành công.",
            ))
            continue

        if error_type == "invalid_action":
            findings.append(Finding(
                test_id=test_id,
                verdict="test_error",
                reason=f"Action không hợp lệ hoặc không được hỗ trợ. Log: {log[-500:]}",
            ))
            continue

        test_case = test_cases.get(test_id)
        if test_case is None:
            findings.append(Finding(
                test_id=test_id,
                verdict="inconclusive",
                reason="Không tìm thấy test case tương ứng để phân tích.",
            ))
            continue

        try:
            # Chỉ khởi tạo LLM khi thực sự cần phân tích.
            if llm is None:
                llm = get_llm()

            prompt_data = {
                "spec": state["spec"],
                "app_context": state["app_context"],
                "test_case": test_case,
                "failed_step": result["failed_step"],
                "error_type": error_type,
                "log": log,
            }

            messages = [
                SystemMessage(content=(
                    "You are a careful QA engineer. Analyze the failed UI test. "
                    'Return JSON only: {"verdict": "...", "reason": "..."}. '
                    'Allowed verdicts: "real_bug", "test_error", "inconclusive". '
                    "Use real_bug only when evidence supports a violation of the "
                    "specification. Use test_error only when the test is demonstrably "
                    "wrong. Otherwise use inconclusive. Do not invent evidence."
                )),
                HumanMessage(content=json.dumps(prompt_data, ensure_ascii=False)),
            ]

            raw = response_text(llm.invoke(messages)).strip()

            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                raw = raw.rsplit("```", 1)[0].strip()

            data = json.loads(raw)
            verdict = data.get("verdict")
            reason = data.get("reason")

            if verdict not in {"real_bug", "test_error", "inconclusive"}:
                raise ValueError("LLM trả về verdict không hợp lệ")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("LLM không trả về reason hợp lệ")

            findings.append(Finding(
                test_id=test_id,
                verdict=verdict,
                reason=reason,
            ))

        except Exception as exc:
            # Không để lỗi cấu hình/API khiến agent kết luận bừa.
            findings.append(Finding(
                test_id=test_id,
                verdict="inconclusive",
                reason=f"Không thể phân loại bằng LLM: {type(exc).__name__}: {exc}",
            ))

    return {"findings": findings}



def repair_test(state: AgentState, llm=None) -> dict:
    """Sửa các test được phân loại test_error bằng LLM."""
    import json

    from langchain_core.messages import HumanMessage, SystemMessage
    from shopqa.llm import get_llm, response_text

    # Tăng bộ đếm mỗi khi node repair được gọi.
    next_attempt = state["repair_attempts"] + 1

    # Chỉ sửa test được phân loại test_error.
    repairable_ids = {
        finding["test_id"]
        for finding in state["findings"]
        if finding["verdict"] == "test_error"
    }

    if not repairable_ids:
        return {"repair_attempts": next_attempt}

    test_cases = state["test_cases"]
    updated_test_cases = [dict(test_case) for test_case in test_cases]

    for index, test_case in enumerate(test_cases):
        if test_case["id"] not in repairable_ids:
            continue

        # Tìm kết quả thực thi gần nhất của test này.
        matching_results = [
            result for result in state["results"]
            if result["test_id"] == test_case["id"]
        ]
        if not matching_results:
            continue

        result = matching_results[-1]
        finding = next(
            (
                item for item in state["findings"]
                if item["test_id"] == test_case["id"]
                and item["verdict"] == "test_error"
            ),
            None,
        )
        if finding is None:
            continue

        try:
            if llm is None:
                llm = get_llm()

            prompt_data = {
                "spec": state["spec"],
                "app_context": state["app_context"],
                "test_case": test_case,
                "finding": finding,
                "error_type": result["error_type"],
                "failed_step": result["failed_step"],
                "log": result["log"],
                "allowed_actions": [
                    "goto",
                    "click",
                    "fill",
                    "select",
                    "expect_visible",
                    "expect_not_visible",
                    "expect_text",
                    "expect_url",
                    "expect_enabled",
                    "expect_disabled",
                ],
            }

            messages = [
                SystemMessage(
                    content=(
                        "You are a careful QA test-repair engineer. "
                        "Repair only the test definition, not the application. "
                        "Use the provided app_context; do not invent selectors. "
                        "Preserve the original intent and expected behavior. "
                        "Do not weaken or remove assertions just to make a test pass. "
                        "Return JSON only with this structure: "
                        '{"steps": ["..."], "actions": '
                        '[{"action": "...", "target": "...", "value": "..."}]}. '
                        "Every action must use an allowed action name. "
                        "The actions array must not be empty."
                    )
                ),
                HumanMessage(
                    content=json.dumps(prompt_data, ensure_ascii=False)
                ),
            ]

            raw = response_text(llm.invoke(messages)).strip()

            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                raw = raw.rsplit("```", 1)[0].strip()

            repaired = json.loads(raw)

            steps = repaired.get("steps")
            actions = repaired.get("actions")

            if not isinstance(steps, list) or not all(
                isinstance(step, str) for step in steps
            ):
                continue

            if not isinstance(actions, list) or not actions:
                continue

            allowed_actions = {
                "goto",
                "click",
                "fill",
                "select",
                "expect_visible",
                "expect_not_visible",
                "expect_text",
                "expect_url",
                "expect_enabled",
                "expect_disabled",
            }

            valid_actions = True
            for action in actions:
                if not isinstance(action, dict):
                    valid_actions = False
                    break

                if action.get("action") not in allowed_actions:
                    valid_actions = False
                    break

                if not isinstance(action.get("target"), str):
                    valid_actions = False
                    break

                if "value" in action and not isinstance(
                    action["value"], str
                ):
                    valid_actions = False
                    break

            if not valid_actions:
                continue

            updated_test_cases[index] = {
                **test_case,
                "steps": steps,
                "actions": actions,
            }

        except Exception:
            # Nếu LLM/API/JSON lỗi, giữ nguyên test case gốc.
            continue

    return {
        "test_cases": updated_test_cases,
        "repair_attempts": next_attempt,
    }



def report(state: AgentState) -> dict:
    # TODO: tổng hợp mức độ nghiêm trọng, bước tái hiện, ảnh chụp.
    lines = []
    for f, r in zip(state["findings"], state["results"]):
        lines.append(f"- {f['test_id']}: {f['verdict']} {f['reason']}".rstrip())
        if not r["passed"]:
            lines.append("    " + r["log"].splitlines()[-1])
    return {"report": "\n".join(lines)}
