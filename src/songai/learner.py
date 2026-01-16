from __future__ import annotations

import math
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from songai.store import DocumentRecord, SQLiteDocumentStore


@dataclass(frozen=True)
class AnswerResult:
    document: DocumentRecord
    score: float
    snippet: str

    @property
    def url(self) -> str:
        return self.document.url

    @property
    def title(self) -> str:
        return self.document.title


def _tokenize(text: str) -> list[str]:
    tokens = [token.lower() for token in re.split(r"\W+", text)]
    stopwords = {
        "and",
        "the",
        "for",
        "with",
        "that",
        "this",
        "from",
        "are",
        "was",
        "were",
        "have",
        "has",
        "had",
        "but",
        "not",
        "you",
        "your",
        "our",
        "their",
    }
    return [token for token in tokens if len(token) > 2 and token not in stopwords]


def _index_document(store: SQLiteDocumentStore, document: DocumentRecord) -> None:
    tokens = _tokenize(document.content)
    if not tokens:
        return
    counts = Counter(tokens)
    store.save_doc_index(
        doc_id=document.doc_id,
        term_counts=dict(counts),
        term_count_total=len(tokens),
        indexed_at=datetime.now(timezone.utc).isoformat(),
    )


def run_learning_cycle(store: SQLiteDocumentStore, *, sleep_s: float = 60.0, continuous: bool = False) -> int:
    indexed = 0
    while True:
        pending = store.list_unindexed_documents()
        if not pending:
            if not continuous:
                break
            time.sleep(sleep_s)
            continue
        for document in pending:
            _index_document(store, document)
            indexed += 1
    return indexed


def _score_documents(
    store: SQLiteDocumentStore,
    query: str,
    *,
    limit: int = 5,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[AnswerResult]:
    tokens = _tokenize(query)
    if not tokens:
        return []

    term_rows = store.fetch_term_rows(tokens)
    if not term_rows:
        return []

    total_docs = max(store.count_documents(), 1)
    df_cache = {term: store.count_docs_with_term(term) for term in set(tokens)}
    doc_stats = store.fetch_doc_stats(list({row[0] for row in term_rows}))
    avgdl = store.average_doc_length() or 1.0

    scores: dict[int, float] = {}
    for doc_id, term, count in term_rows:
        doc_len = doc_stats.get(doc_id, 1)
        df = df_cache.get(term, 1)
        idf = math.log((total_docs + 1) / (df + 1)) + 1.0
        norm = (1 - b) + b * (doc_len / avgdl)
        tf = (count * (k1 + 1)) / (count + k1 * norm)
        scores[doc_id] = scores.get(doc_id, 0.0) + (idf * tf)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
    results: list[AnswerResult] = []
    for doc_id, score in ranked:
        document = store.fetch_document_by_id(doc_id)
        if document is None:
            continue
        snippet = _build_snippet(document.content, tokens)
        results.append(AnswerResult(document=document, score=score, snippet=snippet))
    return results


def _build_snippet(content: str, tokens: list[str], max_chars: int = 240) -> str:
    lowered = content.lower()
    for token in tokens:
        idx = lowered.find(token)
        if idx != -1:
            start = max(idx - 60, 0)
            end = min(idx + max_chars, len(content))
            return content[start:end].replace("\n", " ").strip()
    return content[:max_chars].replace("\n", " ").strip()


def answer_query(
    store: SQLiteDocumentStore,
    query: str,
    *,
    limit: int = 3,
) -> list[AnswerResult]:
    return _score_documents(store, query, limit=limit)
