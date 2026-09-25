"""
Task 1 — Thu thập tài liệu chính sách/quy định.

Hướng dẫn:
    1. Chọn chủ đề của nhóm.
    2. Tìm tối thiểu 3 tài liệu PDF/DOCX từ nguồn công khai.
    3. Lưu file gốc vào data/landing/legal/.
    4. Đặt tên không dấu và thể hiện đúng nội dung.

Ví dụ tài liệu: học phí, học bổng, ký túc xá, quy trình đăng ký.
Nếu website chặn crawler, hãy chọn nguồn công khai khác; không vượt WAF.

Chủ đề: Pháp luật cho hộ kinh doanh. Nguồn: Công báo Chính phủ (congbao.chinhphu.vn).
Bản PDF ký số trên vanban.chinhphu.vn là ảnh scan (không có text) nên dùng
bản DOCX/PDF text của Công báo.
"""

import base64
import io
import json
import re
import tempfile
import zipfile
from html import unescape
from pathlib import Path

import certifi
import requests


DATA_DIR = Path(__file__).parent.parent / "data" / "landing" / "legal"
SOURCES_FILE = DATA_DIR / "sources.json"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# g7.cdnchinhphu.vn (nơi Công báo phát file DOCX) không gửi chứng chỉ trung gian.
# Bổ sung chứng chỉ trung gian chính thức của GlobalSign; chuỗi vẫn được xác thực
# đến root CA trong certifi, không tắt kiểm tra SSL.
GLOBALSIGN_INTERMEDIATE = "http://secure.globalsign.com/cacert/gsrsaovsslca2018.crt"

# file_url=None: lấy link DOCX mới nhất trên trang Công báo khi chạy.
SOURCES = [
    {
        "filename": "nd-168-2025-dang-ky-ho-kinh-doanh.pdf",
        "title": "Nghị định 168/2025/NĐ-CP về đăng ký doanh nghiệp — Chương VIII: Hộ kinh doanh và đăng ký hộ kinh doanh",
        "url": "https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-168-2025-nd-cp-45354.htm",
        # Công báo số 887+888 chứa Chương VIII (hộ kinh doanh) và Chương IX.
        "file_url": "https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2025/6/45354/57300-1-2025887-888168-2025-nd-cp.pdf",
    },
    {
        "filename": "nd-68-2026-thue-ho-kinh-doanh.docx",
        "title": "Nghị định 68/2026/NĐ-CP quy định về chính sách thuế và quản lý thuế đối với hộ kinh doanh, cá nhân kinh doanh",
        "url": "https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-68-2026-nd-cp-469047.htm",
        "file_url": None,
    },
    {
        # Nâng ngưỡng doanh thu không chịu thuế từ 500 triệu lên 01 tỷ đồng/năm.
        "filename": "nd-141-2026-sua-doi-nd-68-nguong-doanh-thu.docx",
        "title": "Nghị định 141/2026/NĐ-CP sửa đổi, bổ sung Nghị định 68/2026/NĐ-CP (nâng ngưỡng doanh thu không chịu thuế lên 01 tỷ đồng/năm) và Nghị định 320/2025/NĐ-CP",
        "url": "https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-141-2026-nd-cp-469455.htm",
        "file_url": None,
    },
    {
        "filename": "tt-18-2026-thu-tuc-quan-ly-thue-ho-kinh-doanh.docx",
        "title": "Thông tư 18/2026/TT-BTC quy định về hồ sơ, thủ tục quản lý thuế đối với hộ kinh doanh, cá nhân kinh doanh",
        "url": "https://congbao.chinhphu.vn/van-ban/thong-tu-so-18-2026-tt-btc-469080/63294.htm",
        "file_url": None,
    },
    {
        "filename": "nd-254-2026-hoa-don-dien-tu.docx",
        "title": "Nghị định 254/2026/NĐ-CP hướng dẫn Luật Quản lý thuế số 108/2025/QH15 về hóa đơn điện tử, chứng từ điện tử",
        "url": "https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-254-2026-nd-cp-469957.htm",
        "file_url": None,
    },
]


def setup_directory() -> None:
    """Tạo thư mục lưu tài liệu gốc."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Ready: {DATA_DIR}")


def _ca_bundle() -> str:
    """certifi + chứng chỉ trung gian GlobalSign còn thiếu trên CDN."""
    der = requests.get(GLOBALSIGN_INTERMEDIATE, timeout=30).content
    pem = "-----BEGIN CERTIFICATE-----\n"
    b64 = base64.b64encode(der).decode()
    pem += "\n".join(b64[i : i + 64] for i in range(0, len(b64), 64))
    pem += "\n-----END CERTIFICATE-----\n"
    bundle = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
    bundle.write(Path(certifi.where()).read_text() + pem)
    bundle.close()
    return bundle.name


def _find_docx_link(page_url: str) -> str:
    html = requests.get(page_url, timeout=60, headers=HEADERS).text
    match = re.search(r'href="(https://g7\.cdnchinhphu\.vn/[^"]+\.docx)"', html)
    if not match:
        raise RuntimeError(f"No DOCX link on {page_url}")
    return unescape(match.group(1))


def _normalize_docx(content: bytes) -> bytes:
    """DOCX của Công báo dùng '\\' trong đường dẫn zip; python-docx/mammoth cần '/'."""
    src = zipfile.ZipFile(io.BytesIO(content))
    out_buf = io.BytesIO()
    with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as out:
        for info in src.infolist():
            out.writestr(info.filename.replace("\\", "/"), src.read(info))
    return out_buf.getvalue()


def download_documents() -> None:
    """Tải ít nhất 3 PDF/DOCX từ nguồn công khai và ghi sources.json (url, title)."""
    ca_bundle = None
    metadata = {}
    for source in SOURCES:
        path = DATA_DIR / source["filename"]
        file_url = source["file_url"]
        if not path.exists():
            if file_url is None:
                file_url = _find_docx_link(source["url"])
                ca_bundle = ca_bundle or _ca_bundle()
            response = requests.get(file_url, timeout=120, headers=HEADERS, verify=ca_bundle or True)
            response.raise_for_status()
            content = response.content
            if path.suffix == ".docx":
                content = _normalize_docx(content)
            path.write_bytes(content)
            print(f"Saved: {path.name} ({len(content) // 1024} KB)")
        else:
            print(f"Skip (exists): {path.name}")
        metadata[source["filename"]] = {"title": source["title"], "url": source["url"]}

    SOURCES_FILE.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {SOURCES_FILE.name}")


if __name__ == "__main__":
    setup_directory()
    download_documents()
