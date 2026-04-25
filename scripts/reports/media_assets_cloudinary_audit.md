# Audit media_assets Cloudinary

## Tóm tắt

- Tổng media_assets: **11**
- Cloudinary assets: **11**
- Non-Cloudinary assets: **0**
- Product-linked assets: **6**
- Unlinked Cloudinary assets: **5**
- Mismatched assets: **7**
- Chuẩn root mong muốn: `China_web`
- Chuẩn thư mục sản phẩm: `products`

## Danh sách asset sai chuẩn

| media_id | title | storage_path | expected_folder | reasons | linked_products |
| --- | --- | --- | --- | --- | --- |
| 1 | Corporate hero image | seed/hero-home.jpg |  | wrong_root_folder |  |
| 2 | About section image | seed/about-section.jpg |  | wrong_root_folder |  |
| 3 | Contact office image | seed/contact-map.jpg |  | wrong_root_folder |  |
| 4 | Travertine | china-web/products/travertine |  | wrong_root_folder |  |
| 5 | Travertine | china-web/products/travertine | China_web/products | product_folder_mismatch, wrong_root_folder | #81:- (product_images.url) |
| 6 | Travertine | china-web/products/travertine | China_web/products | product_folder_mismatch, wrong_root_folder | #81:- (product_images.url) |
| 7 | Travertine | china-web/products/travertine | China_web/products | product_folder_mismatch, wrong_root_folder | #81:- (product_images.url) |