from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ScrapeConfig:
    start_urls: Iterable[str]
    allowed_domains: Iterable[str]
    user_agent: str = "SongAIResearchBot/0.1"
    max_pages: int = 50
    request_timeout_s: int = 15
    output_db: Path = Path("data/songai.db")
    crawl_delay_s: float = 1.0
    idle_sleep_s: float = 60.0
    continuous: bool = False
    min_content_chars: int = 500
    max_content_chars: int = 200_000
    max_links_per_page: int = 200
    disallow_extensions: tuple[str, ...] = (
        ".pdf",
        ".zip",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".mp4",
        ".mp3",
    )
    allowed_schemes: tuple[str, ...] = ("http", "https")
    extra_headers: dict[str, str] = field(default_factory=dict)
