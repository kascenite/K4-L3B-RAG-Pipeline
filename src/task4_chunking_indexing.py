"""
Task 4 — Chunking, embedding và indexing.

Hướng dẫn:
    1. Đọc toàn bộ Markdown trong data/standardized/.
    2. Chia văn bản bằng strategy đã chọn.
    3. Embed chunks bằng một provider duy nhất.
    4. Upsert vào ChromaDB với cosine distance.

Mỗi document/chunk phải theo docs/MODULE_CONTRACTS.md. ID cần ổn định để
chạy lại pipeline không tạo dữ liệu trùng. Task 5 phải dùng chung embed_texts().
"""

import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

STANDARDIZED_DIR = Path(__file__).parent.parent / "data" / "standardized"
CHROMA_DIR = Path(__file__).parent.parent / "chroma_db"

# Giải thích lựa chọn tham số trong báo cáo nhóm.
# ~1000 ký tự (~250 token) đủ chứa trọn một khoản/điểm của văn bản pháp luật;
# ưu tiên cắt tại ranh giới Chương/Điều để chunk không trộn hai điều luật.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
CHUNKING_METHOD = "recursive"
SEPARATORS = ["\n**Chương ", "\n**Điều ", "\nChương ", "\nĐiều ", "\n\n", "\n", ". ", " ", ""]
MIN_LETTER_RATIO = 0.3  # bỏ chunk toàn ô bảng trống / số hiệu biểu mẫu

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "gemini")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-2")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))
EMBED_BATCH_SIZE = 100  # giới hạn batchEmbedContents của Gemini

COLLECTION_NAME = "rag_documents"

# Văn bản sửa đổi bằng cách "thay cụm từ" không khớp ngữ nghĩa với câu hỏi, nên chunk
# gốc (mức cũ) luôn thắng khi retrieve. Gắn ghi chú sửa đổi vào chunk gốc chứa cụm từ cũ.
# source -> (cụm từ cũ, ghi chú)
AMENDMENTS = {
    "nd-68-2026-thue-ho-kinh-doanh.md": (
        "500 triệu đồng",
        "[Ghi chú sửa đổi: Nghị định 141/2026/NĐ-CP (hiệu lực từ 01/01/2026) đã thay "
        "\"500 triệu đồng\" bằng \"01 tỷ đồng\" tại Điều 3, Điều 4, khoản 1 Điều 8, Điều 9, "
        "Điều 10, khoản 3 Điều 11, khoản 1 và 2 Điều 12, khoản 4 Điều 17, khoản 3 Điều 18 "
        "của Nghị định 68/2026/NĐ-CP. Mức hiện hành là 01 tỷ đồng.]",
    ),
}


def embed_texts(texts: list[str], is_query: bool = False) -> list[list[float]]:
    """Embed texts theo EMBEDDING_PROVIDER. Task 5 gọi với is_query=True."""
    if EMBEDDING_PROVIDER == "gemini":
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        config = types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT",
            output_dimensionality=EMBEDDING_DIM,
        )
        vectors = []
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            # Mỗi text phải là một Content riêng, nếu không gemini-embedding-2
            # gộp cả list thành một embedding duy nhất.
            contents = [
                types.Content(parts=[types.Part(text=t)])
                for t in texts[i : i + EMBED_BATCH_SIZE]
            ]
            for attempt in range(5):
                try:
                    result = client.models.embed_content(
                        model=EMBEDDING_MODEL, contents=contents, config=config
                    )
                    break
                except genai.errors.ClientError as error:
                    if error.code != 429 or attempt == 4:
                        raise
                    # Free tier: 100 text/phút cho mỗi model -> chờ hết cửa sổ 1 phút.
                    time.sleep(61)
            vectors.extend(e.values for e in result.embeddings)
        return vectors
    if EMBEDDING_PROVIDER == "sentence_transformers":
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(EMBEDDING_MODEL)
        return model.encode(texts, normalize_embeddings=True).tolist()
    raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {EMBEDDING_PROVIDER}")


