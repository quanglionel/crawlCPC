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
  - One-source crawl also runs in background now, so the progress panel works there too.
  - One-source progress is now real article progress (`completed_articles / total_articles`), not fake timer-based progress.
- Source review:
  - UI supports export of source review JSON and bulk delete with checkboxes.
- Blocked sources:
  - There is now a dedicated tab for sources that cannot currently be crawled.
  - Records are stored separately from normal sources.


## Recent Source-Specific Decisions

- `thmeythmey.com`:
  - Source target is `https://thmeythmey.com/category/9`.
  - Direct category and detail pages are blocked by Cloudflare.
  - Preset sets `preserve_listing_urls: true`, loads the homepage, and extracts only `.section-container:has(.filter-nav a[href='https://thmeythmey.com/category/9']) + .news-grid .news-card`.
  - Tested 2/2 successfully on 2026-04-28 through `run_crawl(... target_url='https://thmeythmey.com/category/9')`.

- `nac.org.kh`:
  - Đã thêm nguồn với preset dùng chung với BayonTV (`configs/auto_bayontv-com-kh.json`).
  - Target: https://nac.org.kh/
  - Đang ở chế độ listing, crawl tối đa 2 bài, 1 trang.
  - Được auto-generate, kiểm tra thành công với bài mẫu: https://nac.org.kh/article/9576
- `bayontv.com.kh`:
  - Works.
  - `published_at` is inferred from `og:image` date in `configs/bayontv_news_only.json`.
- `www.btv.com.kh`:
  - Dedicated source and preset added.
  - Must only crawl:
    - `/category/national-new`
    - `/category/important-news`
  - Uses `page-link` attribute, not plain `href`.
- `cambodiadaily.com`:
  - Use `https://www.cambodiadaily.com/category/news/` as the source target.
  - Use `configs/cambodiadaily_com_news.json`, not the old BayonTV auto preset.
- `cwcicambodia.net`:
  - Use `https://cwcicambodia.net/category/news/` as the source target and preset listing URL.
- `maff.gov.kh`:
  - Use `https://www.maff.gov.kh/news` as the source target.
  - `configs/auto_maff-gov-kh.json` is narrowed to `/newsdetail/<id>` links; old homepage target was too broad.
  - `published_at` is extracted from the `og:image` URL date because article pages do not provide standard publish meta.
- `mfaic.gov.kh`:
  - Existing source was repointed from BayonTV auto preset to `configs/mfaic_gov_kh_media.json`.
  - Use `https://www.mfaic.gov.kh/Media/News` as listing. The requested bare `/en/media/view` route is not a listing; detail pages require a slug.
  - Browser-like headers are required to avoid MFAIC's "Request Rejected" WAF page.
  - Tested 2/2 successfully; title/date/content/images come from `.viewpost-title`, `.viewpost-date`, `.viewpost-content`, `.viewpost img`.
- `mme.gov.kh`:
  - Use `https://mme.gov.kh/newsroom` as the source target.
  - `configs/auto_mme-gov-kh.json` is narrowed to `/newsroom/all-news/<slug>` links; old homepage target was broad.
  - Tested 2/2 successfully; detail content is under `.news-single article p`.
- `moc.gov.kh`:
  - Use `https://moc.gov.kh/kh/news` as the source target.
  - The `/kh/news` page is Next.js client-rendered and static HTML currently has only skeleton cards; direct crawl test returned 0/0 links.
  - The JS chunk references GraphQL `publicNewsList` at `https://graphql.moc.gov.kh/graphql`, but direct POST returned 403 "Site Under Maintenance" on 2026-04-28.
- `pressocm.gov.kh`:
  - Existing source was repointed from `configs/auto_bayontv-com-kh.json` to `configs/pressocm_gov_kh.json`.
  - Listing uses `.entry-title a[href]` and strict `/archives/<id>` article URLs.
  - Detail extraction uses `.tdb-title-text`, `time[datetime]`, `.td-post-content`, and image lazy-load URLs from `img[data-lazy-src]`.
  - Tested 2/2 successfully on 2026-04-28. Some Press OCM articles are scan/PDF style and legitimately have little or no text content, but images are captured.
  - Backend date parser now supports English month display dates with comma, e.g. `24 April, 2026`.
