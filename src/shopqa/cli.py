"""Chạy agent từ dòng lệnh.

Ví dụ (shop chạy ở cổng 8000):
  python -m shopqa.cli --spec specs/checkout.md --base-url http://localhost:8000 --pages /
  python -m shopqa.cli --spec specs/checkout.md --base-url http://localhost:8000 --no-self-repair
"""
import argparse
import json
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from shopqa.graph import build_graph
from shopqa.state import initial_state
from shopqa.tools.browser import build_app_context


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
    context = build_app_context(args.base_url, args.pages)
    state = initial_state(spec, args.base_url, context, args.max_repairs)

    graph = build_graph(self_repair=not args.no_self_repair)
    final = graph.invoke(state)

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
