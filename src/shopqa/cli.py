"""Chạy agent từ dòng lệnh.

Ví dụ (shop chạy ở cổng 8000):
  python -m shopqa.cli --spec specs/checkout.md --base-url http://localhost:8000 --pages /
  python -m shopqa.cli --spec specs/checkout.md --base-url http://localhost:8000 --no-self-repair
"""
import argparse
import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from shopqa.graph import build_graph
from shopqa.log import log
from shopqa.state import initial_state
from shopqa.tracing import flush as flush_traces
from shopqa.tracing import get_trace_config
from shopqa.tools.browser import build_app_context


def explain_error(err: Exception) -> str:
    """Đoán nguyên nhân thường gặp từ nội dung lỗi để báo bằng một câu dễ hiểu."""
    text = f"{type(err).__name__}: {err}"
    low = text.lower()
    if "503" in text or "unavailable" in low or "overloaded" in low:
        hint = "Gemini đang quá tải (lỗi phía Google). Chờ vài phút rồi chạy lại, hoặc tăng SHOPQA_LLM_RETRIES trong .env."
    elif "429" in text or "resource_exhausted" in low or "quota" in low:
        hint = "Hết hạn mức gọi Gemini. Chờ rồi chạy lại, hoặc xem hạn mức trong Google AI Studio."
    elif "api key" in low or "api_key" in low or "permission" in low or "403" in text or "401" in text:
        hint = "Khóa API sai hoặc không có quyền. Kiểm tra GOOGLE_API_KEY trong .env (nhớ lưu file)."
    elif "404" in text or "not found" in low:
        hint = "Tên model không đúng. Kiểm tra LLM_MODEL trong .env."
    elif "timeout" in low or "timed out" in low:
        hint = "Hết thời gian chờ. Thử tăng SHOPQA_LLM_TIMEOUT trong .env."
    else:
        hint = "Lỗi chưa nhận diện được, xem chi tiết ở dòng trên."
    return f"{text[:400]}\n           -> {hint}"


def main() -> None:
    ap = argparse.ArgumentParser(description="ShopQA-Agent")
    ap.add_argument("--spec", required=True, help="file .md mô tả tính năng")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--pages", nargs="+", default=["/"],
                    help="các trang cần đọc để lấy danh sách phần tử UI (mặc định: /)")
    ap.add_argument("--no-self-repair", action="store_true", help="chạy phiên bản A (không tự sửa)")
    ap.add_argument("--max-repairs", type=int, default=3)
    args = ap.parse_args()

    spec = Path(args.spec).read_text(encoding="utf-8")
    log(f"[cli] đọc phần tử UI của {args.base_url}")
    context = build_app_context(args.base_url, args.pages)
    state = initial_state(spec, args.base_url, context, args.max_repairs)

    variant = "A" if args.no_self_repair else "B"
    config = get_trace_config(
        run_name="shopqa-cli", session_id=state["run_id"],
        tags=["cli", f"variant-{variant}", os.getenv("LLM_MODEL", "unknown-model")],
        metadata={"base_url": args.base_url, "spec": args.spec, "variant": variant})

    graph = build_graph(self_repair=not args.no_self_repair)
    try:
        final = graph.invoke(state, config=config)
    except Exception as e:  # noqa: BLE001 - muốn báo gọn thay vì in cả traceback dài
        log(f"[cli] LỖI: {explain_error(e)}")
        flush_traces()
        raise SystemExit(1)
    flush_traces()
    log("[cli] xong")

    for t, r in zip(final["test_cases"], final["results"]):
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"[{mark}] {t['id']}: {t['title']}")
    print("\n--- Báo cáo ---")
    print(final["report"])

    out = Path("artifacts") / final["run_id"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "run.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nĐã lưu kết quả và ảnh chụp tại {out}")


if __name__ == "__main__":
    main()