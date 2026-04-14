# China Web FastAPI Backend

Backend này được đặt trong `China_Web_BE/backend`, dùng chung với frontend ở `China_Web_FE`, bám sát schema trong `E:\uiChina_Web\China_Web_FE\docs\db_web_trung.xlsx` và có bổ sung một số bảng mở rộng cần thiết để triển khai thực tế:

- `content_blocks`, `content_block_items`: quản lý block lặp cho home/about/honors/subsidiary
- `entity_media`: gallery nhiều ảnh cho `page`, `project`, `branch`, `post`
- `inquiry_submissions`: nhận dữ liệu form liên hệ/inquiry
- mở rộng `branches` với `slug`, `summary`, `body`, `image_id`, `hero_image_id`, `meta_title`, `meta_description`

## Cấu trúc

```text
backend/
  app/
    api/         # routers + dependencies
    core/        # config + security
    db/          # session + init db
    models/      # SQLAlchemy models
    schemas/     # Pydantic schemas
    services/    # registry + query logic
    main.py
  scripts/
    seed.py
```

## Chạy local

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Database

- Mặc định project chạy bằng SQLite với file `backend/china_web.db`.
- Khi dùng cấu hình mặc định, không cần pgAdmin và không cần đăng nhập PostgreSQL.
- Nếu muốn đổi sang PostgreSQL, sửa `DATABASE_URL` trong `.env` theo dạng `postgresql+psycopg://postgres:<REAL_POSTGRES_PASSWORD>@127.0.0.1:5432/<db_name>`.
- Lỗi `password authentication failed for user "postgres"` trong pgAdmin nghĩa là mật khẩu của PostgreSQL server không khớp. Mật khẩu này là mật khẩu đã đặt khi cài PostgreSQL, không phải mật khẩu mặc định của project.

Swagger:

- `http://localhost:8000/docs`

## Admin token

Các route `/api/v1/admin/*` yêu cầu header:

```text
X-Admin-Token: <  china-web-admin-2026 >
```

## Gợi ý tích hợp FE

- Public data: `/api/v1/public/*`
- Admin/CMS: `/api/v1/admin/*`
- Bootstrap menu/settings: `/api/v1/public/bootstrap?language_code=en`