def get_collection():
    """Mở Chroma collection dùng cosine distance."""
    import chromadb

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def load_documents() -> list[dict]:
    """Đọc Markdown và trả về danh sách Document; title/url lấy từ header của Task 3."""
    documents = []
    for path in sorted(STANDARDIZED_DIR.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        header, _, body = text.partition("\n---\n")
        title = re.search(r"^# (.+)$", header, re.M)
        url = re.search(r"^\*\*Source:\*\* (\S+)", header, re.M)
        documents.append({
            "id": path.relative_to(STANDARDIZED_DIR).as_posix(),
            "content": body.strip() or text,
            "metadata": {
                "source": path.name,
                "title": title.group(1).strip() if title else path.stem,
                "doc_type": "legal" if "legal" in path.parts else "news",
                "url": url.group(1) if url else None,
            },
        })
    return documents


def chunk_documents(documents: list[dict]) -> list[dict]:
    """Chia Document thành chunks có id và chunk_index."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=SEPARATORS,
    )
    chunks = []
    for document in documents:
        texts = [
            text.strip() for text in splitter.split_text(document["content"])
            if sum(ch.isalpha() for ch in text) / len(text) >= MIN_LETTER_RATIO
        ]
        old_phrase, note = AMENDMENTS.get(document["metadata"]["source"], (None, None))
        for index, text in enumerate(texts):
            if old_phrase and old_phrase in text:
                text = f"{note}\n\n{text}"
            chunks.append({
                "id": f"{document['id']}::chunk-{index}",
                "content": text,
                "metadata": {**document["metadata"], "chunk_index": index},
            })
    return chunks


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """Thêm embedding vào từng chunk.

    Tiêu đề văn bản được ghép vào text khi embed (không lưu vào content) để chunk
    như "Điều 9. Hiệu lực thi hành" vẫn biết thuộc văn bản nào.
    """
    # Tái sử dụng embedding đã có trong Chroma nếu chunk không đổi -> chạy lại
    # không tốn quota API.
    existing = get_collection().get(
        ids=[chunk["id"] for chunk in chunks], include=["documents", "embeddings"]
    )
    cached = {
        id_: vector for id_, doc, vector
        in zip(existing["ids"], existing["documents"], existing["embeddings"])
    }
    cached_docs = dict(zip(existing["ids"], existing["documents"]))
    missing = [c for c in chunks if cached_docs.get(c["id"]) != c["content"]]
    vectors = embed_texts(
        [f"{chunk['metadata']['title']}\n\n{chunk['content']}" for chunk in missing]
    ) if missing else []
    cached.update({chunk["id"]: vector for chunk, vector in zip(missing, vectors)})
    for chunk in chunks:
        chunk["embedding"] = list(cached[chunk["id"]])
    print(f"Embedded {len(missing)} new/changed chunks, reused {len(chunks) - len(missing)}")
    return chunks


def index_to_vectorstore(chunks: list[dict]) -> None:
    """Upsert chunks vào ChromaDB và xóa chunk cũ không còn trong corpus."""
    collection = get_collection()
    # Chroma không nhận metadata None; Task 5 trả lại url=None khi thiếu.
    metadatas = [
        {key: value for key, value in chunk["metadata"].items() if value is not None}
        for chunk in chunks
    ]
    collection.upsert(
        ids=[chunk["id"] for chunk in chunks],
        documents=[chunk["content"] for chunk in chunks],
        embeddings=[chunk["embedding"] for chunk in chunks],
        metadatas=metadatas,
    )
    stale = set(collection.get(include=[])["ids"]) - {chunk["id"] for chunk in chunks}
    if stale:
        collection.delete(ids=list(stale))


def run_pipeline() -> None:
    """Chạy load, chunk, embed và index."""
    documents = load_documents()
    chunks = chunk_documents(documents)
    embedded_chunks = embed_chunks(chunks)
    index_to_vectorstore(embedded_chunks)
    print(f"Indexed {len(embedded_chunks)} chunks")


if __name__ == "__main__":
    run_pipeline()
