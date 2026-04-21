from __future__ import annotations

import os
from typing import Any

import requests


DEFAULT_SUMMARY_PROMPT = """Bạn là trợ lý biên tập tin tức.

Hãy tóm tắt bài viết theo mẫu sau:

1. Tiêu đề ngắn:
2. Ý chính:
3. Bối cảnh:
4. Các bên liên quan:
5. Mốc thời gian / địa điểm:
6. Nhận định ngắn:

Yêu cầu:
- Viết bằng tiếng Việt.
- Ưu tiên sự kiện, số liệu, tên riêng.
- Không bịa thêm thông tin ngoài bài.

Bài viết:
Nguồn: {source_name}
Ngày đăng: {published_at}
URL: {url}
Tiêu đề: {title}
Tóm tắt gốc: {summary}
Nội dung:
{content}
"""

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OPENAI_RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"
GROQ_CHAT_COMPLETIONS_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
MAX_ARTICLE_CHARS = 60000


class SummarizerError(RuntimeError):
    pass


def normalize_article_payload(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "source_name": str(payload.get("source_name") or ""),
        "published_at": str(payload.get("published_at") or ""),
        "url": str(payload.get("url") or ""),
        "title": str(payload.get("title") or ""),
        "summary": str(payload.get("summary") or ""),
        "content": str(payload.get("content") or "")[:MAX_ARTICLE_CHARS],
    }


def render_summary_prompt(prompt_template: str, article: dict[str, str]) -> str:
    prompt = prompt_template or DEFAULT_SUMMARY_PROMPT
    for key, value in article.items():
        prompt = prompt.replace("{" + key + "}", value)

    has_article_placeholder = any("{" + key + "}" in (prompt_template or "") for key in article)
    if has_article_placeholder:
        return prompt

    article_block = "\n\n---\nBài viết cần tóm tắt:\n"
    article_block += f"Nguồn: {article['source_name']}\n"
    article_block += f"Ngày đăng: {article['published_at']}\n"
    article_block += f"URL: {article['url']}\n"
    article_block += f"Tiêu đề: {article['title']}\n"
    article_block += f"Tóm tắt gốc: {article['summary']}\n"
    article_block += f"Nội dung:\n{article['content']}"
    return prompt + article_block


def summarize_with_gemini(article_payload: dict[str, Any], prompt_template: str) -> dict[str, str]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SummarizerError("Chưa cấu hình GEMINI_API_KEY trên server.")

    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"
    article = normalize_article_payload(article_payload)
    prompt = render_summary_prompt(prompt_template, article)
    endpoint = GEMINI_ENDPOINT.format(model=model)

    try:
        response = requests.post(
            endpoint,
            params={"key": api_key},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "topP": 0.9,
                    "maxOutputTokens": 2048,
                },
            },
            timeout=90,
        )
    except requests.RequestException as exc:
        raise SummarizerError(f"Không gọi được Gemini: {exc}") from exc

    if response.status_code >= 400:
        try:
            error_payload = response.json()
            message = error_payload.get("error", {}).get("message") or response.text
        except ValueError:
            message = response.text
        raise SummarizerError(f"Gemini trả lỗi {response.status_code}: {message}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise SummarizerError("Gemini trả về phản hồi không phải JSON.") from exc

    parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "\n".join(str(part.get("text") or "") for part in parts).strip()
    if not text:
        raise SummarizerError("Gemini không trả về nội dung tóm tắt.")

    return {"summary": text, "model": model}


def _extract_openai_text(payload: dict[str, Any]) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"]).strip()

    output = payload.get("output") or []
    chunks: list[str] = []
    for item in output:
        for content in item.get("content") or []:
            if content.get("type") in {"output_text", "text"}:
                chunks.append(str(content.get("text") or ""))

    return "\n".join(chunk for chunk in chunks if chunk).strip()


def summarize_with_openai(article_payload: dict[str, Any], prompt_template: str) -> dict[str, str]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SummarizerError("Chưa cấu hình OPENAI_API_KEY trên server.")

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    article = normalize_article_payload(article_payload)
    prompt = render_summary_prompt(prompt_template, article)

    try:
        response = requests.post(
            OPENAI_RESPONSES_ENDPOINT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "input": prompt,
                "max_output_tokens": 2048,
            },
            timeout=90,
        )
    except requests.RequestException as exc:
        raise SummarizerError(f"Không gọi được OpenAI: {exc}") from exc

    if response.status_code >= 400:
        try:
            error_payload = response.json()
            message = error_payload.get("error", {}).get("message") or response.text
        except ValueError:
            message = response.text
        raise SummarizerError(f"OpenAI trả lỗi {response.status_code}: {message}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise SummarizerError("OpenAI trả về phản hồi không phải JSON.") from exc

    text = _extract_openai_text(payload)
    if not text:
        raise SummarizerError("OpenAI không trả về nội dung tóm tắt.")

    return {"summary": text, "model": model}


def _extract_chat_completion_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""

    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, list):
        chunks = [str(part.get("text") or "") for part in content if isinstance(part, dict)]
        return "\n".join(chunk for chunk in chunks if chunk).strip()
    return str(content).strip()


