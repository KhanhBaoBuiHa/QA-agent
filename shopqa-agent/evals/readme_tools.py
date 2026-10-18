"""Thay nội dung giữa hai dấu mốc trong README, để bảng số liệu và ảnh bằng chứng luôn khớp dữ liệu thật.

README cần có sẵn hai dòng:   <!-- TÊN:START -->   và   <!-- TÊN:END -->
"""
from pathlib import Path


def replace_block(readme_path, name: str, content: str) -> None:
    path = Path(readme_path)
    text = path.read_text(encoding="utf-8")
    start, end = f"<!-- {name}:START -->", f"<!-- {name}:END -->"
    i, j = text.find(start), text.find(end)
    if i == -1 or j == -1 or j < i:
        raise ValueError(f"README {path} thiếu cặp dấu mốc {start} ... {end}")
    path.write_text(text[: i + len(start)] + "\n" + content.strip() + "\n" + text[j:], encoding="utf-8")