- `grandnewsasia.com`:
  - Use `https://grandnewsasia.com/archives/category/local-news` as the source target.
  - Use `configs/grandnewsasia_local_news.json`; article content is under `.main-text p`.
- `immigration.gov.kh`:
  - Use `https://immigration.gov.kh/news` as the source target.
  - The public news list is Angular-rendered; static HTML gives menu pages only.
  - `configs/auto_immigration-gov-kh.json` uses Firestore REST `projects/egdi-ecosystem/databases/(default)/documents:runQuery`, collection `news`, `display_path` contains `fSWeA16hLDGk6hEpCxHD`, `status.key = 2`.
- `interior.gov.kh`:
  - Use `https://interior.gov.kh/news` as the source target.
  - `configs/auto_interior-gov-kh.json` is narrowed to `/news/<hash>` links; old broad preset crawled menu/footer pages.
  - Dates can be `28-April-2026`; backend date parser now supports English month names in this shape.
- `kampuchea.news`:
  - Source was removed from `sources/`.
  - Unused preset `configs/kampuchea_news_listing.json` was also removed so the URL no longer appears in UI preset data.
  - It is an aggregator; cards link to original publishers such as AKP/Kiripost, so crawl results show those publishers.
- `kampucheathmey.com`:
  - Khmer source now uses `configs/kampucheathmey_kh.json`, not the old BayonTV auto preset.
  - English source added as `sources/en-kampucheathmey-com.json` using `configs/kampucheathmey_en.json`.
  - Both tested 2/2 successfully on 2026-04-28; English publishes dates as `YYYY-MM-DD`, Khmer has `article:published_time`.
- `khmercircle.blogspot.com`:
  - Existing source was repointed from BayonTV auto preset to `configs/khmercircle_blogspot.json`.
  - Tested 2/2 successfully; content comes from `.post-body`, dates from `.date-header span`.
- `khmerization.blogspot.com`:
  - Existing source was repointed from BayonTV auto preset to `configs/khmerization_blogspot.json`.
  - Tested 2/2 successfully for links/title/date/image; first homepage posts are video-only and have empty text content by source HTML.
- `khmerkrom.org`:
  - Source `sources/khmerkrom-org.json` was removed.
  - Feed preset `configs/khmerkrom_org.json` was removed so `https://khmerkrom.org/feed/` no longer appears in UI preset data.
  - Network test on 2026-04-28: feed, homepage, and www homepage all reset the connection.
- `navy.mil.kh`:
  - Source `sources/navy-mil-kh.json` was removed.
  - Unused preset `configs/auto_navy-mil-kh.json` was removed.
  - The auto-generated top candidate was `/cdn-cgi/l/email-protection`, not a valid article.
- `mlmupc.gov.kh`:
  - Source `sources/mlmupc-gov-kh.json` was removed.
  - Unused preset `configs/mlmupc_gov_kh.json` was removed.
  - User asked to remove `https://mlmupc.gov.kh/#`.
- `monoroom.info`:
  - Source `sources/monoroom-info.json` was removed.
  - It used shared `configs/auto_bayontv-com-kh.json`, so no preset was removed.
- `rac.gov.kh`:
  - Source `sources/rac-gov-kh.json` was removed.
  - User asked to remove `https://rac.gov.kh/`.
- `cambodian.cri.cn`:
  - Source was removed from `sources/`.
- `cambodiantimes.com`:
  - HTTP crawler and cloudscraper both hit Cloudflare `403`.
  - Source was removed from `sources/`.
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
- `df1df79` Add project context memory
- `f71d24a` Add blocked sources tab and crawl updates

## Notes For Future Edits

- Ignore untracked private/local files unless user explicitly asks:
  - `crawlCPC`
  - `crawlCPC.pub`
  - local `context/` updates may exist and should not be discarded.
- Prefer updating `context/` after meaningful changes so future sessions can resume cheaply.
