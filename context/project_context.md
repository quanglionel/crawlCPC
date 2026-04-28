# Project Context

## Project Summary

This repo is a newsroom-oriented multi-source crawler with:

- Flask admin-style UI
- JSON presets for site extraction rules
- JSON source records for crawl targets
- file-based outputs
- optional display translation to Vietnamese

The app is designed so non-technical source management can happen in the UI while presets remain reusable.

## Main Goals

- Crawl articles from many websites
- Reuse one preset across multiple structurally similar sources when possible
- Let the user run single-source or multi-source jobs in a simple UI
- Keep only recent articles in crawl-all mode

## Core Folders

- `app/` backend logic
- `templates/` Flask HTML
- `static/` frontend JS/CSS
- `sources/` source catalog
- `configs/` crawler presets
- `output/` crawl results
- `context/` resume memory


## Current Important Sources / Behaviors

- `bayontv.com.kh`
  - dedicated news-only preset
  - `published_at` derived from `og:image`
- `www.btv.com.kh`
  - dedicated preset
  - only two categories allowed:
    - `national-new`
    - `important-news`
  - link extraction uses `page-link`
  - preset preserves multiple listing URLs
  
- `nac.org.kh`
  - source: `sources/nac-org-kh.json`
  - preset: `configs/auto_bayontv-com-kh.json`
  - target: `https://nac.org.kh/`
  - mode: listing, max_pages: 1, max_articles: 2
  - auto-generated, currently uses BayonTV preset for extraction
  - sample article: https://nac.org.kh/article/9576
- `cambodiadaily.com`
  - dedicated news-category preset
  - source should target `/category/news/`, not homepage
- `cwcicambodia.net`
  - source and preset should target `/category/news/`, not homepage
- `maff.gov.kh`
  - source should target `https://www.maff.gov.kh/news`, not homepage
  - preset `configs/auto_maff-gov-kh.json` only accepts `/newsdetail/<id>` article URLs
  - detail pages do not expose standard published meta; date is derived from `og:image` filename like `thumb_2026-04-28_...`
- `mfaic.gov.kh`
  - source should use `https://www.mfaic.gov.kh/Media/News` with preset `configs/mfaic_gov_kh_media.json`
  - user-facing `/en/media/view` without a slug is not a valid listing URL and returns 404/unknown content type
  - detail URLs are `/Media/View/<slug>` and redirect to `/en/media/view/<slug>`
  - full browser-like headers are needed; otherwise the site can return a short "Request Rejected" page
- `mme.gov.kh`
  - source should target `https://mme.gov.kh/newsroom`, not homepage
  - preset `configs/auto_mme-gov-kh.json` only accepts `/newsroom/all-news/<slug>` article URLs
  - content selector should prioritize `.news-single article p` / `.entry-content article p`
- `moc.gov.kh`
  - source should target `https://moc.gov.kh/kh/news`, not `/kh`
  - listing page is a Next.js client-rendered page; static HTML currently only exposes loading skeleton, not article cards
  - article data is fetched through GraphQL at `https://graphql.moc.gov.kh/graphql`, but on 2026-04-28 direct HTTP requests returned 403 "Site Under Maintenance"
  - existing preset still uses URL regexes for `/kh/news/<id>` when links are present
- `grandnewsasia.com`
  - source should target `/archives/category/local-news`
  - uses dedicated preset `configs/grandnewsasia_local_news.json`
- `immigration.gov.kh`
  - source should target `/news`
  - preset uses Firestore REST (`egdi-ecosystem`, collection `news`) because the public news page is Angular-rendered and static HTML only exposes menu links
- `interior.gov.kh`
  - source should target `/news`
  - preset should only accept article URLs like `/news/<hash>`, not menu/footer links
  - dates may be displayed as `28-April-2026`; backend parser supports this format
- `thmeythmey.com`
  - listing-card fallback because detail pages are Cloudflare-blocked
- `kampuchea.news`
  - source was intentionally removed from `sources/`
  - unused preset `configs/kampuchea_news_listing.json` was also removed
  - reason: it is an aggregator and its cards link to original publishers such as AKP, so results look like AKP rather than Kampuchea-owned articles
- `kampucheathmey.com`
  - Khmer source uses `sources/kampucheathmey-1776587652.json` with dedicated preset `configs/kampucheathmey_kh.json`
  - English source uses `sources/en-kampucheathmey-com.json` with dedicated preset `configs/kampucheathmey_en.json`
  - both presets crawl homepage links via strict article URL regex and extract content from `#mvp-content-main p`
- `khmercircle.blogspot.com`
  - source exists as `sources/khmercircle-blogspot-com.json`
  - uses dedicated preset `configs/khmercircle_blogspot.json`, not the old BayonTV auto preset
  - Blogspot dates like `Tuesday, 28 April 2026` are parseable by backend date logic
- `khmerization.blogspot.com`
  - source exists as `sources/khmerization-blogspot-com.json`
  - uses dedicated preset `configs/khmerization_blogspot.json`
  - some posts are video-only embeds and legitimately have no text content in `.post-body`
- `khmerkrom.org`
  - source was intentionally removed from `sources/`
  - unused feed preset `configs/khmerkrom_org.json` was also removed
  - reason: `https://khmerkrom.org/feed/`, homepage, and www homepage reset the connection in this environment
- `navy.mil.kh`
  - source was intentionally removed from `sources/`
  - unused preset `configs/auto_navy-mil-kh.json` was also removed
  - reason: auto candidate was a Cloudflare email-protection path, not a news article
- `mlmupc.gov.kh`
  - source was intentionally removed from `sources/`
  - unused preset `configs/mlmupc_gov_kh.json` was also removed
  - user asked to remove `https://mlmupc.gov.kh/#`
- `cambodian.cri.cn`
  - source was intentionally removed from `sources/`
- `cambodiantimes.com`
  - currently blocked by Cloudflare for HTTP crawler access
  - source was intentionally removed from `sources/`

## Current Product Features

- Instant Vietnamese translation toggle
- Bulk source deletion
- Export source review list
- Live crawl-all progress with live article append
- Selected-sources crawl mode
- Single-source crawl progress based on completed articles / total articles
- Blocked-sources tab for saving sources that currently cannot be crawled

## Known Operational Caveats

- Some sites expose unstable or partial dates.
- Some Cloudflare-protected sites cannot be crawled reliably via HTTP.
- Multi-listing presets may need `preserve_listing_urls: true`.
