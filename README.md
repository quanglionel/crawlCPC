# Media Article Crawler

Tool Python chạy trong Docker để crawl bài viết từ một web truyền thông dựa trên cấu hình CSS selector, kèm giao diện web để thao tác trực tiếp trên trình duyệt.

## Tính năng

- Giao diện web để chọn preset config, sửa JSON config, chạy crawl và xem kết quả ngay trên trang.
- Có ô nhập `URL cần crawl` riêng để đổi sang chuyên mục hoặc bài viết khác mà không phải sửa tay `listing_urls`.
- Có tab `Nguồn` để lưu nhiều URL crawl khác nhau, mỗi nguồn tham chiếu tới một preset.
- Có tab `Preset` để quản lý các bộ selector trong `configs/`.
- Có tab `Tóm tắt` để nhận bài từ kết quả crawl và gửi sang Gemini theo prompt mẫu.
- Nhiều nguồn có thể dùng chung một preset.
- Có tuỳ chọn dịch kết quả hiển thị sang tiếng Việt, còn JSON output vẫn giữ nguyên bản gốc.
- Crawl từ trang chuyên mục hoặc trang chủ.
- Theo link bài viết rồi trích xuất `title`, `summary`, `content`, `published_at`, `author`, `category`, `image`.
- Đổi sang website khác bằng cách sửa file JSON config.
- Chạy hoàn toàn bằng Docker hoặc Docker Compose.

## Cấu trúc

- `app/main.py`: entrypoint chung cho CLI và web UI.
- `app/web.py`: web server và giao diện.
- `app/catalog.py`: quản lý lưu trữ nguồn và preset.
- `app/crawler.py`: logic crawl và trích xuất dữ liệu.
- `configs/vnexpress_kinh_doanh.json`: cấu hình mẫu cho VnExpress mục Kinh doanh.
- `sources/*.json`: các nguồn đã lưu.
- `output/articles.json`: file output sau khi chạy.

## Chạy giao diện bằng Docker

Build image:

```bash
docker build -t media-crawler .
```

Chạy web app:

```bash
docker run --rm -p 8000:8000 -v ${PWD}:/app media-crawler
```

Mở trình duyệt tại `http://localhost:8000`.

## Chạy bằng Docker Compose

Chạy giao diện:

```bash
docker compose up --build web
```

Chạy batch crawler:

```bash
docker compose run --rm crawler
```

## Chạy CLI trực tiếp trong image

```bash
docker run --rm -v ${PWD}:/app media-crawler python -m app.main crawl --config configs/vnexpress_kinh_doanh.json --output output/articles.json --max-pages 1 --max-articles 5
```

## Deploy Render

Docker image mặc định chạy web bằng Gunicorn qua `app.wsgi:app` và đọc cổng từ biến môi trường `PORT` của Render. Khi deploy bằng Docker trên Render, chỉ cần build từ `Dockerfile`; không dùng start command kiểu `python -m app.main web` hoặc `flask run` vì hai lệnh đó sẽ chạy Flask development server.

Để dùng tab tóm tắt, cấu hình thêm Environment Variable trên Render.

Khuyến nghị dùng Groq free tier:

- `GROQ_API_KEY`: API key dùng để gọi Groq.
- `GROQ_MODEL`: model Groq muốn dùng, mặc định là `llama-3.1-8b-instant`.
- `SUMMARY_PROVIDER`: đặt là `groq`.

Tuỳ chọn dùng Gemini:

- `GEMINI_API_KEY`: API key dùng để gọi Gemini.
- `GEMINI_MODEL`: model Gemini muốn dùng, mặc định là `gemini-2.0-flash`.

Hoặc dùng OpenAI:

- `OPENAI_API_KEY`: API key dùng để gọi OpenAI.
- `OPENAI_MODEL`: model OpenAI muốn dùng, mặc định là `gpt-4o-mini`.
- `SUMMARY_PROVIDER`: chọn `groq`, `openai`, `gemini`, hoặc `auto`. Mặc định `auto`; nếu có `GROQ_API_KEY` thì ưu tiên Groq, sau đó đến OpenAI, rồi Gemini.

