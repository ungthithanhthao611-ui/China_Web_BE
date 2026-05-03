from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin_user
from app.models.media import MediaAsset
from app.models.news import NewsPost
from app.models.orders import Order, OrderItem
from app.models.products import Product
from app.models.user import User

router = APIRouter(dependencies=[Depends(require_admin_user)])

VN_TZ = timezone(timedelta(hours=7))


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

    total_orders = (
        db.query(func.count(Order.id))
        .filter(Order.placed_at >= start_dt, Order.placed_at <= end_dt)
        .scalar()
        or 0
    )
    prev_total_orders = (
        db.query(func.count(Order.id))
        .filter(Order.placed_at >= prev_start_dt, Order.placed_at <= prev_end_dt)
        .scalar()
        or 0
    )

    total_revenue = (
        db.query(func.sum(Order.total_amount))
        .filter(
            Order.status == "completed",
            Order.placed_at >= start_dt,
            Order.placed_at <= end_dt,
        )
        .scalar()
        or 0.0
    )
    prev_total_revenue = (
        db.query(func.sum(Order.total_amount))
        .filter(
            Order.status == "completed",
            Order.placed_at >= prev_start_dt,
            Order.placed_at <= prev_end_dt,
        )
        .scalar()
        or 0.0
    )

    total_products = db.query(func.count(Product.id)).scalar() or 0
    prev_total_products = db.query(func.count(Product.id)).filter(Product.created_at <= prev_end_dt).scalar() or 0

    total_customers = db.query(func.count(User.id)).filter(User.role == "user").scalar() or 0
    prev_total_customers = db.query(func.count(User.id)).filter(User.role == "user", User.created_at <= prev_end_dt).scalar() or 0

    def calc_growth(cur: float, prev: float) -> str:
        if prev == 0:
            return "+100%" if cur > 0 else "0%"
        pct = ((cur - prev) / prev) * 100
        return f"+{pct:.1f}%" if pct > 0 else f"{pct:.1f}%"

    revenue_series = _collect_revenue_series(db=db, start_dt=start_dt, end_dt=end_dt)
    revenue_points = [
        {"label": label, "value": revenue}
        for label, revenue in zip(revenue_series["labels"], revenue_series["revenues"], strict=False)
    ][:60]

    latest_orders_db = (
        db.query(Order)
        .filter(Order.placed_at >= start_dt, Order.placed_at <= end_dt)
        .order_by(Order.placed_at.desc())
        .limit(5)
        .all()
    )
    latest_orders = [
        {
            "code": order.code,
            "customer": order.customer_name,
            "time": order.placed_at.strftime("%H:%M"),
            "statusKey": order.status,
            "amount": _format_currency(order.total_amount),
        }
        for order in latest_orders_db
    ]

    top_products_db = (
        db.query(
            OrderItem.product_name,
            func.sum(OrderItem.quantity).label("total_sold"),
            func.sum(OrderItem.unit_price * OrderItem.quantity).label("revenue"),
            Product.image_url,
            Product.stock_quantity,
        )
        .select_from(OrderItem)
        .join(Order)
        .outerjoin(Product, Product.id == OrderItem.product_id)
        .filter(
            Order.status == "completed",
            Order.placed_at >= start_dt,
            Order.placed_at <= end_dt,
        )
        .group_by(OrderItem.product_name, Product.image_url, Product.stock_quantity)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(5)
        .all()
    )
    top_products = [
        {
            "name": row.product_name,
            "sold": int(row.total_sold),
            "revenue": float(row.revenue or 0),
            "stock_quantity": row.stock_quantity if row.stock_quantity is not None else 0,
            "image_url": row.image_url or "",
        }
        for row in top_products_db
    ]

    status_counts = (
        db.query(Order.status, func.count(Order.id))
        .filter(Order.placed_at >= start_dt, Order.placed_at <= end_dt)
        .group_by(Order.status)
        .all()
    )
    status_dict = {row[0]: row[1] for row in status_counts}
    total_orders_for_pct = sum(status_dict.values()) or 1

    order_stats = []
    color_map = {
        "pending_confirmation": "#f8b72b",
        "confirmed": "#3b82f6",
        "shipping": "#8b5cf6",
        "completed": "#10b981",
        "cancelled": "#ef4444",
    }
    for status_key, color in color_map.items():
        count = status_dict.get(status_key, 0)
        if count > 0:
            pct = round((count / total_orders_for_pct) * 100, 1)
            order_stats.append({"key": status_key, "value": pct, "color": color, "count": count})

    out_of_stock = db.query(func.count(Product.id)).filter(Product.stock_quantity <= 0).scalar() or 0
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
            {"key": "total_orders", "value": str(total_orders), "growth": calc_growth(total_orders, prev_total_orders), "tone": "blue"},
            {"key": "total_revenue", "value": _format_currency(total_revenue), "growth": calc_growth(total_revenue, prev_total_revenue), "tone": "success"},
            {"key": "products", "value": str(total_products), "growth": calc_growth(total_products, prev_total_products), "tone": "purple"},
            {"key": "customers", "value": str(total_customers), "growth": calc_growth(total_customers, prev_total_customers), "tone": "orange"},
        ],
        "revenuePoints": revenue_points,
        "latestOrders": latest_orders,
        "topProducts": top_products,
        "orderStats": order_stats,
        "quickStats": [
            {"key": "out_of_stock", "value": out_of_stock, "tone": "danger"},
            {"key": "new_customers", "value": new_customers, "tone": "success"},
            {"key": "posts", "value": posts, "tone": "info"},
            {"key": "videos", "value": videos, "tone": "blue"},
        ],
    }
