"""Chọn LLM theo biến môi trường, để đổi nhà cung cấp mà không sửa code.

  LLM_PROVIDER = anthropic | google | ollama | openai
  LLM_MODEL    = tên model của nhà cung cấp đã chọn (bắt buộc)

Chỉ cần cài gói langchain tương ứng với provider bạn dùng.

  SHOPQA_LLM_TIMEOUT = số giây chờ tối đa cho MỖI lần gọi LLM (mặc định 60)
  SHOPQA_LLM_RETRIES = số lần tự thử lại khi gặp lỗi tạm thời như hết hạn mức (mặc định 2)

Vì sao cần: mặc định của langchain-google-genai là KHÔNG có timeout và thử lại tới 6 lần
với thời gian chờ tăng dần, nên khi bị giới hạn lượt gọi chương trình có vẻ như treo im lặng.
"""
import os


def get_llm(provider: str | None = None, model: str | None = None, temperature: float = 0.0):
    provider = (provider or os.getenv("LLM_PROVIDER", "anthropic")).lower()
    model = model or os.getenv("LLM_MODEL")
    if not model:
        raise RuntimeError("Chưa đặt LLM_MODEL (xem .env.example).")
    timeout = float(os.getenv("SHOPQA_LLM_TIMEOUT", "60"))
    retries = int(os.getenv("SHOPQA_LLM_RETRIES", "2"))

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, temperature=temperature, max_tokens=4096,
                             timeout=timeout, max_retries=retries)
    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model, temperature=temperature,
                                      timeout=timeout, max_retries=retries)
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=model, temperature=temperature,
                          client_kwargs={"timeout": timeout})
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, temperature=temperature,
                          timeout=timeout, max_retries=retries)
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