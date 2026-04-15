"""
MAX messenger notifications (platform-api.max.ru).
Расширение: inline_keyboard для смены статуса заказа + /answers callback.
Расширение v2: кнопка статуса оплаты (🟠/🟢), редактирование сообщений.
"""

import json
import logging
from typing import Any

import httpx

from config.settings import settings
from .models import OrderStatus, PaymentMethod
from .order_status import get_next_statuses

logger = logging.getLogger(__name__)

MAX_MESSAGES_URL = "https://platform-api.max.ru/messages"
MAX_ANSWERS_URL = "https://platform-api.max.ru/answers"
_TIMEOUT = 10.0

# Русские метки и цвета кнопок (intent: positive=зелёный, negative=красный, default=синий/серый)
_STATUS_LABEL: dict[OrderStatus, tuple[str, str]] = {
    OrderStatus.new:        ("🟠 НОВЫЙ",       "default"),
    OrderStatus.accepted:   ("🔵 ПРИНЯТ",      "default"),
    OrderStatus.cooking:    ("👨‍🍳 ГОТОВИТСЯ",  "default"),
    OrderStatus.on_the_way: ("🛵 В ПУТИ",      "default"),
    OrderStatus.delivered:  ("✅ ДОСТАВЛЕН",   "positive"),
    OrderStatus.cancelled:  ("❌ ОТМЕНИТЬ",    "negative"),
}


async def send_max_message(
    user_id: int,
    text: str,
    attachments: list[dict[str, Any]] | None = None,
) -> str | None:
    """
    Отправляет сообщение пользователю MAX через /messages.
    Возвращает message_id (mid) при успехе, None при ошибке.
    """
    if not settings.MAX_BOT_TOKEN:
        logger.warning("MAX_BOT_TOKEN not set, skipping MAX notify")
        return None

    headers = {
        "Authorization": settings.MAX_BOT_TOKEN,
        "Content-Type": "application/json",
    }
    params: dict[str, Any] = {"user_id": user_id}
    body: dict[str, Any] = {"text": text}
    if attachments:
        body["attachments"] = attachments

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                MAX_MESSAGES_URL, params=params, json=body, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
            # MAX иногда возвращает success=false, но сообщение доставлено —
            # это видно по наличию message.body.mid в ответе (баг MAX API
            # при отправке сообщений с inline_keyboard).
            mid = (data.get("message") or {}).get("body", {}).get("mid")
            delivered = data.get("success") or bool(mid)
            if not delivered:
                logger.error(
                    "MAX messages API returned success=false for user_id=%s: %s",
                    user_id,
                    data,
                )
                return None
            logger.info(
                "MAX messages OK for user_id=%s mid=%s",
                user_id,
                mid or "?",
            )
        return mid  # str | None
    except httpx.HTTPStatusError as e:
        logger.error(
            "MAX messages HTTP error for user_id=%s: %s",
            user_id,
            e.response.text,
        )
    except ValueError as e:
        logger.error("MAX messages JSON parse error for user_id=%s: %s", user_id, e)
    except httpx.RequestError as e:
        logger.error("MAX messages request error for user_id=%s: %s", user_id, e)
    return None


