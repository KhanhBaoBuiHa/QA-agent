"""Node 2: chạy từng test bằng Playwright, chụp ảnh từng bước."""
import os
from pathlib import Path

from playwright.sync_api import Browser, sync_playwright

from shopqa.state import AgentState, TestCase, TestResult
from shopqa.tools.browser import ActionError, describe, execute_action


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, "1" if default else "0").lower() in ("1", "true", "yes")


def _shot(page, path: Path) -> str | None:
    try:
        page.screenshot(path=str(path))
        return str(path)
    except Exception:  # noqa: BLE001 - lỗi chụp ảnh không được làm hỏng kết quả test
        return None


def _run_one(browser: Browser, test: TestCase, base_url: str, out_dir: Path,
             timeout_ms: int) -> TestResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1280, "height": 800})  # mỗi test một context sạch
    page = context.new_page()
    log: list[str] = []
    shots: list[str] = []
    try:
        for i, act in enumerate(test["actions"], start=1):
            try:
                execute_action(page, act, base_url, timeout_ms)
            except ActionError as e:
                log.append(f"✗ {i}. {describe(act)} -> {e.kind}: {e.message}")
                if path := _shot(page, out_dir / f"step_{i:02d}_FAILED.png"):
                    shots.append(path)
                return TestResult(test_id=test["id"], passed=False, log="\n".join(log),
                                  screenshots=shots, failed_step=i, error_type=e.kind)
            log.append(f"✓ {i}. {describe(act)}")
            if path := _shot(page, out_dir / f"step_{i:02d}.png"):
                shots.append(path)
        return TestResult(test_id=test["id"], passed=True, log="\n".join(log),
                          screenshots=shots, failed_step=None, error_type="")
    finally:
        context.close()


def run_tests(state: AgentState, *, headless: bool | None = None,
              timeout_ms: int | None = None, artifacts_dir: str | None = None) -> dict:
    """Chạy toàn bộ test_cases trong state. Chạy lại tất cả mỗi lượt (đơn giản, dễ đo)."""
    headless = _env_bool("SHOPQA_HEADLESS", True) if headless is None else headless
    timeout_ms = timeout_ms or int(os.getenv("SHOPQA_TIMEOUT_MS", "5000"))
    artifacts_dir = artifacts_dir or os.getenv("SHOPQA_ARTIFACTS", "artifacts")

    out_root = Path(artifacts_dir) / state["run_id"] / f"attempt_{state['repair_attempts']}"
    results: list[TestResult] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            for test in state["test_cases"]:
                results.append(_run_one(browser, test, state["base_url"],
                                        out_root / test["id"], timeout_ms))
        finally:
            browser.close()
    return {"results": results}
