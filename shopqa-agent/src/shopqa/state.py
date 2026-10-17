"""State chạy xuyên suốt các node của agent ShopQA.

Mỗi node nhận state, trả về một dict chứa CHỈ những khóa nó muốn cập nhật.
LangGraph sẽ tự gộp dict đó vào state hiện tại.

Lưu ý thiết kế: test KHÔNG phải là code Python do LLM viết, mà là một danh sách
`actions` có cấu trúc (goto, click, fill, expect_text, ...). Lý do: không phải
exec() code lạ, mỗi bước log được riêng, và việc tự sửa test chỉ là sửa vài dòng JSON.
"""
from datetime import datetime
from typing import Optional, TypedDict, Literal

# Ba kết quả mà node classify có thể đưa ra cho mỗi test
Verdict = Literal[
    "pass",
    "real_bug",
    "test_error",
    "inconclusive",
]


class Action(TypedDict, total=False):
    action: str   # goto | click | fill | select | expect_visible | expect_not_visible
                  # | expect_text | expect_url | expect_enabled | expect_disabled
    target: str   # đường dẫn (goto) hoặc selector
    value: str    # nội dung nhập / văn bản kỳ vọng


class TestCase(TypedDict):
    id: str
    title: str
    steps: list[str]        # kịch bản bằng lời (để người đọc báo cáo)
    expected: str           # kết quả mong đợi bằng lời
    actions: list[Action]   # phần máy chạy được


class TestResult(TypedDict):
    test_id: str
    passed: bool
    log: str                # log từng bước
    screenshots: list[str]  # đường dẫn ảnh chụp từng bước
    failed_step: Optional[int]  # bước (tính từ 1) bị lỗi, None nếu pass
    error_type: str         # "" nếu pass; xem tools/browser.py để biết các loại


class Finding(TypedDict):
    test_id: str
    verdict: Verdict
    reason: str             # LLM giải thích vì sao phân loại như vậy


class AgentState(TypedDict):
    # --- đầu vào ---
    spec: str                      # mô tả tính năng cần kiểm thử
    base_url: str                  # địa chỉ shop, vd http://localhost:8000
    app_context: str               # danh sách phần tử UI thật (để LLM không bịa selector)
    run_id: str                    # dùng đặt tên thư mục ảnh chụp/kết quả

    # --- dữ liệu trung gian ---
    test_cases: list[TestCase]
    results: list[TestResult]
    findings: list[Finding]

    # --- điều khiển vòng tự sửa ---
    repair_attempts: int           # đã sửa mấy lần
    max_repairs: int               # tối đa bao nhiêu lần (vd 3)

    # --- đầu ra ---
    report: str


def initial_state(
    spec: str,
    base_url: str,
    app_context: str = "",
    max_repairs: int = 3,
) -> AgentState:
    """Tạo state ban đầu."""
    return AgentState(
        spec=spec,
        base_url=base_url.rstrip("/"),
        app_context=app_context,
        run_id=datetime.now().strftime("%Y%m%d-%H%M%S"),
        test_cases=[],
        results=[],
        findings=[],
        repair_attempts=0,
        max_repairs=max_repairs,
        report="",
    )
