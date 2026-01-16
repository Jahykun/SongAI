from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from songai.config import ScrapeConfig
from songai.learner import run_learning_cycle
from songai.scraper import run_scrape
from songai.store import SQLiteDocumentStore


@dataclass(frozen=True)
class PipelineConfig:
    scrape_config: ScrapeConfig
    learn_idle_sleep_s: float = 60.0


def _run_scraper(scrape_config: ScrapeConfig) -> None:
    run_scrape(scrape_config)


def _run_learner(db_path: Path, idle_sleep_s: float) -> None:
    store = SQLiteDocumentStore(db_path)
    store.initialize()
    run_learning_cycle(store, sleep_s=idle_sleep_s, continuous=True)


def run_pipeline(config: PipelineConfig) -> None:
    scrape_config = ScrapeConfig(
        start_urls=config.scrape_config.start_urls,
        allowed_domains=config.scrape_config.allowed_domains,
        user_agent=config.scrape_config.user_agent,
        max_pages=config.scrape_config.max_pages,
        request_timeout_s=config.scrape_config.request_timeout_s,
        output_db=config.scrape_config.output_db,
        crawl_delay_s=config.scrape_config.crawl_delay_s,
        idle_sleep_s=config.scrape_config.idle_sleep_s,
        continuous=True,
        min_content_chars=config.scrape_config.min_content_chars,
        max_content_chars=config.scrape_config.max_content_chars,
        max_links_per_page=config.scrape_config.max_links_per_page,
        disallow_extensions=config.scrape_config.disallow_extensions,
        allowed_schemes=config.scrape_config.allowed_schemes,
        extra_headers=config.scrape_config.extra_headers,
    )

    scraper_thread = threading.Thread(
        target=_run_scraper, args=(scrape_config,), daemon=True
    )
    learner_thread = threading.Thread(
        target=_run_learner,
        args=(scrape_config.output_db, config.learn_idle_sleep_s),
        daemon=True,
    )

    scraper_thread.start()
    learner_thread.start()

    scraper_thread.join()
    learner_thread.join()
