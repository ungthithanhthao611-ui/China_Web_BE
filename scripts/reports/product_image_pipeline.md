# Pipeline tổng ảnh sản phẩm

## Tóm tắt

- Pipeline status: **WARN**
- CSV input: `E:\uiChina_Web\China_BE\scripts\reports\missing_product_images_template.csv`
- Execute requested: **True**
- Allow warn import: **True**
- Import attempted: **True**
- Import executed: **True**
- Import gate reason: Validate đạt điều kiện cho phép import.

## Kết quả validate

- Validate status: **WARN**
- PASS: **0**
- WARN: **19**
- FAIL: **0**

## Kết quả import

- Ready: **0**
- Updated: **0**
- Skipped: **19**

## Kết quả audit cuối

- Audit health: **WARN**
- Sản phẩm thiếu ảnh chính: **19**
- Sản phẩm thiếu hoàn toàn ảnh: **19**
- DB refs chưa map media_assets: **0**
- DB refs mất file trên Cloudinary: **0**

## Hướng dẫn dùng

- Dry-run tổng: `python scripts/run_product_image_pipeline.py`
- Execute an toàn khi validate PASS: `python scripts/run_product_image_pipeline.py --execute`
- Execute cả khi validate WARN: `python scripts/run_product_image_pipeline.py --execute --allow-warn-import`

## File report chi tiết

- Validate chi tiết nằm trong phần `validate` của JSON pipeline.
- Import chi tiết nằm trong phần `import` của JSON pipeline.
- Audit chi tiết nằm trong phần `audit` của JSON pipeline.