def summarize_with_groq(article_payload: dict[str, Any], prompt_template: str) -> dict[str, str]:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise SummarizerError("Chưa cấu hình GROQ_API_KEY trên server.")

    model = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant").strip() or "llama-3.1-8b-instant"
    article = normalize_article_payload(article_payload)
    prompt = render_summary_prompt(prompt_template, article)

    try:
        response = requests.post(
            GROQ_CHAT_COMPLETIONS_ENDPOINT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Bạn là trợ lý biên tập tin tức. Trả lời bằng tiếng Việt.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 2048,
            },
            timeout=90,
        )
    except requests.RequestException as exc:
        raise SummarizerError(f"Không gọi được Groq: {exc}") from exc

    if response.status_code >= 400:
        try:
            error_payload = response.json()
            message = error_payload.get("error", {}).get("message") or response.text
        except ValueError:
            message = response.text
        raise SummarizerError(f"Groq trả lỗi {response.status_code}: {message}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise SummarizerError("Groq trả về phản hồi không phải JSON.") from exc

    text = _extract_chat_completion_text(payload)
    if not text:
        raise SummarizerError("Groq không trả về nội dung tóm tắt.")

    return {"summary": text, "model": model}


def summarize_article(article_payload: dict[str, Any], prompt_template: str) -> dict[str, str]:
    provider = os.environ.get("SUMMARY_PROVIDER", "auto").strip().lower() or "auto"
    if provider == "groq":
        result = summarize_with_groq(article_payload, prompt_template)
        return {**result, "provider": "groq"}
    if provider == "openai":
        result = summarize_with_openai(article_payload, prompt_template)
        return {**result, "provider": "openai"}
    if provider == "gemini":
        result = summarize_with_gemini(article_payload, prompt_template)
        return {**result, "provider": "gemini"}
    if provider != "auto":
        raise SummarizerError("SUMMARY_PROVIDER chỉ hỗ trợ: auto, groq, openai, gemini.")

    if os.environ.get("GROQ_API_KEY", "").strip():
        result = summarize_with_groq(article_payload, prompt_template)
        return {**result, "provider": "groq"}
    if os.environ.get("OPENAI_API_KEY", "").strip():
        result = summarize_with_openai(article_payload, prompt_template)
        return {**result, "provider": "openai"}
    if os.environ.get("GEMINI_API_KEY", "").strip():
        result = summarize_with_gemini(article_payload, prompt_template)
        return {**result, "provider": "gemini"}

    raise SummarizerError("Chưa cấu hình GROQ_API_KEY, OPENAI_API_KEY hoặc GEMINI_API_KEY trên server.")
