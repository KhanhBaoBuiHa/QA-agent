"""Chọn ảnh chụp làm bằng chứng từ các lần đo đã có, cắt gọn rồi (tùy chọn) ghi vào README.

Với mỗi lỗi cài sẵn, lấy ảnh ở bước agent bắt được lỗi, và ảnh của CÙNG kiểu kiểm tra trên shop sạch để so sánh.

  python evals/collect_evidence.py                                  # chỉ tạo ảnh trong docs/evidence/
  python evals/collect_evidence.py --update-readme ../README.md     # tạo ảnh và ghi vào README

Chạy ở thư mục shopqa-agent, sau khi đã đo (cần evals/results/runs.csv và thư mục artifacts/).
Ảnh Langfuse tự chụp màn hình rồi lưu là docs/evidence/langfuse_trace.png, script sẽ tự đưa vào README nếu có.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT))

from evals.readme_tools import replace_block  # noqa: E402
from evals.run_many import MODES, detecting_result, read_rows  # noqa: E402

TITLES = {
    "coupon": "Lỗi mã giảm giá (`?bug=coupon`: giảm 1% thay vì 10%)",
    "checkout": "Lỗi nút thanh toán (`?bug=checkout`: không bị vô hiệu khi giỏ trống)",
}


def norm(path) -> Path:
    """Đường dẫn Windows (dấu \\) trong CSV/run.json vẫn đọc được trên mọi hệ điều hành."""
    return Path(str(path).replace("\\", "/"))


def load_final(row: dict):
    path = norm(row.get("artifacts_dir", "")) / "run.json"
    return json.loads(path.read_text(encoding="utf-8")) if row.get("artifacts_dir") and path.exists() else None


def bug_evidence(mode: str, rows: list[dict]):
    for row in reversed(rows):
        if row["mode"] != mode or row["status"] != "ok" or row["detected"] != "True":
            continue
        final = load_final(row)
        result = detecting_result(mode, final) if final else None
        if not result or not result["screenshots"] or not norm(result["screenshots"][-1]).exists():
            continue
        test = next(t for t in final["test_cases"] if t["id"] == result["test_id"])
        return {"image": norm(result["screenshots"][-1]), "run": row["run_id"],
                "report": result["log"].strip().splitlines()[-1],
                "action": test["actions"][result["failed_step"] - 1]["action"]}
    return None


def clean_evidence(mode: str, bug: dict, rows: list[dict]):
    """Ảnh của cùng kiểu kiểm tra (cùng loại action, cùng phần tử) đã PASS trên shop sạch."""
    target = MODES[mode]["bug_target"]
    for row in reversed(rows):
        if row["mode"] != "clean" or row["status"] != "ok" or row["false_alarm"] != "False":
            continue
        final = load_final(row)
        if not final:
            continue
        results = {r["test_id"]: r for r in final["results"]}
        for test in final["test_cases"]:
            result = results.get(test["id"])
            if not result or not result["passed"]:
                continue
            for i, act in enumerate(test["actions"]):
                if act["action"] == bug["action"] and target in (act.get("target") or ""):
                    if i < len(result["screenshots"]) and norm(result["screenshots"][i]).exists():
                        return {"image": norm(result["screenshots"][i]), "run": row["run_id"]}
    return None


def save_cropped(src: Path, dst: Path) -> None:
    """Cắt bỏ phần trắng thừa để chữ đủ lớn khi hiển thị trong README (cần Pillow; không có thì chép nguyên ảnh)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageChops
    except ImportError:
        shutil.copyfile(src, dst)
        return
    img = Image.open(src).convert("RGB")
    bbox = ImageChops.difference(img, Image.new("RGB", img.size, (255, 255, 255))).getbbox()
    if bbox:
        pad = 16
        bbox = (max(bbox[0] - pad, 0), max(bbox[1] - pad, 0),
                min(bbox[2] + pad, img.width), min(bbox[3] + pad, img.height))
        img = img.crop(bbox)
    img.save(dst)


def build_markdown(items: list[dict], image_dir: str, langfuse: bool) -> str:
    if not items and not langfuse:
        return "_Chưa có ảnh bằng chứng. Chạy `python evals/collect_evidence.py --update-readme ../README.md` sau khi đo._"
    parts = []
    for it in items:
        parts.append(f"**{TITLES[it['mode']]}**\n")
        if it.get("clean"):
            parts.append("| Shop có lỗi | Shop đúng |\n|:---:|:---:|\n"
                         f"| ![{it['mode']} có lỗi]({image_dir}/{it['mode']}_bug.png) "
                         f"| ![{it['mode']} shop đúng]({image_dir}/{it['mode']}_clean.png) |\n")
        else:
            parts.append(f"![{it['mode']} có lỗi]({image_dir}/{it['mode']}_bug.png)\n")
        parts.append(f"> Agent báo: `{it['report'].replace('`', chr(39))}`\n")
    if langfuse:
        parts.append(f"**Trace của một lần chạy trên Langfuse**\n\n![Trace trên Langfuse]({image_dir}/langfuse_trace.png)\n")
    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description="Tạo ảnh bằng chứng từ các lần đo")
    ap.add_argument("--csv", default="evals/results/runs.csv")
    ap.add_argument("--out", default="docs/evidence", help="thư mục lưu ảnh")
    ap.add_argument("--readme-image-dir", default="shopqa-agent/docs/evidence",
                    help="đường dẫn thư mục ảnh tính từ README (để viết link ảnh)")
    ap.add_argument("--update-readme", metavar="README")
    args = ap.parse_args()

    rows = read_rows(Path(args.csv))
    out = Path(args.out)
    items = []
    for mode in ("coupon", "checkout"):
        bug = bug_evidence(mode, rows)
        if not bug:
            print(f"[{mode}] chưa có lần chạy bắt được lỗi kèm ảnh: bỏ qua")
            continue
        save_cropped(bug["image"], out / f"{mode}_bug.png")
        clean = clean_evidence(mode, bug, rows)
        if clean:
            save_cropped(clean["image"], out / f"{mode}_clean.png")
        print(f"[{mode}] ảnh lỗi từ lần chạy {bug['run']}; ảnh shop đúng: "
              f"{'lần chạy ' + clean['run'] if clean else 'KHÔNG tìm thấy (cần một lần chạy shop sạch có test cùng kiểu)'}")
        items.append({"mode": mode, "clean": bool(clean), "report": bug["report"]})

    has_langfuse = (out / "langfuse_trace.png").exists()
    if not has_langfuse:
        print(f"(Chưa có {out / 'langfuse_trace.png'}: chụp màn hình trace trên Langfuse và lưu vào đó nếu muốn đưa vào README)")
    if args.update_readme:
        replace_block(args.update_readme, "EVIDENCE", build_markdown(items, args.readme_image_dir, has_langfuse))
        print(f"Đã cập nhật phần bằng chứng trong {args.update_readme}")


if __name__ == "__main__":
    main()
