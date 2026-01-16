from __future__ import annotations

import argparse

from songai.config import ScrapeConfig
from songai.learner import answer_query, run_learning_cycle
from songai.pipeline import PipelineConfig, run_pipeline
from songai.scraper import run_scrape
from songai.search import search_documents
from songai.store import SQLiteDocumentStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SongAI bootstrap")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scrape_parser = subparsers.add_parser("scrape", help="Run the web scraper.")
    scrape_parser.add_argument(
        "--start-url",
        action="append",
        required=True,
        help="Seed URL(s) to start crawling from.",
    )
    scrape_parser.add_argument(
        "--allowed-domain",
        action="append",
        required=True,
        help="Allowed domain(s) for crawling.",
    )
    scrape_parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="Maximum number of pages to visit (0 = unlimited).",
    )
    scrape_parser.add_argument(
        "--output-db",
        default="data/songai.db",
        help="SQLite path for storing scraped documents.",
    )
    scrape_parser.add_argument(
        "--continuous",
        action="store_true",
        help="Keep running and waiting for new URLs.",
    )
    scrape_parser.add_argument(
        "--idle-sleep-s",
        type=float,
        default=60.0,
        help="Sleep seconds between idle cycles in continuous mode.",
    )

    search_parser = subparsers.add_parser("search", help="Query stored documents.")
    search_parser.add_argument(
        "--query",
        required=True,
        help="Search query string.",
    )
    search_parser.add_argument(
        "--output-db",
        default="data/songai.db",
        help="SQLite path for reading stored documents.",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of results to return.",
    )

    learn_parser = subparsers.add_parser("learn", help="Build/update the local index.")
    learn_parser.add_argument(
        "--output-db",
        default="data/songai.db",
        help="SQLite path for reading stored documents.",
    )
    learn_parser.add_argument(
        "--continuous",
        action="store_true",
        help="Keep indexing as new documents arrive.",
    )
    learn_parser.add_argument(
        "--idle-sleep-s",
        type=float,
        default=60.0,
        help="Sleep seconds between idle cycles in continuous mode.",
    )

    answer_parser = subparsers.add_parser(
        "answer", help="Answer a query using the local index."
    )
    answer_parser.add_argument(
        "--query",
        required=True,
        help="Question or query string.",
    )
    answer_parser.add_argument(
        "--output-db",
        default="data/songai.db",
        help="SQLite path for reading stored documents.",
    )
    answer_parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Number of top sources to show.",
    )

    run_parser = subparsers.add_parser(
        "run", help="Run scraper + learner together (continuous)."
    )
    run_parser.add_argument(
        "--start-url",
        action="append",
        required=True,
        help="Seed URL(s) to start crawling from.",
    )
    run_parser.add_argument(
        "--allowed-domain",
        action="append",
        required=True,
        help="Allowed domain(s) for crawling.",
    )
    run_parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="Maximum number of pages per run (0 = unlimited).",
    )
    run_parser.add_argument(
        "--output-db",
        default="data/songai.db",
        help="SQLite path for storing scraped documents.",
    )
    run_parser.add_argument(
        "--crawl-delay-s",
        type=float,
        default=1.0,
        help="Delay between requests when scraping.",
    )
    run_parser.add_argument(
        "--learn-idle-sleep-s",
        type=float,
        default=60.0,
        help="Sleep seconds between idle cycles in the learner.",
    )

    status_parser = subparsers.add_parser("status", help="Show index stats.")
    status_parser.add_argument(
        "--output-db",
        default="data/songai.db",
        help="SQLite path for reading stored documents.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "scrape":
        config = ScrapeConfig(
            start_urls=args.start_url,
            allowed_domains=args.allowed_domain,
            max_pages=args.max_pages,
            output_db=args.output_db,
            continuous=args.continuous,
            idle_sleep_s=args.idle_sleep_s,
        )
        result = run_scrape(config)
        print(
            "Scrape finished: visited={visited} saved={saved} last={last} idle={idle}".format(
                visited=result.pages_visited,
                saved=result.pages_saved,
                last=result.last_url,
                idle=result.idle_cycles,
            )
        )
        return

    if args.command == "search":
        store = SQLiteDocumentStore(args.output_db)
        store.initialize()
        results = search_documents(store, args.query, limit=args.limit)
        for rank, result in enumerate(results, start=1):
            print(f"{rank}. {result.title} ({result.url}) [score={result.score:.2f}]")
        return

    if args.command == "learn":
        store = SQLiteDocumentStore(args.output_db)
        store.initialize()
        indexed = run_learning_cycle(
            store, sleep_s=args.idle_sleep_s, continuous=args.continuous
        )
        print(f"Indexed {indexed} documents.")
        return

    if args.command == "answer":
        store = SQLiteDocumentStore(args.output_db)
        store.initialize()
        results = answer_query(store, args.query, limit=args.limit)
        if not results:
            print("No results found. Try running 'learn' after scraping.")
            return
        for rank, result in enumerate(results, start=1):
            print(f"{rank}. {result.title} ({result.url}) [score={result.score:.2f}]")
            print(f"   {result.snippet}")
        return

    if args.command == "run":
        scrape_config = ScrapeConfig(
            start_urls=args.start_url,
            allowed_domains=args.allowed_domain,
            max_pages=args.max_pages,
            output_db=args.output_db,
            crawl_delay_s=args.crawl_delay_s,
            continuous=True,
        )
        pipeline_config = PipelineConfig(
            scrape_config=scrape_config,
            learn_idle_sleep_s=args.learn_idle_sleep_s,
        )
        run_pipeline(pipeline_config)
        return

    if args.command == "status":
        store = SQLiteDocumentStore(args.output_db)
        store.initialize()
        total_docs = store.count_documents()
        indexed_docs = store.count_indexed_documents()
        pending_urls = store.count_pending_urls()
        print(f"Documents: {total_docs}")
        print(f"Indexed: {indexed_docs}")
        print(f"Pending URLs: {pending_urls}")
        return


if __name__ == "__main__":
    main()
