from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from songai.config import ScrapeConfig
from songai.store import Document, SQLiteDocumentStore


@dataclass
class ScrapeResult:
    pages_visited: int
    pages_saved: int
    last_url: str | None
    idle_cycles: int


def _is_allowed_url(url: str, config: ScrapeConfig) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in config.allowed_schemes:
        return False
    if not any(parsed.netloc.endswith(domain) for domain in config.allowed_domains):
        return False
    if parsed.path.lower().endswith(config.disallow_extensions):
        return False
    return True


def _extract_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    text = "\n".join(line.strip() for line in soup.get_text().splitlines())
    cleaned = "\n".join(line for line in text.splitlines() if line)
    return title, cleaned


def _normalize_text(text: str, *, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        return text[:max_chars]
    return text


def _discover_links(base_url: str, html: str, *, max_links: int) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if href.startswith("#"):
            continue
        links.append(urljoin(base_url, href))
        if len(links) >= max_links:
            break
    return links


def _build_robot_parser(url: str, user_agent: str) -> RobotFileParser:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except OSError:
        return parser
    parser.modified()
    parser.crawl_delay(user_agent)
    return parser


def run_scrape(config: ScrapeConfig) -> ScrapeResult:
    session = requests.Session()
    headers = {"User-Agent": config.user_agent, **config.extra_headers}
    session.headers.update(headers)

    store = SQLiteDocumentStore(config.output_db)
    store.initialize()

    for url in config.start_urls:
        store.add_url(url, datetime.now(timezone.utc).isoformat())

    pages_saved = 0
    pages_visited = 0
    last_url = None
    idle_cycles = 0

    robots_parsers: dict[str, RobotFileParser] = {}

    while True:
        if config.max_pages > 0 and pages_visited >= config.max_pages:
            break
        url = store.pop_next_url()
        if url is None:
            if not config.continuous:
                break
            idle_cycles += 1
            time.sleep(config.idle_sleep_s)
            continue
        if not _is_allowed_url(url, config):
            store.mark_url(url, "skipped", datetime.now(timezone.utc).isoformat())
            continue

        parsed = urlparse(url)
        if parsed.netloc not in robots_parsers:
            robots_parsers[parsed.netloc] = _build_robot_parser(url, config.user_agent)

        parser = robots_parsers[parsed.netloc]
        if parser.can_fetch(config.user_agent, url) is False:
            store.mark_url(url, "disallowed", datetime.now(timezone.utc).isoformat())
            continue

        pages_visited += 1
        last_url = url
        try:
            response = session.get(url, timeout=config.request_timeout_s)
        except requests.RequestException:
            store.mark_url(url, "failed", datetime.now(timezone.utc).isoformat())
            continue
        if response.status_code != 200:
            store.mark_url(url, "failed", datetime.now(timezone.utc).isoformat())
            continue
        title, text = _extract_text(response.text)
        normalized = _normalize_text(text, max_chars=config.max_content_chars)
        if not normalized or len(normalized) < config.min_content_chars:
            store.mark_url(url, "empty", datetime.now(timezone.utc).isoformat())
            continue
        content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if store.has_content_hash(content_hash):
            store.mark_url(url, "duplicate", datetime.now(timezone.utc).isoformat())
            continue

        document = Document(
            url=url,
            title=title,
            content=normalized,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            content_hash=content_hash,
        )
        store.save_document(document)
        pages_saved += 1
        store.mark_url(url, "done", datetime.now(timezone.utc).isoformat())

        for link in _discover_links(
            url, response.text, max_links=config.max_links_per_page
        ):
            if _is_allowed_url(link, config):
                store.add_url(link, datetime.now(timezone.utc).isoformat())
        time.sleep(config.crawl_delay_s)

    return ScrapeResult(
        pages_visited=pages_visited,
        pages_saved=pages_saved,
        last_url=last_url,
        idle_cycles=idle_cycles,
    )
