from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import json
import re
import threading
import time
import unicodedata
import uuid
import zipfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, render_template, request, send_file

from app.auto_preset import resolve_preset_for_new_source
from app.catalog import (
    build_preset_lookup,
    delete_preset,
    delete_source,
    list_presets,
    list_sources,
    repoint_sources_to_preset,
    save_preset,
    save_source,
    sources_using_preset,
)
from app.service import PROJECT_ROOT, load_config_from_json, parse_target_url, resolve_path, run_crawl
from app.translator import prepare_result_for_display


ALL_SOURCES_KEY = "__all__"
RECENT_WINDOW_HOURS = 24
ALL_SOURCES_MAX_CONCURRENT_SOURCES = 8
ALL_SOURCES_PER_DOMAIN_CONCURRENCY = 1
ALL_SOURCES_ARTICLE_WORKERS = 2
CRAWL_JOBS: dict[str, dict[str, Any]] = {}
CRAWL_JOBS_LOCK = threading.Lock()
NON_ARTICLE_PATH_PARTS = {
    "",
    "home",
    "homepage",
    "trang-chu",
    "index",
    "about",
    "about-us",
    "gioi-thieu",
    "contact",
    "contact-us",
    "lien-he",
    "aboutus",
    "leaders",
    "leadership",
    "organiclist",
    "category",
    "categories",
    "tag",
    "tags",
    "archive",
    "archives",
}


def create_crawl_job(job_id: str, source_count: int, output_path: str) -> None:
    with CRAWL_JOBS_LOCK:
        CRAWL_JOBS[job_id] = {
            "job_id": job_id,
            "status": "running",
            "source_count": source_count,
            "processed_sources": 0,
            "crawled_source_count": 0,
            "kept_source_count": 0,
            "article_count": 0,
            "dropped_no_time_count": 0,
            "dropped_old_count": 0,
            "current_source": "",
            "articles": [],
            "output_path": output_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "error": "",
        }


def get_crawl_job(job_id: str) -> dict[str, Any] | None:
    with CRAWL_JOBS_LOCK:
        payload = CRAWL_JOBS.get(job_id)
        return deepcopy(payload) if payload else None


def update_crawl_job(job_id: str, **updates: Any) -> None:
    with CRAWL_JOBS_LOCK:
        job = CRAWL_JOBS.get(job_id)
        if not job:
            return
        for key, value in updates.items():
            job[key] = value
        job["updated_at"] = datetime.now(timezone.utc).isoformat()


def append_crawl_job_articles(job_id: str, articles: list[dict[str, Any]]) -> None:
    if not articles:
        return

    with CRAWL_JOBS_LOCK:
        job = CRAWL_JOBS.get(job_id)
        if not job:
            return
        known_urls = {str(article.get("url") or "") for article in job.get("articles", [])}
        for article in articles:
            article_url = str(article.get("url") or "")
            if article_url and article_url in known_urls:
                continue
            job.setdefault("articles", []).append(article)
            if article_url:
                known_urls.add(article_url)
        job["updated_at"] = datetime.now(timezone.utc).isoformat()


def parse_optional_int(raw_value: str, field_name: str) -> int | None:
    value = raw_value.strip()
    if not value:
        return None
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{field_name} must be greater than 0.")
    return parsed


