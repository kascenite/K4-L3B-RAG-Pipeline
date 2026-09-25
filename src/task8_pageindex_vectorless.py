"""
Task 8 — PageIndex vectorless fallback.

Hướng dẫn:
    1. Đọc PAGEINDEX_API_KEY từ .env.
    2. Upload tài liệu ở định dạng PageIndex hỗ trợ.
    3. Cache document IDs để không upload lại.
    4. Parse kết quả thành SearchResult có method pageindex.

PageIndex là dịch vụ ngoài: cần timeout và xử lý lỗi để pipeline không crash.
"""

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

PAGEINDEX_API_KEY = os.getenv("PAGEINDEX_API_KEY", "")
STANDARDIZED_DIR = Path(__file__).parent.parent / "data" / "standardized"
LEGAL_LANDING_DIR = Path(__file__).parent.parent / "data" / "landing" / "legal"
DOC_IDS_PATH = Path(__file__).parent.parent / "pageindex_doc_ids.json"
POLL_INTERVAL = 2
QUERY_TIMEOUT = 30  # giây; hết giờ thì bỏ document đó, không làm treo pipeline


def _client():
    if not PAGEINDEX_API_KEY:
        raise RuntimeError("PAGEINDEX_API_KEY is not set")
    from pageindex import PageIndexClient

    return PageIndexClient(api_key=PAGEINDEX_API_KEY)


def _load_doc_ids() -> dict[str, str]:
    if DOC_IDS_PATH.exists():
        return json.loads(DOC_IDS_PATH.read_text(encoding="utf-8"))
    return {}


def upload_documents() -> None:
    """Upload tài liệu và lưu document IDs để tái sử dụng.

    SDK chỉ nhận PDF -> upload các PDF gốc trong data/landing/legal/.
    """
    client = _client()
    doc_ids = _load_doc_ids()
    for path in sorted(LEGAL_LANDING_DIR.glob("*.pdf")):
        if path.name in doc_ids:
            continue
        doc_ids[path.name] = client.submit_document(str(path))["doc_id"]
        print(f"Uploaded {path.name} -> {doc_ids[path.name]}")
        DOC_IDS_PATH.write_text(json.dumps(doc_ids, indent=2), encoding="utf-8")


def _wait_retrieval(client, retrieval_id: str) -> dict:
    deadline = time.monotonic() + QUERY_TIMEOUT
    while time.monotonic() < deadline:
        result = client.get_retrieval(retrieval_id)
        if result.get("status") == "completed":
            return result
        if result.get("status") == "failed":
            break
        time.sleep(POLL_INTERVAL)
    return {}


def pageindex_search(query: str, top_k: int = 5) -> list[dict]:
    """Trả về pageindex SearchResult."""
    client = _client()
    doc_ids = _load_doc_ids()
    if not doc_ids:
        raise RuntimeError("No PageIndex documents uploaded; run upload_documents()")

    titles = {
        path.stem: path.read_text(encoding="utf-8").split("\n", 1)[0].lstrip("# ").strip()
        for path in (STANDARDIZED_DIR / "legal").glob("*.md")
    }
    results = []
    for source, doc_id in doc_ids.items():
        retrieval = client.submit_query(doc_id, query)
        for node in _wait_retrieval(client, retrieval["retrieval_id"]).get("retrieved_nodes", []):
            content = "\n".join(
                item.get("relevant_content", "") for item in node.get("relevant_contents", [])
            ).strip()
            if not content:
                continue
            stem = Path(source).stem
            results.append({
                "id": f"pageindex::{source}::{node.get('node_id', len(results))}",
                "content": content,
                "metadata": {
                    "source": f"{stem}.md",
                    "title": titles.get(stem, node.get("title") or stem),
                    "doc_type": "legal",
                    "url": None,
                    "chunk_index": len(results),
                },
                "retrieval_method": "pageindex",
            })
    # API không trả score -> gán score giảm dần theo rank.
    return [
        {**item, "score": 1.0 / rank}
        for rank, item in enumerate(results[:top_k], 1)
    ]


if __name__ == "__main__":
    upload_documents()
