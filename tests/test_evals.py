import json
from types import SimpleNamespace

import pytest

from evals import run_many as rm


def tc(test_id, actions):
    return {"id": test_id, "title": test_id, "steps": [], "expected": "", "actions": actions}


def res(test_id, passed=True, error_type="", failed_step=None):
    return {"test_id": test_id, "passed": passed, "log": "", "screenshots": [],
            "failed_step": failed_step, "error_type": error_type}


TOTAL = {"action": "expect_text", "target": '[data-testid="cart-total"]', "value": "90.000"}
CHECKOUT = {"action": "expect_disabled", "target": '[data-testid="checkout-button"]'}
GOTO = {"action": "goto", "target": "/"}


def test_detects_coupon_bug_when_total_assertion_fails():
    final = {"test_cases": [tc("t1", [GOTO, TOTAL])],
             "results": [res("t1", False, "assertion_failed", 2)], "findings": [], "repair_attempts": 0}
    assert rm.evaluate("coupon", final)["detected"] is True


def test_failure_on_other_element_is_not_a_detection():
    final = {"test_cases": [tc("t1", [GOTO, CHECKOUT])],
             "results": [res("t1", False, "assertion_failed", 2)], "findings": [], "repair_attempts": 0}
    assert rm.evaluate("coupon", final)["detected"] is False


def test_wrong_selector_failure_is_not_a_detection():
    final = {"test_cases": [tc("t1", [GOTO, TOTAL])],
             "results": [res("t1", False, "element_not_found", 2)], "findings": [], "repair_attempts": 0}
    assert rm.evaluate("coupon", final)["detected"] is False


def test_checkout_bug_detected_on_checkout_button():
    final = {"test_cases": [tc("t1", [GOTO, CHECKOUT])],
             "results": [res("t1", False, "assertion_failed", 2)], "findings": [], "repair_attempts": 0}
    assert rm.evaluate("checkout", final)["detected"] is True


def test_clean_mode_counts_any_failure_as_false_alarm():
    final = {"test_cases": [tc("t1", [GOTO, TOTAL]), tc("t2", [GOTO, TOTAL])],
             "results": [res("t1"), res("t2", False, "element_not_found", 2)],
             "findings": [{"test_id": "t2", "verdict": "inconclusive", "reason": ""}], "repair_attempts": 1}
    m = rm.evaluate("clean", final)
    assert m["false_alarm"] is True and m["detected"] is None
    assert m["n_tests"] == 2 and m["n_failed"] == 1 and m["verdicts"] == {"inconclusive": 1}


def test_clean_mode_all_pass_is_no_false_alarm():
    final = {"test_cases": [tc("t1", [GOTO, TOTAL])], "results": [res("t1")], "findings": [], "repair_attempts": 0}
    assert rm.evaluate("clean", final)["false_alarm"] is False


@pytest.mark.parametrize("message,kind", [
    ("429 RESOURCE_EXHAUSTED You exceeded your current quota", "quota"),
    ("503 UNAVAILABLE This model is currently experiencing high demand", "overloaded"),
    ("Request timed out", "timeout"),
    ("boom", "other"),
])
def test_error_kind(message, kind):
    assert rm.error_kind(RuntimeError(message)) == kind


def test_summarize_excludes_api_errors_from_denominator():
    rows = [
        {"prompt_version": "p", "variant": "B", "mode": "coupon", "status": "ok", "detected": "True", "false_alarm": ""},
        {"prompt_version": "p", "variant": "B", "mode": "coupon", "status": "ok", "detected": "False", "false_alarm": ""},
        {"prompt_version": "p", "variant": "B", "mode": "coupon", "status": "error:overloaded", "detected": "", "false_alarm": ""},
        {"prompt_version": "p", "variant": "B", "mode": "clean", "status": "ok", "detected": "", "false_alarm": "False"},
    ]
    s = {g["mode"]: g for g in rm.summarize(rows)}
    assert (s["coupon"]["runs"], s["coupon"]["detected"], s["coupon"]["api_errors"]) == (2, 1, 1)
    assert (s["clean"]["runs"], s["clean"]["false_alarms"]) == (1, 0)
    assert "1/2 (50%)" in rm.format_table(rm.summarize(rows))


def test_csv_header_written_once_and_roundtrips(tmp_path):
    path = tmp_path / "runs.csv"
    rm.append_row(path, {"mode": "coupon", "status": "ok", "detected": True})
    rm.append_row(path, {"mode": "clean", "status": "ok", "false_alarm": False})
    rows = rm.read_rows(path)
    assert [r["mode"] for r in rows] == ["coupon", "clean"] and rows[0]["detected"] == "True"
    assert path.read_text(encoding="utf-8-sig").count("timestamp") == 1


def make_args(tmp_path, **kw):
    base = dict(spec=str(tmp_path / "spec.md"), base_url="http://shop", pages=["/"], modes=["coupon"],
                variants=["B"], runs=2, prompt_version="t", max_repairs=3, pause=0, error_pause=0,
                max_consecutive_errors=3, csv=str(tmp_path / "runs.csv"))
    base.update(kw)
    (tmp_path / "spec.md").write_text("spec", encoding="utf-8")
    return SimpleNamespace(**base)


def fake_final(passed):
    return {"run_id": "r", "test_cases": [tc("t1", [GOTO, TOTAL])],
            "results": [res("t1", passed, "" if passed else "assertion_failed", None if passed else 2)],
            "findings": [], "repair_attempts": 0, "_artifacts_dir": "x"}


def test_experiment_uses_bug_url_and_counts_only_successful_runs(tmp_path):
    seen = []

    def run_once(spec, url, pages, self_repair, max_repairs, tags, meta):
        seen.append(url)
        if len(seen) == 2:
            raise RuntimeError("503 UNAVAILABLE")
        return fake_final(False)

    rm.run_experiment(make_args(tmp_path), run_once=run_once, sleep=lambda s: None)
    rows = rm.read_rows(tmp_path / "runs.csv")
    assert all(u == "http://shop/?bug=coupon" for u in seen)
    assert [r["status"] for r in rows] == ["ok", "error:overloaded", "ok"]
    assert sum(r["detected"] == "True" for r in rows) == 2


def test_experiment_stops_everything_on_quota_error(tmp_path):
    calls = []

    def run_once(*a):
        calls.append(1)
        raise RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded")

    rm.run_experiment(make_args(tmp_path, modes=["coupon", "clean"]), run_once=run_once, sleep=lambda s: None)
    assert len(calls) == 1
    assert rm.read_rows(tmp_path / "runs.csv")[0]["status"] == "error:quota"


def test_experiment_stops_after_consecutive_errors(tmp_path):
    calls = []

    def run_once(*a):
        calls.append(1)
        raise RuntimeError("503 UNAVAILABLE")

    rm.run_experiment(make_args(tmp_path, runs=5), run_once=run_once, sleep=lambda s: None)
    assert len(calls) == 3
