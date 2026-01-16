from __future__ import annotations

from dataclasses import dataclass

from songai.store import Document, SQLiteDocumentStore


@dataclass(frozen=True)
class SearchResult:
    document: Document
    score: float

    @property
    def url(self) -> str:
        return self.document.url

    @property
    def title(self) -> str:
        return self.document.title


def _tokenize(text: str) -> list[str]:
    return [token for token in text.lower().split() if token]


def _score_document(document: Document, tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    haystack = document.content.lower()
    score = 0.0
    for token in tokens:
        score += haystack.count(token)
    return score


def search_documents(
    store: SQLiteDocumentStore, query: str, *, limit: int = 5
) -> list[SearchResult]:
    tokens = _tokenize(query)
    documents = store.list_documents()
    scored = [
        SearchResult(document=document, score=_score_document(document, tokens))
        for document in documents
    ]
    scored = [result for result in scored if result.score > 0]
    scored.sort(key=lambda result: result.score, reverse=True)
    return scored[:limit]
