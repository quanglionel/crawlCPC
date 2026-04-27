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
- `cambodiadaily.com`
  - dedicated news-category preset
  - source should target `/category/news/`, not homepage
- `thmeythmey.com`
  - listing-card fallback because detail pages are Cloudflare-blocked

## Current Product Features

- Instant Vietnamese translation toggle
- Bulk source deletion
- Export source review list
- Live crawl-all progress with live article append
- Selected-sources crawl mode
- Blocked-sources tab for saving sources that currently cannot be crawled

## Known Operational Caveats

- Some sites expose unstable or partial dates.
- Some Cloudflare-protected sites cannot be crawled reliably via HTTP.
- Multi-listing presets may need `preserve_listing_urls: true`.
