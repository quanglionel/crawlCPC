from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.service import DATA_ROOT


BLOCKED_SOURCES_DIR = DATA_ROOT / "blocked_sources"


_BLOCKED_CACHE_SIGNATURE: tuple[tuple[str, int, int], ...] | None = None
_BLOCKED_CACHE_DATA: list[dict[str, Any]] | None = None


def _clone_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in records]


def _dir_signature(directory: Path, pattern: str) -> tuple[tuple[str, int, int], ...]:
    items: list[tuple[str, int, int]] = []
    for path in sorted(directory.glob(pattern)):
        try:
            stat = path.stat()
        except OSError:
            continue
        items.append((path.name, int(stat.st_mtime_ns), int(stat.st_size)))
    return tuple(items)


def _invalidate_cache() -> None:
    global _BLOCKED_CACHE_SIGNATURE, _BLOCKED_CACHE_DATA
    _BLOCKED_CACHE_SIGNATURE = None
    _BLOCKED_CACHE_DATA = None


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-_")
    return slug or "item"


def ensure_blocked_sources_dir() -> None:
    BLOCKED_SOURCES_DIR.mkdir(parents=True, exist_ok=True)


def blocked_source_file_path(record_key: str) -> Path:
    ensure_blocked_sources_dir()
    return BLOCKED_SOURCES_DIR / f"{slugify(record_key)}.json"


def normalize_blocked_source_record(data: dict[str, Any], record_key: str | None = None) -> dict[str, Any]:
    key = slugify(record_key or str(data.get("record_key") or data.get("source_key") or data.get("name") or "blocked"))
    return {
        "record_key": key,
        "source_key": str(data.get("source_key") or "").strip(),
        "name": str(data.get("name") or key).strip(),
        "target_url": str(data.get("target_url") or "").strip(),
        "reason": str(data.get("reason") or "").strip(),
        "last_checked_at": str(data.get("last_checked_at") or "").strip(),
        "notes": str(data.get("notes") or "").strip(),
    }


def list_blocked_sources() -> list[dict[str, Any]]:
    global _BLOCKED_CACHE_SIGNATURE, _BLOCKED_CACHE_DATA
    ensure_blocked_sources_dir()
    signature = _dir_signature(BLOCKED_SOURCES_DIR, "*.json")
    if _BLOCKED_CACHE_SIGNATURE == signature and _BLOCKED_CACHE_DATA is not None:
        return _clone_records(_BLOCKED_CACHE_DATA)

    records: list[dict[str, Any]] = []
    for path in sorted(BLOCKED_SOURCES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        records.append(normalize_blocked_source_record(data, record_key=path.stem))
    records.sort(key=lambda item: (item["name"].lower(), item["record_key"]))
    _BLOCKED_CACHE_SIGNATURE = signature
    _BLOCKED_CACHE_DATA = _clone_records(records)
    return records


def save_blocked_source(record_data: dict[str, Any], original_record_key: str | None = None) -> dict[str, Any]:
    record = normalize_blocked_source_record(record_data)
    destination = blocked_source_file_path(record["record_key"])
    if original_record_key and slugify(original_record_key) != record["record_key"]:
        previous = blocked_source_file_path(original_record_key)
        if previous.exists():
            previous.unlink()
    destination.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    _invalidate_cache()
    return record


def delete_blocked_source(record_key: str) -> None:
    path = blocked_source_file_path(record_key)
    if path.exists():
        path.unlink()
        _invalidate_cache()
