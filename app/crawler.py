from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import cloudscraper
except Exception:  # pragma: no cover - optional dependency
    cloudscraper = None


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def extract_text(node: Any) -> str:
    return normalize_text(node.get_text(" ", strip=True))


def describe_exception(exc: Exception) -> str:
    message = str(exc)
    lowered = message.lower()

    if "nameresolutionerror" in lowered or "failed to resolve" in lowered or "getaddrinfo failed" in lowered:
        return "Khong resolve duoc domain cua website. Co the DNS dang loi hoac domain chua co ban ghi A/AAAA."
    if "ssLError".lower() in lowered or "certificate verify failed" in lowered:
        return "Khong the ket noi SSL toi website nay."
    if "read timed out" in lowered or "connect timeout" in lowered:
        return "Ket noi toi website bi timeout."
    if "cloudflare challenge" in lowered or "just a moment" in lowered:
        return "Website dang bat Cloudflare challenge/CAPTCHA, crawler HTTP thong thuong khong the truy cap duoc."

    return message


@dataclass
class FetchSettings:
    timeout: int
    delay_seconds: float
    user_agent: str
    verify_ssl: bool
    respect_robots_txt: bool
    headers: dict[str, str]


class MediaCrawler:
    def __init__(self, config: dict[str, Any], output_path: Path) -> None:
        self.config = config
        self.output_path = output_path
        self.site_name = config.get("site_name", "media-site")
        self.base_url = config["base_url"]
        self.allowed_domains = set(config.get("allowed_domains") or [urlparse(self.base_url).netloc])
        self.hash_link_prefix = str(config.get("hash_link_prefix") or "").strip()
        self.link_selectors = config["article_link_selectors"]
        self.article_link_pattern = re.compile(config.get("article_link_pattern", ".*"))
        self.article_link_exclude_patterns = [
            re.compile(pattern) for pattern in config.get("article_link_exclude_patterns", [])
        ]
        self.article_link_order = str(config.get("article_link_order") or "as_found").strip().lower()
        article_link_id_pattern = config.get("article_link_id_pattern")
        self.article_link_id_pattern = re.compile(article_link_id_pattern) if article_link_id_pattern else None
        self.article_link_regexes = [
            re.compile(pattern) for pattern in config.get("article_link_regexes", [])
        ]
        self.fields = config["fields"]
        self.remove_selectors = config.get("remove_selectors", [])
        request_settings = config.get("request", {})
        self.fetch_settings = FetchSettings(
            timeout=int(request_settings.get("timeout_seconds", 20)),
            delay_seconds=float(request_settings.get("delay_seconds", 0)),
            user_agent=request_settings.get(
                "user_agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            ),
            verify_ssl=bool(request_settings.get("verify_ssl", True)),
            respect_robots_txt=bool(request_settings.get("respect_robots_txt", False)),
            headers={str(key): str(value) for key, value in request_settings.get("headers", {}).items()},
        )
        self.session = self._build_session()
        self.robot_parsers: dict[str, RobotFileParser] = {}
        self.run_warnings: list[str] = []
        self.api_config = config.get("api") or {}

    @staticmethod
    def _looks_like_cloudflare_block(status_code: int, body: str, headers: dict[str, str] | None = None) -> bool:
        if status_code != 403:
            return False
        lowered = (body or "").lower()
        header_blob = " ".join(f"{k}:{v}" for k, v in (headers or {}).items()).lower()
        signals = (
            "just a moment",
            "cloudflare",
            "cf-browser-verification",
            "attention required",
            "captcha",
            "cf-ray",
            "server:cloudflare",
        )
        return any(signal in lowered for signal in signals) or any(signal in header_blob for signal in signals)

    def _fetch_html_with_cloudscraper(self, url: str) -> requests.Response:
        if cloudscraper is None:
            raise requests.HTTPError(
                f"Cloudflare challenge detected but cloudscraper is not installed for URL: {url}"
            )

        scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
        scraper.headers.update({"User-Agent": self.fetch_settings.user_agent})
        scraper.headers.update(self.fetch_settings.headers)
        response = scraper.get(
            url,
            timeout=self.fetch_settings.timeout,
            verify=self.fetch_settings.verify_ssl,
        )
        if self._looks_like_cloudflare_block(response.status_code, response.text, dict(response.headers)):
            raise PermissionError(f"Cloudflare challenge still blocks access: {url}")
        return response

    def _build_session(self) -> requests.Session:
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.headers.update({"User-Agent": self.fetch_settings.user_agent})
        session.headers.update(self.fetch_settings.headers)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _load_robot_parser(self, url: str) -> RobotFileParser:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        if robots_url in self.robot_parsers:
            return self.robot_parsers[robots_url]

        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            response = self.session.get(
                robots_url,
                timeout=self.fetch_settings.timeout,
                verify=self.fetch_settings.verify_ssl,
            )
            if response.ok:
                parser.parse(response.text.splitlines())
            else:
                parser.parse([])
        except requests.RequestException:
            parser.parse([])

        self.robot_parsers[robots_url] = parser
        return parser

    def _can_fetch(self, url: str) -> bool:
        if not self.fetch_settings.respect_robots_txt:
            return True
        parser = self._load_robot_parser(url)
        return parser.can_fetch(self.fetch_settings.user_agent, url)

    def fetch_html(self, url: str) -> str:
        if not self._can_fetch(url):
            raise PermissionError(f"Blocked by robots.txt: {url}")

        response = self.session.get(
            url,
            timeout=self.fetch_settings.timeout,
            verify=self.fetch_settings.verify_ssl,
        )
        if response.status_code == 403 and (
            "window.location.href" in response.text
            or "server_name_session" in response.headers.get("Set-Cookie", "")
        ):
            time.sleep(max(self.fetch_settings.delay_seconds, 0.5))
            response = self.session.get(
                url,
                timeout=self.fetch_settings.timeout,
                verify=self.fetch_settings.verify_ssl,
            )

        if self._looks_like_cloudflare_block(response.status_code, response.text, dict(response.headers)):
            response = self._fetch_html_with_cloudscraper(url)

        response.raise_for_status()
        declared_encoding = (response.encoding or "").lower()
        if declared_encoding in {"", "iso-8859-1", "latin-1"} and response.apparent_encoding:
            response.encoding = response.apparent_encoding
        if self.fetch_settings.delay_seconds > 0:
            time.sleep(self.fetch_settings.delay_seconds)
        return response.text

    def fetch_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        method: str = "GET",
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_method = method.upper()
        if request_method == "POST":
            response = self.session.post(
                url,
                params=params,
                json=json_body,
                timeout=self.fetch_settings.timeout,
                verify=self.fetch_settings.verify_ssl,
            )
        else:
            response = self.session.get(
                url,
                params=params,
                timeout=self.fetch_settings.timeout,
                verify=self.fetch_settings.verify_ssl,
            )
        response.raise_for_status()
        if self.fetch_settings.delay_seconds > 0:
            time.sleep(self.fetch_settings.delay_seconds)
        return response.json()

    def build_listing_urls(self, max_pages: int | None = None) -> list[str]:
        urls: list[str] = []
        for url in self.config.get("listing_urls", []):
            urls.append(url)

        pagination = self.config.get("pagination")
        if not pagination:
            return urls

        start_page = int(pagination.get("start_page", 2))
        end_page = int(pagination.get("end_page", start_page))
        if max_pages is not None:
            generated_page_count = max(max_pages - len(urls), 0)
            end_page = min(end_page, start_page + generated_page_count - 1) if generated_page_count else start_page - 1

        url_template = pagination["url_template"]
        for page in range(start_page, end_page + 1):
            urls.append(url_template.format(page=page))
        return urls

    def is_allowed_article_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc and parsed.netloc not in self.allowed_domains:
            return False
        if not self.article_link_pattern.search(url):
            return False
        return not any(pattern.search(url) for pattern in self.article_link_exclude_patterns)

    def extract_listing_links(self, listing_url: str) -> list[str]:
        html = self.fetch_html(listing_url)
        parser = "xml" if listing_url.lower().endswith(".xml") or html.lstrip().startswith("<?xml") else "lxml"
        soup = BeautifulSoup(html, parser)
        links: list[str] = []
        seen: set[str] = set()

        def add_candidate(raw_url: str) -> None:
            if not raw_url:
                return
            candidate = raw_url.strip().strip("\"'")
            candidate = candidate.replace("\\/", "/")
            if candidate.startswith("#") and self.hash_link_prefix:
                candidate = f"{self.hash_link_prefix}{candidate.lstrip('#')}"
            else:
                candidate = candidate.split("#", 1)[0]
            absolute_url = urljoin(listing_url, candidate)
            if absolute_url in seen:
                return
            if not self.is_allowed_article_url(absolute_url):
                return
            seen.add(absolute_url)
            links.append(absolute_url)

        for selector in self.link_selectors:
            for node in soup.select(selector):
                href = node.get("href")
                if not href:
                    continue
                add_candidate(href)

        for pattern in self.article_link_regexes:
            for match in pattern.finditer(html):
                add_candidate(match.group(1) if match.groups() else match.group(0))

        if self.article_link_order == "id_desc":
            links.sort(key=self._article_link_sort_key, reverse=True)
        return links

    def _article_link_sort_key(self, url: str) -> int:
        if self.article_link_id_pattern:
            match = self.article_link_id_pattern.search(url)
            if match:
                try:
                    return int(match.group(1))
                except (TypeError, ValueError):
                    return -1

        fallback = re.search(r"/(\d+)(?:/|$)", url)
        if fallback:
            try:
                return int(fallback.group(1))
            except (TypeError, ValueError):
                return -1
        return -1

    def _format_api_value(self, value: Any, page: int) -> Any:
        if isinstance(value, str):
            return value.format(page=page)
        if isinstance(value, list):
            return [self._format_api_value(item, page=page) for item in value]
        if isinstance(value, dict):
            return {key: self._format_api_value(item, page=page) for key, item in value.items()}
        return value

    def _format_api_params(self, params: dict[str, Any], page: int) -> dict[str, Any]:
        return self._format_api_value(params, page=page)

    def _json_values_at_path(self, data: Any, path: str | None) -> list[Any]:
        if not path:
            return [data]

        parts = [part for part in path.split(".") if part]

        def walk(value: Any, remaining_parts: list[str]) -> list[Any]:
            if value is None:
                return []
            if not remaining_parts:
                if isinstance(value, list):
                    return value
                return [value]

            part = remaining_parts[0]
            rest = remaining_parts[1:]
            if isinstance(value, list):
                values: list[Any] = []
                if part.isdigit():
                    index = int(part)
                    if 0 <= index < len(value):
                        values.extend(walk(value[index], rest))
                    return values
                for item in value:
                    values.extend(walk(item, remaining_parts))
                return values

            if isinstance(value, dict):
                return walk(value.get(part), rest)

            return []

        return walk(data, parts)

    def _stringify_json_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            if re.search(r"<[a-zA-Z][^>]*>", value):
                return extract_text(BeautifulSoup(value, "lxml"))
            return normalize_text(value)
        if isinstance(value, (int, float, bool)):
            return normalize_text(str(value))
        if isinstance(value, dict):
            for key in ("text", "name", "url"):
                if value.get(key):
                    return normalize_text(str(value[key]))
            return normalize_text(json.dumps(value, ensure_ascii=False))
        return normalize_text(str(value))

    def _template_from_json_item(self, template: str, item: dict[str, Any]) -> str:
        def replace_placeholder(match: re.Match[str]) -> str:
            values = self._json_values_at_path(item, match.group(1))
            return self._stringify_json_value(values[0]) if values else ""

        return re.sub(r"\{([^{}]+)\}", replace_placeholder, template)

    def extract_api_listing_links(self, max_pages: int | None = None, max_articles: int | None = None) -> list[str]:
        listing_config = self.api_config.get("listing") or {}
        if not listing_config:
            return []

        url = listing_config["url"]
        method = str(listing_config.get("method") or "GET").upper()
        params = listing_config.get("params", {})
        json_body = listing_config.get("json") or listing_config.get("body")
        items_path = listing_config.get("items_path", "items")
        link_field = listing_config.get("link_field", "url")
        link_template = listing_config.get("link_template")
        page_count = max_pages or int(listing_config.get("default_pages", 1))
        links: list[str] = []
        seen: set[str] = set()

        for page in range(1, page_count + 1):
            payload = self.fetch_json(
                url,
                params=self._format_api_params(params, page=page),
                method=method,
                json_body=self._format_api_value(json_body, page=page) if isinstance(json_body, dict) else None,
            )
            items = self._json_values_at_path(payload, items_path)
            for item in items:
                if not isinstance(item, dict):
                    continue
                if link_template:
                    article_url = self._template_from_json_item(link_template, item)
                else:
                    article_url = self._stringify_json_value(item.get(link_field))
                if not article_url:
                    continue
                article_url = urljoin(self.base_url, article_url)
                if article_url in seen:
                    continue
                if not self.is_allowed_article_url(article_url):
                    continue
                seen.add(article_url)
                links.append(article_url)
                if max_articles and len(links) >= max_articles:
                    return links
        return links

    def _clean_article_soup(self, soup: BeautifulSoup) -> BeautifulSoup:
        for selector in self.remove_selectors:
            for node in soup.select(selector):
                node.decompose()
        return soup

    def _extract_from_spec(self, soup: BeautifulSoup, spec: dict[str, Any], url: str) -> list[str]:
        selector = spec["selector"]
        attr = spec.get("attr")
        mode = spec.get("mode", "text")

        if selector == "$url":
            return [url]

        nodes = soup.select(selector)
        values: list[str] = []
        for node in nodes:
            if attr:
                value = normalize_text(node.get(attr, ""))
            elif mode == "html":
                value = str(node)
            else:
                value = extract_text(node)
            if value:
                values.append(value)

        return values

    def extract_field(self, soup: BeautifulSoup, field_name: str, url: str) -> Any:
        config = self.fields[field_name]
        mode = config.get("mode", "first")
        separator = config.get("separator", "\n\n")
        extractors = config["extractors"]

        values: list[str] = []
        for spec in extractors:
            current_values = self._extract_from_spec(soup, spec, url)
            if mode == "first" and current_values:
                return current_values[0]
            values.extend(current_values)

        if mode == "first":
            return None
        if mode == "join":
            deduped_values = list(dict.fromkeys(values))
            return separator.join(deduped_values) if deduped_values else None
        if mode == "list":
            return list(dict.fromkeys(values))
        return values

    def _api_article_id(self, article_url: str) -> str:
        article_config = self.api_config.get("article") or {}
        id_pattern = article_config.get("id_pattern")
        if not id_pattern:
            return article_url.rstrip("/").rsplit("/", 1)[-1]
        match = re.search(id_pattern, article_url)
        if not match:
            raise ValueError(f"Could not extract API article id from {article_url}")
        return match.group(1)

    def extract_json_field(self, data: dict[str, Any], field_name: str, article_url: str) -> Any:
        json_fields = self.api_config.get("json_fields") or {}
        config = json_fields[field_name]
        mode = config.get("mode", "first")
        separator = config.get("separator", "\n\n")
        extractors = config["extractors"]
        values: list[str] = []

        for spec in extractors:
            if spec.get("selector") == "$url" or spec.get("path") == "$url":
                current_values = [article_url]
            elif spec.get("template"):
                current_values = [self._template_from_json_item(spec["template"], data)]
            else:
                current_values = [
                    self._stringify_json_value(value)
                    for value in self._json_values_at_path(data, spec.get("path"))
                ]
            current_values = [value for value in current_values if value]
            if mode == "first" and current_values:
                return current_values[0]
            values.extend(current_values)

        if mode == "first":
            return None
        if mode == "join":
            deduped_values = list(dict.fromkeys(values))
            return separator.join(deduped_values) if deduped_values else None
        if mode == "list":
            return list(dict.fromkeys(values))
        return values

    def extract_api_article(self, article_url: str) -> dict[str, Any]:
        article_config = self.api_config.get("article") or {}
        article_id = self._api_article_id(article_url)
        api_url = article_config["url_template"].format(id=article_id)
        payload = self.fetch_json(api_url)
        root_values = self._json_values_at_path(payload, article_config.get("root_path"))
        data = root_values[0] if root_values else payload
        if not isinstance(data, dict):
            raise ValueError(f"API article payload is not an object: {api_url}")

        article: dict[str, Any] = {"url": article_url, "site_name": self.site_name}
        for field_name in self.fields:
            article[field_name] = self.extract_json_field(data, field_name, article_url)
        return article

    def extract_article(self, article_url: str) -> dict[str, Any]:
        if self.api_config.get("article"):
            return self.extract_api_article(article_url)

        html = self.fetch_html(article_url)
        soup = self._clean_article_soup(BeautifulSoup(html, "lxml"))
        article: dict[str, Any] = {"url": article_url, "site_name": self.site_name}
        for field_name in self.fields:
            article[field_name] = self.extract_field(soup, field_name, article_url)
        return article

    def crawl(
        self,
        max_pages: int | None = None,
        max_articles: int | None = None,
        workers: int = 4,
        article_link_filter: Callable[[str], bool] | None = None,
    ) -> list[dict[str, Any]]:
        self.run_warnings = []
        article_links: list[str] = []
        if self.api_config.get("listing"):
            try:
                article_links = self.extract_api_listing_links(max_pages=max_pages, max_articles=max_articles)
                if article_link_filter:
                    article_links = [url for url in article_links if article_link_filter(url)]
                    if max_articles:
                        article_links = article_links[:max_articles]
            except Exception as exc:
                listing_url = str((self.api_config.get("listing") or {}).get("url") or self.base_url)
                self.run_warnings.append(f"Khong doc duoc API danh sach {listing_url}: {describe_exception(exc)}")
        else:
            listing_urls = self.build_listing_urls(max_pages=max_pages)

            seen_links: set[str] = set()
            for listing_url in listing_urls:
                try:
                    listing_links = self.extract_listing_links(listing_url)
                except Exception as exc:
                    self.run_warnings.append(f"Khong doc duoc trang danh sach {listing_url}: {describe_exception(exc)}")
                    continue

                for article_url in listing_links:
                    if article_link_filter and not article_link_filter(article_url):
                        continue
                    if article_url in seen_links:
                        continue
                    seen_links.add(article_url)
                    article_links.append(article_url)
                    if max_articles and len(article_links) >= max_articles:
                        break
                if max_articles and len(article_links) >= max_articles:
                    break

        results_by_url: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=max(workers, 1)) as executor:
            futures = {executor.submit(self.extract_article, url): url for url in article_links}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    results_by_url[url] = future.result()
                except Exception as exc:
                    results_by_url[url] = {
                        "url": url,
                        "site_name": self.site_name,
                        "error": describe_exception(exc),
                    }

        results = [results_by_url[url] for url in article_links if url in results_by_url]
        return results

    def build_payload(self, articles: list[dict[str, Any]]) -> dict[str, Any]:
        success_count = sum(1 for article in articles if "error" not in article)
        return {
            "site_name": self.site_name,
            "article_count": len(articles),
            "success_count": success_count,
            "error_count": len(articles) - success_count,
            "warnings": list(self.run_warnings),
            "articles": articles,
        }

    def save(self, articles: list[dict[str, Any]]) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.build_payload(articles)
        with self.output_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)


def load_crawler(config_path: Path, output_path: Path) -> MediaCrawler:
    return MediaCrawler(config=read_json(config_path), output_path=output_path)
