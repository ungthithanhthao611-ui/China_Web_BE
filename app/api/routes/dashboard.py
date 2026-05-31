from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin_user
from app.models.media import MediaAsset
from app.models.news import NewsPost
from app.models.orders import Order, OrderItem
from app.models.products import Product, ContactInquiry
from app.models.user import User

router = APIRouter(dependencies=[Depends(require_admin_user)])

VN_TZ = timezone(timedelta(hours=7))
LOW_STOCK_THRESHOLD = 10


def _parse_dashboard_range(
    start_date: str | None,
    end_date: str | None,
) -> tuple[datetime, datetime]:
    now = datetime.now(VN_TZ)
    try:
        end_dt = (
            datetime.strptime(end_date, "%Y-%m-%d")
            .replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=VN_TZ)
            if end_date
            else now
        )
        start_dt = (
            datetime.strptime(start_date, "%Y-%m-%d")
            .replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=VN_TZ)
            if start_date
            else (end_dt - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        )
    except (ValueError, TypeError):
        end_dt = now
        start_dt = (end_dt - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)

    if start_dt > end_dt:
        original_start = start_dt
        original_end = end_dt
        start_dt, end_dt = original_end.replace(hour=0, minute=0, second=0, microsecond=0), original_start.replace(
            hour=23,
            minute=59,
            second=59,
            microsecond=999999,
        )

    return start_dt, end_dt


def _format_currency(value: float | int) -> str:
    return f"{int(value):,}đ".replace(",", ".")


def _collect_revenue_series(db: Session, start_dt: datetime, end_dt: datetime) -> dict[str, Any]:
    days_diff = max((end_dt.date() - start_dt.date()).days, 0)
    labels: list[str] = []
    revenues: list[int] = []
    total = 0

    for offset in range(min(days_diff + 1, 366)):
        target_date = start_dt + timedelta(days=offset)
        day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=VN_TZ)
        day_end = target_date.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=VN_TZ)

        revenue_value = int(
            float(
                db.query(func.sum(Order.total_amount))
                .filter(
                    Order.status == "completed",
                    Order.placed_at >= day_start,
                    Order.placed_at <= day_end,
                )
                .scalar()
                or 0
            )
        )
        labels.append(target_date.strftime("%d/%m"))
        revenues.append(revenue_value)
        total += revenue_value

    return {
        "labels": labels,
        "revenues": revenues,
        "total": total,
    }


def _serialize_stock_product(product: Product) -> dict[str, Any]:
    return {
        "id": int(product.id),
        "name": product.name,
        "sku": product.sku or "---",
        "stock_quantity": int(product.stock_quantity or 0),
        "image_url": product.image_url or "",
        "is_active": bool(product.is_active),
    }


