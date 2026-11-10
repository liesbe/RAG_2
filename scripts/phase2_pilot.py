"""Run the small, synthetic phase 2 retrieval and reranking pilot."""

from __future__ import annotations

import gc
import tempfile
import time
from pathlib import Path
from typing import Literal, TypedDict

import chromadb
import torch
from pydantic import BaseModel, TypeAdapter
from sentence_transformers import CrossEncoder, SentenceTransformer
from transformers import PreTrainedTokenizerBase

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "eval" / "phase2_pilot"
EMBEDDING_MODEL = "BAAI/bge-m3"
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64
TOP_K = 20
TOP_N = 5


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class EvaluationQuestion(BaseModel):
    question: str
    history: list[HistoryMessage]
    expected_chunk_id: str


class Chunk(TypedDict):
    chunk_id: str
    content: str
    source: str
    chunk_index: int


class QuestionResult(TypedDict):
    question: str
    expected_chunk_id: str
    dense_top5: list[str]
    reranked_top5: list[str]
    citation_ids: list[str]


def _chunks_from_fixtures(tokenizer: PreTrainedTokenizerBase) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(FIXTURES.glob("*.txt")):
        doc_id = path.stem
        chunk_index = 0
        for section in path.read_text(encoding="utf-8").split("\n\n"):
            token_ids = tokenizer.encode(section, add_special_tokens=False)
            start = 0
            while start < len(token_ids):
                token_window = token_ids[start : start + CHUNK_SIZE]
                content = tokenizer.decode(token_window, skip_special_tokens=True)
                if not isinstance(content, str):
                    raise RuntimeError("The tokenizer returned non-text content.")
                chunks.append(
                    {
                        "chunk_id": f"{doc_id}:{chunk_index}",
                        "content": content,
                        "source": path.name,
                        "chunk_index": chunk_index,
                    }
                )
                chunk_index += 1
                if start + CHUNK_SIZE >= len(token_ids):
                    break
                start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _build_query(question: EvaluationQuestion) -> str:
    recent_history = question.history[-4:]
    context = "\n".join(f"{message.role}: {message.content}" for message in recent_history)
    if not context:
        return question.question
    return f"Recent conversation:\n{context}\nCurrent question: {question.question}"


def _load_questions() -> list[EvaluationQuestion]:
    path = FIXTURES / "questions.json"
    return TypeAdapter(list[EvaluationQuestion]).validate_json(path.read_bytes())


