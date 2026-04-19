from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
import re

from app.crawler import MediaCrawler, read_json


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIGS_DIR = PROJECT_ROOT / "configs"


def resolve_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def discover_config_paths() -> list[Path]:
    if not CONFIGS_DIR.exists():
        return []
    return sorted(path for path in CONFIGS_DIR.glob("*.json") if path.is_file())


def read_config_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_config_from_json(config_json: str) -> dict[str, Any]:
    return json.loads(config_json)


def parse_target_url(raw_value: str) -> str | None:
    value = raw_value.strip()
    if not value:
        return None

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Target URL must start with http:// or https:// and include a valid domain.")
    return value


def infer_target_mode(config: dict[str, Any], target_url: str, requested_mode: str) -> str:
    if requested_mode in {"listing", "article"}:
        return requested_mode

    article_link_pattern = config.get("article_link_pattern")
    if article_link_pattern:
        try:
            if re.search(article_link_pattern, target_url):
                return "article"
        except re.error:
            pass

    if target_url.rstrip("/").lower().endswith(".html"):
        return "article"

    return "listing"


def prepare_runtime_config(
    config: dict[str, Any],
    target_url: str | None = None,
    target_mode: str = "auto",
    include_target_warnings: bool = True,
) -> tuple[dict[str, Any], str | None, list[str]]:
    runtime_config = deepcopy(config)
    warnings: list[str] = []

    if not target_url:
        return runtime_config, None, warnings

    parsed = urlparse(target_url)
    custom_domain = parsed.netloc
    original_domain = urlparse(str(config.get("base_url", ""))).netloc
    runtime_config["base_url"] = f"{parsed.scheme}://{custom_domain}"
    runtime_config["allowed_domains"] = [custom_domain]

    effective_mode = infer_target_mode(runtime_config, target_url, target_mode)

    if effective_mode == "article":
        if include_target_warnings:
            warnings.append("Custom URL is being crawled as a single article page.")
        return runtime_config, effective_mode, warnings

    runtime_config["listing_urls"] = [target_url]
    runtime_config.pop("pagination", None)
    if include_target_warnings:
        warnings.append("Custom URL is being used as the listing page for this run.")

    if custom_domain != original_domain:
        runtime_config["article_link_pattern"] = rf"https?://{re.escape(custom_domain)}/.*"
        if include_target_warnings:
            warnings.append("Article link matching was relaxed to the domain of the custom URL.")

    return runtime_config, effective_mode, warnings


def run_crawl(
    config: dict[str, Any],
    output_path: Path,
    max_pages: int | None = None,
    max_articles: int | None = None,
    workers: int = 4,
    save_output: bool = True,
    target_url: str | None = None,
    target_mode: str = "auto",
    include_target_warnings: bool = True,
    article_link_filter: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    runtime_config, effective_target_mode, extra_warnings = prepare_runtime_config(
        config=config,
        target_url=target_url,
        target_mode=target_mode,
        include_target_warnings=include_target_warnings,
    )
    crawler = MediaCrawler(config=runtime_config, output_path=output_path)

    if target_url and effective_target_mode == "article":
        if max_pages:
            extra_warnings.append("max_pages is ignored when crawling a single article URL.")
        if max_articles and max_articles != 1:
            extra_warnings.append("max_articles is ignored when crawling a single article URL.")
        try:
            articles = [crawler.extract_article(target_url)]
        except Exception as exc:
            articles = [
                {
                    "url": target_url,
                    "site_name": crawler.site_name,
                    "error": str(exc),
                }
            ]
    else:
        articles = crawler.crawl(
            max_pages=max_pages,
            max_articles=max_articles,
            workers=workers,
            article_link_filter=article_link_filter,
        )

    payload = crawler.build_payload(articles)
    payload["warnings"] = [*extra_warnings, *payload["warnings"]]
    payload["output_path"] = str(output_path)
    payload["duration_seconds"] = round(time.perf_counter() - started_at, 2)
    payload["target_url"] = target_url
    payload["target_mode"] = effective_target_mode
    if save_output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
    return payload


def run_crawl_from_file(
    config_path: Path,
    output_path: Path,
    max_pages: int | None = None,
    max_articles: int | None = None,
    workers: int = 4,
    save_output: bool = True,
) -> dict[str, Any]:
    return run_crawl(
        config=read_json(config_path),
        output_path=output_path,
        max_pages=max_pages,
        max_articles=max_articles,
        workers=workers,
        save_output=save_output,
    )
