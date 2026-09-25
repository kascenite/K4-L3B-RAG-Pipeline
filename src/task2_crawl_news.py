"""
Task 2 — Crawl bài viết/thông báo.

Hướng dẫn:
    1. Điền tối thiểu 5 URL công khai vào ARTICLE_URLS.
    2. Crawl từng URL bằng Crawl4AI.
    3. Lưu mỗi bài thành một JSON trong data/landing/news/.
    4. Giữ đủ url, title, date_crawled và content_markdown.

Cài browser trước khi chạy:
    python -m playwright install chromium
    
-> Dùng Firecrawl or bất cứ công cụ nào bạn quen    
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig, DefaultMarkdownGenerator


DATA_DIR = Path(__file__).parent.parent / "data" / "landing" / "news"

# Chủ đề: Pháp luật cho hộ kinh doanh (thuế, đăng ký, hóa đơn điện tử).
ARTICLE_URLS = [
    "https://baochinhphu.vn/quy-dinh-moi-ve-dang-ky-ho-kinh-doanh-102250702150908133.htm",
    "https://baochinhphu.vn/huong-dan-khai-thue-nop-thue-gtgt-thue-thu-nhap-ca-nhan-doi-voi-ho-kinh-doanh-ca-nhan-kinh-doanh-102260306084928557.htm",
    "https://baochinhphu.vn/tu-2026-ho-kinh-doanh-phai-bao-co-quan-thue-cac-tai-khoan-nhan-tien-102260307185152112.htm",
    "https://baochinhphu.vn/chinh-thuc-nang-nguong-chiu-thue-voi-ho-kinh-doanh-len-01-ty-dong-nam-ap-dung-tu-1-1-2026-102260429185517215.htm",
    "https://vnexpress.net/co-quan-thue-huong-dan-ho-kinh-doanh-ke-khai-nop-thue-tu-2026-5013509.html",
    "https://dantri.com.vn/kinh-doanh/chinh-thuc-ban-hanh-nghi-dinh-ve-quan-ly-thue-ho-ca-nhan-kinh-doanh-20260305225531512.htm",
    "https://tuoitre.vn/khong-su-dung-doanh-thu-nam-2026-de-xac-dinh-lai-nghia-vu-thue-cua-ho-kinh-doanh-20260306110116155.htm",
    "https://vietnamnet.vn/ho-kinh-doanh-su-dung-hoa-don-dien-tu-ke-khai-thue-ra-sao-tu-nam-2026-2470000.html",
]

# Trang bị chặn (WAF/captcha) thường trả nội dung rất ngắn hoặc có các cụm này.
BLOCKED_MARKERS = ("access denied", "captcha", "just a moment", "attention required", "403 forbidden")
MIN_CONTENT_CHARS = 800
# Cắt phần "bài liên quan" nằm cuối thân bài.
TAIL_MARKERS = ("Tham khảo thêm", "Đọc nhiều trong", "Đọc tiếp", "Tin liên quan")

# Chỉ lấy sapo + thân bài, bỏ menu, bài liên quan, footer.
ARTICLE_SELECTORS = {
    "baochinhphu.vn": [".detail-sapo", ".detail-content"],
    "vnexpress.net": ["p.description", "article.fck_detail"],
    "dantri.com.vn": ["article"],
    "tuoitre.vn": [".detail-sapo", ".detail-content"],
    "vietnamnet.vn": [".content-detail-sapo", ".maincontent"],
}


def _run_config(url: str) -> CrawlerRunConfig:
    return CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        target_elements=ARTICLE_SELECTORS.get(urlparse(url).netloc.removeprefix("www.")),
        excluded_tags=["nav", "header", "footer", "aside", "form", "script", "style"],
        excluded_selector=".box-tinlienquanv2",  # box "tin liên quan" trong thân bài VnExpress
        remove_overlay_elements=True,
        markdown_generator=DefaultMarkdownGenerator(options={"ignore_images": True, "ignore_links": True}),
        page_timeout=60000,
    )


async def crawl_article(url: str) -> dict:
    """Crawl một URL; raise nếu bị chặn hoặc nội dung quá ngắn."""
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=_run_config(url))
    if not result.success:
        raise RuntimeError(f"HTTP {result.status_code}: {result.error_message}")
    content = result.markdown.raw_markdown
    for marker in TAIL_MARKERS:
        content = content.split(marker, 1)[0]
    content = re.sub(r"(\n[ \t*#]*)+$", "", content).strip()
    title = (result.metadata or {}).get("title") or ""
    if len(content) < MIN_CONTENT_CHARS or any(m in (title + content[:500]).lower() for m in BLOCKED_MARKERS):
        raise RuntimeError(f"Blocked or empty page ({len(content)} chars, title={title!r})")
    return {
        "url": url,
        "title": title.strip(),
        "date_crawled": datetime.now().isoformat(timespec="seconds"),
        "content_markdown": content,
    }


async def crawl_all() -> None:
    """Crawl và lưu từng bài thành một file JSON."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for index, url in enumerate(ARTICLE_URLS, 1):
        try:
            article = await crawl_article(url)
            output = DATA_DIR / f"article_{index:02d}.json"
            output.write_text(
                json.dumps(article, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"Saved: {output}")
        except Exception as error:
            print(f"Failed: {url} — {error}")


if __name__ == "__main__":
    asyncio.run(crawl_all())