def _rank_dense(
    collection: chromadb.Collection,
    embedding_model: SentenceTransformer,
    query: str,
) -> tuple[list[str], list[str]]:
    query_embedding = embedding_model.encode(
        query,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    results = collection.query(
        query_embeddings=[query_embedding.tolist()],
        n_results=min(TOP_K, collection.count()),
        include=["documents", "distances", "metadatas"],
    )
    chunk_ids = results["ids"][0]
    distances_by_query = results["distances"]
    if not distances_by_query:
        raise RuntimeError("Chroma did not return distances for the pilot query.")
    distances = distances_by_query[0]
    dense_ranked_ids = [
        chunk_id
        for chunk_id, _ in sorted(zip(chunk_ids, distances, strict=True), key=lambda item: item[1])
    ]
    return dense_ranked_ids, chunk_ids


def _rerank(
    reranker: CrossEncoder,
    query: str,
    chunk_ids: list[str],
    contents: dict[str, str],
) -> list[str]:
    scores = reranker.predict(
        [(query, contents[chunk_id]) for chunk_id in chunk_ids],
        batch_size=2,
        show_progress_bar=False,
    )
    return [
        chunk_id
        for chunk_id, _ in sorted(
            zip(chunk_ids, scores, strict=True), key=lambda item: float(item[1]), reverse=True
        )
    ]


def _hit_rate(
    rows: list[QuestionResult],
    ranking_key: Literal["dense_top5", "reranked_top5"],
) -> float:
    hits = sum(row["expected_chunk_id"] in row[ranking_key][:TOP_N] for row in rows)
    return hits / len(rows) if rows else 0.0


def _directory_size(path: Path) -> int:
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


def main() -> None:
    torch.set_num_threads(1)
    started = time.perf_counter()
    embedding_model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    embedding_loaded_at = time.perf_counter()

    chunks = _chunks_from_fixtures(embedding_model.tokenizer)
    if len(chunks) <= TOP_N:
        raise RuntimeError(f"Pilot needs more than {TOP_N} chunks; found {len(chunks)}.")
    contents = {chunk["chunk_id"]: chunk["content"] for chunk in chunks}

    embeddings = embedding_model.encode(
        [chunk["content"] for chunk in chunks],
        batch_size=2,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    with tempfile.TemporaryDirectory(prefix="rag-phase2-pilot-") as temp_dir:
        client = chromadb.PersistentClient(path=temp_dir)
        collection = client.create_collection(
            name="pilot",
            metadata={"hnsw:space": "cosine"},
        )
        collection.add(
            ids=[chunk["chunk_id"] for chunk in chunks],
            embeddings=embeddings.tolist(),
            documents=[chunk["content"] for chunk in chunks],
            metadatas=[
                {
                    "source": chunk["source"],
                    "chunk_index": chunk["chunk_index"],
                }
                for chunk in chunks
            ],
        )
        collection_ready_at = time.perf_counter()

        questions = _load_questions()
        if len(questions) != 10:
            raise RuntimeError(f"Pilot expects 10 questions; found {len(questions)}.")
        expected_ids = {chunk["chunk_id"] for chunk in chunks}
        if any(question.expected_chunk_id not in expected_ids for question in questions):
            raise RuntimeError("Pilot questions refer to a chunk that does not exist.")
        rows: list[QuestionResult] = []
        dense_queries: list[tuple[EvaluationQuestion, str, list[str], list[str]]] = []
        for question in questions:
            query = _build_query(question)
            dense_ids, candidate_ids = _rank_dense(collection, embedding_model, query)
            dense_queries.append((question, query, dense_ids, candidate_ids))
        retrieval_finished_at = time.perf_counter()

        del embedding_model, embeddings
        gc.collect()
        reranker = CrossEncoder(RERANKER_MODEL, max_length=512, device="cpu")
        reranker_loaded_at = time.perf_counter()
        for question, query, dense_ids, candidate_ids in dense_queries:
            reranked_ids = _rerank(reranker, query, candidate_ids, contents)[:TOP_N]
            row: QuestionResult = {
                "question": question.question,
                "expected_chunk_id": question.expected_chunk_id,
                "dense_top5": dense_ids[:TOP_N],
                "reranked_top5": reranked_ids,
                "citation_ids": reranked_ids,
            }
            if not set(row["citation_ids"]).issubset(set(candidate_ids)):
                raise RuntimeError("Pilot generated a citation outside retrieved candidates.")
            rows.append(row)
        reranking_finished_at = time.perf_counter()
        index_bytes = _directory_size(Path(temp_dir))

    print(f"Embedding model load: {embedding_loaded_at - started:.1f}s")
    print(f"Chunks indexed: {len(chunks)}")
    print(f"Dense top_k: {TOP_K} (available chunks: {len(chunks)})")
    print(f"Reranked top_n: {TOP_N}")
    print(f"Embedding + index: {collection_ready_at - embedding_loaded_at:.1f}s")
    print(
        f"Dense retrieval ({len(questions)} questions): "
        f"{retrieval_finished_at - collection_ready_at:.1f}s"
    )
    print(f"Reranker load: {reranker_loaded_at - retrieval_finished_at:.1f}s")
    print(
        f"Reranking ({len(questions)} questions): {reranking_finished_at - reranker_loaded_at:.1f}s"
    )
    print(f"Temporary Chroma index: {index_bytes / 1024:.1f} KiB")
    print(f"Dense hit@{TOP_N}: {_hit_rate(rows, 'dense_top5'):.0%}")
    print(f"Reranked hit@{TOP_N}: {_hit_rate(rows, 'reranked_top5'):.0%}")
    print("Question results:")
    for row in rows:
        rank = (
            row["reranked_top5"].index(row["expected_chunk_id"]) + 1
            if row["expected_chunk_id"] in row["reranked_top5"]
            else "miss"
        )
        print(f"- {row['expected_chunk_id']} at {rank}: {row['question']}")
    citation_count = sum(len(row["citation_ids"]) for row in rows)
    print(f"Citation IDs linked to retrieved chunks: {citation_count}")


if __name__ == "__main__":
    main()
