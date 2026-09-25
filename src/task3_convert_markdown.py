"""
Task 3 — Chuẩn hóa dữ liệu sang Markdown.

Hướng dẫn:
    1. Dùng MarkItDown để convert PDF/DOCX.
    2. Đọc JSON và giữ metadata ở đầu file Markdown.
    3. Giữ cấu trúc thư mục legal/ và news/.
    4. Không tạo file rỗng hoặc file trùng khi chạy lại.

Cài đặt:
    Dependency MarkItDown đã được khai báo trong pyproject.toml.
    
-> Hoặc dùng công cụ nào bạn quen khác Markitdown
"""

import json
import re
import unicodedata
from pathlib import Path

from markitdown import MarkItDown


LANDING_DIR = Path(__file__).parent.parent / "data" / "landing"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "standardized"


def _header(title: str, url: str, extra: str = "") -> str:
    return f"# {title}\n\n**Source:** {url}\n\n{extra}---\n\n"


def _clean_legal_text(text: str) -> str:
    """Bỏ header trang Công báo, số trang, ô bảng trống, dòng kẻ biểu mẫu; chuẩn hóa NFC."""
    text = unicodedata.normalize("NFC", text)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"CÔNG BÁO/Số .*", stripped) or re.fullmatch(r"\d{1,3}|\\", stripped):
            continue
        line = re.sub(r"(?:\\?[._…]){4,}", "…", line)  # dòng chấm/gạch điền biểu mẫu
        line = re.sub(r"\|(?:\s*\|){2,}", "| |", line)  # chuỗi ô bảng trống
        lines.append(re.sub(r"[ \t]{2,}", " ", line).rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def convert_legal_docs() -> None:
    """Convert PDF/DOCX vào standardized/legal; title/url lấy từ sources.json của Task 1."""
    legal_dir = LANDING_DIR / "legal"
    output_dir = OUTPUT_DIR / "legal"
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = json.loads((legal_dir / "sources.json").read_text(encoding="utf-8"))
    converter = MarkItDown()
    for path in sorted(legal_dir.iterdir()):
        if path.suffix.lower() not in {".pdf", ".doc", ".docx"}:
            continue
        meta = sources.get(path.name, {"title": path.stem, "url": ""})
        body = _clean_legal_text(converter.convert(str(path)).text_content)
        if not body.strip():
            print(f"Skip (empty text): {path.name}")
            continue
        (output_dir / f"{path.stem}.md").write_text(
            _header(meta["title"], meta["url"]) + body, encoding="utf-8"
        )
        print(f"Converted: {path.name}")


def convert_news_articles() -> None:
    """Convert JSON vào standardized/news, giữ title/url/date_crawled ở đầu file."""
    news_dir = LANDING_DIR / "news"
    output_dir = OUTPUT_DIR / "news"
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(news_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not data["content_markdown"].strip():
            print(f"Skip (empty): {path.name}")
            continue
        header = _header(data["title"].strip(), data["url"], f"**Crawled:** {data['date_crawled']}\n\n")
        body = unicodedata.normalize("NFC", data["content_markdown"].strip())
        (output_dir / f"{path.stem}.md").write_text(header + body + "\n", encoding="utf-8")
        print(f"Converted: {path.name}")


def convert_all() -> None:
    """Convert toàn bộ dữ liệu landing."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    convert_legal_docs()
    convert_news_articles()
    print(f"Saved Markdown to: {OUTPUT_DIR}")


if __name__ == "__main__":
    convert_all()
