# Kế hoạch migrate Cloudinary media_assets

## Tóm tắt

- Root đích: `China_web`
- Folder sản phẩm đích: `products`
- Tổng asset sai chuẩn: **7**
- Có thể migrate tự động: **0**
- Cần review thủ công: **7**

## Chi tiết kế hoạch

| media_id | current_storage_path | target_public_id | status | linked_product | reasons | notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | seed/hero-home.jpg |  | manual_review | - | wrong_root_folder | Asset chưa liên kết sản phẩm hoặc thuộc module khác; cần quyết định chuẩn folder riêng.; Asset seed cũ đang ở folder seed/. Nên xác nhận module sử dụng trước khi migrate. |
| 2 | seed/about-section.jpg |  | manual_review | - | wrong_root_folder | Asset chưa liên kết sản phẩm hoặc thuộc module khác; cần quyết định chuẩn folder riêng.; Asset seed cũ đang ở folder seed/. Nên xác nhận module sử dụng trước khi migrate. |
| 3 | seed/contact-map.jpg |  | manual_review | - | wrong_root_folder | Asset chưa liên kết sản phẩm hoặc thuộc module khác; cần quyết định chuẩn folder riêng.; Asset seed cũ đang ở folder seed/. Nên xác nhận module sử dụng trước khi migrate. |
| 4 | china-web/products/travertine |  | manual_review | - | wrong_root_folder | Asset chưa liên kết sản phẩm hoặc thuộc module khác; cần quyết định chuẩn folder riêng. |
| 5 | china-web/products/travertine |  | manual_review | #81 / - / product_images.url | product_folder_mismatch, wrong_root_folder | Sản phẩm liên kết chưa có slug nên chưa thể tính folder đích chắc chắn. |
| 6 | china-web/products/travertine |  | manual_review | #81 / - / product_images.url | product_folder_mismatch, wrong_root_folder | Sản phẩm liên kết chưa có slug nên chưa thể tính folder đích chắc chắn. |
| 7 | china-web/products/travertine |  | manual_review | #81 / - / product_images.url | product_folder_mismatch, wrong_root_folder | Sản phẩm liên kết chưa có slug nên chưa thể tính folder đích chắc chắn. |