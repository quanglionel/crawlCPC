# AI Context

Use `context/` as the first stop when resuming work on this repo.

## How To Resume Fast

1. Read [README](F:/pyro/Crack/context/README.md).
2. Read [project_context.md](F:/pyro/Crack/context/project_context.md).
3. Read [ai_context.md](F:/pyro/Crack/context/ai_context.md) for recent memory.
4. Only then inspect repo files if the context docs are not enough.

## Current High-Value Memory

- Project type: Flask web UI + JSON-configured crawler for Cambodian/news sites.
- Runtime data model:
  - `sources/*.json`: saved source definitions.
  - `configs/*.json`: crawler presets/selectors.
  - `output/*.json`: crawl results.
- Important working behavior:
  - Deleting a source in the UI removes its `sources/*.json` file, so it does not come back on rebuild/wakeup.
  - Render persistent disk may be off, so bundled `sources/` matters.
- Translation:
  - Summary feature was removed.
  - Display translation to Vietnamese is a live toggle in the UI.
  - Results are precomputed with both original and translated display fields so toggle is instant.
- Crawl-all:
  - Supports all sources, selected sources, or one source.
  - Live polling now appends articles as they arrive instead of waiting for full completion.
- Source review:
  - UI supports export of source review JSON and bulk delete with checkboxes.

## Recent Source-Specific Decisions

- `thmeythmey.com`:
  - Detail pages are blocked by Cloudflare.
  - Source uses homepage/listing-card extraction fallback.
- `bayontv.com.kh`:
  - Works.
  - `published_at` is inferred from `og:image` date in `configs/bayontv_news_only.json`.
- `www.btv.com.kh`:
  - Dedicated source and preset added.
  - Must only crawl:
    - `/category/national-new`
    - `/category/important-news`
  - Uses `page-link` attribute, not plain `href`.
- `khmertimeskh.com`:
  - Source removed because Cloudflare blocked homepage, feed, sitemap, API, and browser automation attempts.

## Important Commits Already Landed

- `3229ee1` Make translation toggle switch instantly
- `7fb7032` Add bulk source deletion
- `82f6493` Add source review export
- `c5e23b0` Remove summary feature
- `be5c292` Add ThmeyThmey listing-card source
- `95ac7ad` Show crawl-all articles as they arrive
- `f334901` Add selected sources crawl mode
- `a6efca8` Remove Khmer Times source
- `3bcdacf` Add dedicated BTV source categories

## Notes For Future Edits

- Ignore untracked private/local files unless user explicitly asks:
  - `crawlCPC`
  - `crawlCPC.pub`
  - local `context/` updates may exist and should not be discarded.
- Prefer updating `context/` after meaningful changes so future sessions can resume cheaply.