async def answer_max_callback(
    callback_id: str,
    notification: str | None = None,
    message_text: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> bool:
    """
    Подтверждает callback кнопки через /answers.
    notification — всплывающая подпись (до 64 символов).
    message_text — если нужно обновить текст сообщения.
    """
    if not settings.MAX_BOT_TOKEN:
        logger.warning("MAX_BOT_TOKEN not set, skipping callback answer")
        return False

    headers = {
        "Authorization": settings.MAX_BOT_TOKEN,
        "Content-Type": "application/json",
    }
    params: dict[str, Any] = {"callback_id": callback_id}
    body: dict[str, Any] = {}
    if notification:
        body["notification"] = notification
    if message_text is not None or attachments is not None:
        body["message"] = {}
        if message_text is not None:
            body["message"]["text"] = message_text
        body["message"]["attachments"] = attachments or []

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                MAX_ANSWERS_URL, params=params, json=body, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success", False):
                logger.error(
                    "MAX answers API returned success=false for callback_id=%s: %s",
                    callback_id,
                    data,
                )
                return False
            logger.info("MAX answers OK for callback_id=%s: %s", callback_id, data)
            return True
    except httpx.HTTPStatusError as e:
        logger.error(
            "MAX answers HTTP error for callback_id=%s: %s",
            callback_id,
            e.response.text,
        )
    except ValueError as e:
        logger.error(
            "MAX answers JSON parse error for callback_id=%s: %s", callback_id, e
        )
    except httpx.RequestError as e:
        logger.error("MAX answers request error for callback_id=%s: %s", callback_id, e)
    return False


def build_payment_button(
    order_id: int,
    payment_confirmed: bool,
    payment_method: PaymentMethod,
) -> dict[str, Any]:
    """
    Заметная кнопка статуса оплаты.
    cash — кликабельна (toggle). ЮКасса/СБП — индикатор (pay_info).
    """
    if payment_confirmed:
        text = "🟢 ОПЛАЧЕНО"
        intent = "positive"
    else:
        text = "🟠 ОЖИДАЕТ ОПЛАТЫ"
        intent = "default"

    action = "pay_toggle" if payment_method == PaymentMethod.cash else "pay_info"
    return {
        "type": "callback",
        "text": text,
        "intent": intent,
        "payload": json.dumps({"order_id": order_id, "action": action}),
    }


def build_order_status_keyboard(
    order_id: int,
    current_status: OrderStatus,
    payment_confirmed: bool = False,
    payment_method: PaymentMethod | None = None,
) -> list[dict[str, Any]]:
    """
    Строит inline_keyboard с двумя рядами кнопок:
      - Ряд 1 (если payment_method передан): заметная кнопка статуса оплаты
      - Ряд 2: кнопки допустимых переходов статуса заказа
    """
    buttons_rows: list[list[dict[str, Any]]] = []

    # Ряд 1 — кнопка оплаты
    if payment_method is not None:
        buttons_rows.append(
            [build_payment_button(order_id, payment_confirmed, payment_method)]
        )

    # Ряд 2 — смена статуса заказа
    status_row: list[dict[str, Any]] = []
    for next_status in get_next_statuses(current_status):
        label, intent = _STATUS_LABEL.get(
            next_status, (next_status.value.upper(), "default")
        )
        payload = json.dumps(
            {"order_id": order_id, "status": next_status.value},
            ensure_ascii=False,
        )
        status_row.append(
            {"type": "callback", "text": label, "intent": intent, "payload": payload}
        )
    if status_row:
        buttons_rows.append(status_row)

    if not buttons_rows:
        return []

    return [{"type": "inline_keyboard", "payload": {"buttons": buttons_rows}}]


async def send_max_order_message(
    user_id: int,
    text: str,
    order_id: int,
    current_status: OrderStatus,
    payment_confirmed: bool = False,
    payment_method: PaymentMethod | None = None,
) -> str | None:
    """Отправляет сообщение о заказе с кнопками статуса и оплаты. Возвращает mid."""
    attachments = (
        build_order_status_keyboard(
            order_id, current_status, payment_confirmed, payment_method
        )
        or None
    )
    return await send_max_message(user_id, text, attachments=attachments)


async def notify_client_status_update(
    client_max_uid: int,
    order_number: str,
    new_status: "OrderStatus",
) -> bool:
    """
    Уведомляет клиента о смене статуса заказа.
    Вызывается из update_order_status_endpoint после успешного перехода.
    """
    _STATUS_CLIENT_TEXT: dict[OrderStatus, str] = {
        OrderStatus.accepted:   "✅ Ваш заказ #{num} принят и передан на кухню.",
        OrderStatus.cooking:    "👨‍🍳 Ваш заказ #{num} готовится.",
        OrderStatus.on_the_way: "🛵 Ваш заказ #{num} уже в пути!",
        OrderStatus.delivered:  "🎉 Ваш заказ #{num} доставлен. Приятного аппетита!",
        OrderStatus.cancelled:  "❌ Ваш заказ #{num} отменён. Свяжитесь с нами если это ошибка.",
    }
    text = _STATUS_CLIENT_TEXT.get(new_status)
    if not text:
        return False  # new/промежуточные статусы клиенту не шлём
    mid = await send_max_message(client_max_uid, text.format(num=order_number))
    return mid is not None


async def send_max_start_reply(user_id: int, menu_url: str, welcome_text: str) -> bool:
    """
    Отвечает на /start клиентским приветствием и кнопкой-ссылкой на меню.
    """
    attachments = [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [{"type": "link", "text": "🍱 Открыть меню", "url": menu_url}]
                ]
            },
        }
    ]
    mid = await send_max_message(user_id, welcome_text, attachments=attachments)
    return mid is not None


