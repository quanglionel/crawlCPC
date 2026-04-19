from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.service import CONFIGS_DIR, PROJECT_ROOT, discover_config_paths, load_config_from_json, read_config_text


SOURCES_DIR = PROJECT_ROOT / "sources"


_SOURCES_CACHE_SIGNATURE: tuple[tuple[str, int, int], ...] | None = None
_SOURCES_CACHE_DATA: list[dict[str, Any]] | None = None
_PRESETS_CACHE_SIGNATURE: tuple[tuple[str, int, int], ...] | None = None
_PRESETS_CACHE_DATA: list[dict[str, Any]] | None = None
_PRESET_LOOKUP_CACHE_SIGNATURE: tuple[tuple[str, int, int], ...] | None = None
_PRESET_LOOKUP_CACHE_DATA: dict[str, str] | None = None


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


def _invalidate_sources_cache() -> None:
    global _SOURCES_CACHE_SIGNATURE, _SOURCES_CACHE_DATA
    _SOURCES_CACHE_SIGNATURE = None
    _SOURCES_CACHE_DATA = None


def _invalidate_presets_cache() -> None:
    global _PRESETS_CACHE_SIGNATURE, _PRESETS_CACHE_DATA, _PRESET_LOOKUP_CACHE_SIGNATURE, _PRESET_LOOKUP_CACHE_DATA
    _PRESETS_CACHE_SIGNATURE = None
    _PRESETS_CACHE_DATA = None
    _PRESET_LOOKUP_CACHE_SIGNATURE = None
    _PRESET_LOOKUP_CACHE_DATA = None


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-_")
    return slug or "item"


def ensure_sources_dir() -> None:
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)


def resolve_preset_path(relative_path: str) -> Path:
    candidate = (PROJECT_ROOT / relative_path).resolve()
    configs_root = CONFIGS_DIR.resolve()
    if not str(candidate).startswith(str(configs_root)):
        raise ValueError("Preset path must stay inside the configs directory.")
    if candidate.suffix.lower() != ".json":
        raise ValueError("Preset path must point to a JSON file.")
    return candidate


def source_file_path(source_key: str) -> Path:
    ensure_sources_dir()
    return SOURCES_DIR / f"{slugify(source_key)}.json"


def normalize_source_record(data: dict[str, Any], source_key: str | None = None) -> dict[str, Any]:
    key = slugify(source_key or str(data.get("source_key") or data.get("name") or "source"))
    return {
        "source_key": key,
        "name": str(data.get("name") or key).strip(),
        "target_url": str(data.get("target_url") or "").strip(),
        "target_mode": str(data.get("target_mode") or "auto").strip() or "auto",
        "preset_path": str(data.get("preset_path") or "").strip(),
        "output": str(data.get("output") or f"output/{key}.json").strip(),
        "max_pages": data.get("max_pages"),
        "max_articles": data.get("max_articles"),
        "workers": data.get("workers") if data.get("workers") is not None else 4,
        "notes": str(data.get("notes") or "").strip(),
    }


def list_sources() -> list[dict[str, Any]]:
    global _SOURCES_CACHE_SIGNATURE, _SOURCES_CACHE_DATA
    ensure_sources_dir()
    signature = _dir_signature(SOURCES_DIR, "*.json")
    if _SOURCES_CACHE_SIGNATURE == signature and _SOURCES_CACHE_DATA is not None:
        return _clone_records(_SOURCES_CACHE_DATA)

    sources: list[dict[str, Any]] = []
    for path in sorted(SOURCES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        sources.append(normalize_source_record(data, source_key=path.stem))
    sources.sort(key=lambda item: (item["name"].lower(), item["source_key"]))
    _SOURCES_CACHE_SIGNATURE = signature
    _SOURCES_CACHE_DATA = _clone_records(sources)
    return sources


def save_source(source_data: dict[str, Any], original_source_key: str | None = None) -> dict[str, Any]:
    source = normalize_source_record(source_data)
    destination = source_file_path(source["source_key"])
    if original_source_key and slugify(original_source_key) != source["source_key"]:
        previous = source_file_path(original_source_key)
        if previous.exists():
            previous.unlink()
    destination.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")
    _invalidate_sources_cache()
    return source


def delete_source(source_key: str) -> None:
    path = source_file_path(source_key)
    if path.exists():
        path.unlink()
        _invalidate_sources_cache()


def list_presets() -> list[dict[str, Any]]:
    global _PRESETS_CACHE_SIGNATURE, _PRESETS_CACHE_DATA
    signature = _dir_signature(CONFIGS_DIR, "*.json")
    if _PRESETS_CACHE_SIGNATURE == signature and _PRESETS_CACHE_DATA is not None:
        return _clone_records(_PRESETS_CACHE_DATA)

    presets: list[dict[str, Any]] = []
    for path in discover_config_paths():
        relative_path = path.relative_to(PROJECT_ROOT).as_posix()
        try:
            config = load_config_from_json(read_config_text(path))
        except json.JSONDecodeError:
            config = {}
        label = str(config.get("site_name") or path.stem.replace("_", " ")).strip()
        presets.append(
            {
                "path": relative_path,
                "key": path.stem,
                "label": label,
                "site_name": str(config.get("site_name") or "").strip(),
            }
        )
    presets.sort(key=lambda item: (item["label"].lower(), item["path"]))
    _PRESETS_CACHE_SIGNATURE = signature
    _PRESETS_CACHE_DATA = _clone_records(presets)
    return presets


def build_preset_lookup(presets: list[dict[str, Any]] | None = None) -> dict[str, str]:
    global _PRESET_LOOKUP_CACHE_SIGNATURE, _PRESET_LOOKUP_CACHE_DATA
    signature = _dir_signature(CONFIGS_DIR, "*.json")
    if _PRESET_LOOKUP_CACHE_SIGNATURE == signature and _PRESET_LOOKUP_CACHE_DATA is not None:
        return dict(_PRESET_LOOKUP_CACHE_DATA)

    items = presets or list_presets()
    lookup = {item["path"]: read_config_text(resolve_preset_path(item["path"])) for item in items}
    _PRESET_LOOKUP_CACHE_SIGNATURE = signature
    _PRESET_LOOKUP_CACHE_DATA = dict(lookup)
    return lookup


def save_preset(config_json: str, preset_key: str, original_preset_path: str | None = None) -> str:
    key = slugify(preset_key)
    destination = CONFIGS_DIR / f"{key}.json"
    destination.write_text(config_json.strip() + "\n", encoding="utf-8")
    relative_path = destination.relative_to(PROJECT_ROOT).as_posix()
    if original_preset_path and original_preset_path != relative_path:
        previous = resolve_preset_path(original_preset_path)
        if previous.exists():
            previous.unlink()
    _invalidate_presets_cache()
    return relative_path


def delete_preset(relative_path: str) -> None:
    path = resolve_preset_path(relative_path)
    if path.exists():
        path.unlink()
        _invalidate_presets_cache()


def sources_using_preset(preset_path: str) -> list[dict[str, Any]]:
    return [source for source in list_sources() if source.get("preset_path") == preset_path]


def repoint_sources_to_preset(previous_preset_path: str, new_preset_path: str) -> None:
    if previous_preset_path == new_preset_path:
        return
    for source in list_sources():
        if source.get("preset_path") != previous_preset_path:
            continue
        source["preset_path"] = new_preset_path
        save_source(source, original_source_key=source["source_key"])
