import json
import sys

import pytest

from evals import collect_evidence as ce
from evals.readme_tools import replace_block
from evals.run_many import append_row

TOTAL = {"action": "expect_text", "target": '[data-testid="cart-total"]', "value": "90.000"}
GOTO = {"action": "goto", "target": "/"}


def test_replace_block_replaces_only_the_marked_part(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("trước\n<!-- X:START -->\ncũ\n<!-- X:END -->\nsau\n", encoding="utf-8")
    replace_block(readme, "X", "mới")
    assert readme.read_text(encoding="utf-8") == "trước\n<!-- X:START -->\nmới\n<!-- X:END -->\nsau\n"


def test_replace_block_fails_clearly_without_markers(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("không có dấu mốc", encoding="utf-8")
    with pytest.raises(ValueError, match="dấu mốc"):
        replace_block(readme, "X", "mới")


def make_run(tmp_path, name, passed, shots_dir):
    """Dựng một thư mục artifacts giả (có ảnh thật và run.json) với đường dẫn kiểu Windows."""
    from PIL import Image, ImageDraw

    run_dir = tmp_path / "artifacts" / name
    run_dir.mkdir(parents=True)
    shots = []
    for i in range(1, 3):
        img = Image.new("RGB", (1280, 800), "white")
        ImageDraw.Draw(img).rectangle((10, 10, 300, 200), fill="black")   # nội dung nhỏ ở góc trái trên
        suffix = "_FAILED" if (not passed and i == 2) else ""
        path = run_dir / f"step_{i:02d}{suffix}.png"
        img.save(path)
        shots.append(str(path).replace("/", "\\"))                          # như trên Windows
    result = {"test_id": "t1", "passed": passed, "screenshots": shots,
              "log": "✓ 1. goto /\n" + ("✓ 2. expect_text" if passed else
                                          "✗ 2. expect_text -> assertion_failed: kỳ vọng 90.000đ, thực tế 99.000đ"),
              "failed_step": None if passed else 2, "error_type": "" if passed else "assertion_failed"}
    final = {"test_cases": [{"id": "t1", "title": "x", "steps": [], "expected": "", "actions": [GOTO, TOTAL]}],
             "results": [result], "findings": []}
    (run_dir / "run.json").write_text(json.dumps(final), encoding="utf-8")
    return str(run_dir).replace("/", "\\")


def test_collects_cropped_pairs_and_updates_readme(tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    from PIL import Image

    bug_dir = make_run(tmp_path, "run-bug", False, None)
    clean_dir = make_run(tmp_path, "run-clean", True, None)
    csv_path = tmp_path / "runs.csv"
    append_row(csv_path, {"mode": "coupon", "status": "ok", "detected": "True", "run_id": "run-bug", "artifacts_dir": bug_dir})
    append_row(csv_path, {"mode": "clean", "status": "ok", "false_alarm": "False", "run_id": "run-clean", "artifacts_dir": clean_dir})
    readme = tmp_path / "README.md"
    readme.write_text("# t\n<!-- EVIDENCE:START -->\n<!-- EVIDENCE:END -->\n", encoding="utf-8")
    out = tmp_path / "docs" / "evidence"

    monkeypatch.setattr(sys, "argv", ["x", "--csv", str(csv_path), "--out", str(out), "--update-readme", str(readme)])
    ce.main()

    bug_img, clean_img = out / "coupon_bug.png", out / "coupon_clean.png"
    assert bug_img.exists() and clean_img.exists()
    assert Image.open(bug_img).width < 400                      # đã cắt phần trắng thừa
    text = readme.read_text(encoding="utf-8")
    assert "shopqa-agent/docs/evidence/coupon_bug.png" in text and "shopqa-agent/docs/evidence/coupon_clean.png" in text
    assert "thực tế 99.000đ" in text and "checkout_bug.png" not in text


def test_placeholder_when_there_is_no_evidence(tmp_path, monkeypatch):
    csv_path = tmp_path / "runs.csv"
    append_row(csv_path, {"mode": "coupon", "status": "ok", "detected": "False", "artifacts_dir": ""})
    readme = tmp_path / "README.md"
    readme.write_text("<!-- EVIDENCE:START -->\n<!-- EVIDENCE:END -->\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["x", "--csv", str(csv_path), "--out", str(tmp_path / "o"),
                                      "--update-readme", str(readme)])
    ce.main()
    assert "Chưa có ảnh bằng chứng" in readme.read_text(encoding="utf-8")
