# Data Context

There is no traditional SQL database here. The project is file-backed.

## Storage Layout

- `sources/*.json`
  - one saved source per file
- `configs/*.json`
  - crawler preset definitions
- `output/*.json`
  - crawl result payloads
- `cache/translations/*.json`
  - translation cache

## Source Record Shape

Typical fields:

- `source_key`
- `name`
- `target_url`
- `target_mode`
- `preset_path`
- `output`
- `max_pages`
- `max_articles`
- `workers`
- `notes`

## Preset Record Shape

Important preset fields:

- `site_name`
- `base_url`
- `allowed_domains`
- `listing_urls`
- `article_link_selectors`
- `article_link_attribute` (optional; used by `www.btv.com.kh`)
- `article_link_regexes` (optional)
- `article_link_pattern`
- `article_link_order`
- `fields`
- `remove_selectors`
- `request`
- `preserve_listing_urls` (optional; used by multi-category source presets)

## Output Payload Shape

Typical result keys:

- `site_name`
- `article_count`
- `success_count`
- `error_count`
- `warnings`
- `articles`
- `output_path`
- `duration_seconds`
- `target_url`
- `target_mode`

Article keys commonly include:

- `url`
- `site_name`
- `title`
- `summary`
- `published_at`
- `author`
- `content`
- `images`
- `error` (when extraction fails)

Display-prepared articles may also include:

- `display_title`
- `display_summary`
- `display_published_at`
- `display_content`
- `display_content_truncated`
- `display_language`
- `translation_error`
