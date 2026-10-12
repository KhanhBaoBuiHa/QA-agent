"""Các node CHƯA LÀM THẬT (bước 3, 4, 5 sau này): classify, repair_test, report.

Mỗi hàm giữ nguyên chữ ký để thay thế dần bằng file riêng (classify.py, ...).
"""
from shopqa.state import AgentState, Finding


def classify(state: AgentState) -> dict:
    # TODO: gọi LLM đọc log + ảnh để phân loại. Tạm dùng quy tắc theo error_type:
    # assertion_failed là tín hiệu mạnh của lỗi thật, còn lại nghi lỗi do test.
    findings: list[Finding] = []
    for r in state["results"]:
        if r["passed"]:
            findings.append(Finding(test_id=r["test_id"], verdict="pass", reason=""))
        elif r["error_type"] == "assertion_failed":
            findings.append(Finding(test_id=r["test_id"], verdict="real_bug",
                                    reason="phần tử có nhưng kết quả khác kỳ vọng"))
        else:
            findings.append(Finding(test_id=r["test_id"], verdict="test_error",
                                    reason=f"nghi lỗi do test ({r['error_type']})"))
    return {"findings": findings}


def repair_test(state: AgentState) -> dict:
    # TODO: gọi LLM sửa CHỈ những test bị phân loại test_error.
    # Hiện tại chưa sửa gì, chỉ tăng bộ đếm để vòng lặp có điểm dừng.
    return {"repair_attempts": state["repair_attempts"] + 1}


def report(state: AgentState) -> dict:
    # TODO: tổng hợp mức độ nghiêm trọng, bước tái hiện, ảnh chụp.
    lines = []
    for f, r in zip(state["findings"], state["results"]):
        lines.append(f"- {f['test_id']}: {f['verdict']} {f['reason']}".rstrip())
        if not r["passed"]:
            lines.append("    " + r["log"].splitlines()[-1])
    return {"report": "\n".join(lines)}
