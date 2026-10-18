"""Chạy agent lặp lại nhiều lần theo từng chế độ lỗi, ghi số liệu ra CSV và in bảng tổng hợp.

Ví dụ (shop demo đang chạy ở cổng 8000):
  python evals/run_many.py --runs 5 --prompt-version sau-sua                 # cả 3 chế độ, phiên bản B
  python evals/run_many.py --modes checkout clean --runs 5 --variants A B    # so sánh A và B
  python evals/run_many.py --summary                                          # chỉ in lại bảng từ CSV

Định nghĩa các chỉ số (độc lập với node classify, chỉ dựa vào kết quả chạy trình duyệt):
  - "Bắt được lỗi": ở chế độ có lỗi, có ít nhất một test FAIL với loại lỗi assertion_failed
    đúng vào phần tử của lỗi cài sẵn (coupon -> cart-total, checkout -> checkout-button).
  - "Báo nhầm": ở chế độ shop sạch, có bất kỳ test nào FAIL.
Lần chạy bị lỗi API (quá tải, hết hạn mức) được ghi riêng và KHÔNG tính vào mẫu số.
"""
import argparse
import csv
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # để import được `evals.readme_tools`

from shopqa.log import log  # noqa: E402  (import log trước để in UTF-8 trên Windows)
from shopqa.state import initial_state  # noqa: E402

# Mỗi chế độ: tham số gắn vào địa chỉ shop và dấu hiệu nhận ra lỗi cài sẵn.
MODES = {
    "coupon":   {"query": "?bug=coupon",   "bug_target": "cart-total"},
    "checkout": {"query": "?bug=checkout", "bug_target": "checkout-button"},
    "clean":    {"query": "",              "bug_target": None},
}

FIELDS = ["timestamp", "run_id", "mode", "variant", "prompt_version", "model", "status",
          "n_tests", "n_failed", "detected", "false_alarm", "error_types", "verdicts",
          "repair_attempts", "seconds", "artifacts_dir", "note"]


def error_kind(exc: Exception) -> str:
    """Phân loại lỗi để quyết định dừng hẳn hay chạy tiếp."""
    if isinstance(exc, ImportError):
        return "setup"  # thiếu gói / sai môi trường Python: không phải lỗi API, không phải một lần đo
    text = f"{type(exc).__name__} {exc}".lower()
    if "429" in text or "resource_exhausted" in text or "quota" in text:
        return "quota"
    if "503" in text or "unavailable" in text or "overloaded" in text:
        return "overloaded"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    return "other"


def detecting_result(mode: str, final: dict):
    """Trả về kết quả test đã bắt được lỗi cài sẵn (hoặc None): FAIL kiểu assertion_failed đúng vào phần tử của lỗi."""
    bug_target = MODES[mode]["bug_target"]
    if not bug_target:
        return None
    tests = {t["id"]: t for t in final.get("test_cases", [])}
    for r in final.get("results", []):
        if r["passed"] or r["error_type"] != "assertion_failed" or not r.get("failed_step"):
            continue
        actions = tests.get(r["test_id"], {}).get("actions", [])
        idx = r["failed_step"] - 1
        if 0 <= idx < len(actions) and bug_target in (actions[idx].get("target") or ""):
            return r
    return None


def evaluate(mode: str, final: dict) -> dict:
    """Tính các chỉ số của một lần chạy từ state cuối cùng."""
    results = final.get("results", [])
    failed = [r for r in results if not r["passed"]]
    has_bug = MODES[mode]["bug_target"] is not None
    return {
        "n_tests": len(results),
        "n_failed": len(failed),
        "detected": (detecting_result(mode, final) is not None) if has_bug else None,
        "false_alarm": None if has_bug else len(failed) > 0,
        "error_types": dict(Counter(r["error_type"] for r in failed)),
        "verdicts": dict(Counter(f["verdict"] for f in final.get("findings", []))),
        "repair_attempts": final.get("repair_attempts", 0),
    }