Khi chạy bằng Docker Compose, có thể đặt các biến này trong file `.env` ở thư mục dự án.

Để nguồn/preset thêm từ UI không mất sau khi Render restart hoặc redeploy, cần bật Persistent Disk và cấu hình:

- Disk mount path: `/var/data`
- Environment Variable: `APP_DATA_DIR=/var/data`

Khi `APP_DATA_DIR` được bật, app sẽ đọc/ghi các thư mục mutable tại `/var/data`: `sources/`, `configs/`, `output/`, `cache/`. Lần chạy đầu nếu `/var/data/sources` hoặc `/var/data/configs` đang trống, app tự copy dữ liệu JSON mặc định từ image sang đó.

Nếu deploy Render bằng Python environment thay vì Docker, dùng start command:

```bash
gunicorn app.wsgi:app --config gunicorn_config.py
```

## Tùy chỉnh config

Ví dụ cấu hình:

```json
{
  "site_name": "my-news-site",
  "base_url": "https://example.com",
  "listing_urls": ["https://example.com/news"],
  "article_link_selectors": ["article h2 a", ".story-card a"],
  "article_link_pattern": "https://example\\.com/news/.+",
  "fields": {
    "title": {
      "mode": "first",
      "extractors": [{"selector": "h1"}, {"selector": "meta[property='og:title']", "attr": "content"}]
    },
    "content": {
      "mode": "join",
      "separator": "\n\n",
      "extractors": [{"selector": ".article-body p"}]
    }
  }
}
```

### Các mode hỗ trợ

- `first`: lấy giá trị đầu tiên tìm được.
- `join`: nối nhiều node text lại thành một chuỗi.
- `list`: lấy danh sách text duy nhất.

## Lưu ý

- Chỉ nên crawl các website mà bạn có quyền truy cập và phù hợp với điều khoản sử dụng.
- Với website render bằng JavaScript mạnh, cần mở rộng tool sang Playwright hoặc browser automation.

## Deploy Oracle Always Free (khong ngu dong)

Du an da co san bo file deploy Docker-only cho Oracle Cloud Always Free:

- Compose override: `docker-compose.oracle.yml`
- Caddy reverse proxy + HTTPS: `deploy/oracle/Caddyfile`
- Script cai Docker: `deploy/oracle/scripts/install_docker_oracle.sh`
- Script deploy: `deploy/oracle/scripts/deploy_oracle.sh`
- Huong dan day du: `deploy/oracle/DEPLOY_ORACLE_ALWAYS_FREE.md`

Luong trien khai nhanh:

```bash
sudo bash deploy/oracle/scripts/install_docker_oracle.sh
cp deploy/oracle/.env.oracle.example deploy/oracle/.env.oracle
bash deploy/oracle/scripts/deploy_oracle.sh
```

## Deploy Google Cloud Trial 90 ngay (Docker-only)

Du an da co san bo file deploy Docker-only cho VM trial:

- Compose override: `docker-compose.gcp-trial.yml`
- Caddy reverse proxy + HTTPS: `deploy/gcp-trial/Caddyfile`
- Script cai Docker: `deploy/gcp-trial/scripts/install_docker_ubuntu.sh`
- Script deploy: `deploy/gcp-trial/scripts/deploy_gcp_trial.sh`
- Huong dan day du + checklist chuyen ha tang: `deploy/gcp-trial/DEPLOY_GCP_TRIAL_90D.md`

Luong trien khai nhanh:

```bash
sudo bash deploy/gcp-trial/scripts/install_docker_ubuntu.sh
cp deploy/gcp-trial/.env.gcp-trial.example deploy/gcp-trial/.env.gcp-trial
bash deploy/gcp-trial/scripts/deploy_gcp_trial.sh
```
