"""
Staff notifications aggregator.
Drop-in replacement для telegram.notify_both().
Channels: MAX + SMS (parallel).
DLQ для MAX-ошибок: Redis list dlq:max.
"""

import json
import logging
import asyncio
from datetime import datetime
from typing import Optional

from .max_notify import (
    notify_max_staff,
    notify_max_staff_order,
    send_max_message,
    build_order_status_keyboard,
)
from .models import OrderStatus
from .sms import notify_sms_staff

logger = logging.getLogger(__name__)

_redis = None
_dlq_task: Optional[asyncio.Task] = None


def init_notifications(redis_client) -> None:
    """Инжектирует Redis-клиент. Вызывается один раз из lifespan после инициализации Redis."""
    global _redis
    _redis = redis_client


async def _push_failed_max_to_dlq(
    failed_uids: list[int],
    text: str,
    attachments: list | None = None,
) -> None:
    """Пушит неудавшиеся MAX-доставки в DLQ."""
    if not failed_uids or not _redis:
        return
    for uid in failed_uids:
        entry = json.dumps(
            {
                "user_id": uid,
                "text": text,
                "attachments": attachments or [],
                "timestamp": datetime.now().isoformat(),
                "retries": 0,
            }
        )
        await _redis.rpush("dlq:max", entry)
        logger.warning("MAX failed for uid=%s → pushed to dlq:max", uid)


async def notify_both(text: str) -> None:
    """
    Drop-in replacement для telegram.notify_both(text).
    Отправляет уведомления через MAX и SMS параллельно.
    Неудавшиеся MAX-доставки попадают в Redis dlq:max.
    """
    failed_uids, failed_phones = await asyncio.gather(
        notify_max_staff(text),
        notify_sms_staff(text),
    )
    if failed_phones:
        logger.warning("SMS failed for phones=%s", failed_phones)
    await _push_failed_max_to_dlq(failed_uids, text, attachments=None)


async def notify_order_to_staff(
    text: str,
    order_id: int,
    current_status: OrderStatus,
) -> None:
    """
    Уведомление о заказе с кнопками смены статуса (MAX) + SMS параллельно.
    Используется вместо notify_both при создании/обновлении заказа.
    """
    attachments = build_order_status_keyboard(order_id, current_status) or None
    failed_uids, failed_phones = await asyncio.gather(
        notify_max_staff_order(text, order_id, current_status),
        notify_sms_staff(text),
    )
    if failed_phones:
        logger.warning("SMS failed for phones=%s", failed_phones)
    await _push_failed_max_to_dlq(failed_uids, text, attachments=attachments)


async def get_failed_notifications_count() -> int:
    """Размер DLQ из Redis. Async-замена sync get_failed_notifications_count() из telegram.py."""
    if _redis:
        try:
            return await _redis.llen("dlq:max")
        except Exception as e:
            logger.error("Redis llen dlq:max error: %s", e)
    return 0


async def _dlq_worker() -> None:
    """Ретраит dlq:max каждые 60 секунд."""
    while True:
        await asyncio.sleep(60)
        if not _redis:
            continue
        try:
            retried = 0
            while True:
                item = await _redis.lpop("dlq:max")
                if not item:
                    break
                try:
                    data = json.loads(item)
                    if data.get("retries", 0) >= 5:
                        logger.error(
                            "DLQ: dropping after 5 retries for uid=%s",
                            data.get("user_id"),
                        )
                        break
                    attachments = data.get("attachments") or None
                    ok = await send_max_message(
                        data["user_id"], data["text"], attachments=attachments
                    )
                    if ok:
                        retried += 1
                    else:
                        data["retries"] = data.get("retries", 0) + 1
                        await _redis.rpush("dlq:max", json.dumps(data))
                        break
                except Exception as e:
                    logger.error("DLQ item processing error: %s", e)
                    await _redis.rpush("dlq:max", item)
                    break
            if retried:
                logger.info("DLQ worker: retried %d MAX notifications", retried)
        except Exception as e:
            logger.error("DLQ worker cycle error: %s", e)


def start_dlq_worker() -> asyncio.Task:
    """Запускает фоновую DLQ-задачу. Вызывается из lifespan."""
    global _dlq_task
    _dlq_task = asyncio.create_task(_dlq_worker())
    logger.info("DLQ worker started")
    return _dlq_task


def stop_dlq_worker() -> None:
    """Отменяет DLQ-задачу. Вызывается из lifespan cleanup."""
    if _dlq_task and not _dlq_task.done():
        _dlq_task.cancel()
        logger.info("DLQ worker stopped")