def append_row(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    # utf-8-sig để Excel mở file CSV tiếng Việt không bị lỗi font
    with path.open("a", newline="", encoding="utf-8-sig" if new_file else "utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in FIELDS})


def drop_setup_errors(path: Path) -> int:
    """Xóa các dòng lỗi cài đặt (thiếu gói...) đã lỡ ghi vào CSV. Trả về số dòng đã xóa."""
    rows = read_rows(path)
    keep = [r for r in rows
            if not (r.get("status", "").startswith("error:") and
                    ("ModuleNotFoundError" in r.get("note", "") or "ImportError" in r.get("note", "")))]
    if len(keep) != len(rows):
        path.unlink()
        for r in keep:
            append_row(path, r)
    return len(rows) - len(keep)


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _is_true(value) -> bool:
    return str(value).lower() == "true"


def summarize(rows: list[dict]) -> list[dict]:
    """Gom theo (prompt_version, variant, mode). Lần lỗi API không vào mẫu số."""
    groups: dict[tuple, dict] = {}
    for r in rows:
        key = (r["prompt_version"], r["variant"], r["mode"])
        g = groups.setdefault(key, {"prompt_version": key[0], "variant": key[1], "mode": key[2],
                                    "runs": 0, "detected": 0, "false_alarms": 0, "api_errors": 0})
        if r["status"] != "ok":
            g["api_errors"] += 1
            continue
        g["runs"] += 1
        g["detected"] += _is_true(r["detected"])
        g["false_alarms"] += _is_true(r["false_alarm"])
    return sorted(groups.values(), key=lambda g: (g["prompt_version"], g["variant"], g["mode"]))


def format_table(summary: list[dict]) -> str:
    def frac(n, d):
        return f"{n}/{d} ({n / d:.0%})" if d else "-"

    lines = ["| Prompt | Phiên bản | Chế độ | Số lần chạy | Bắt được lỗi | Báo nhầm | Lần lỗi API (không tính) |",
             "|---|---|---|---|---|---|---|"]
    for g in summary:
        has_bug = MODES[g["mode"]]["bug_target"] is not None
        lines.append(
            f"| {g['prompt_version']} | {g['variant']} | {g['mode']} | {g['runs']} | "
            f"{frac(g['detected'], g['runs']) if has_bug else '-'} | "
            f"{frac(g['false_alarms'], g['runs']) if not has_bug else '-'} | {g['api_errors']} |")
    return "\n".join(lines)


def run_agent_once(spec: str, base_url: str, pages: list[str], self_repair: bool,
                   max_repairs: int, trace_tags: list[str], trace_meta: dict) -> dict:
    """Một lần chạy đầy đủ, giống hệt CLI. Tách riêng để test thay thế được."""
    from shopqa.graph import build_graph
    from shopqa.tools.browser import build_app_context
    from shopqa.tracing import flush, get_trace_config

    state = initial_state(spec, base_url, build_app_context(base_url, pages), max_repairs)
    config = get_trace_config(run_name="shopqa-eval", session_id=state["run_id"],
                              tags=["eval", *trace_tags], metadata=trace_meta)
    try:
        final = build_graph(self_repair=self_repair).invoke(state, config=config)
    finally:
        flush()
    out = Path(os.getenv("SHOPQA_ARTIFACTS", "artifacts")) / final["run_id"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "run.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    final["_artifacts_dir"] = str(out)
    return final


def run_experiment(args, run_once=run_agent_once, sleep=time.sleep) -> None:
    spec = Path(args.spec).read_text(encoding="utf-8")
    csv_path = Path(args.csv)
    model = os.getenv("LLM_MODEL", "unknown")
    base = args.base_url.rstrip("/")
    consecutive_errors = 0

    for variant in args.variants:
        for mode in args.modes:
            url = f"{base}/{MODES[mode]['query']}" if MODES[mode]["query"] else base
            ok_runs = 0
            while ok_runs < args.runs:
                n = ok_runs + 1
                log(f"[eval] mode={mode} variant={variant} lần {n}/{args.runs}")
                started = time.monotonic()
                row = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "mode": mode, "variant": variant,
                       "prompt_version": args.prompt_version, "model": model}
                try:
                    final = run_once(spec, url, args.pages, variant == "B", args.max_repairs,
                                     [mode, f"variant-{variant}", args.prompt_version, model],
                                     {"mode": mode, "variant": variant, "prompt_version": args.prompt_version})
                
                except Exception as exc:  # noqa: BLE001
                    import traceback

                    kind = error_kind(exc)
                    error_detail = f"{type(exc).__name__}: {str(exc)}"
                    if kind == "setup":
                        log(f"[eval] LỖI CÀI ĐẶT (không phải lỗi API, không ghi vào CSV): {error_detail}")
                        log("[eval] Kiểm tra đã bật .venv, đã cài gói trong requirements.txt (và gói provider LLM) chưa.")
                        return

                    row.update(
                        status=f"error:{kind}",
                        seconds=round(time.monotonic() - started, 1),
                        note=error_detail[:1000],
                    )
                    append_row(csv_path, row)
                    consecutive_errors += 1

                    log(f"[eval] lỗi ({kind}): {error_detail}")
                    traceback.print_exc()

                    if kind == "quota":
                        log("[eval] HẾT HẠN MỨC: dừng hẳn.")
                        return

                    if consecutive_errors >= args.max_consecutive_errors:
                        log(f"[eval] {consecutive_errors} lần lỗi liên tiếp: dừng để tránh tốn hạn mức.")
                        return

                    sleep(args.error_pause)
                    continue

                consecutive_errors = 0
                metrics = evaluate(mode, final)
                row.update(status="ok", run_id=final["run_id"], seconds=round(time.monotonic() - started, 1),
                           artifacts_dir=final.get("_artifacts_dir", ""), **metrics)
                row["error_types"] = json.dumps(metrics["error_types"], ensure_ascii=False)
                row["verdicts"] = json.dumps(metrics["verdicts"], ensure_ascii=False)
                append_row(csv_path, row)
                log(f"[eval] xong: {metrics['n_failed']}/{metrics['n_tests']} test FAIL | "
                    f"bắt được lỗi={metrics['detected']} | báo nhầm={metrics['false_alarm']}")
                ok_runs += 1
                if ok_runs < args.runs:
                    sleep(args.pause)


def main() -> None:
    ap = argparse.ArgumentParser(description="Chạy lặp ShopQA-Agent và tổng hợp số liệu")
    ap.add_argument("--spec", default="specs/checkout.md")
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--pages", nargs="+", default=["/"])
    ap.add_argument("--modes", nargs="+", choices=list(MODES), default=list(MODES))
    ap.add_argument("--variants", nargs="+", choices=["A", "B"], default=["B"],
                    help="A = không tự sửa, B = có vòng tự sửa")
    ap.add_argument("--runs", type=int, default=5, help="số lần chạy THÀNH CÔNG mỗi chế độ")
    ap.add_argument("--prompt-version", default="current", help="nhãn để phân biệt các phiên bản prompt")
    ap.add_argument("--max-repairs", type=int, default=3)
    ap.add_argument("--pause", type=int, default=20, help="giây nghỉ giữa hai lần chạy")
    ap.add_argument("--error-pause", type=int, default=60, help="giây nghỉ sau một lần lỗi API")
    ap.add_argument("--max-consecutive-errors", type=int, default=3)
    ap.add_argument("--csv", default="evals/results/runs.csv")
    ap.add_argument("--summary", action="store_true", help="chỉ in bảng tổng hợp từ file CSV")
    ap.add_argument("--drop-setup-errors", action="store_true",
                    help="xóa khỏi CSV các dòng lỗi cài đặt (ModuleNotFoundError...) rồi in bảng")
    ap.add_argument("--update-readme", metavar="README",
                    help="ghi bảng tổng hợp vào README, giữa hai dấu mốc <!-- RESULTS:START --> và <!-- RESULTS:END -->")
    args = ap.parse_args()

    if args.drop_setup_errors:
        print(f"Đã xóa {drop_setup_errors(Path(args.csv))} dòng lỗi cài đặt khỏi {args.csv}")
    elif not args.summary:
        run_experiment(args)
    rows = read_rows(Path(args.csv))
    table = format_table(summarize(rows)) if rows else "(chưa có số liệu)"
    print("\n" + table)
    if args.update_readme and rows:
        from evals.readme_tools import replace_block
        replace_block(args.update_readme, "RESULTS", table)
        print(f"Đã cập nhật bảng kết quả trong {args.update_readme}")


if __name__ == "__main__":
    main()
