from __future__ import annotations

import argparse
import sys

from app.auto_preset import auto_preset_missing_sources
from app.batch_sources import run_ready_sources_batch
from app.service import resolve_path, run_crawl_from_file
from app.web import run_web_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Media article crawler with CLI and web UI.")
    subparsers = parser.add_subparsers(dest="command")

    crawl_parser = subparsers.add_parser("crawl", help="Run the crawler from the command line.")
    crawl_parser.add_argument("--config", required=True, help="Path to crawler JSON config.")
    crawl_parser.add_argument("--output", default="output/articles.json", help="Path to output JSON file.")
    crawl_parser.add_argument("--max-pages", type=int, default=None, help="Max number of listing pages to visit.")
    crawl_parser.add_argument("--max-articles", type=int, default=None, help="Max number of articles to crawl.")
    crawl_parser.add_argument("--workers", type=int, default=4, help="Number of concurrent article fetch workers.")

    web_parser = subparsers.add_parser("web", help="Run the web interface.")
    web_parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind.")
    web_parser.add_argument("--port", type=int, default=8000, help="Port to listen on.")

    batch_parser = subparsers.add_parser("batch-sources", help="Run configured sources from a source-list JSON file in order.")
    batch_parser.add_argument("--input", required=True, help="Path to sources.web.ready.json.")
    batch_parser.add_argument("--output-dir", default="output/batch", help="Directory for per-source output JSON files.")
    batch_parser.add_argument("--report", default=None, help="Path to the batch report JSON file.")
    batch_parser.add_argument("--max-pages", type=int, default=1, help="Max listing pages per source.")
    batch_parser.add_argument("--max-articles", type=int, default=2, help="Max articles per source.")
    batch_parser.add_argument("--workers", type=int, default=None, help="Article workers per source. Defaults to each saved source.")
    batch_parser.add_argument("--include-inactive", action="store_true", help="Also process sources whose status is not ACTIVE.")
    batch_parser.add_argument("--limit", type=int, default=None, help="Only process the first N rows from the input file.")

    auto_parser = subparsers.add_parser(
        "auto-preset-sources",
        help="Create generic presets for source-list rows that do not have a configured preset, then crawl them in order.",
    )
    auto_parser.add_argument("--input", required=True, help="Path to sources.web.ready.json.")
    auto_parser.add_argument("--output-dir", default="output/auto", help="Directory for per-source output JSON files.")
    auto_parser.add_argument("--report", default=None, help="Path to the auto-preset report JSON file.")
    auto_parser.add_argument("--max-pages", type=int, default=1, help="Max listing pages per source.")
    auto_parser.add_argument("--max-articles", type=int, default=2, help="Max articles per source.")
    auto_parser.add_argument("--workers", type=int, default=2, help="Article workers per source.")
    auto_parser.add_argument("--timeout-seconds", type=int, default=10, help="HTTP timeout for probing each source.")
    auto_parser.add_argument("--include-inactive", action="store_true", help="Also process sources whose status is not ACTIVE.")
    auto_parser.add_argument("--limit", type=int, default=None, help="Only process the first N missing-preset rows.")
    auto_parser.add_argument("--priority", default=None, help="Only process sources with this priority, for example HIGH or LOW.")
    auto_parser.add_argument("--allow-external-redirect", action="store_true", help="Allow presets for sources that redirect to unrelated domains.")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    raw_args = argv if argv is not None else sys.argv[1:]
    if not raw_args:
        raw_args = ["web"]
    args = parser.parse_args(raw_args)

    if args.command == "crawl":
        payload = run_crawl_from_file(
            config_path=resolve_path(args.config),
            output_path=resolve_path(args.output),
            max_pages=args.max_pages,
            max_articles=args.max_articles,
            workers=args.workers,
            save_output=True,
        )
        print(f"Crawled {payload['success_count']}/{payload['article_count']} articles into {args.output}")
        return

    if args.command == "web":
        run_web_server(host=args.host, port=args.port)
        return

    if args.command == "batch-sources":
        report = run_ready_sources_batch(
            input_path=resolve_path(args.input),
            output_dir=resolve_path(args.output_dir),
            report_path=resolve_path(args.report) if args.report else None,
            max_pages=args.max_pages,
            max_articles=args.max_articles,
            workers=args.workers,
            active_only=not args.include_inactive,
            limit=args.limit,
        )
        summary = report["summary"]
        print(
            "Batch completed: "
            f"{summary['completed']} crawled, "
            f"{summary['failed']} failed, "
            f"{summary['skipped_no_preset']} skipped without preset, "
            f"{summary['skipped_inactive']} skipped inactive. "
            f"Report: {report['report_path']}"
        )
        return

    if args.command == "auto-preset-sources":
        report = auto_preset_missing_sources(
            input_path=resolve_path(args.input),
            output_dir=resolve_path(args.output_dir),
            report_path=resolve_path(args.report) if args.report else None,
            max_pages=args.max_pages,
            max_articles=args.max_articles,
            workers=args.workers,
            timeout_seconds=args.timeout_seconds,
            active_only=not args.include_inactive,
            limit=args.limit,
            priority=args.priority,
            allow_external_redirect=args.allow_external_redirect,
        )
        summary = report["summary"]
        print(
            "Auto preset completed: "
            f"{summary['created']} presets created, "
            f"{summary['crawl_completed']} crawled, "
            f"{summary['crawl_empty']} empty, "
            f"{summary['failed']} failed, "
            f"{summary['skipped_no_article_links']} without article links. "
            f"Report: {report['report_path']}"
        )
        return

    parser.print_help()


if __name__ == "__main__":
    main()
