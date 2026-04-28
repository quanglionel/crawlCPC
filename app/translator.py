from __future__ import annotations

import hashlib
import json
import re
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import requests

from app.service import PROJECT_ROOT


CACHE_DIR = PROJECT_ROOT / "cache" / "translations"
DISPLAY_CONTENT_LIMIT = 420
MAX_TRANSLATE_CHARS = 1800
TRANSLATE_ENDPOINT = "https://translate.googleapis.com/translate_a/single"


class TranslatorError(RuntimeError):
    pass


class TranslatorRateLimitError(TranslatorError):
    pass


def normalize_translation_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def cache_key(text: str, target_language: str) -> str:
    digest = hashlib.sha256(f"{target_language}\0{text}".encode("utf-8")).hexdigest()
    return digest


def read_cache(text: str, target_language: str) -> str | None:
    path = CACHE_DIR / f"{cache_key(text, target_language)}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    translated = payload.get("translated")
    return str(translated) if translated else None


def write_cache(text: str, translated: str, target_language: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{cache_key(text, target_language)}.json"
    payload = {
        "target_language": target_language,
        "source": text,
        "translated": translated,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def split_text(text: str, max_chars: int = MAX_TRANSLATE_CHARS) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current = ""
    for part in re.split(r"(\n+)", text):
        if len(current) + len(part) <= max_chars:
            current += part
            continue
        if current.strip():
            chunks.append(current)
            current = ""
        while len(part) > max_chars:
            chunks.append(part[:max_chars])
            part = part[max_chars:]
        current = part

    if current.strip():
        chunks.append(current)
    return chunks


class GoogleWebTranslator:
    def __init__(self, target_language: str = "vi", timeout_seconds: int = 20, max_retries: int = 2) -> None:
        self.target_language = target_language
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.unavailable_reason: str | None = None
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            }
        )

    def translate(self, text: str) -> str:
        if self.unavailable_reason:
            raise TranslatorRateLimitError(self.unavailable_reason)

        clean_text = text.strip()
        if not clean_text:
            return text

        cached = read_cache(clean_text, self.target_language)
        if cached is not None:
            return cached

        translated = "".join(self._translate_chunk(chunk) for chunk in split_text(clean_text))
        translated = normalize_translation_text(translated)
        if not translated:
            raise TranslatorError("Dịch vụ dịch trả về kết quả rỗng.")
        write_cache(clean_text, translated, self.target_language)
        return translated

    def _translate_chunk(self, text: str) -> str:
        payload = None
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.post(
                    TRANSLATE_ENDPOINT,
                    params={
                        "client": "gtx",
                        "sl": "auto",
                        "tl": self.target_language,
                        "dt": "t",
                    },
                    data={"q": text},
                    timeout=self.timeout_seconds,
                )
                if response.status_code == 429 or "/sorry/" in response.url:
                    self.unavailable_reason = "Google Translate tam thoi gioi han request (429). Hay thu lai sau."
                    raise TranslatorRateLimitError(self.unavailable_reason)
                response.raise_for_status()
                payload = response.json()
                break
            except TranslatorRateLimitError:
                raise
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(0.5 * (attempt + 1))

        if payload is None:
            raise TranslatorError(f"Dich vu dich loi: {last_error}") from last_error

        try:
            segments = payload[0]
            return "".join(segment[0] for segment in segments if segment and segment[0])
        except (IndexError, TypeError) as exc:
            raise TranslatorError("Không đọc được phản hồi từ dịch vụ dịch.") from exc


def clipped_content(value: Any) -> tuple[str | None, bool]:
    if not value:
        return None, False
    text = str(value)
    if len(text) <= DISPLAY_CONTENT_LIMIT:
        return text, False
    return text[:DISPLAY_CONTENT_LIMIT], True


def set_original_display_fields(article: dict[str, Any]) -> None:
    content_preview, is_truncated = clipped_content(article.get("content"))
    article["display_title"] = article.get("title") or article.get("url")
    article["display_summary"] = article.get("summary")
    article["display_published_at"] = article.get("published_at")
    article["display_content"] = content_preview
    article["display_content_truncated"] = is_truncated
    article["display_language"] = "original"


def translate_article_for_display(article: dict[str, Any], translator: GoogleWebTranslator) -> None:
    set_original_display_fields(article)
    article["display_language"] = "original"

    fields = {
        "display_title": article.get("title"),
        "display_summary": article.get("summary"),
        "display_published_at": article.get("published_at"),
    }
    content_preview, is_truncated = clipped_content(article.get("content"))
    fields["display_content"] = content_preview
    article["display_content_truncated"] = is_truncated

    translated_count = 0
    field_errors: list[str] = []
    for display_field, source_value in fields.items():
        if not source_value:
            continue
        try:
            article[display_field] = translator.translate(str(source_value))
            translated_count += 1
        except TranslatorRateLimitError as exc:
            field_errors.append(str(exc))
            break
        except Exception as exc:
            field_errors.append(f"{display_field}: khong dich duoc")

    if translated_count:
        article["display_language"] = "vi"
    if field_errors:
        article["translation_error"] = "; ".join(dict.fromkeys(field_errors))


def prepare_result_for_display(result: dict[str, Any], translate_to_vi: bool = False) -> dict[str, Any]:
    display_result = deepcopy(result)
    articles = display_result.get("articles") or []
    for article in articles:
        set_original_display_fields(article)

    display_result["translation"] = {
        "enabled": bool(translate_to_vi),
        "target_language": "vi",
        "provider": "google-web",
        "article_success_count": 0,
        "article_error_count": 0,
    }

    if not translate_to_vi:
        return display_result

    translator = GoogleWebTranslator(target_language="vi")
    translation_warnings: list[str] = []
    for index, article in enumerate(articles, start=1):
        if article.get("error"):
            continue
        if translator.unavailable_reason:
            set_original_display_fields(article)
            article["translation_error"] = translator.unavailable_reason
            display_result["translation"]["article_error_count"] += 1
            continue
        try:
            translate_article_for_display(article, translator)
            if article.get("display_language") == "vi":
                display_result["translation"]["article_success_count"] += 1
            else:
                display_result["translation"]["article_error_count"] += 1
                translation_warnings.append(f"Khong dich duoc bai #{index}: khong co truong nao dich thanh cong.")
            if article.get("translation_error"):
                translation_warnings.append(f"Dich mot phan bai #{index}: {article['translation_error']}")
        except Exception as exc:
            set_original_display_fields(article)
            article["display_language"] = "original"
            article["translation_error"] = "Khong dich duoc bai nay."
            display_result["translation"]["article_error_count"] += 1
            if translator.unavailable_reason:
                translation_warnings.append(translator.unavailable_reason)
            translation_warnings.append(f"Không dịch được bài #{index}: {exc}")

    if translation_warnings:
        display_result.setdefault("warnings", [])
        display_result["warnings"].extend(translation_warnings)

    return display_result
