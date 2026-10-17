import sys

import pytest

from shopqa import tracing

KEYS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "SHOPQA_TRACING")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)


def enable(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://127.0.0.1:9")


def test_disabled_without_keys():
    assert not tracing.is_enabled()
    assert tracing.get_trace_config() == {}
    tracing.flush()  # không được lỗi


def test_can_be_switched_off_even_with_keys(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setenv("SHOPQA_TRACING", "0")
    assert tracing.get_trace_config() == {}


def test_config_has_callback_session_and_tags(monkeypatch):
    pytest.importorskip("langfuse")
    enable(monkeypatch)
    cfg = tracing.get_trace_config(run_name="x", session_id="run-1", tags=["a", "b"], metadata={"mode": "coupon"})
    assert len(cfg["callbacks"]) == 1 and cfg["run_name"] == "x"
    assert cfg["metadata"] == {"mode": "coupon", "langfuse_session_id": "run-1", "langfuse_tags": ["a", "b"]}


def test_missing_package_does_not_break_the_run(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setitem(sys.modules, "langfuse.langchain", None)  # giả lập chưa cài
    assert tracing.get_trace_config() == {}


def test_flush_swallows_errors(monkeypatch):
    pytest.importorskip("langfuse")
    enable(monkeypatch)
    import langfuse

    def boom():
        raise RuntimeError("network down")

    monkeypatch.setattr(langfuse, "get_client", boom)
    tracing.flush()  # không được ném lỗi
