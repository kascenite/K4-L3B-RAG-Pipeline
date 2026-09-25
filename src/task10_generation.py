"""
Task 10 — Generation có citation.

Hướng dẫn:
    1. Retrieve top-k chunks.
    2. Reorder để giảm lost-in-the-middle.
    3. Format context kèm title và source.
    4. Gọi provider được chọn trong .env.
    5. Trả answer, sources và retrieval_source.

Nếu context không đủ hoặc provider lỗi, trả safe refusal; không bịa thông tin.
"""

import os
import re
import time

from dotenv import load_dotenv

from .task9_retrieval_pipeline import retrieve


load_dotenv()

TOP_K = 5
TOP_P = 0.9
TEMPERATURE = 0.3

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "gemini": "gemma-4-26b-a4b-it",
    "anthropic": "claude-haiku-4-5-20251001",
}
LLM_MODEL = os.getenv("LLM_MODEL") or DEFAULT_MODELS.get(LLM_PROVIDER, "")

REFUSAL = "Tôi không thể xác minh thông tin này từ nguồn hiện có."

SYSTEM_PROMPT = f"""Bạn là trợ lý pháp lý về hộ kinh doanh tại Việt Nam.
Chỉ trả lời dựa trên context được cung cấp, bằng tiếng Việt, ngắn gọn.
Mỗi khẳng định phải kèm citation dạng [n], với n là số của Document trong context.
Chỉ dùng số Document có trong context. Không dùng kiến thức bên ngoài.
Nếu các Document mâu thuẫn về một con số hay quy định, văn bản sửa đổi hoặc ban hành
sau được ưu tiên (ví dụ Nghị định 141/2026 sửa Nghị định 68/2026): trả lời theo mức
hiện hành và nói rõ mức cũ đã bị thay thế, kèm citation cho cả hai.
Nếu một Document có "Ghi chú sửa đổi", mức mới áp dụng cho mọi Document khác còn ghi mức cũ
(kể cả bài báo đăng trước khi sửa đổi).
Citation chỉ ghi số trong ngoặc vuông, ví dụ [1] hoặc [1][3], không ghi chữ "Document".
Nếu context không chứa đủ evidence để trả lời, chỉ trả lời đúng câu: {REFUSAL}"""


def reorder_for_llm(chunks: list[dict]) -> list[dict]:
    """Đưa chunks quan trọng về đầu và cuối context (giảm lost-in-the-middle)."""
    if len(chunks) <= 2:
        return list(chunks)
    return chunks[::2] + chunks[1::2][::-1]


def format_context(chunks: list[dict]) -> str:
    """Tạo context có title và source label.

    Số Document lấy từ ``citation_id`` (thứ hạng gốc trong ``sources``) nếu có,
    để [n] trong câu trả lời trỏ đúng ``sources[n-1]`` dù context đã reorder.
    """
    parts = []
    for index, chunk in enumerate(chunks, 1):
        metadata = chunk["metadata"]
        number = chunk.get("citation_id", index)
        parts.append(
            f"[Document {number} | Title: {metadata['title']} | "
            f"Source: {metadata['source']}]\n{chunk['content']}"
        )
    return "\n\n---\n\n".join(parts)


def call_llm(system_prompt: str, user_message: str) -> str:
    """Gọi OpenAI, Gemini hoặc Anthropic theo cấu hình."""
    if LLM_PROVIDER == "gemini":
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=TEMPERATURE,
            top_p=TOP_P,
        )
        for attempt in range(4):
            try:
                response = client.models.generate_content(
                    model=LLM_MODEL, contents=user_message, config=config
                )
                return response.text or ""
            except genai.errors.APIError as error:
                # 429 quota / 500, 503 lỗi server thường chỉ tạm thời -> thử lại có backoff.
                if error.code not in (429, 500, 503) or attempt == 3:
                    raise
                time.sleep(5 * 2**attempt)
    if LLM_PROVIDER == "openai":
        from openai import OpenAI

        response = OpenAI(api_key=os.environ["OPENAI_API_KEY"]).chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=TEMPERATURE,
            top_p=TOP_P,
        )
        return response.choices[0].message.content or ""
    if LLM_PROVIDER == "anthropic":
        from anthropic import Anthropic

        response = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]).messages.create(
            model=LLM_MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            temperature=TEMPERATURE,
        )
        return "".join(block.text for block in response.content if block.type == "text")
    raise ValueError(f"Unsupported LLM_PROVIDER: {LLM_PROVIDER}")


def generate_from_chunks(query: str, chunks: list[dict], raise_errors: bool = False) -> dict:
    """Sinh câu trả lời có citation từ chunks đã retrieve (dùng chung cho eval A/B).

    Eval đặt ``raise_errors=True`` để lỗi provider không bị ghi nhận thành refusal.
    """
    refusal = {"answer": REFUSAL, "sources": [], "retrieval_source": "none"}
    if not chunks:
        return refusal

    numbered = [{**chunk, "citation_id": rank} for rank, chunk in enumerate(chunks, 1)]
    context = format_context(reorder_for_llm(numbered))
    user_message = f"Context:\n{context}\n\nQuestion: {query}"
    try:
        answer = call_llm(SYSTEM_PROMPT, user_message).strip()
    except Exception as error:
        if raise_errors:
            raise
        print(f"LLM call failed: {error}")
        return refusal
    if not answer or REFUSAL in answer:
        return refusal
    # Chuẩn hoá "[Document 2]" -> "[2]" để citation luôn map về sources[n-1].
    answer = re.sub(r"\[Document (\d+)\]", r"[\1]", answer)
    return {
        "answer": answer,
        "sources": chunks,
        "retrieval_source": "pageindex" if chunks[0]["retrieval_method"] == "pageindex" else "hybrid",
    }


def generate_with_citation(query: str, top_k: int = TOP_K) -> dict:
    """Trả về GenerationResult."""
    try:
        chunks = retrieve(query, top_k=top_k)
    except Exception as error:
        print(f"Retrieval failed: {error}")
        chunks = []
    return generate_from_chunks(query, chunks)


if __name__ == "__main__":
    print(generate_with_citation("test query"))
