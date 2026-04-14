from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session
from yookassa import Configuration, Payment

from config import settings
from .models import Order, OrderStatus


class YooKassaConfigError(RuntimeError):
    pass


class YooKassaWebhookError(RuntimeError):
    pass


def _ensure_yookassa_config() -> None:
    if not settings.YOOKASSA_SHOP_ID or not settings.YOOKASSA_SECRET_KEY:
        raise YooKassaConfigError("YooKassa credentials are not configured")

    Configuration.account_id = settings.YOOKASSA_SHOP_ID
    Configuration.secret_key = settings.YOOKASSA_SECRET_KEY


def _build_return_url(order: Order) -> str:
    base_url = settings.BASE_URL.rstrip("/")
    return f"{base_url}/thanks/{order.id}"


def _amount_value(order: Order) -> str:
    amount = getattr(order, "total_rub", None)
    if amount is None:
        raise YooKassaConfigError(
            "Order total_rub field is required for YooKassa payment"
        )
    return str(Decimal(str(amount)).quantize(Decimal("0.01")))


def _verify_webhook_signature(raw_body: bytes, signature: str | None) -> None:
    if not signature:
        raise YooKassaWebhookError("Missing X-Content-SHA256 header")

    secret = settings.YOOKASSA_SECRET_KEY
    if not secret:
        raise YooKassaConfigError("YooKassa secret key is not configured")

    digest = hmac.HMAC(secret.encode(), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()

    if not hmac.compare_digest(expected, signature):
        raise YooKassaWebhookError("Invalid webhook signature")


def _build_receipt(order: Order) -> dict:
    """
    Формирует чек для ЮКассы (54-ФЗ).
    Каждая позиция — товар с именем, ценой, количеством и НДС.
    Доставка добавляется отдельной строкой если delivery_fee_rub > 0.
    """
    items = []

    for item in order.items:
        unit_price = Decimal(str(item.price_rub_snapshot)).quantize(Decimal("0.01"))
        items.append({
            "description": item.name_snapshot[:128],
            "quantity": str(Decimal(str(item.qty)).quantize(Decimal("0.001"))),
            "amount": {
                "value": str(unit_price),
                "currency": "RUB",
            },
            "vat_code": 1,  # без НДС
            "payment_mode": "full_prepayment",
            "payment_subject": "commodity",
        })

    if order.delivery_fee_rub and order.delivery_fee_rub > 0:
        fee = str(Decimal(str(order.delivery_fee_rub)).quantize(Decimal("0.01")))
        items.append({
            "description": "Доставка",
            "quantity": "1",
            "amount": {
                "value": fee,
                "currency": "RUB",
            },
            "vat_code": 1,
            "payment_mode": "full_prepayment",
            "payment_subject": "service",
        })

    return {
        "customer": {
            "phone": order.phone_e164,
        },
        "items": items,
    }


def create_yookassa_payment(order: Order, db: Session) -> str:
    _ensure_yookassa_config()

    payment = Payment.create(
        {
            "amount": {
                "value": _amount_value(order),
                "currency": "RUB",
            },
            "capture": True,
            "payment_method_types": ["bank_card", "sbp"],  # yoo_money исключён
            "confirmation": {
                "type": "embedded",  # виджет; redirect показывал все методы
            },
            "description": f"Оплата заказа #{order.order_number or order.id}",
            "receipt": _build_receipt(order),
            "metadata": {
                "order_id": str(order.id),
            },
        },
        uuid.uuid4().hex,
    )

    order.yookassa_payment_id = payment.id
    order.yookassa_status = getattr(payment, "status", "pending")
    db.add(order)
    db.flush()

    confirmation = getattr(payment, "confirmation", None)
    confirmation_token = getattr(confirmation, "confirmation_token", None)
    if not confirmation_token:
        raise YooKassaWebhookError("YooKassa did not return confirmation_token")

    return confirmation_token


def handle_webhook(
    payload: dict[str, Any],
    signature: str | None,
    raw_body: bytes,
    db: Session,
) -> None:
    _verify_webhook_signature(raw_body, signature)

    obj = payload.get("object") or {}
    payment_id = obj.get("id")
    status = obj.get("status")

    if not payment_id:
        raise YooKassaWebhookError("Missing payment id in webhook payload")

    order = db.query(Order).filter(Order.yookassa_payment_id == payment_id).first()
    if not order:
        raise YooKassaWebhookError("Order not found for YooKassa payment")

    order.yookassa_status = status

    if status == "succeeded":
        order.payment_confirmed = True
        order.status = OrderStatus.accepted

    db.add(order)
    db.flush()
