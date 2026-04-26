# Audit tổng thể hệ thống ảnh sản phẩm

## Trạng thái tổng quan

- Health status: **WARN**
- Prefix Cloudinary audit: `China_web`
- Tổng media_assets: **218**
- Tổng URL ảnh sản phẩm/galleries: **52**
- Cloudinary còn thiếu trong media_assets: **0**
- media_assets mất file trên Cloudinary: **0**
- DB refs chưa map media_assets: **0**
- DB refs mất file trên Cloudinary: **0**
- Duplicate public_id trong media_assets: **0**
- Sản phẩm thiếu ảnh chính: **4**
- Sản phẩm thiếu hoàn toàn ảnh: **4**
- Sản phẩm lặp ảnh chính trong gallery: **0**
- Sản phẩm có gallery trùng URL: **0**

## Diễn giải

- Có 4 sản phẩm chưa có ảnh chính
- Có 4 sản phẩm chưa có bất kỳ ảnh nào

## Sản phẩm thiếu ảnh chính

| product_id | slug | name | sku |
| --- | --- | --- | --- |
| 677 | da-mem-os-14 | Đá vân sọc | OS.14 |
| 678 | da-mem-os-15 | Đá vôi | OS.15 |
| 679 | da-mem-os-16 | Gạch thẻ | OS.16 |
| 680 | da-mem-os-17 | Gạch thẻ cổ điển | OS.17 |

## Sản phẩm không có bất kỳ ảnh nào

| product_id | slug | name | sku |
| --- | --- | --- | --- |
| 677 | da-mem-os-14 | Đá vân sọc | OS.14 |
| 678 | da-mem-os-15 | Đá vôi | OS.15 |
| 679 | da-mem-os-16 | Gạch thẻ | OS.16 |
| 680 | da-mem-os-17 | Gạch thẻ cổ điển | OS.17 |

## Sản phẩm bị lặp ảnh chính trong gallery

Không có dữ liệu bất thường.

## Sản phẩm có gallery bị trùng URL

Không có dữ liệu bất thường.

## Sản phẩm có ảnh chính không hợp lệ

Không có dữ liệu bất thường.

## Sản phẩm có gallery URL không hợp lệ

Không có dữ liệu bất thường.

## Sản phẩm có ảnh chính chưa map media_assets

Không có dữ liệu bất thường.

## Sản phẩm có ảnh chính chết trên Cloudinary

Không có dữ liệu bất thường.

## Sản phẩm có gallery chưa map media_assets

Không có dữ liệu bất thường.

## Sản phẩm có gallery chết trên Cloudinary

Không có dữ liệu bất thường.

## public_id trùng trong media_assets

Không có dữ liệu bất thường.