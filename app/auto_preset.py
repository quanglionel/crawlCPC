from __future__ import annotations

import csv
import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from app.batch_sources import canonical_domain
from app.catalog import list_presets, list_sources, resolve_preset_path, save_source, slugify
from app.crawler import describe_exception
from app.service import CONFIGS_DIR, PROJECT_ROOT, resolve_path, run_crawl


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "km,en-US;q=0.9,en;q=0.8,vi;q=0.7",
}

GENERIC_NAMES = {"com", "gov", "org", "net", "blogspot", "cri"}
BAD_EXTENSIONS = {
    ".7z",
    ".avi",
    ".css",
    ".doc",
    ".docx",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".rar",
    ".svg",
    ".webp",
    ".xls",
    ".xlsx",
    ".xml",
    ".zip",
}
BAD_PATH_PARTS = {
    "about",
    "advertise",
    "author",
    "category",
    "contact",
    "feed",
    "login",
    "page",
    "privacy",
    "register",
    "rss",
    "search",
    "tag",
    "terms",
    "wp-admin",
    "wp-content",
    "wp-json",
}

ARTICLE_LINK_SELECTORS = [
    "article a[href]",
    ".post a[href]",
    ".entry a[href]",
    ".entry-title a[href]",
    ".post-title a[href]",
    ".news-title a[href]",
    ".item-title a[href]",
    ".card a[href]",
    ".item a[href]",
    ".news-item a[href]",
    "h1 a[href]",
    "h2 a[href]",
    "h3 a[href]",
    "a[href]",
]

ARTICLE_LINK_EXCLUDES = [
    r"/(?:about|advertise|author|category|contact|feed|login|page|privacy|register|rss|search|tag|terms)(?:/|$)",
    r"/(?:wp-admin|wp-content|wp-json)(?:/|$)",
    r"\.(?:7z|avi|css|docx?|gif|ico|jpe?g|js|mp3|mp4|pdf|png|rar|svg|webp|xlsx?|xml|zip)(?:[?#]|$)",
    r"(?:facebook|instagram|linkedin|telegram|tiktok|twitter|x|youtube)\.com",
    r"/(?:home|homepage|latest|latest-news|contact|contact-us|about|about-us|trang-chu|lien-he)(?:/|$)",
    r"^https?://[^/]+/?(?:[?#].*)?$",
]

NON_ARTICLE_PATH_PARTS = {
    "about",
    "about-us",
    "contact",
    "contact-us",
    "home",
    "homepage",
    "latest",
    "latest-news",
    "lien-he",
    "trang-chu",
}

ARTICLE_FIELDS = {
    "title": {
        "mode": "first",
        "extractors": [
            {"selector": "meta[property='og:title']", "attr": "content"},
            {"selector": "meta[name='twitter:title']", "attr": "content"},
            {"selector": "h1.entry-title"},
            {"selector": "h1.post-title"},
            {"selector": "h1.article-title"},
            {"selector": "h1"},
            {"selector": "title"},
        ],
    },
    "summary": {
        "mode": "first",
        "extractors": [
            {"selector": "meta[property='og:description']", "attr": "content"},
            {"selector": "meta[name='description']", "attr": "content"},
            {"selector": ".entry-summary"},
            {"selector": ".article-summary"},
            {"selector": ".excerpt"},
        ],
    },
    "published_at": {
        "mode": "first",
        "extractors": [
            {"selector": "meta[property='article:published_time']", "attr": "content"},
            {"selector": "meta[name='pubdate']", "attr": "content"},
            {"selector": "meta[name='publishdate']", "attr": "content"},
            {"selector": "time[datetime]", "attr": "datetime"},
            {"selector": "time"},
            {"selector": ".published"},
            {"selector": ".post-date"},
            {"selector": ".entry-date"},
            {"selector": ".date"},
        ],
    },
    "author": {
        "mode": "first",
        "extractors": [
            {"selector": "meta[name='author']", "attr": "content"},
            {"selector": ".author"},
            {"selector": ".byline"},
        ],
    },
    "content": {
        "mode": "join",
        "separator": "\n\n",
        "extractors": [
            {"selector": "article .entry-content p"},
            {"selector": "article .post-content p"},
            {"selector": "article .article-content p"},
            {"selector": "article .td-post-content p"},
            {"selector": ".entry-content p"},
            {"selector": ".post-content p"},
            {"selector": ".article-content p"},
            {"selector": ".news-detail p"},
            {"selector": ".detail-content p"},
            {"selector": ".single-content p"},
            {"selector": ".td-post-content p"},
            {"selector": "article p"},
            {"selector": "main p"},
        ],
    },
    "images": {
        "mode": "list",
        "extractors": [
            {"selector": "meta[property='og:image']", "attr": "content"},
            {"selector": "article img[src]", "attr": "src"},
            {"selector": ".entry-content img[src]", "attr": "src"},
            {"selector": ".post-content img[src]", "attr": "src"},
        ],
    },
}