@router.get("/revenue")
def get_dashboard_revenue(
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    start_dt, end_dt = _parse_dashboard_range(from_date, to_date)
    return _collect_revenue_series(db=db, start_dt=start_dt, end_dt=end_dt)


@router.get("/stats")
def get_dashboard_stats(
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    start_dt, end_dt = _parse_dashboard_range(start_date, end_date)
    delta = end_dt - start_dt
    prev_end_dt = start_dt - timedelta(microseconds=1)
    prev_start_dt = start_dt - delta

    total_inquiries = (
        db.query(func.count(ContactInquiry.id))
        .filter(ContactInquiry.created_at >= start_dt, ContactInquiry.created_at <= end_dt)
        .scalar()
        or 0
    )
    prev_total_inquiries = (
        db.query(func.count(ContactInquiry.id))
        .filter(ContactInquiry.created_at >= prev_start_dt, ContactInquiry.created_at <= prev_end_dt)
        .scalar()
        or 0
    )

    total_posts = db.query(func.count(NewsPost.id)).scalar() or 0
    prev_total_posts = db.query(func.count(NewsPost.id)).filter(NewsPost.created_at <= prev_end_dt).scalar() or 0

    total_products = db.query(func.count(Product.id)).scalar() or 0
    prev_total_products = db.query(func.count(Product.id)).filter(Product.created_at <= prev_end_dt).scalar() or 0

    total_customers = db.query(func.count(User.id)).filter(User.role == "user").scalar() or 0
    prev_total_customers = db.query(func.count(User.id)).filter(User.role == "user", User.created_at <= prev_end_dt).scalar() or 0

    def calc_growth(cur: float, prev: float) -> str:
        if prev == 0:
            return "+100%" if cur > 0 else "0%"
        pct = ((cur - prev) / prev) * 100
        return f"+{pct:.1f}%" if pct > 0 else f"{pct:.1f}%"

    latest_inquiries_db = (
        db.query(ContactInquiry)
        .filter(ContactInquiry.created_at >= start_dt, ContactInquiry.created_at <= end_dt)
        .order_by(ContactInquiry.created_at.desc())
        .limit(5)
        .all()
    )
    latest_inquiries = [
        {
            "id": int(inquiry.id),
            "name": inquiry.full_name,
            "email": inquiry.email,
            "phone": inquiry.phone or "---",
            "subject": inquiry.subject or "Yêu cầu báo giá",
            "status": inquiry.status,
            "time": inquiry.created_at.strftime("%d/%m %H:%M"),
        }
        for inquiry in latest_inquiries_db
    ]

    low_stock_products_db = (
        db.query(Product)
        .filter(Product.stock_quantity > 0, Product.stock_quantity <= LOW_STOCK_THRESHOLD)
        .order_by(Product.stock_quantity.asc(), Product.updated_at.desc())
        .limit(12)
        .all()
    )
    out_of_stock_products_db = (
        db.query(Product)
        .filter(Product.stock_quantity <= 0)
        .order_by(Product.updated_at.desc())
        .limit(12)
        .all()
    )

    low_stock_products = [_serialize_stock_product(product) for product in low_stock_products_db]
    out_of_stock_products = [_serialize_stock_product(product) for product in out_of_stock_products_db]
    out_of_stock = len(out_of_stock_products)
    low_stock_count = len(low_stock_products)

    new_customers = (
        db.query(func.count(User.id))
        .filter(
            User.role == "user",
            User.created_at >= start_dt,
            User.created_at <= end_dt,
        )
        .scalar()
        or 0
    )
    posts = db.query(func.count(NewsPost.id)).scalar() or 0
    videos = db.query(func.count(MediaAsset.id)).filter(MediaAsset.asset_type == "video").scalar() or 0

    return {
        "kpis": [
            {"key": "products", "value": str(total_products), "growth": calc_growth(total_products, prev_total_products), "tone": "purple"},
            {"key": "customers", "value": str(total_customers), "growth": calc_growth(total_customers, prev_total_customers), "tone": "orange"},
            {"key": "inquiries", "value": str(total_inquiries), "growth": calc_growth(total_inquiries, prev_total_inquiries), "tone": "success"},
            {"key": "posts", "value": str(total_posts), "growth": calc_growth(total_posts, prev_total_posts), "tone": "blue"},
        ],
        "revenuePoints": [],
        "latestOrders": [],
        "latestInquiries": latest_inquiries,
        "topProducts": [],
        "orderStats": [],
        "quickStats": [
            {"key": "out_of_stock", "value": out_of_stock, "tone": "danger"},
            {"key": "low_stock", "value": low_stock_count, "tone": "warning"},
            {"key": "new_customers", "value": new_customers, "tone": "success"},
            {"key": "posts", "value": posts, "tone": "info"},
            {"key": "videos", "value": videos, "tone": "blue"},
        ],
        "inventory": {
            "lowStockThreshold": LOW_STOCK_THRESHOLD,
            "lowStockProducts": low_stock_products,
            "outOfStockProducts": out_of_stock_products,
        },
    }
