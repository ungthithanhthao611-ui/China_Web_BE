from __future__ import annotations

from typing import Any


def normalize_price(value: float | int | None) -> float:
    if value is None:
        return 0.0
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def normalize_stock_quantity(value: int | float | None) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def resolve_price_components(
    *,
    price: float | int | None,
    original_price: float | int | None,
    sale_price: float | int | None,
) -> dict[str, float | bool]:
    legacy_price = normalize_price(price)
    normalized_original_price = normalize_price(original_price)
    normalized_sale_price = normalize_price(sale_price)

    if normalized_original_price <= 0 and legacy_price > 0:
        normalized_original_price = legacy_price

    if normalized_sale_price > 0 and normalized_original_price <= 0:
        normalized_original_price = normalized_sale_price
        normalized_sale_price = 0.0

    has_sale_price = (
        normalized_original_price > 0
        and normalized_sale_price > 0
        and normalized_sale_price < normalized_original_price
    )

    effective_price = (
        normalized_sale_price
        if has_sale_price
        else normalized_original_price or legacy_price
    )

    return {
        'price': normalize_price(effective_price),
        'original_price': normalize_price(normalized_original_price),
        'sale_price': normalize_price(normalized_sale_price if has_sale_price else 0.0),
        'effective_price': normalize_price(effective_price),
        'has_sale_price': has_sale_price,
    }


def normalize_product_pricing_input(data: dict[str, Any]) -> dict[str, Any]:
    resolved = resolve_price_components(
        price=data.get('price'),
        original_price=data.get('original_price'),
        sale_price=data.get('sale_price'),
    )
    data['price'] = resolved['price']
    data['original_price'] = resolved['original_price']
    data['sale_price'] = resolved['sale_price']
    return data


def decorate_product_pricing_payload(payload: dict[str, Any], product: Any) -> dict[str, Any]:
    resolved = resolve_price_components(
        price=getattr(product, 'price', None),
        original_price=getattr(product, 'original_price', None),
        sale_price=getattr(product, 'sale_price', None),
    )
    payload.update(resolved)
    payload['stock_quantity'] = normalize_stock_quantity(getattr(product, 'stock_quantity', 0))
    payload['in_stock'] = payload['stock_quantity'] > 0
    return payload


def resolve_order_item_price_snapshot(product: Any) -> tuple[float, float, float]:
    resolved = resolve_price_components(
        price=getattr(product, 'price', None),
        original_price=getattr(product, 'original_price', None),
        sale_price=getattr(product, 'sale_price', None),
    )
    return (
        normalize_price(resolved['original_price']),
        normalize_price(resolved['sale_price']),
        normalize_price(resolved['effective_price']),
    )
