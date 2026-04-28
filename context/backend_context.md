# Backend Context

## Main Backend Files

- [app/web.py](F:/pyro/Crack/app/web.py)
  - Flask routes and UI workflow.
  - Source/preset CRUD.
  - Crawl run handling.
  - Crawl-all background job and polling payload.
- [app/service.py](F:/pyro/Crack/app/service.py)
  - Runtime config preparation.
  - Source/config/output path resolution.
  - `run_crawl(...)`.
- [app/crawler.py](F:/pyro/Crack/app/crawler.py)
  - Core crawler engine.
  - Listing link extraction, article extraction, retries, Cloudflare handling.
- [app/catalog.py](F:/pyro/Crack/app/catalog.py)
  - Source/preset file storage.
- [app/translator.py](F:/pyro/Crack/app/translator.py)
  - Google web translate display-only translation cache.

## Key Runtime Behaviors

- `DATA_ROOT` defaults to project root unless `APP_DATA_DIR` is set.
- Seed behavior copies bundled `configs/` and `sources/` into runtime data dirs if runtime dirs are empty.
- `prepare_runtime_config(...)` normally overrides `listing_urls` with `target_url` for listing runs.
- Special case was added:
  - if preset has `preserve_listing_urls: true`, runtime keeps preset `listing_urls`.
  - This is needed for multi-category sources such as `www.btv.com.kh`.

## Crawler Notes

- Link extraction:
  - Default attribute is `href`.
  - New support exists for `article_link_attribute`, e.g. `page-link`.
- `MediaCrawler.crawl(...)` now supports `progress_callback` so single-source jobs can report per-article completion.
- Regex extraction:
  - `_extract_from_spec(...)` supports optional `regex`.
  - `$url` extractors also support `regex`, useful for deriving dates from article URLs.
- JSON/API extraction:
  - Root JSON arrays are valid `items_path: ""` listing payloads.
  - Firestore REST value wrappers (`stringValue`, `timestampValue`, `mapValue`, `arrayValue`, etc.) are normalized when extracting JSON fields.
  - JSON responses force UTF-8 when the server omits a charset, preventing Khmer mojibake from Firestore.
- Listing card extraction:
  - Optional `listing_articles.enabled` mode exists for sources where detail pages are blocked but listing cards are readable.
  - Used by ThmeyThmey and Kampuchea News.
  - `allow_external_article_urls: true` lets aggregator presets keep original external article URLs instead of rejecting non-base domains.

## Translation Notes

- Display translation uses Google web translate with a local file cache.
- Translation requests use POST with retries to reduce failures on longer text.
- Article translation is per-field: if one field fails, successful translated fields still display and failed fields keep their original text.
- If Google returns 429/rate-limit, translation stops for the current batch and the UI shows a short retry-later message instead of the raw Google `/sorry` URL.

## Crawl-All Job Model

- Job state lives in memory in `CRAWL_JOBS`.
- Each job includes:
  - progress counters
  - `articles` for live UI append
  - output path
- Single-source crawl now also uses this background job system.
- For single-source runs:
  - `source_count = 1`
  - UI polls `/api/crawl-jobs/<job_id>`
  - articles are tagged with `source_key` and `source_name` before live display and final output save
  - saved payload `site_name` is normalized to the source name instead of trusting preset `site_name`
  - job state also tracks `total_articles` and `completed_articles`
  - final result is reloaded from saved output JSON when job completes
- `run_all_sources_crawl_job(...)`:
  - translates newly found articles for display
  - appends them to job state during execution
  - final page reload still happens at completion for full JSON/pagination state

## Current Dedicated Kampuchea Thmey Presets

- `configs/kampucheathmey_kh.json`
  - Source: `sources/kampucheathmey-1776587652.json`
  - Listing: `https://www.kampucheathmey.com/`
  - Article URL regex: same-domain category slug plus numeric ID.
  - Content selector: `#mvp-content-main p`.
- `configs/kampucheathmey_en.json`
  - Source: `sources/en-kampucheathmey-com.json`
  - Listing: `https://en.kampucheathmey.com/`
  - Uses the same MVP WordPress structure.
- Do not remove generic `header` in these presets because the post date is inside `#mvp-post-head`.

## Current Blogspot Presets

- `configs/khmercircle_blogspot.json`
  - Source: `sources/khmercircle-blogspot-com.json`
  - Listing links: `h3.post-title a[href]`, `.post-title a[href]`
  - Article regex: `/YYYY/MM/slug.html`
  - Content selector: `.post-body p`, then `.post-body`
- `configs/khmerization_blogspot.json`
  - Source: `sources/khmerization-blogspot-com.json`
  - Same Blogspot extraction pattern.
  - Some newest posts are only YouTube iframes, so text content can be empty without being an extraction error.
- Do not remove `.widget` in Blogspot presets; Blogger wraps the main post list/article in widgets.

## Current MFAIC Preset

- `configs/mfaic_gov_kh_media.json`
  - Source: `sources/mfaic-gov-kh.json`
  - Listing: `https://www.mfaic.gov.kh/Media/News`
  - Link regex accepts `/Media/View/<slug>` and `/en/media/view/<slug>`.
  - Extraction uses `.viewpost-title`, `.viewpost-date`, `.viewpost-content`, `.viewpost img`.
  - Needs browser-like request headers to avoid the site's request rejection page.

## Filtering Logic In Crawl-All

- Keep article only if:
  - not a non-article URL/page
  - has parsable `published_at`, or date can be inferred from URL
  - within recent 24h window
- `parse_article_timestamp(...)` supports English month display dates such as `28-April-2026`.

## Source Management Behavior

- Source delete in UI removes the source JSON file.
- Bulk source delete exists.
- Blocked-source records are stored separately in `blocked_sources/*.json`.
- Export endpoints:
  - single source JSON
  - zip of all sources
  - `sources_review.json`
