from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Document:
    url: str
    title: str
    content: str
    retrieved_at: str
    content_hash: str


@dataclass(frozen=True)
class DocumentRecord(Document):
    doc_id: int


class SQLiteDocumentStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=30)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    title TEXT,
                    content TEXT,
                    retrieved_at TEXT,
                    content_hash TEXT
                )
                """
            )
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(documents)").fetchall()
            }
            if "content_hash" not in columns:
                conn.execute("ALTER TABLE documents ADD COLUMN content_hash TEXT")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS url_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    status TEXT,
                    last_seen TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS doc_index (
                    doc_id INTEGER,
                    term TEXT,
                    count INTEGER,
                    PRIMARY KEY (doc_id, term)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS doc_index_meta (
                    doc_id INTEGER PRIMARY KEY,
                    indexed_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS doc_stats (
                    doc_id INTEGER PRIMARY KEY,
                    term_count INTEGER
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_doc_index_term ON doc_index(term)"
            )
            conn.commit()

    def save_document(self, document: Document) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO documents (url, title, content, retrieved_at, content_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    document.url,
                    document.title,
                    document.content,
                    document.retrieved_at,
                    document.content_hash,
                ),
            )
            conn.commit()

    def add_url(self, url: str, last_seen: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO url_queue (url, status, last_seen)
                VALUES (?, ?, ?)
                """,
                (url, "pending", last_seen),
            )
            conn.commit()

    def pop_next_url(self) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, url FROM url_queue
                WHERE status = 'pending'
                ORDER BY id ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            url_id, url = row
            conn.execute(
                "UPDATE url_queue SET status = 'in_progress' WHERE id = ?",
                (url_id,),
            )
            conn.commit()
        return url

    def mark_url(self, url: str, status: str, last_seen: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE url_queue
                SET status = ?, last_seen = ?
                WHERE url = ?
                """,
                (status, last_seen, url),
            )
            conn.commit()

    def list_documents(self) -> list[Document]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT url, title, content, retrieved_at, content_hash FROM documents"
            ).fetchall()
        return [Document(*row) for row in rows]

    def list_documents_with_id(self) -> list[DocumentRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, url, title, content, retrieved_at, content_hash FROM documents"
            ).fetchall()
        return [
            DocumentRecord(
                doc_id=row[0],
                url=row[1],
                title=row[2],
                content=row[3],
                retrieved_at=row[4],
                content_hash=row[5],
            )
            for row in rows
        ]

    def list_unindexed_documents(self) -> list[DocumentRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT d.id, d.url, d.title, d.content, d.retrieved_at, d.content_hash
                FROM documents d
                LEFT JOIN doc_index_meta m ON d.id = m.doc_id
                WHERE m.doc_id IS NULL
                """
            ).fetchall()
        return [
            DocumentRecord(
                doc_id=row[0],
                url=row[1],
                title=row[2],
                content=row[3],
                retrieved_at=row[4],
                content_hash=row[5],
            )
            for row in rows
        ]

    def save_doc_index(
        self, doc_id: int, term_counts: dict[str, int], term_count_total: int, indexed_at: str
    ) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO doc_index (doc_id, term, count)
                VALUES (?, ?, ?)
                """,
                [(doc_id, term, count) for term, count in term_counts.items()],
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO doc_stats (doc_id, term_count)
                VALUES (?, ?)
                """,
                (doc_id, term_count_total),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO doc_index_meta (doc_id, indexed_at)
                VALUES (?, ?)
                """,
                (doc_id, indexed_at),
            )
            conn.commit()

    def count_documents(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
        return int(row[0]) if row else 0

    def fetch_term_rows(self, terms: list[str]) -> list[tuple[int, str, int]]:
        if not terms:
            return []
        placeholders = ",".join("?" for _ in terms)
        query = f"""
            SELECT doc_id, term, count
            FROM doc_index
            WHERE term IN ({placeholders})
        """
        with self._connect() as conn:
            rows = conn.execute(query, terms).fetchall()
        return [(int(row[0]), str(row[1]), int(row[2])) for row in rows]

    def fetch_doc_stats(self, doc_ids: list[int]) -> dict[int, int]:
        if not doc_ids:
            return {}
        placeholders = ",".join("?" for _ in doc_ids)
        query = f"""
            SELECT doc_id, term_count
            FROM doc_stats
            WHERE doc_id IN ({placeholders})
        """
        with self._connect() as conn:
            rows = conn.execute(query, doc_ids).fetchall()
        return {int(row[0]): int(row[1]) for row in rows}

    def count_docs_with_term(self, term: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(DISTINCT doc_id) FROM doc_index WHERE term = ?",
                (term,),
            ).fetchone()
        return int(row[0]) if row else 0

    def fetch_document_by_id(self, doc_id: int) -> DocumentRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, url, title, content, retrieved_at, content_hash
                FROM documents
                WHERE id = ?
                """,
                (doc_id,),
            ).fetchone()
        if row is None:
            return None
        return DocumentRecord(
            doc_id=int(row[0]),
            url=row[1],
            title=row[2],
            content=row[3],
            retrieved_at=row[4],
            content_hash=row[5],
        )

    def has_content_hash(self, content_hash: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM documents WHERE content_hash = ? LIMIT 1",
                (content_hash,),
            ).fetchone()
        return row is not None

    def count_indexed_documents(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM doc_index_meta").fetchone()
        return int(row[0]) if row else 0

    def count_pending_urls(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM url_queue WHERE status = 'pending'"
            ).fetchone()
        return int(row[0]) if row else 0

    def average_doc_length(self) -> float:
        with self._connect() as conn:
            row = conn.execute("SELECT AVG(term_count) FROM doc_stats").fetchone()
        if row is None or row[0] is None:
            return 0.0
        return float(row[0])
