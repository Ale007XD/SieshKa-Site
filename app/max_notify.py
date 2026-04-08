"""
MAX messenger notifications (platform-api.max.ru).
Расширение: inline_keyboard для смены статуса заказа + /answers callback.
"""

import json
import logging
from typing import Any

import httpx

from config.settings import settings
from .models import OrderStatus
from .order_status import get_next_statuses

logger = logging.getLogger(__name__)

MAX_MESSAGES_URL = "https://platform-api.max.ru/messages"
MAX_ANSWERS_URL = "https://platform-api.max.ru/answers"
_TIMEOUT = 10.0


async def send_max_message(
    user_id: int,
    text: str,
    attachments: list[dict[str, Any]] | None = None,
) -> bool:
    """
    Отправляет сообщение одному пользователю MAX.
    attachments — опциональный список (inline_keyboard и т.д.).
    Возвращает True при успехе.
    """
    if not settings.MAX_BOT_TOKEN:
        logger.warning("MAX_BOT_TOKEN not set, skipping MAX notify")
        return False

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
        return True
    except httpx.HTTPStatusError as e:
        logger.error("MAX API HTTP error for user_id=%s: %s", user_id, e.response.text)
    except httpx.RequestError as e:
        logger.error("MAX API request error for user_id=%s: %s", user_id, e)
    return False


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
    if message_text is not None:
        body["message"] = {"text": message_text}
        if attachments:
            body["message"]["attachments"] = attachments

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                MAX_ANSWERS_URL, params=params, json=body, headers=headers
            )
            resp.raise_for_status()
        return True
    except httpx.HTTPStatusError as e:
        logger.error(
            "MAX answers HTTP error for callback_id=%s: %s",
            callback_id,
            e.response.text,
        )
    except httpx.RequestError as e:
        logger.error("MAX answers request error for callback_id=%s: %s", callback_id, e)
    return False


def build_order_status_keyboard(
    order_id: int,
    current_status: OrderStatus,
) -> list[dict[str, Any]]:
    """
    Строит inline_keyboard для сообщения о заказе.
    Кнопки — допустимые следующие статусы из VALID_STATUS_TRANSITIONS.
    Возвращает пустой список если переходов нет (delivered / cancelled).
    """
    buttons_row: list[dict[str, Any]] = []
    for next_status in get_next_statuses(current_status):
        payload = json.dumps(
            {"order_id": order_id, "status": next_status.value},
            ensure_ascii=False,
        )
        buttons_row.append(
            {
                "type": "callback",
                "text": next_status.value,
                "payload": payload,
            }
        )
    if not buttons_row:
        return []
    return [
        {
            "type": "inline_keyboard",
            "payload": {"buttons": [buttons_row]},
        }
    ]


async def send_max_order_message(
    user_id: int,
    text: str,
    order_id: int,
    current_status: OrderStatus,
) -> bool:
    """Отправляет сообщение о заказе с кнопками смены статуса."""
    attachments = build_order_status_keyboard(order_id, current_status) or None
    return await send_max_message(user_id, text, attachments=attachments)


async def notify_max_staff(text: str) -> list[int]:
    """
    Рассылка всем MAX_STAFF_CHAT_IDS (без кнопок).
    Возвращает список user_id которым не удалось отправить.
    """
    failed: list[int] = []
    for uid in settings.MAX_STAFF_CHAT_IDS:
        ok = await send_max_message(uid, text)
        if not ok:
            failed.append(uid)
    return failed


async def notify_max_staff_order(
    text: str,
    order_id: int,
    current_status: OrderStatus,
) -> list[int]:
    """
    Рассылка всем MAX_STAFF_CHAT_IDS с кнопками смены статуса.
    Возвращает список user_id которым не удалось отправить.
    """
    failed: list[int] = []
    for uid in settings.MAX_STAFF_CHAT_IDS:
        ok = await send_max_order_message(uid, text, order_id, current_status)
        if not ok:
            failed.append(uid)
    return failed
