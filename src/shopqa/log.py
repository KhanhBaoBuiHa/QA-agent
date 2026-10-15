"""In tiến độ ra màn hình (có giờ), để biết agent đang làm gì thay vì im lặng."""
import sys
import time

# Trên Windows, khi đầu ra bị chuyển hướng/đưa qua pipe (vd `| Select-Object`), Python dùng
# bảng mã cp1252 và không in được tiếng Việt. Ép UTF-8 để không bao giờ bị lỗi này.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

_START = time.monotonic()


def log(message: str) -> None:
    elapsed = time.monotonic() - _START
    print(f"[{elapsed:6.1f}s] {message}", flush=True)