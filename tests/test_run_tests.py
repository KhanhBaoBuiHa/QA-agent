import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright  # noqa: E402

from shopqa.nodes.run_tests import run_tests  # noqa: E402
from shopqa.state import initial_state  # noqa: E402

SHOP_DIR = Path(__file__).resolve().parents[1] / "demo_shop" / "mini_shop"


@pytest.fixture(scope="module", autouse=True)
def chromium_available():
    try:
        with sync_playwright() as p:
            p.chromium.launch().close()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Chromium chưa cài: {e}")


@pytest.fixture(scope="module")
def base_url():
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=str(SHOP_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def tid(name):
    return f'[data-testid="{name}"]'


def coupon_test(test_id, start="/"):
    return {"id": test_id, "title": "Áp mã", "steps": [], "expected": "giảm 10%", "actions": [
        {"action": "goto", "target": start},
        {"action": "click", "target": tid("add-p1")},
        {"action": "fill", "target": tid("coupon-input"), "value": "SALE10"},
        {"action": "click", "target": tid("apply-coupon")},
        {"action": "expect_text", "target": tid("cart-total"), "value": "90.000"},
    ]}


def run(base_url, tmp_path, tests):
    state = initial_state("spec", base_url)
    state["test_cases"] = tests
    return {r["test_id"]: r for r in
            run_tests(state, timeout_ms=800, artifacts_dir=str(tmp_path))["results"]}


def test_happy_paths_pass_and_take_screenshots(base_url, tmp_path):
    add = {"id": "add", "title": "Thêm", "steps": [], "expected": "", "actions": [
        {"action": "goto", "target": "/"},
        {"action": "click", "target": tid("add-p1")},
        {"action": "expect_text", "target": tid("cart-count"), "value": "1"},
        {"action": "expect_text", "target": tid("cart-total"), "value": "100.000"}]}
    empty = {"id": "empty", "title": "Giỏ trống", "steps": [], "expected": "", "actions": [
        {"action": "goto", "target": "/"},
        {"action": "expect_disabled", "target": tid("checkout-button")}]}
    res = run(base_url, tmp_path, [add, empty, coupon_test("coupon")])
    assert all(r["passed"] for r in res.values()), {k: v["log"] for k, v in res.items()}
    assert len(res["add"]["screenshots"]) == 4
    assert all(Path(p).exists() for p in res["add"]["screenshots"])


def test_coupon_bug_is_assertion_failed(base_url, tmp_path):
    res = run(base_url, tmp_path, [coupon_test("coupon_bug", "/?bug=coupon")])["coupon_bug"]
    assert not res["passed"]
    assert res["error_type"] == "assertion_failed" and res["failed_step"] == 5
    assert "99.000" in res["log"]            # log nói rõ giá trị thực tế
    assert res["screenshots"][-1].endswith("step_05_FAILED.png")


def test_checkout_bug_is_assertion_failed(base_url, tmp_path):
    t = {"id": "co", "title": "", "steps": [], "expected": "", "actions": [
        {"action": "goto", "target": "/?bug=checkout"},
        {"action": "expect_disabled", "target": tid("checkout-button")}]}
    res = run(base_url, tmp_path, [t])["co"]
    assert res["error_type"] == "assertion_failed"


def test_wrong_selector_is_element_not_found(base_url, tmp_path):
    t = {"id": "bad", "title": "", "steps": [], "expected": "", "actions": [
        {"action": "goto", "target": "/"},
        {"action": "click", "target": tid("khong-ton-tai")}]}
    res = run(base_url, tmp_path, [t])["bad"]
    assert res["error_type"] == "element_not_found" and res["failed_step"] == 2


def test_invalid_selector_syntax_is_invalid_action(base_url, tmp_path):
    t = {"id": "syn", "title": "", "steps": [], "expected": "", "actions": [
        {"action": "goto", "target": "/"},
        {"action": "click", "target": "div[[["}]}
    assert run(base_url, tmp_path, [t])["syn"]["error_type"] == "invalid_action"


def test_unreachable_site_is_navigation_error(tmp_path):
    state = initial_state("spec", "http://127.0.0.1:9")
    state["test_cases"] = [{"id": "nav", "title": "", "steps": [], "expected": "",
                            "actions": [{"action": "goto", "target": "/"}]}]
    res = run_tests(state, timeout_ms=800, artifacts_dir=str(tmp_path))["results"][0]
    assert res["error_type"] == "navigation_error"


def test_tests_are_isolated(base_url, tmp_path):
    """Giỏ hàng của test trước không được rò sang test sau."""
    a = {"id": "a", "title": "", "steps": [], "expected": "", "actions": [
        {"action": "goto", "target": "/"}, {"action": "click", "target": tid("add-p1")}]}
    b = {"id": "b", "title": "", "steps": [], "expected": "", "actions": [
        {"action": "goto", "target": "/"},
        {"action": "expect_text", "target": tid("cart-count"), "value": "0"}]}
    assert run(base_url, tmp_path, [a, b])["b"]["passed"]


def test_base_url_query_is_applied_to_every_page(base_url, tmp_path):
    """base_url có ?bug=coupon thì test dùng goto "/" vẫn gặp lỗi cài sẵn."""
    res = run(f"{base_url}/?bug=coupon", tmp_path, [coupon_test("flag")])["flag"]
    assert res["error_type"] == "assertion_failed" and "99.000" in res["log"]


def test_resolve_url_merges_queries():
    from shopqa.tools.browser import resolve_url
    assert resolve_url("http://h:1", "/") == "http://h:1/"
    assert resolve_url("http://h:1/?bug=a", "/") == "http://h:1/?bug=a"
    assert resolve_url("http://h:1/?bug=a", "/cart?x=1") == "http://h:1/cart?x=1&bug=a"
    assert resolve_url("http://h:1/shop", "cart") == "http://h:1/shop/cart"
    assert resolve_url("http://h:1", "https://other.com/x") == "https://other.com/x"
