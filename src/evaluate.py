"""
Evaluation A/B: Config A dense-only vs Config B hybrid + RRF.

Hai bước, kết quả ghi ra disk để chạy lại không mất phần đã xong (quota free tier):
    python -m src.evaluate generate   # retrieve + generate cho cả 2 config
    python -m src.evaluate score      # chấm 4 metric ragas, in bảng tổng hợp

Judge: Gemini qua endpoint OpenAI-compatible (ragas cần async client).
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from .task9_retrieval_pipeline import retrieve
from .task10_generation import TOP_K, generate_from_chunks


load_dotenv()

EVAL_DIR = Path(__file__).parent.parent / "group_project" / "evaluation"
GOLDEN_PATH = EVAL_DIR / "golden_dataset.json"
RUNS_DIR = EVAL_DIR / "runs"
CONFIGS = {"A_dense": False, "B_hybrid_rrf": True}  # name -> use_reranking
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gemini-3.5-flash-lite")
GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
METRICS = ("faithfulness", "answer_relevancy", "context_recall", "context_precision")


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _save(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def generate() -> None:
    golden = _load(GOLDEN_PATH)
    for name, use_reranking in CONFIGS.items():
        path = RUNS_DIR / f"{name}.json"
        rows = _load(path)
        for case in golden[len(rows):]:
            start = time.perf_counter()
            chunks = retrieve(case["question"], top_k=TOP_K, use_reranking=use_reranking)
            retrieval_s = time.perf_counter() - start
            result = generate_from_chunks(case["question"], chunks, raise_errors=True)
            rows.append({
                **case,
                "answer": result["answer"],
                "retrieved_ids": [chunk["id"] for chunk in chunks],
                "retrieved_contexts": [chunk["content"] for chunk in chunks],
                "retrieval_s": round(retrieval_s, 3),
                "total_s": round(time.perf_counter() - start, 3),
            })
            _save(path, rows)
            print(f"[{name}] {len(rows)}/{len(golden)} {case['question'][:60]}")


async def _score_row(metrics: dict, row: dict) -> dict:
    q, ctx, ref = row["question"], row["retrieved_contexts"], row["expected_answer"]
    calls = {
        "faithfulness": lambda: metrics["faithfulness"].ascore(
            user_input=q, response=row["answer"], retrieved_contexts=ctx),
        "answer_relevancy": lambda: metrics["answer_relevancy"].ascore(
            user_input=q, response=row["answer"]),
        "context_recall": lambda: metrics["context_recall"].ascore(
            user_input=q, retrieved_contexts=ctx, reference=ref),
        "context_precision": lambda: metrics["context_precision"].ascore(
            user_input=q, retrieved_contexts=ctx, reference=ref),
    }
    scores = {}
    for name, call in calls.items():
        for attempt in range(4):
            try:
                scores[name] = float((await call()).value)
                break
            except Exception as error:
                if attempt == 3:
                    print(f"  {name} failed: {error}")
                    scores[name] = None
                else:
                    await asyncio.sleep(15 * (attempt + 1))
    return scores


async def _score_all() -> None:
    from openai import AsyncOpenAI
    from ragas.embeddings.base import embedding_factory
    from ragas.llms import llm_factory
    from ragas.metrics.collections import (
        AnswerRelevancy,
        ContextPrecisionWithReference,
        ContextRecall,
        Faithfulness,
    )

    client = AsyncOpenAI(api_key=os.environ["GEMINI_API_KEY"], base_url=GEMINI_OPENAI_URL)
    llm = llm_factory(JUDGE_MODEL, client=client, max_tokens=4096)
    embeddings = embedding_factory("openai", model="gemini-embedding-2", client=client)
    metrics = {
        "faithfulness": Faithfulness(llm=llm),
        "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=embeddings, strictness=1),
        "context_recall": ContextRecall(llm=llm),
        "context_precision": ContextPrecisionWithReference(llm=llm),
    }
    for name in CONFIGS:
        path = RUNS_DIR / f"{name}.json"
        rows = _load(path)
        for index, row in enumerate(rows):
            if all(row.get(metric) is not None for metric in METRICS):
                continue
            row.update(await _score_row(metrics, row))
            _save(path, rows)
            print(f"[{name}] scored {index + 1}/{len(rows)}")


def summarize() -> None:
    summary = {}
    for name in CONFIGS:
        rows = _load(RUNS_DIR / f"{name}.json")
        means = {}
        for metric in METRICS:
            values = [row[metric] for row in rows if row.get(metric) is not None]
            means[metric] = sum(values) / len(values) if values else None
        means["average"] = sum(means[m] for m in METRICS) / len(METRICS)
        means["mean_total_s"] = sum(row["total_s"] for row in rows) / len(rows)
        means["mean_retrieval_s"] = sum(row["retrieval_s"] for row in rows) / len(rows)
        summary[name] = means
    _save(RUNS_DIR / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    if step in ("generate", "all"):
        generate()
    if step in ("score", "all"):
        asyncio.run(_score_all())
    if step in ("summary", "score", "all"):
        summarize()