async def notify_max_staff(text: str) -> list[int]:
    """
    Рассылка всем MAX_STAFF_CHAT_IDS (без кнопок).
    Возвращает список user_id которым не удалось отправить.
    """
    failed: list[int] = []
    for uid in settings.MAX_STAFF_CHAT_IDS:
        mid = await send_max_message(uid, text)
        if mid is None:
            failed.append(uid)
    return failed


async def notify_max_staff_order(
    text: str,
    order_id: int,
    current_status: OrderStatus,
    payment_confirmed: bool = False,
    payment_method: PaymentMethod | None = None,
) -> tuple[dict[int, str], list[int]]:
    """
    Рассылка всем MAX_STAFF_CHAT_IDS с кнопками статуса и оплаты.
    Возвращает (message_ids_map, failed_uids).
    message_ids_map: {user_id: mid} — для последующего редактирования.
    """
    message_ids: dict[int, str] = {}
    failed: list[int] = []
    for uid in settings.MAX_STAFF_CHAT_IDS:
        mid = await send_max_order_message(
            uid, text, order_id, current_status, payment_confirmed, payment_method
        )
        if mid is not None:
            message_ids[uid] = mid
        else:
            failed.append(uid)
    return message_ids, failed


async def edit_max_message(
    message_id: str,
    text: str,
    attachments: list[dict[str, Any]] | None = None,
) -> bool:
    """Редактирует существующее MAX-сообщение через PUT /messages."""
    if not settings.MAX_BOT_TOKEN:
        logger.warning("MAX_BOT_TOKEN not set, skipping message edit")
        return False

    headers = {
        "Authorization": settings.MAX_BOT_TOKEN,
        "Content-Type": "application/json",
    }
    params: dict[str, Any] = {"message_id": message_id}
    body: dict[str, Any] = {"text": text}
    if attachments:
        body["attachments"] = attachments

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.put(
                MAX_MESSAGES_URL, params=params, json=body, headers=headers
            )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success", False):
            logger.error(
                "MAX PUT messages success=false for mid=%s: %s", message_id, data
            )
        return data.get("success", False)
    except httpx.HTTPStatusError as e:
        logger.error(
            "MAX PUT messages HTTP error for mid=%s: %s", message_id, e.response.text
        )
    except Exception as e:
        logger.error("MAX PUT messages error for mid=%s: %s", message_id, e)
    return False


async def edit_max_order_payment_status(
    max_message_ids_json: str,
    message_text: str,
    order_id: int,
    current_status: OrderStatus,
    payment_confirmed: bool,
    payment_method: PaymentMethod,
) -> None:
    """
    Обновляет кнопку оплаты во всех MAX-сообщениях заказа.
    Вызывается: при YooKassa webhook succeeded + при ручном pay_toggle (cash).
    max_message_ids_json: JSON {"<user_id>": "<mid>", ...} из order.max_message_ids.
    """
    try:
        mids: dict[str, str] = json.loads(max_message_ids_json)
    except (ValueError, TypeError):
        logger.warning("edit_max_order_payment_status: некорректный max_message_ids_json")
        return

    keyboard = build_order_status_keyboard(
        order_id, current_status, payment_confirmed, payment_method
    )
    attachments = keyboard or None

    for mid in mids.values():
        if mid:
            await edit_max_message(mid, message_text, attachments)
