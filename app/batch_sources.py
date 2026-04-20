from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.catalog import list_sources, resolve_preset_path, slugify
from app.crawler import read_json
from app.service import DATA_ROOT, resolve_path, run_crawl


DOMAIN_ALIASES = {
    "cen.com.kh": "cen-news.com",
    "vodhotnews.com": "vodkhmer.news",
}


def canonical_domain(raw_url: str | None) -> str:
    if not raw_url:
        return ""

    value = str(raw_url).strip()
    if not value:
        return ""
    if "://" not in value:
        value = f"https://{value}"

    parsed = urlparse(value)
    domain = parsed.netloc.lower().split("@")[-1].split(":")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    return DOMAIN_ALIASES.get(domain, domain)


def _relative_or_absolute(path: Path) -> str:
    try:
        return path.relative_to(DATA_ROOT).as_posix()
    except ValueError:
        return str(path)


def _load_ready_sources(input_path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(input_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Source file is not valid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError("Source file must be a JSON array.")

    return [item for item in data if isinstance(item, dict)]


def _build_source_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for source in list_sources():
        domains = {canonical_domain(source.get("target_url"))}
        try:
            preset = read_json(resolve_preset_path(source.get("preset_path", "")))
        except (OSError, ValueError, json.JSONDecodeError):
            preset = {}

        domains.add(canonical_domain(preset.get("base_url")))
        for listing_url in preset.get("listing_urls") or []:
            domains.add(canonical_domain(str(listing_url)))

        for domain in sorted(domain for domain in domains if domain):
            index.setdefault(domain, source)

    return index


def _find_catalog_source(ready_source: dict[str, Any], source_index: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    for field_name in ("base_url", "rss_url"):
        domain = canonical_domain(ready_source.get(field_name))
        if domain and domain in source_index:
            return source_index[domain], domain
    return None, canonical_domain(ready_source.get("base_url"))


def _serialize_warnings(warnings: Any) -> str:
    if not isinstance(warnings, list):
        return ""
    return " | ".join(str(item) for item in warnings if item)


def _write_report(report_path: Path, payload: dict[str, Any]) -> Path:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = report_path.with_suffix(".csv")
    rows = payload.get("items") or []
    fieldnames = [
        "index",
        "name",
        "base_url",
        "source_status",
        "priority",
        "matched_source_key",
        "matched_source_name",
        "run_status",
        "article_count",
        "success_count",
        "duration_seconds",
        "output_path",
        "error",
        "warnings",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})

    return csv_path


def run_ready_sources_batch(
    input_path: Path,
    output_dir: Path | None = None,
    report_path: Path | None = None,
    max_pages: int | None = 1,
    max_articles: int | None = 2,
    workers: int | None = None,
    active_only: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    ready_sources = _load_ready_sources(input_path)
    if limit is not None:
        ready_sources = ready_sources[: max(limit, 0)]

    output_root = output_dir or resolve_path("output/batch")
    report_file = report_path or output_root / "sources_web_ready_report.json"
    source_index = _build_source_index()
    items: list[dict[str, Any]] = []
    summary = {
        "total": len(ready_sources),
        "completed": 0,
        "failed": 0,
        "skipped_inactive": 0,
        "skipped_no_preset": 0,
    }

    for index, ready_source in enumerate(ready_sources, start=1):
        source_status = str(ready_source.get("status") or "").strip().upper()
        row: dict[str, Any] = {
            "index": index,
            "name": str(ready_source.get("name") or "").strip(),
            "base_url": str(ready_source.get("base_url") or "").strip(),
            "rss_url": str(ready_source.get("rss_url") or "").strip(),
            "source_status": source_status,
            "priority": str(ready_source.get("priority") or "").strip(),
            "is_primary": ready_source.get("is_primary"),
            "notes": str(ready_source.get("notes") or "").strip(),
            "matched_domain": canonical_domain(str(ready_source.get("base_url") or "")),
            "matched_source_key": "",
            "matched_source_name": "",
            "matched_preset_path": "",
            "run_status": "",
            "article_count": 0,
            "success_count": 0,
            "duration_seconds": 0,
            "output_path": "",
            "error": "",
            "warnings": "",
        }

        if active_only and source_status != "ACTIVE":
            row["run_status"] = "skipped_inactive"
            summary["skipped_inactive"] += 1
            items.append(row)
            continue

        catalog_source, matched_domain = _find_catalog_source(ready_source, source_index)
        row["matched_domain"] = matched_domain
        if not catalog_source:
            row["run_status"] = "skipped_no_preset"
            summary["skipped_no_preset"] += 1
            items.append(row)
            continue

        row["matched_source_key"] = catalog_source["source_key"]
        row["matched_source_name"] = catalog_source["name"]
        row["matched_preset_path"] = catalog_source["preset_path"]
        output_path = output_root / f"{index:03d}_{slugify(catalog_source['source_key'])}.json"
        row["output_path"] = _relative_or_absolute(output_path)

        try:
            config = read_json(resolve_preset_path(catalog_source["preset_path"]))
            payload = run_crawl(
                config=config,
                output_path=output_path,
                max_pages=max_pages if max_pages is not None else catalog_source.get("max_pages"),
                max_articles=max_articles if max_articles is not None else catalog_source.get("max_articles"),
                workers=workers if workers is not None else int(catalog_source.get("workers") or 4),
                target_url=catalog_source.get("target_url") or None,
                target_mode=catalog_source.get("target_mode") or "auto",
                include_target_warnings=False,
                save_output=True,
            )
        except Exception as exc:
            row["run_status"] = "failed"
            row["error"] = str(exc)
            summary["failed"] += 1
            items.append(row)
            continue

        row["run_status"] = "completed"
        row["article_count"] = payload.get("article_count", 0)
        row["success_count"] = payload.get("success_count", 0)
        row["duration_seconds"] = payload.get("duration_seconds", 0)
        row["warnings"] = _serialize_warnings(payload.get("warnings"))
        summary["completed"] += 1
        items.append(row)

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_path": str(input_path),
        "active_only": active_only,
        "max_pages": max_pages,
        "max_articles": max_articles,
        "workers": workers,
        "summary": summary,
        "items": items,
    }
    csv_path = _write_report(report_file, report)
    report["report_path"] = _relative_or_absolute(report_file)
    report["csv_report_path"] = _relative_or_absolute(csv_path)
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
