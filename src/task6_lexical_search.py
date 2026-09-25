"""
Task 6 — Lexical search bằng BM25.

Dùng cùng corpus chunks với Task 5. BM25 phù hợp với từ khóa chính xác, mã tài
liệu và tên riêng. Output phải theo SearchResult và sort score giảm dần.
"""

import re


CORPUS: list[dict] = []
_REAL_CORPUS: list[dict] = []
_INDEX_CACHE: tuple[int, object] | None = None


def tokenize(text: str) -> list[str]:
    # Tiếng Việt: tách theo âm tiết; \w unicode giữ dấu, giữ cả số hiệu "68/2026".
    return re.findall(r"\w+(?:/\w+)*", text.lower())


def load_corpus() -> list[dict]:
    """Đọc chunks đã index ở Task 4 từ Chroma để BM25 và dense dùng chung corpus."""
    from .task4_chunking_indexing import get_collection

    data = get_collection().get(include=["documents", "metadatas"])
    return [
        {"id": item_id, "content": content, "metadata": {"url": None, **metadata}}
        for item_id, content, metadata in zip(data["ids"], data["documents"], data["metadatas"])
    ]


def build_bm25_index(corpus: list[dict]):
    """Tạo BM25 index từ cùng corpus chunks của Task 4."""
    # BM25Plus giữ idf dương; BM25Okapi cho idf=0 với term xuất hiện ở nửa corpus.
    from rank_bm25 import BM25Plus

    return BM25Plus([tokenize(item["content"]) for item in corpus])


def _get_corpus_and_index() -> tuple[list[dict], object]:
    global _REAL_CORPUS, _INDEX_CACHE
    corpus = CORPUS
    if not corpus:
        if not _REAL_CORPUS:
            _REAL_CORPUS = load_corpus()
        corpus = _REAL_CORPUS
    if _INDEX_CACHE is None or _INDEX_CACHE[0] != id(corpus):
        _INDEX_CACHE = (id(corpus), build_bm25_index(corpus))
    return corpus, _INDEX_CACHE[1]


def lexical_search(query: str, top_k: int = 10) -> list[dict]:
    """Trả về BM25 SearchResult theo score giảm dần."""
    corpus, bm25 = _get_corpus_and_index()
    tokens = tokenize(query)
    if not corpus or not tokens:
        return []
    scores = bm25.get_scores(tokens)
    # BM25Plus cộng delta cho mọi doc -> chỉ giữ doc có ít nhất một term khớp.
    matched = [
        index for index, item_tokens in enumerate(bm25.doc_freqs)
        if any(token in item_tokens for token in tokens)
    ]
    matched.sort(key=lambda index: scores[index], reverse=True)
    return [
        {
            "id": corpus[index]["id"],
            "content": corpus[index]["content"],
            "score": float(scores[index]),
            "metadata": corpus[index]["metadata"],
            "retrieval_method": "bm25",
        }
        for index in matched[:top_k]
    ]


if __name__ == "__main__":
    for result in lexical_search("thuế hộ kinh doanh", top_k=3):
        print(result["score"], result["id"])
