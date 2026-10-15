"""Các hàm bọc Playwright: chạy một action, và "chụp" danh sách phần tử UI của trang.

Các loại lỗi (error_type) mà một action có thể gây ra, để node classify dùng:
  element_not_found      không tìm thấy phần tử (selector sai HOẶC web thiếu phần tử)
  element_not_actionable thấy phần tử nhưng không bấm/nhập được (vd nút bị vô hiệu)
  assertion_failed       phần tử có, nhưng nội dung/trạng thái khác kỳ vọng (tín hiệu mạnh của lỗi thật)
  navigation_error       không mở được trang
  invalid_action         action sai cú pháp (vd selector không hợp lệ)
  runtime_error          lỗi không lường trước
"""
import re
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from shopqa.state import Action


class ActionError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def resolve_url(base_url: str, target: str) -> str:
    """Ghép base_url với đường dẫn của action.

    Nếu base_url có query (vd http://localhost:8000/?bug=coupon) thì query đó được
    gắn vào MỌI trang agent mở. Dùng để bật "feature flag"/lỗi cài sẵn của shop demo
    mà không cần sửa test do LLM sinh ra.
    """
    if target.startswith(("http://", "https://")):
        return target
    base = urlsplit(base_url)
    root = urlunsplit((base.scheme, base.netloc, base.path.rstrip("/") + "/", "", ""))
    url = urljoin(root, target.lstrip("/"))
    if base.query:
        u = urlsplit(url)
        query = f"{u.query}&{base.query}" if u.query else base.query
        url = urlunsplit((u.scheme, u.netloc, u.path, query, u.fragment))
    return url


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _first_line(message: str) -> str:
    lines = [l for l in message.strip().splitlines() if l.strip()]
    return lines[0][:200] if lines else "lỗi không rõ"


def _wait_until(page: Page, predicate, timeout_ms: int) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        if predicate():
            return True
        if time.monotonic() >= deadline:
            return False
        page.wait_for_timeout(100)


def describe(act: Action) -> str:
    parts = [act["action"]]
    if act.get("target"):
        parts.append(act["target"])
    if act.get("value") is not None:
        parts.append(f"= {act['value']!r}")
    return " ".join(parts)


def execute_action(page: Page, act: Action, base_url: str, timeout_ms: int = 5000) -> None:
    """Chạy một action. Thành công thì trả về None, thất bại thì raise ActionError."""
    kind, target, value = act["action"], act.get("target"), act.get("value")
    try:
        if kind == "goto":
            page.goto(resolve_url(base_url, target), timeout=timeout_ms)
        elif kind == "click":
            page.click(target, timeout=timeout_ms)
        elif kind == "fill":
            page.fill(target, value, timeout=timeout_ms)
        elif kind == "select":
            page.select_option(target, value, timeout=timeout_ms)
        elif kind == "expect_visible":
            page.wait_for_selector(target, state="visible", timeout=timeout_ms)
        elif kind == "expect_not_visible":
            try:
                page.wait_for_selector(target, state="hidden", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                raise ActionError("assertion_failed", f"{target} vẫn đang hiển thị")
        elif kind == "expect_text":
            loc = page.locator(target).first
            loc.wait_for(state="visible", timeout=timeout_ms)
            actual = ""

            def has_text() -> bool:
                nonlocal actual
                actual = _norm(loc.inner_text())
                return _norm(value) in actual

            if not _wait_until(page, has_text, timeout_ms):
                raise ActionError("assertion_failed",
                                  f"kỳ vọng chứa {value!r}, thực tế là {actual!r}")
        elif kind in ("expect_enabled", "expect_disabled"):
            loc = page.locator(target).first
            loc.wait_for(state="attached", timeout=timeout_ms)
            want_disabled = kind == "expect_disabled"
            if not _wait_until(page, lambda: loc.is_disabled() == want_disabled, timeout_ms):
                state = "đang bị vô hiệu" if loc.is_disabled() else "đang bật"
                raise ActionError("assertion_failed", f"{target} {state}, trái với kỳ vọng")
        elif kind == "expect_url":
            try:
                page.wait_for_url(lambda url: value in url, timeout=timeout_ms)
            except PlaywrightTimeoutError:
                raise ActionError("assertion_failed",
                                  f"URL hiện tại {page.url!r} không chứa {value!r}")
        else:
            raise ActionError("invalid_action", f"action không hỗ trợ: {kind}")
    except ActionError:
        raise
    except PlaywrightTimeoutError as e:
        msg = _first_line(str(e))
        if kind == "goto":
            raise ActionError("navigation_error", msg)
        if "not enabled" in str(e) or "intercepts pointer" in str(e):
            raise ActionError("element_not_actionable", msg)
        raise ActionError("element_not_found", msg)
    except PlaywrightError as e:
        kind_ = "navigation_error" if kind == "goto" else "invalid_action"
        raise ActionError(kind_, _first_line(str(e)))
    except Exception as e:  # noqa: BLE001 - muốn bắt mọi thứ để test không làm sập cả lượt chạy
        raise ActionError("runtime_error", f"{type(e).__name__}: {e}")


_SNAPSHOT_JS = """
() => Array.from(document.querySelectorAll('a, button, input, select, textarea, [data-testid]')).map(el => {
  const r = el.getBoundingClientRect();
  return {
    tag: el.tagName.toLowerCase(),
    testid: el.getAttribute('data-testid') || '',
    id: el.id || '',
    name: el.getAttribute('name') || '',
    type: el.getAttribute('type') || '',
    text: (el.innerText || el.placeholder || '').trim().slice(0, 60),
    visible: r.width > 0 && r.height > 0,
  };
}).filter(e => e.testid || e.visible)
"""


def snapshot_page(page: Page) -> str:
    """Liệt kê các phần tử tương tác của trang hiện tại, dạng văn bản cho LLM đọc."""
    lines = []
    for e in page.evaluate(_SNAPSHOT_JS):
        if e["testid"]:
            selector = f'[data-testid="{e["testid"]}"]'
        elif e["id"]:
            selector = f'#{e["id"]}'
        elif e["name"]:
            selector = f'[name="{e["name"]}"]'
        else:
            selector = e["tag"]
        extra = f' type={e["type"]}' if e["type"] else ""
        text = f' text="{e["text"]}"' if e["text"] else ""
        lines.append(f"- <{e['tag']}> {selector}{extra}{text}")
    return "\n".join(lines)


def build_app_context(base_url: str, paths: list[str], timeout_ms: int = 10000) -> str:
    """Mở từng trang, ghi lại các phần tử UI thật để LLM không phải đoán selector."""
    sections = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            for path in paths:
                page.goto(resolve_url(base_url, path), timeout=timeout_ms)
                sections.append(f"Page {path}:\n{snapshot_page(page)}")
        finally:
            browser.close()
    return "\n\n".join(sections)
