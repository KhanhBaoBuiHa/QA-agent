
"""Optional Langfuse tracing for ShopQA-Agent.

Tracing is best-effort: missing dependencies or tracing failures
must never prevent the QA workflow from running.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    """Return whether tracing is enabled and credentials are configured."""
    if os.getenv("SHOPQA_TRACING", "1").strip().lower() in {
        "0", "false", "no", "off"
    }:
        return False

    return bool(
        os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
        and os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    )


def get_trace_config(
    run_name: str | None = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build LangGraph config for Langfuse, or return {} if unavailable."""
    if not is_enabled():
        return {}

    try:
        from langfuse.langchain import CallbackHandler

        handler = CallbackHandler()

        trace_metadata = dict(metadata or {})
        if session_id is not None:
            trace_metadata["langfuse_session_id"] = session_id
        if tags is not None:
            trace_metadata["langfuse_tags"] = tags

        config: dict[str, Any] = {
            "callbacks": [handler],
            "metadata": trace_metadata,
        }

        if run_name is not None:
            config["run_name"] = run_name

        return config

    except Exception as exc:
        logger.warning(
            "Langfuse tracing unavailable; continuing without tracing: %s",
            exc,
        )
        return {}


def flush() -> None:
    """Flush pending Langfuse events without interrupting the QA run."""
    if not is_enabled():
        return

    try:
        import langfuse

        client = langfuse.get_client()
        client.flush()
    except Exception as exc:
        logger.warning("Could not flush Langfuse events: %s", exc)
