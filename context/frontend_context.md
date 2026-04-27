# Frontend Context

## Main Files

- [templates/index.html](F:/pyro/Crack/templates/index.html)
- [static/app.js](F:/pyro/Crack/static/app.js)
- [static/styles.css](F:/pyro/Crack/static/styles.css)

## Main UI Areas

- Crawl tab
- Sources tab
- Presets tab

## Crawl Tab Behavior

- Can run:
  - all sources
  - selected sources
  - one source
- `max_articles` label on crawl screen is effectively “per source” for multi-source runs.
- Translation to Vietnamese is a checkbox toggle that changes visible text immediately.

## Live Crawl-All UX

- Job panel polls `/api/crawl-jobs/<job_id>`.
- Articles append live while job is running.
- Final completion reload is still used to restore full server-rendered result JSON and pagination.

## Selected Sources Mode

- `selected_source_key = "__custom__"` means “Nguồn đã chọn”.
- UI shows a checkbox list of sources and a count of selected items.

## Source Tab Behavior

- Search/filter sources client-side.
- Check/uncheck sources for bulk delete.
- Export review list and source ZIP from here.

## Result Card Data Model

Each card stores both original and translated values in `data-*` attributes so toggling does not require another request.

Notable attributes:

- `data-original-title`
- `data-original-summary`
- `data-original-date`
- `data-original-content`
- `data-vi-title`
- `data-vi-summary`
- `data-vi-date`
- `data-vi-content`

## Styling Notes

- Quick crawl area includes source selector, count field, translation toggle, and optional selected-source picker.
- BTV selected-source picker UI was added and should stay lightweight and scrollable.
