# Dev Rules

Project-specific working rules for future sessions:

## Context First

- Read `context/` before rescanning the repo.
- Update `context/` when large behavior changes land.

## Source Editing

- If user wants a source gone permanently, remove its `sources/*.json` file.
- Do not assume Render persistent disk exists.
- Prefer dedicated presets for sites with special structure instead of overloading generic presets.

## Safe Git Hygiene

- Do not touch private/untracked local files unless user asks:
  - `crawlCPC`
  - `crawlCPC.pub`
- Treat `context/` as user-owned memory; extend it, do not casually wipe it.

## UI / Product Expectations

- Crawl-all should feel live.
- Translation toggle should switch instantly without reload.
- Source management should support review/export/delete in bulk.

## Technical Preferences

- Prefer small targeted preset fixes over sweeping crawler rewrites.
- Add crawler abstractions only when multiple sources need them.
- For dynamic sites:
  - try plain HTTP first
  - then cloudscraper
  - then browser automation only if necessary
- If a site is permanently Cloudflare-blocked and user wants it removed, remove the source instead of leaving a broken entry around.
