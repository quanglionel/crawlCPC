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
- Regex extraction:
  - `_extract_from_spec(...)` supports optional `regex`.
- Listing card extraction:
  - Optional `listing_articles.enabled` mode exists for sources where detail pages are blocked but listing cards are readable.
  - Used by ThmeyThmey.

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
  - final result is reloaded from saved output JSON when job completes
- `run_all_sources_crawl_job(...)`:
  - translates newly found articles for display
  - appends them to job state during execution
  - final page reload still happens at completion for full JSON/pagination state

## Filtering Logic In Crawl-All

- Keep article only if:
  - not a non-article URL/page
  - has parsable `published_at`, or date can be inferred from URL
  - within recent 24h window

## Source Management Behavior

- Source delete in UI removes the source JSON file.
- Bulk source delete exists.
- Blocked-source records are stored separately in `blocked_sources/*.json`.
- Export endpoints:
  - single source JSON
  - zip of all sources
  - `sources_review.json`