REMOVE_SELECTORS = [
    "script",
    "style",
    "noscript",
    "iframe",
    "form",
    "nav",
    "header",
    "footer",
    ".advertisement",
    ".ads",
    ".ad",
    ".share",
    ".social-share",
    ".related-posts",
    ".related",
    ".comments",
]


def _load_ready_sources(input_path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(input_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Source file is not valid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError("Source file must be a JSON array.")
    return [item for item in data if isinstance(item, dict)]


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _netloc(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower().split("@")[-1].split(":")[0]


def _related_domain(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return left == right or left.endswith(f".{right}") or right.endswith(f".{left}")


def _is_external_redirect(original_url: str, final_url: str) -> bool:
    original_domain = canonical_domain(original_url)
    final_domain = canonical_domain(final_url)
    return not _related_domain(original_domain, final_domain)


def _clean_url(raw_url: str, base_url: str) -> str | None:
    absolute = urljoin(base_url, raw_url.strip())
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    path = parsed.path or "/"
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", parsed.query, ""))


def _has_bad_extension(path: str) -> bool:
    lowered_path = path.lower()
    return any(lowered_path.endswith(extension) for extension in BAD_EXTENSIONS)


def _path_parts(path: str) -> set[str]:
    return {part.lower() for part in path.split("/") if part}


def _is_candidate_article_url(url: str, listing_url: str, allowed_domains: set[str]) -> bool:
    parsed = urlparse(url)
    if not parsed.netloc or parsed.scheme not in {"http", "https"}:
        return False

    link_domain = canonical_domain(url)
    if not any(_related_domain(link_domain, allowed_domain) for allowed_domain in allowed_domains):
        return False

    listing = urlparse(listing_url)
    if parsed.netloc == listing.netloc and parsed.path.rstrip("/") == listing.path.rstrip("/"):
        return False

    if _has_bad_extension(parsed.path):
        return False

    parts = _path_parts(parsed.path)
    if parts & BAD_PATH_PARTS:
        return False

    return bool(parsed.path.strip("/") or parsed.query)


def _score_article_url(url: str, anchor_text: str) -> int:
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parsed.query.lower()
    parts = [part for part in path.split("/") if part]
    score = 0

    if re.search(r"/20\d{2}/\d{1,2}/\d{1,2}", path):
        score += 9
    if re.search(r"(?:^|[-_/])\d{4,}(?:[-_/]|$|\.html?)", path) or re.search(r"(?:id|p)=\d{3,}", query):
        score += 6
    if path.endswith((".html", ".htm")):
        score += 5
    if len(parts) >= 2:
        score += 3
    if any(word in path for word in ("article", "detail", "news", "post", "story")):
        score += 3
    if parts and len(parts[-1]) >= 12 and "-" in parts[-1]:
        score += 3
    if 20 <= len(anchor_text.strip()) <= 180:
        score += 2
    if len(parts) <= 1 and not query:
        score -= 3

    return score


def _collect_article_candidates(html: str, listing_url: str, allowed_domains: set[str]) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    candidates_by_url: dict[str, dict[str, Any]] = {}

    for node in soup.select("a[href]"):
        url = _clean_url(str(node.get("href") or ""), listing_url)
        if not url or not _is_candidate_article_url(url, listing_url, allowed_domains):
            continue
        anchor_text = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        score = _score_article_url(url, anchor_text)
        if score < 2:
            continue
        previous = candidates_by_url.get(url)
        if previous and previous["score"] >= score:
            continue
        candidates_by_url[url] = {"url": url, "text": anchor_text, "score": score}

    return sorted(candidates_by_url.values(), key=lambda item: item["score"], reverse=True)


def _build_source_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for source in list_sources():
        domain = canonical_domain(source.get("target_url"))
        if domain:
            index.setdefault(domain, source)
    return index


def _display_name(source: dict[str, Any], domain: str) -> str:
    raw_name = str(source.get("name") or "").strip()
    if not raw_name or raw_name.lower() in GENERIC_NAMES:
        return domain
    return raw_name


def _infer_article_pattern(allowed_netlocs: set[str], top_candidate_url: str | None = None) -> str:
    host_pattern = "|".join(re.escape(host) for host in sorted(host for host in allowed_netlocs if host))
    if not host_pattern:
        host_pattern = r"[^/]+"

    # Default generic pattern if we cannot infer a stronger structure.
    fallback = rf"^https?://(?:{host_pattern})/.+"
    if not top_candidate_url:
        return fallback

    parsed = urlparse(top_candidate_url)
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return fallback

    if re.search(r"/20\d{2}/\d{1,2}/\d{1,2}", parsed.path):
        return rf"^https?://(?:{host_pattern})/.+/20\d{{2}}/\d{{1,2}}/\d{{1,2}}/(?:[^/?#]+)(?:/)?(?:[?#].*)?$"

    last_part = parts[-1]
    if re.fullmatch(r"\d{4,}", last_part):
        return rf"^https?://(?:{host_pattern})/.+/\d{{4,}}(?:/)?(?:[?#].*)?$"

    if "-" in last_part and len(last_part) >= 12:
        return rf"^https?://(?:{host_pattern})/.+/.{{12,}}(?:/)?(?:[?#].*)?$"

    return fallback


def _build_config(
    label: str,
    listing_url: str,
    allowed_netlocs: set[str],
    timeout_seconds: int,
    top_candidate_url: str | None = None,
) -> dict[str, Any]:
    return {
        "site_name": label,
        "base_url": _origin(listing_url),
        "allowed_domains": sorted(allowed_netlocs),
        "listing_urls": [listing_url],
        "article_link_selectors": ARTICLE_LINK_SELECTORS,
        "article_link_pattern": _infer_article_pattern(allowed_netlocs, top_candidate_url=top_candidate_url),
        "article_link_exclude_patterns": ARTICLE_LINK_EXCLUDES,
        "fields": ARTICLE_FIELDS,
        "remove_selectors": REMOVE_SELECTORS,
        "request": {
            "timeout_seconds": timeout_seconds,
            "delay_seconds": 0.2,
            "respect_robots_txt": False,
            "headers": DEFAULT_HEADERS,
        },
        "auto_generated": True,
    }


def _relative_or_absolute(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_report(report_path: Path, payload: dict[str, Any]) -> Path:
    _write_json(report_path, payload)
    csv_path = report_path.with_suffix(".csv")
    rows = payload.get("items") or []
    fieldnames = [
        "index",
        "name",
        "base_url",
        "priority",
        "run_status",
        "source_key",
        "preset_path",
        "article_count",
        "success_count",
        "duration_seconds",
        "output_path",
        "candidate_count",
        "error",
    ]
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return csv_path


def auto_preset_missing_sources(
    input_path: Path,
    output_dir: Path | None = None,
    report_path: Path | None = None,
    max_pages: int | None = 1,
    max_articles: int | None = 2,
    workers: int = 2,
    timeout_seconds: int = 10,
    active_only: bool = True,
    limit: int | None = None,
    priority: str | None = None,
    allow_external_redirect: bool = False,
) -> dict[str, Any]:
    ready_sources = _load_ready_sources(input_path)
    output_root = output_dir or resolve_path("output/auto")
    report_file = report_path or output_root / "auto_preset_report.json"
    source_index = _build_source_index()
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    priority_filter = priority.strip().upper() if priority else None

    items: list[dict[str, Any]] = []
    summary = {
        "total": len(ready_sources),
        "created": 0,
        "crawl_completed": 0,
        "crawl_empty": 0,
        "failed": 0,
        "skipped_existing_preset": 0,
        "skipped_inactive": 0,
        "skipped_priority": 0,
        "skipped_external_redirect": 0,
        "skipped_no_article_links": 0,
    }
    processed_missing = 0

    for index, ready_source in enumerate(ready_sources, start=1):
        source_status = str(ready_source.get("status") or "").strip().upper()
        base_url = str(ready_source.get("base_url") or "").strip()
        source_priority = str(ready_source.get("priority") or "").strip().upper()
        domain = canonical_domain(base_url)
        row: dict[str, Any] = {
            "index": index,
            "name": str(ready_source.get("name") or "").strip(),
            "base_url": base_url,
            "status": source_status,
            "priority": source_priority,
            "domain": domain,
            "run_status": "",
            "source_key": "",
            "preset_path": "",
            "listing_url": "",
            "candidate_count": 0,
            "top_candidate_url": "",
            "article_count": 0,
            "success_count": 0,
            "duration_seconds": 0,
            "output_path": "",
            "error": "",
        }

        if active_only and source_status != "ACTIVE":
            row["run_status"] = "skipped_inactive"
            summary["skipped_inactive"] += 1
            items.append(row)
            continue

        if priority_filter and source_priority != priority_filter:
            row["run_status"] = "skipped_priority"
            summary["skipped_priority"] += 1
            items.append(row)
            continue

        if domain in source_index:
            row["run_status"] = "skipped_existing_preset"
            row["source_key"] = source_index[domain].get("source_key", "")
            summary["skipped_existing_preset"] += 1
            items.append(row)
            continue

        if limit is not None and processed_missing >= limit:
            row["run_status"] = "skipped_limit"
            items.append(row)
            continue
        processed_missing += 1

        try:
            response = session.get(base_url, timeout=timeout_seconds, allow_redirects=True)
            response.raise_for_status()
        except Exception as exc:
            row["run_status"] = "failed"
            row["error"] = describe_exception(exc)
            summary["failed"] += 1
            items.append(row)
            continue

        listing_url = response.url
        row["listing_url"] = listing_url
        if not allow_external_redirect and _is_external_redirect(base_url, listing_url):
            row["run_status"] = "skipped_external_redirect"
            row["error"] = f"Redirected to unrelated domain: {listing_url}"
            summary["skipped_external_redirect"] += 1
            items.append(row)
            continue

        final_domain = canonical_domain(listing_url)
        allowed_domains = {domain, final_domain}
        allowed_netlocs = {_netloc(base_url), _netloc(listing_url)}
        candidates = _collect_article_candidates(response.text, listing_url, allowed_domains)
        row["candidate_count"] = len(candidates)
        if candidates:
            row["top_candidate_url"] = candidates[0]["url"]
            allowed_netlocs.add(_netloc(candidates[0]["url"]))
        if not candidates:
            row["run_status"] = "skipped_no_article_links"
            summary["skipped_no_article_links"] += 1
            items.append(row)
            continue

        label = _display_name(ready_source, final_domain)
        source_key = slugify(final_domain.replace(".", "-"))
        preset_filename = f"auto_{source_key}.json"
        preset_path = CONFIGS_DIR / preset_filename
        relative_preset_path = preset_path.relative_to(PROJECT_ROOT).as_posix()
        config = _build_config(
            label=label,
            listing_url=listing_url,
            allowed_netlocs=allowed_netlocs,
            timeout_seconds=timeout_seconds,
            top_candidate_url=candidates[0]["url"] if candidates else None,
        )
        config["auto_source"] = {
            "original_name": row["name"],
            "original_base_url": base_url,
            "top_candidate_url": row["top_candidate_url"],
            "candidate_count": len(candidates),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_json(preset_path, config)

        output_path = output_root / f"{index:03d}_{source_key}.json"
        source_record = save_source(
            {
                "source_key": source_key,
                "name": label,
                "target_url": listing_url,
                "target_mode": "listing",
                "preset_path": relative_preset_path,
                "output": _relative_or_absolute(output_path),
                "max_pages": max_pages,
                "max_articles": max_articles,
                "workers": workers,
                "notes": f"Auto-generated from {base_url}. Top candidate: {row['top_candidate_url']}",
            }
        )
        source_index[domain] = source_record
        source_index[final_domain] = source_record

        row["source_key"] = source_key
        row["preset_path"] = relative_preset_path
        row["output_path"] = _relative_or_absolute(output_path)
        summary["created"] += 1

        try:
            payload = run_crawl(
                config=config,
                output_path=output_path,
                max_pages=max_pages,
                max_articles=max_articles,
                workers=workers,
                target_url=listing_url,
                target_mode="listing",
                include_target_warnings=False,
                save_output=True,
            )
        except Exception as exc:
            row["run_status"] = "failed"
            row["error"] = describe_exception(exc)
            summary["failed"] += 1
            items.append(row)
            continue

        row["article_count"] = payload.get("article_count", 0)
        row["success_count"] = payload.get("success_count", 0)
        row["duration_seconds"] = payload.get("duration_seconds", 0)
        if row["success_count"]:
            row["run_status"] = "crawl_completed"
            summary["crawl_completed"] += 1
        else:
            row["run_status"] = "crawl_empty"
            row["error"] = "Preset was created, but crawl did not return successful articles."
            summary["crawl_empty"] += 1
        items.append(row)

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_path": str(input_path),
        "active_only": active_only,
        "priority": priority_filter,
        "max_pages": max_pages,
        "max_articles": max_articles,
        "workers": workers,
        "timeout_seconds": timeout_seconds,
        "summary": summary,
        "items": items,
    }
    csv_path = _write_report(report_file, report)
    report["report_path"] = _relative_or_absolute(report_file)
    report["csv_report_path"] = _relative_or_absolute(csv_path)
    _write_json(report_file, report)
    return report


def _build_unique_preset_path(domain_key: str) -> Path:
    base_name = f"auto_{slugify(domain_key)}"
    candidate = CONFIGS_DIR / f"{base_name}.json"
    if not candidate.exists():
        return candidate

    suffix = 2
    while True:
        candidate = CONFIGS_DIR / f"{base_name}_{suffix}.json"
        if not candidate.exists():
            return candidate
        suffix += 1


def _probe_runtime_config(config: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    runtime = copy.deepcopy(config)
    request = runtime.setdefault("request", {})
    existing_timeout = request.get("timeout_seconds")
    try:
        if existing_timeout is not None:
            request["timeout_seconds"] = max(3, min(int(existing_timeout), timeout_seconds))
        else:
            request["timeout_seconds"] = timeout_seconds
    except (TypeError, ValueError):
        request["timeout_seconds"] = timeout_seconds
    request["delay_seconds"] = 0
    return runtime


def _url_article_quality(url: str) -> int:
    parsed = urlparse(url)
    parts = [part.lower() for part in parsed.path.split("/") if part]
    if not parts:
        return -3

    if any(part in NON_ARTICLE_PATH_PARTS for part in parts):
        return -2

    score = 0
    if re.search(r"/20\d{2}/\d{1,2}/\d{1,2}", parsed.path):
        score += 4
    if re.search(r"(?:^|[-_/])\d{4,}(?:[-_/]|$)", parsed.path):
        score += 3
    if len(parts) >= 2:
        score += 2
    if len(parts[-1]) >= 10:
        score += 1
    return score


def find_compatible_preset_for_source(
    target_url: str,
    timeout_seconds: int = 8,
    max_pages: int = 1,
    max_articles: int = 1,
    workers: int = 1,
) -> dict[str, Any] | None:
    best_match: dict[str, Any] | None = None
    probe_output_path = resolve_path("output/_probe_source_match.json")

    for preset in list_presets():
        preset_path = str(preset.get("path") or "").strip()
        if not preset_path:
            continue
        try:
            config = json.loads(resolve_preset_path(preset_path).read_text(encoding="utf-8"))
        except Exception:
            continue

        try:
            payload = run_crawl(
                config=_probe_runtime_config(config, timeout_seconds=timeout_seconds),
                output_path=probe_output_path,
                max_pages=max_pages,
                max_articles=max_articles,
                workers=workers,
                save_output=False,
                target_url=target_url,
                target_mode="listing",
                include_target_warnings=False,
            )
        except Exception:
            continue

        success_count = int(payload.get("success_count") or 0)
        article_count = int(payload.get("article_count") or 0)
        warning_count = len(payload.get("warnings") or [])
        if success_count <= 0:
            continue

        url_scores: list[int] = []
        for article in payload.get("articles") or []:
            url = str(article.get("url") or "")
            if not url:
                continue
            url_scores.append(_url_article_quality(url))

        if not url_scores:
            continue

        structured_count = sum(1 for score in url_scores if score >= 2)
        bad_count = sum(1 for score in url_scores if score < 0)
        total_urls = len(url_scores)
        # Reject presets that mostly return non-article pages such as home/contact/listing.
        if structured_count == 0 or (bad_count * 3) >= total_urls:
            continue

        score = (success_count * 100) + (article_count * 10) - warning_count + (structured_count * 5) - (bad_count * 8)
        candidate = {
            "preset_path": preset_path,
            "preset_label": str(preset.get("label") or preset_path),
            "score": score,
            "success_count": success_count,
            "article_count": article_count,
            "warnings": payload.get("warnings") or [],
            "structured_count": structured_count,
            "bad_count": bad_count,
        }
        if not best_match or candidate["score"] > best_match["score"]:
            best_match = candidate

    return best_match


def create_auto_preset_for_source(
    target_url: str,
    source_name: str,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    response = session.get(target_url, timeout=timeout_seconds, allow_redirects=True)
    response.raise_for_status()

    listing_url = response.url
    original_domain = canonical_domain(target_url)
    final_domain = canonical_domain(listing_url)
    allowed_domains = {original_domain, final_domain}
    allowed_netlocs = {_netloc(target_url), _netloc(listing_url)}
    candidates = _collect_article_candidates(response.text, listing_url, allowed_domains)
    if candidates:
        allowed_netlocs.add(_netloc(candidates[0]["url"]))

    label = _display_name({"name": source_name}, final_domain)
    domain_key = final_domain.replace(".", "-") or slugify(source_name)
    preset_path = _build_unique_preset_path(domain_key)
    relative_preset_path = preset_path.relative_to(PROJECT_ROOT).as_posix()

    config = _build_config(
        label=label,
        listing_url=listing_url,
        allowed_netlocs=allowed_netlocs,
        timeout_seconds=timeout_seconds,
        top_candidate_url=candidates[0]["url"] if candidates else None,
    )
    config["auto_source"] = {
        "original_name": source_name,
        "original_base_url": target_url,
        "top_candidate_url": candidates[0]["url"] if candidates else "",
        "candidate_count": len(candidates),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(preset_path, config)

    return {
        "preset_path": relative_preset_path,
        "preset_label": label,
        "listing_url": listing_url,
        "candidate_count": len(candidates),
        "top_candidate_url": candidates[0]["url"] if candidates else "",
        "created": True,
    }


def resolve_preset_for_new_source(
    target_url: str,
    source_name: str,
    timeout_seconds: int = 8,
) -> dict[str, Any]:
    compatible = find_compatible_preset_for_source(
        target_url=target_url,
        timeout_seconds=timeout_seconds,
        max_pages=1,
        max_articles=5,
        workers=1,
    )
    if compatible:
        compatible["created"] = False
        compatible["resolution"] = "matched_existing"
        return compatible

    created = create_auto_preset_for_source(
        target_url=target_url,
        source_name=source_name,
        timeout_seconds=max(timeout_seconds, 8),
    )
    created["resolution"] = "created_new"
    return created
