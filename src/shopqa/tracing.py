"""Langfuse (tùy chọn): ghi lại trace của từng node và từng lần gọi LLM.

Bật bằng cách điền trong .env:
  LANGFUSE_PUBLIC_KEY=pk-lf-...
  LANGFUSE_SECRET_KEY=sk-lf-...
  LANGFUSE_BASE_URL=https://cloud.langfuse.com      (project ở vùng Mỹ: https://us.cloud.langfuse.com)
Đặt SHOPQA_TRACING=0 để tắt tạm thời mà không cần xóa khóa.

Nguyên tắc: tracing KHÔNG BAO GIỜ được làm hỏng một lần chạy. Thiếu khóa, thiếu gói, hay
Langfuse lỗi mạng đều chỉ in một dòng cảnh báo rồi agent chạy tiếp như bình thường.
"""
import os

from shopqa.log import log


def is_enabled() -> bool:
    has_keys = bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))
    return has_keys and os.getenv("SHOPQA_TRACING", "1") != "0"


def get_trace_config(run_name: str = "shopqa-run", session_id: str | None = None,
                     tags: list[str] | None = None, metadata: dict | None = None) -> dict:
    """Trả về `config` để truyền vào graph.invoke(state, config=...). Rỗng nếu tracing đang tắt."""
    if not is_enabled():
        return {}
    try:
        from langfuse.langchain import CallbackHandler

        handler = CallbackHandler()
    except ImportError:
        log("[tracing] đã có khóa Langfuse nhưng chưa cài gói: pip install langfuse (chạy không trace)")
        return {}
    except Exception as e:  # noqa: BLE001
        log(f"[tracing] không khởi tạo được Langfuse ({type(e).__name__}), chạy không trace")
        return {}

    meta = dict(metadata or {})
    if session_id:
        meta["langfuse_session_id"] = session_id   # gom các trace cùng một lần chạy
    if tags:
        meta["langfuse_tags"] = list(tags)         # lọc trên giao diện Langfuse
    return {"callbacks": [handler], "run_name": run_name, "tags": list(tags or []), "metadata": meta}


def flush() -> None:
    """Gửi nốt trace còn đang chờ. Bắt buộc với chương trình ngắn như CLI, nếu không trace có thể mất."""
    if not is_enabled():
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception as e:  # noqa: BLE001
        log(f"[tracing] không gửi được trace lên Langfuse ({type(e).__name__})")
