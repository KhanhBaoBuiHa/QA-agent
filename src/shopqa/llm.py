"""Chọn LLM theo biến môi trường, để đổi nhà cung cấp mà không sửa code.

  LLM_PROVIDER = anthropic | google | ollama | openai
  LLM_MODEL    = tên model của nhà cung cấp đã chọn (bắt buộc)

Chỉ cần cài gói langchain tương ứng với provider bạn dùng.
"""
import os


def get_llm(provider: str | None = None, model: str | None = None, temperature: float = 0.0):
    provider = (provider or os.getenv("LLM_PROVIDER", "anthropic")).lower()
    model = model or os.getenv("LLM_MODEL")
    if not model:
        raise RuntimeError("Chưa đặt LLM_MODEL (xem .env.example).")

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, temperature=temperature, max_tokens=4096)
    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model, temperature=temperature)
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=model, temperature=temperature)
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, temperature=temperature)
    raise RuntimeError(f"LLM_PROVIDER không hỗ trợ: {provider}")


def response_text(message) -> str:
    """Lấy phần chữ từ phản hồi (một số provider trả về danh sách block thay vì chuỗi)."""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)