def load_catalogs() -> tuple[list[dict[str, Any]], dict[str, str], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    presets = list_presets()
    preset_lookup = build_preset_lookup(presets)
    sources = list_sources()
    source_lookup = {source["source_key"]: source for source in sources}
    return presets, preset_lookup, sources, source_lookup


def first_preset_path(presets: list[dict[str, Any]]) -> str:
    return presets[0]["path"] if presets else ""


def build_initial_crawl_form_data(presets: list[dict[str, Any]], preset_lookup: dict[str, str]) -> dict[str, str]:
    selected_preset = first_preset_path(presets)
    return {
        "selected_source_key": ALL_SOURCES_KEY,
        "selected_preset": selected_preset,
        "target_url": "",
        "target_mode": "auto",
        "config_json": preset_lookup.get(selected_preset, ""),
        "output": "output/articles_ui.json",
        "max_pages": "1",
        "max_articles": "5",
        "workers": "4",
        "crawl_keyword": "",
        "crawl_date_from": "",
        "crawl_date_to": "",
        "translate_to_vi": "on",
    }


def build_initial_source_form_data(presets: list[dict[str, Any]]) -> dict[str, str]:
    return {
        "source_key": "",
        "original_source_key": "",
        "name": "",
        "target_url": "",
        "target_mode": "auto",
        "preset_path": first_preset_path(presets),
        "output": "output/source_articles.json",
        "max_pages": "1",
        "max_articles": "5",
        "workers": "4",
        "notes": "",
    }


def build_initial_preset_form_data(presets: list[dict[str, Any]], preset_lookup: dict[str, str]) -> dict[str, str]:
    selected_preset = first_preset_path(presets)
    return {
        "preset_key": Path(selected_preset).stem if selected_preset else "",
        "original_preset_path": selected_preset,
        "config_json": preset_lookup.get(selected_preset, ""),
    }


def update_crawl_form_data(form_data: dict[str, str], form: Any) -> None:
    form_data.update(
        {
            "selected_source_key": form.get("selected_source_key", form_data["selected_source_key"]).strip(),
            "selected_preset": form.get("selected_preset", form_data["selected_preset"]).strip(),
            "target_url": form.get("target_url", form_data["target_url"]).strip(),
            "target_mode": form.get("target_mode", form_data["target_mode"]).strip() or "auto",
            "config_json": form.get("config_json", form_data["config_json"]).strip(),
            "output": form.get("output", form_data["output"]).strip() or form_data["output"],
            "max_pages": form.get("max_pages", form_data["max_pages"]).strip(),
            "max_articles": form.get("max_articles", form_data["max_articles"]).strip(),
            "workers": form.get("workers", form_data["workers"]).strip() or form_data["workers"],
            "crawl_keyword": form.get("crawl_keyword", form_data["crawl_keyword"]).strip(),
            "crawl_date_from": form.get("crawl_date_from", form_data["crawl_date_from"]).strip(),
            "crawl_date_to": form.get("crawl_date_to", form_data["crawl_date_to"]).strip(),
            "translate_to_vi": "on" if form.get("translate_to_vi") == "on" else "",
        }
    )


def update_source_form_data(form_data: dict[str, str], form: Any) -> None:
    form_data.update(
        {
            "source_key": form.get("source_key", form_data["source_key"]).strip(),
            "original_source_key": form.get("original_source_key", form_data["original_source_key"]).strip(),
            "name": form.get("name", form_data["name"]).strip(),
            "target_url": form.get("target_url", form_data["target_url"]).strip(),
            "target_mode": form.get("target_mode", form_data["target_mode"]).strip() or "auto",
            "preset_path": form.get("preset_path", form_data["preset_path"]).strip(),
            "output": form.get("output", form_data["output"]).strip() or form_data["output"],
            "max_pages": form.get("max_pages", form_data["max_pages"]).strip(),
            "max_articles": form.get("max_articles", form_data["max_articles"]).strip(),
            "workers": form.get("workers", form_data["workers"]).strip() or form_data["workers"],
            "notes": form.get("notes", form_data["notes"]).strip(),
        }
    )


def update_preset_form_data(form_data: dict[str, str], form: Any) -> None:
    form_data.update(
        {
            "preset_key": form.get("preset_key", form_data["preset_key"]).strip(),
            "original_preset_path": form.get("original_preset_path", form_data["original_preset_path"]).strip(),
            "config_json": form.get("config_json", form_data["config_json"]).strip(),
        }
    )


def build_source_form_from_source(source: dict[str, Any]) -> dict[str, str]:
    return {
        "source_key": source["source_key"],
        "original_source_key": source["source_key"],
        "name": str(source.get("name") or ""),
        "target_url": str(source.get("target_url") or ""),
        "target_mode": str(source.get("target_mode") or "auto"),
        "preset_path": str(source.get("preset_path") or ""),
        "output": str(source.get("output") or ""),
        "max_pages": "" if source.get("max_pages") is None else str(source.get("max_pages")),
        "max_articles": "" if source.get("max_articles") is None else str(source.get("max_articles")),
        "workers": "" if source.get("workers") is None else str(source.get("workers")),
        "notes": str(source.get("notes") or ""),
    }


def build_crawl_form_from_source(
    source: dict[str, Any],
    preset_lookup: dict[str, str],
    presets: list[dict[str, Any]],
) -> dict[str, str]:
    selected_preset = str(source.get("preset_path") or "")
    if selected_preset not in preset_lookup:
        selected_preset = first_preset_path(presets)
    return {
        "selected_source_key": source["source_key"],
        "selected_preset": selected_preset,
        "target_url": str(source.get("target_url") or ""),
        "target_mode": str(source.get("target_mode") or "auto"),
        "config_json": preset_lookup.get(selected_preset, ""),
        "output": str(source.get("output") or "output/articles_ui.json"),
        "max_pages": "" if source.get("max_pages") is None else str(source.get("max_pages")),
        "max_articles": "" if source.get("max_articles") is None else str(source.get("max_articles")),
        "workers": "" if source.get("workers") is None else str(source.get("workers")),
        "translate_to_vi": "on",
    }


def build_crawl_form_for_run(
    source: dict[str, Any],
    preset_lookup: dict[str, str],
    presets: list[dict[str, Any]],
    max_articles_override: str = "",
    translate_to_vi: str = "on",
) -> dict[str, str]:
    form_data = build_crawl_form_from_source(source, preset_lookup, presets)
    if max_articles_override.strip():
        form_data["max_articles"] = max_articles_override.strip()
    form_data["translate_to_vi"] = "on" if translate_to_vi == "on" else ""
    return form_data


def build_preset_form_from_path(relative_path: str, preset_lookup: dict[str, str]) -> dict[str, str]:
    return {
        "preset_key": Path(relative_path).stem if relative_path else "",
        "original_preset_path": relative_path,
        "config_json": preset_lookup.get(relative_path, ""),
    }


def parse_result_page(raw_value: str) -> int:
    try:
        page = int((raw_value or "").strip() or "1")
    except ValueError:
        return 1
    return max(page, 1)


def paginate_result_articles(result: dict[str, Any] | None, page: int, page_size: int = 20) -> dict[str, Any]:
    pagination = {
        "page": 1,
        "page_size": page_size,
        "total_pages": 1,
        "total_items": 0,
        "has_prev": False,
        "has_next": False,
        "prev_page": 1,
        "next_page": 1,
        "page_items": 0,
    }
    if not result:
        return pagination

    articles = result.get("articles") or []
    total_items = len(articles)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    current_page = min(max(page, 1), total_pages)
    start = (current_page - 1) * page_size
    end = start + page_size
    result["articles"] = articles[start:end]

    pagination.update(
        {
            "page": current_page,
            "total_pages": total_pages,
            "total_items": total_items,
            "has_prev": current_page > 1,
            "has_next": current_page < total_pages,
            "prev_page": max(1, current_page - 1),
            "next_page": min(total_pages, current_page + 1),
            "page_items": len(result["articles"]),
        }
    )
    return pagination


def parse_article_timestamp(raw_value: str | None) -> datetime | None:
    value = (raw_value or "").strip()
    if not value:
        return None

    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        pass

    iso_like = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})(?:[ T](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?", value)
    if iso_like:
        year = int(iso_like.group(1))
        month = int(iso_like.group(2))
        day = int(iso_like.group(3))
        hour = int(iso_like.group(4) or 0)
        minute = int(iso_like.group(5) or 0)
        second = int(iso_like.group(6) or 0)
        try:
            return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
        except ValueError:
            return None

    vn_like = re.search(r"(?:ngay\s*)?(\d{1,2})\s*thang\s*(\d{1,2})\s*nam\s*(20\d{2})", value, re.IGNORECASE)
    if vn_like:
        day = int(vn_like.group(1))
        month = int(vn_like.group(2))
        year = int(vn_like.group(3))
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            return None

    slash_like = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](20\d{2})", value)
    if slash_like:
        day = int(slash_like.group(1))
        month = int(slash_like.group(2))
        year = int(slash_like.group(3))
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            return None

    return None


def parse_article_datetime(article: dict[str, Any]) -> datetime | None:
    published = parse_article_timestamp(str(article.get("published_at") or ""))
    if published:
        return published

    url = str(article.get("url") or "")
    url_dt = parse_datetime_from_url(url)
    if url_dt:
        return url_dt

    return None


def parse_datetime_from_url(url: str) -> datetime | None:
    url_match = re.search(r"/(20\d{2})/(\d{1,2})/(\d{1,2})(?:/|$)", url)
    if not url_match:
        return None

    year = int(url_match.group(1))
    month = int(url_match.group(2))
    day = int(url_match.group(3))
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


def is_non_article_url(url: str) -> bool:
    parsed = urlparse(url)
    parts = [part.strip().lower() for part in parsed.path.split("/") if part.strip()]
    if not parts:
        return True
    if len(parts) == 1 and parts[0] in NON_ARTICLE_PATH_PARTS:
        return True
    return False


def is_non_article_record(article: dict[str, Any]) -> bool:
    url = str(article.get("url") or "")
    if is_non_article_url(url):
        return True
    title = str(article.get("title") or "")
    display_title = str(article.get("display_title") or "")
    if is_homepage_like_title(title) or is_homepage_like_title(display_title):
        return True
    return False


def normalize_text_for_match(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    ascii_text = ascii_text.lower()
    return re.sub(r"\s+", " ", ascii_text).strip()


def is_homepage_like_title(value: str) -> bool:
    text = normalize_text_for_match(value)
    if not text:
        return False
    direct_hits = {"home", "homepage", "trang chu", "trang chu |"}
    if text in direct_hits:
        return True
    if text.endswith(" - trang chu") or text.endswith(" | trang chu"):
        return True
    if text.endswith(" - home") or text.endswith(" | home"):
        return True
    if " homepage" in text:
        return True
    return False


def build_recent_article_link_filter(cutoff: datetime) -> Callable[[str], bool]:
    def should_keep(url: str) -> bool:
        if is_non_article_url(url):
            return False
        dt = parse_datetime_from_url(url)
        if dt is None:
            return True
        return dt >= cutoff

    return should_keep


def run_crawl_all_sources_last_24h(
    sources: list[dict[str, Any]],
    preset_lookup: dict[str, str],
    output_path: Path,
    max_pages: int | None,
    max_articles: int | None,
    workers: int,
    clicked_at: datetime | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    clicked_at = clicked_at or datetime.now(timezone.utc)
    cutoff = clicked_at - timedelta(hours=RECENT_WINDOW_HOURS)

    all_articles: list[dict[str, Any]] = []
    warnings: list[str] = []
    crawled_sources = 0
    kept_sources = 0
    dropped_no_time = 0
    dropped_old = 0
    dropped_keyword = 0
    dropped_non_article = 0

    total_sources = len(sources)
    domain_limits: dict[str, threading.Semaphore] = defaultdict(
        lambda: threading.Semaphore(ALL_SOURCES_PER_DOMAIN_CONCURRENCY)
    )

    def process_source(source: dict[str, Any]) -> dict[str, Any]:
        source_key = str(source.get("source_key") or "")
        source_name = str(source.get("name") or source_key)
        preset_path = str(source.get("preset_path") or "")
        result: dict[str, Any] = {
            "source_key": source_key,
            "source_name": source_name,
            "articles": [],
            "warnings": [],
            "crawled": 0,
            "dropped_no_time": 0,
            "dropped_old": 0,
            "dropped_non_article": 0,
            "kept": 0,
        }

        if not source_key or not preset_path:
            return result

        config_json = preset_lookup.get(preset_path)
        if not config_json:
            result["warnings"].append(f"[{source_key}] Khong tim thay config cho preset '{preset_path}'.")
            return result

        source_target_url = parse_target_url(str(source.get("target_url") or ""))
        if not source_target_url:
            result["warnings"].append(f"[{source_key}] Nguon khong co target_url hop le.")
            return result

        source_max_pages = max_pages if max_pages is not None else source.get("max_pages")
        source_max_articles = max_articles if max_articles is not None else source.get("max_articles")
        source_workers = max(min(workers, ALL_SOURCES_ARTICLE_WORKERS), 1)
        if source.get("workers") is not None and max_articles is None:
            try:
                source_workers = max(min(int(source.get("workers") or workers), ALL_SOURCES_ARTICLE_WORKERS), 1)
            except (TypeError, ValueError):
                source_workers = max(min(workers, ALL_SOURCES_ARTICLE_WORKERS), 1)

        domain = urlparse(source_target_url).netloc.lower()
        semaphore = domain_limits[domain]
        with semaphore:
            try:
                source_payload = run_crawl(
                    config=load_config_from_json(config_json),
                    output_path=output_path,
                    max_pages=source_max_pages,
                    max_articles=source_max_articles,
                    workers=source_workers,
                    save_output=False,
                    target_url=source_target_url,
                    target_mode=str(source.get("target_mode") or "auto"),
                    include_target_warnings=False,
                    article_link_filter=build_recent_article_link_filter(cutoff),
                )
                result["crawled"] = 1
            except Exception as exc:
                result["warnings"].append(f"[{source_key}] Crawl loi: {exc}")
                return result

        for warning in source_payload.get("warnings") or []:
            result["warnings"].append(f"[{source_key}] {warning}")

        for article in source_payload.get("articles") or []:
            if is_non_article_record(article):
                result["dropped_non_article"] += 1
                continue
            article_time = parse_article_datetime(article)
            if article_time is None:
                result["dropped_no_time"] += 1
                continue
            if article_time < cutoff:
                result["dropped_old"] += 1
                continue

            item = dict(article)
            item["source_key"] = source_key
            item["source_name"] = source_name
            result["articles"].append(item)
            result["kept"] += 1

        return result

    max_source_workers = max(1, min(ALL_SOURCES_MAX_CONCURRENT_SOURCES, total_sources or 1))
    processed_sources = 0
    with ThreadPoolExecutor(max_workers=max_source_workers) as executor:
        futures = [executor.submit(process_source, source) for source in sources]
        for future in as_completed(futures):
            processed_sources += 1
            try:
                source_result = future.result()
            except Exception as exc:
                warnings.append(f"[unknown] Crawl loi: {exc}")
                if progress_callback:
                    progress_callback(
                        {
                            "processed_sources": processed_sources,
                            "source_count": total_sources,
                            "crawled_source_count": crawled_sources,
                            "kept_source_count": kept_sources,
                            "article_count": len(all_articles),
                            "dropped_no_time_count": dropped_no_time,
                            "dropped_old_count": dropped_old,
                            "current_source": "",
                            "new_articles": [],
                        }
                    )
                continue

            warnings.extend(source_result["warnings"])
            crawled_sources += int(source_result["crawled"])
            dropped_no_time += int(source_result["dropped_no_time"])
            dropped_old += int(source_result["dropped_old"])
            dropped_non_article += int(source_result.get("dropped_non_article") or 0)
            dropped_keyword += int(source_result.get("dropped_keyword") or 0)
            if int(source_result["kept"]) > 0:
                kept_sources += 1
            all_articles.extend(source_result["articles"])

            if progress_callback:
                progress_callback(
                    {
                        "processed_sources": processed_sources,
                        "source_count": total_sources,
                        "crawled_source_count": crawled_sources,
                        "kept_source_count": kept_sources,
                        "article_count": len(all_articles),
                        "dropped_no_time_count": dropped_no_time,
                        "dropped_old_count": dropped_old,
                        "dropped_non_article_count": dropped_non_article,
                        "current_source": str(source_result.get("source_name") or ""),
                        "new_articles": source_result["articles"],
                    }
                )

    all_articles.sort(key=lambda item: parse_article_datetime(item) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    success_count = sum(1 for article in all_articles if "error" not in article)
    payload = {
        "site_name": "All Sources",
        "article_count": len(all_articles),
        "success_count": success_count,
        "error_count": len(all_articles) - success_count,
        "warnings": warnings,
        "articles": all_articles,
        "output_path": str(output_path),
        "duration_seconds": round(time.perf_counter() - started_at, 2),
        "target_url": None,
        "target_mode": "all_sources_last_24h",
        "window_hours": RECENT_WINDOW_HOURS,
        "clicked_at": clicked_at.isoformat(),
        "cutoff_at": cutoff.isoformat(),
        "source_count": total_sources,
        "crawled_source_count": crawled_sources,
        "kept_source_count": kept_sources,
        "dropped_no_time_count": dropped_no_time,
        "dropped_old_count": dropped_old,
        "dropped_non_article_count": dropped_non_article,
        "dropped_keyword_count": dropped_keyword,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    return payload


def run_all_sources_crawl_job(
    job_id: str,
    sources: list[dict[str, Any]],
    preset_lookup: dict[str, str],
    output_path: Path,
    max_pages: int | None,
    max_articles: int | None,
    workers: int,
    clicked_at: datetime,
) -> None:
    def publish_progress(progress: dict[str, Any]) -> None:
        new_articles = progress.pop("new_articles", [])
        if new_articles:
            display_payload = prepare_result_for_display(
                {
                    "site_name": "All Sources",
                    "article_count": len(new_articles),
                    "success_count": sum(1 for article in new_articles if "error" not in article),
                    "error_count": sum(1 for article in new_articles if "error" in article),
                    "warnings": [],
                    "articles": new_articles,
                },
                translate_to_vi=True,
            )
            append_crawl_job_articles(job_id, display_payload.get("articles") or [])
        update_crawl_job(job_id, **progress)

    try:
        payload = run_crawl_all_sources_last_24h(
            sources=sources,
            preset_lookup=preset_lookup,
            output_path=output_path,
            max_pages=max_pages,
            max_articles=max_articles,
            workers=workers,
            clicked_at=clicked_at,
            progress_callback=publish_progress,
        )
        final_display_payload = prepare_result_for_display(payload, translate_to_vi=True)
        update_crawl_job(job_id, articles=final_display_payload.get("articles") or [])
        update_crawl_job(
            job_id,
            status="completed",
            processed_sources=payload.get("source_count", 0),
            crawled_source_count=payload.get("crawled_source_count", 0),
            kept_source_count=payload.get("kept_source_count", 0),
            article_count=payload.get("article_count", 0),
            dropped_no_time_count=payload.get("dropped_no_time_count", 0),
            dropped_old_count=payload.get("dropped_old_count", 0),
            current_source="",
            completed_at=datetime.now(timezone.utc).isoformat(),
            target_mode=payload.get("target_mode"),
            window_hours=payload.get("window_hours"),
        )
    except Exception as exc:
        update_crawl_job(
            job_id,
            status="failed",
            error=str(exc),
            current_source="",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )

    @app.route("/", methods=["GET", "POST"])
    def index() -> str:
        presets, preset_lookup, sources, source_lookup = load_catalogs()

        crawl_form_data = build_initial_crawl_form_data(presets, preset_lookup)
        source_form_data = build_initial_source_form_data(presets)
        preset_form_data = build_initial_preset_form_data(presets, preset_lookup)
        result: dict[str, Any] | None = None
        raw_result_json = ""
        page_notice: dict[str, str] | None = None

        active_tab = request.values.get("tab", request.values.get("active_tab", "crawl")).strip() or "crawl"
        if active_tab not in {"crawl", "sources", "presets"}:
            active_tab = "crawl"
        result_page = parse_result_page(request.values.get("result_page", "1"))
        search_sources = request.values.get("search_sources", "").strip()
        active_job_id = request.values.get("job_id", "").strip()
        active_crawl_job = get_crawl_job(active_job_id) if active_job_id else None

        if request.method == "GET" and active_tab == "crawl" and active_crawl_job and active_crawl_job.get("status") == "completed":
            output_path = str(active_crawl_job.get("output_path") or "")
            if output_path:
                resolved_output = resolve_path(output_path)
                if resolved_output.exists():
                    try:
                        loaded_result = json.loads(resolved_output.read_text(encoding="utf-8"))
                        raw_result_json = json.dumps(loaded_result, ensure_ascii=False, indent=2)
                        result = prepare_result_for_display(
                            loaded_result,
                            translate_to_vi=True,
                        )
                    except Exception:
                        pass

        if request.method == "POST":
            action = request.form.get("action", "").strip()
            active_tab = request.form.get("active_tab", active_tab).strip() or active_tab

            update_crawl_form_data(crawl_form_data, request.form)
            update_source_form_data(source_form_data, request.form)
            update_preset_form_data(preset_form_data, request.form)

            try:
                if action == "load_source_into_crawl":
                    source = source_lookup.get(crawl_form_data["selected_source_key"])
                    if not source:
                        raise ValueError("Không tìm thấy nguồn.")
                    crawl_form_data = build_crawl_form_from_source(source, preset_lookup, presets)
                    page_notice = {"level": "success", "text": f"Đã nạp nguồn '{source['name']}' vào tab crawl."}
                    active_tab = "crawl"

                elif action == "run_crawl":
                    max_pages = parse_optional_int(crawl_form_data["max_pages"], "max_pages")
                    max_articles = parse_optional_int(crawl_form_data["max_articles"], "max_articles")
                    workers = parse_optional_int(crawl_form_data["workers"], "workers") or 4

                    if crawl_form_data["selected_source_key"] == ALL_SOURCES_KEY:
                        active_job_id = uuid.uuid4().hex[:12]
                        crawl_form_data["output"] = f"output/articles_all_sources_last_24h_{active_job_id}.json"
                        create_crawl_job(
                            job_id=active_job_id,
                            source_count=len(sources),
                            output_path=crawl_form_data["output"],
                        )
                        clicked_at = datetime.now(timezone.utc)
                        worker = threading.Thread(
                            target=run_all_sources_crawl_job,
                            kwargs={
                                "job_id": active_job_id,
                                "sources": sources,
                                "preset_lookup": preset_lookup,
                                "output_path": resolve_path(crawl_form_data["output"]),
                                "max_pages": max_pages,
                                "max_articles": max_articles,
                                "workers": workers,
                                "clicked_at": clicked_at,
                            },
                            daemon=True,
                        )
                        worker.start()
                        active_crawl_job = get_crawl_job(active_job_id)
                        page_notice = {
                            "level": "success",
                            "text": "Da bat dau crawl tat ca nguon o che do nen. Bai nao crawl duoc se hien thi ngay trong luc chay.",
                        }
                        active_tab = "crawl"
                    else:
                        source = source_lookup.get(crawl_form_data["selected_source_key"])
                        if not source:
                            raise ValueError("Vui lòng chọn một nguồn để crawl.")
                        crawl_form_data = build_crawl_form_for_run(
                            source,
                            preset_lookup,
                            presets,
                            max_articles_override=crawl_form_data["max_articles"],
                            translate_to_vi=request.form.get("translate_to_vi", ""),
                        )
                        if not crawl_form_data["config_json"] and crawl_form_data["selected_preset"] in preset_lookup:
                            crawl_form_data["config_json"] = preset_lookup[crawl_form_data["selected_preset"]]
                        config = load_config_from_json(crawl_form_data["config_json"])
                        target_url = parse_target_url(crawl_form_data["target_url"])
                        result = run_crawl(
                            config=config,
                            output_path=resolve_path(crawl_form_data["output"]),
                            max_pages=max_pages,
                            max_articles=max_articles,
                            workers=workers,
                            save_output=True,
                            target_url=target_url,
                            target_mode=crawl_form_data["target_mode"],
                            include_target_warnings=False,
                        )

                        filtered_articles = [
                            article
                            for article in (result.get("articles") or [])
                            if not is_non_article_record(article)
                        ]
                        result["articles"] = filtered_articles
                        result["article_count"] = len(filtered_articles)
                        result["success_count"] = sum(1 for article in filtered_articles if "error" not in article)
                        result["error_count"] = result["article_count"] - result["success_count"]

                        raw_result_json = json.dumps(result, ensure_ascii=False, indent=2)
                        result = prepare_result_for_display(
                            result,
                            translate_to_vi=True,
                        )

                        display_filtered_articles = [
                            article
                            for article in (result.get("articles") or [])
                            if not is_non_article_record(article)
                        ]
                        result["articles"] = display_filtered_articles
                        result["article_count"] = len(display_filtered_articles)
                        result["success_count"] = sum(1 for article in display_filtered_articles if "error" not in article)
                        result["error_count"] = result["article_count"] - result["success_count"]

                        page_notice = {
                            "level": "success",
                            "text": f"Crawl xong: {result['success_count']}/{result['article_count']} bài thành công.",
                        }
                        active_tab = "crawl"

                elif action == "save_source":
                    if not source_form_data["source_key"] and not source_form_data["name"]:
                        raise ValueError("Hãy nhập ít nhất source key hoặc tên nguồn.")
                    target_url = parse_target_url(source_form_data["target_url"])
                    if not target_url:
                        raise ValueError("URL nguồn là bắt buộc.")
                    # Check for duplicates
                    existing_sources = list_sources()
                    new_key = source_form_data["source_key"] or source_form_data["name"]
                    for s in existing_sources:
                        if s["source_key"] == new_key and s["source_key"] != (source_form_data["original_source_key"] or ""):
                            raise ValueError(f"Nguồn với key '{new_key}' đã tồn tại.")
                        if s["target_url"] == target_url and s["source_key"] != (source_form_data["original_source_key"] or ""):
                            raise ValueError(f"Nguồn với URL '{target_url}' đã tồn tại.")

                    is_new_source = not (source_form_data["original_source_key"] or "").strip()
                    preset_notice = ""
                    if is_new_source:
                        resolution = resolve_preset_for_new_source(
                            target_url=target_url,
                            source_name=source_form_data["name"] or source_form_data["source_key"] or target_url,
                            timeout_seconds=8,
                        )
                        source_form_data["preset_path"] = str(resolution.get("preset_path") or "")
                        if resolution.get("resolution") == "matched_existing":
                            preset_notice = (
                                f"Dùng preset có sẵn '{source_form_data['preset_path']}' "
                                f"(success {resolution.get('success_count', 0)}/{resolution.get('article_count', 0)} khi test nhanh)."
                            )
                        else:
                            preset_notice = f"Tạo preset mới '{source_form_data['preset_path']}' cho nguồn này."

                    if source_form_data["preset_path"] not in preset_lookup:
                        presets, preset_lookup, sources, source_lookup = load_catalogs()
                    if source_form_data["preset_path"] not in preset_lookup:
                        raise ValueError("Không thể xác định preset phù hợp cho nguồn này.")

                    max_pages = parse_optional_int(source_form_data["max_pages"], "max_pages")
                    max_articles = parse_optional_int(source_form_data["max_articles"], "max_articles")
                    workers = parse_optional_int(source_form_data["workers"], "workers") or 4
                    saved_notes = source_form_data["notes"]
                    if preset_notice:
                        saved_notes = f"{saved_notes}\n{preset_notice}".strip() if saved_notes else preset_notice
                    saved_source = save_source(
                        {
                            "source_key": source_form_data["source_key"] or source_form_data["name"],
                            "name": source_form_data["name"] or source_form_data["source_key"],
                            "target_url": target_url,
                            "target_mode": source_form_data["target_mode"],
                            "preset_path": source_form_data["preset_path"],
                            "output": source_form_data["output"],
                            "max_pages": max_pages,
                            "max_articles": max_articles,
                            "workers": workers,
                            "notes": saved_notes,
                        },
                        original_source_key=source_form_data["original_source_key"] or None,
                    )
                    presets, preset_lookup, sources, source_lookup = load_catalogs()
                    source_form_data = build_source_form_from_source(saved_source)
                    notice_text = f"Đã lưu nguồn '{saved_source['name']}'."
                    if preset_notice:
                        notice_text = f"{notice_text} {preset_notice}"
                    page_notice = {"level": "success", "text": notice_text}
                    active_tab = "sources"

                elif action == "edit_source":
                    source = source_lookup.get(request.form.get("source_ref", "").strip())
                    if not source:
                        raise ValueError("Không tìm thấy nguồn.")
                    source_form_data = build_source_form_from_source(source)
                    page_notice = {"level": "success", "text": f"Đang sửa nguồn '{source['name']}'."}
                    active_tab = "sources"

                elif action == "use_source_for_crawl":
                    source = source_lookup.get(request.form.get("source_ref", "").strip())
                    if not source:
                        raise ValueError("Không tìm thấy nguồn.")
                    crawl_form_data = build_crawl_form_from_source(source, preset_lookup, presets)
                    page_notice = {"level": "success", "text": f"Đã nạp nguồn '{source['name']}' vào tab crawl."}
                    active_tab = "crawl"

                elif action == "delete_source":
                    source_key = request.form.get("source_ref", "").strip()
                    source = source_lookup.get(source_key)
                    if not source:
                        raise ValueError("Không tìm thấy nguồn.")
                    delete_source(source_key)
                    presets, preset_lookup, sources, source_lookup = load_catalogs()
                    source_form_data = build_initial_source_form_data(presets)
                    page_notice = {"level": "success", "text": f"Đã xóa nguồn '{source['name']}'."}
                    active_tab = "sources"

                elif action == "delete_sources":
                    source_keys = [key.strip() for key in request.form.getlist("source_refs") if key.strip()]
                    if not source_keys:
                        raise ValueError("Chưa chọn nguồn nào để xóa.")

                    deleted_names: list[str] = []
                    missing_keys: list[str] = []
                    for source_key in dict.fromkeys(source_keys):
                        source = source_lookup.get(source_key)
                        if not source:
                            missing_keys.append(source_key)
                            continue
                        delete_source(source_key)
                        deleted_names.append(source["name"])

                    presets, preset_lookup, sources, source_lookup = load_catalogs()
                    source_form_data = build_initial_source_form_data(presets)
                    if not deleted_names:
                        raise ValueError("Không tìm thấy nguồn nào trong danh sách đã chọn.")

                    notice_text = f"Đã xóa {len(deleted_names)} nguồn."
                    if missing_keys:
                        notice_text = f"{notice_text} Bỏ qua {len(missing_keys)} nguồn không còn tồn tại."
                    page_notice = {"level": "success", "text": notice_text}
                    active_tab = "sources"

                elif action == "save_preset":
                    if not preset_form_data["preset_key"]:
                        raise ValueError("Preset key là bắt buộc.")
                    load_config_from_json(preset_form_data["config_json"])
                    previous_path = preset_form_data["original_preset_path"] or None
                    saved_preset_path = save_preset(
                        config_json=preset_form_data["config_json"],
                        preset_key=preset_form_data["preset_key"],
                        original_preset_path=previous_path,
                    )
                    if previous_path:
                        repoint_sources_to_preset(previous_path, saved_preset_path)
                    presets, preset_lookup, sources, source_lookup = load_catalogs()
                    preset_form_data = build_preset_form_from_path(saved_preset_path, preset_lookup)
                    if crawl_form_data["selected_preset"] == previous_path or not crawl_form_data["selected_preset"]:
                        crawl_form_data["selected_preset"] = saved_preset_path
                        crawl_form_data["config_json"] = preset_lookup.get(saved_preset_path, "")
                    page_notice = {"level": "success", "text": f"Đã lưu preset '{saved_preset_path}'."}
                    active_tab = "presets"

                elif action == "edit_preset":
                    preset_path = request.form.get("preset_ref", "").strip()
                    if preset_path not in preset_lookup:
                        raise ValueError("Không tìm thấy preset.")
                    preset_form_data = build_preset_form_from_path(preset_path, preset_lookup)
                    page_notice = {"level": "success", "text": f"Đang sửa preset '{preset_path}'."}
                    active_tab = "presets"

                elif action == "delete_preset":
                    preset_path = request.form.get("preset_ref", "").strip()
                    linked_sources = sources_using_preset(preset_path)
                    if linked_sources:
                        names = ", ".join(source["name"] for source in linked_sources[:3])
                        if len(linked_sources) > 3:
                            names += ", ..."
                        raise ValueError(
                            f"Không thể xóa preset vì vẫn còn nguồn đang dùng: {names}."
                        )
                    delete_preset(preset_path)
                    presets, preset_lookup, sources, source_lookup = load_catalogs()
                    preset_form_data = build_initial_preset_form_data(presets, preset_lookup)
                    if crawl_form_data["selected_preset"] == preset_path:
                        crawl_form_data["selected_preset"] = first_preset_path(presets)
                        crawl_form_data["config_json"] = preset_lookup.get(crawl_form_data["selected_preset"], "")
                    page_notice = {"level": "success", "text": f"Đã xóa preset '{preset_path}'."}
                    active_tab = "presets"

            except json.JSONDecodeError as exc:
                page_notice = {
                    "level": "error",
                    "text": f"Config JSON không hợp lệ: {exc.msg} tại dòng {exc.lineno}, cột {exc.colno}.",
                }
            except Exception as exc:
                page_notice = {"level": "error", "text": str(exc)}

        result_pagination = paginate_result_articles(result, result_page)

        preset_usage: dict[str, int] = {preset["path"]: 0 for preset in presets}
        for source in sources:
            preset_path = str(source.get("preset_path") or "")
            if preset_path in preset_usage:
                preset_usage[preset_path] += 1
        preset_label_lookup = {preset["path"]: preset["label"] for preset in presets}
        selected_source = (
            source_lookup.get(crawl_form_data["selected_source_key"])
            if crawl_form_data["selected_source_key"] and crawl_form_data["selected_source_key"] != ALL_SOURCES_KEY
            else None
        )

        return render_template(
            "index.html",
            active_tab=active_tab,
            presets=presets,
            preset_lookup=preset_lookup,
            preset_usage=preset_usage,
            preset_label_lookup=preset_label_lookup,
            sources=sources,
            source_lookup=source_lookup,
            selected_source=selected_source,
            all_sources_key=ALL_SOURCES_KEY,
            active_job_id=active_job_id,
            active_crawl_job=active_crawl_job,
            result_pagination=result_pagination,
            crawl_form_data=crawl_form_data,
            source_form_data=source_form_data,
            preset_form_data=preset_form_data,
            result=result,
            raw_result_json=raw_result_json,
            page_notice=page_notice,
            search_sources=search_sources,
        )

    @app.get("/api/crawl-jobs/<job_id>")
    def crawl_job_status(job_id: str):
        payload = get_crawl_job(job_id)
        if not payload:
            return jsonify({"error": "not_found"}), 404
        return jsonify(payload)

    @app.get("/healthz")
    def health_check():
        return jsonify({"ok": True})

    @app.get("/api/sources/<source_key>/export")
    def export_source(source_key: str):
        source_lookup = {source["source_key"]: source for source in list_sources()}
        source = source_lookup.get(source_key)
        if not source:
            return jsonify({"error": "not_found"}), 404

        body = json.dumps(source, ensure_ascii=False, indent=2) + "\n"
        filename = f"{source['source_key']}.json"
        return Response(
            body,
            mimetype="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/sources/export.zip")
    def export_sources_zip():
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for source in list_sources():
                body = json.dumps(source, ensure_ascii=False, indent=2) + "\n"
                archive.writestr(f"{source['source_key']}.json", body)

        buffer.seek(0)
        return send_file(
            buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name="sources_export.zip",
        )

    @app.get("/api/sources/export-list.json")
    def export_sources_review_list():
        sources_payload = []
        for index, source in enumerate(list_sources(), start=1):
            sources_payload.append(
                {
                    "index": index,
                    "review_action": "",
                    "review_note": "",
                    "source_key": source.get("source_key", ""),
                    "name": source.get("name", ""),
                    "target_url": source.get("target_url", ""),
                    "target_mode": source.get("target_mode", ""),
                    "preset_path": source.get("preset_path", ""),
                    "output": source.get("output", ""),
                    "max_pages": source.get("max_pages"),
                    "max_articles": source.get("max_articles"),
                    "workers": source.get("workers"),
                    "notes": source.get("notes", ""),
                }
            )

        body = json.dumps(
            {
                "format": "media-crawler-source-review-v1",
                "instructions": {
                    "review_action": "Optional: keep, delete, update, or add.",
                    "review_note": "Optional note about what should change.",
                    "add_source": "To request a new source, append an object with review_action='add'.",
                },
                "source_count": len(sources_payload),
                "sources": sources_payload,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        return Response(
            body,
            mimetype="application/json; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="sources_review.json"'},
        )

    return app


def run_web_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    app = create_app()
    app.run(host=host, port=port, debug=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the crawler web interface.")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on.")
    args = parser.parse_args()
    run_web_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
