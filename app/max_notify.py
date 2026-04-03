"""
MAX messenger notifications (platform-api.max.ru).
Replaces Telegram for staff notifications in RF.
"""

import logging
import httpx
from config.settings import settings

logger = logging.getLogger(__name__)

MAX_API_URL = "https://platform-api.max.ru/messages"
_TIMEOUT = 10.0


async def send_max_message(user_id: int, text: str) -> bool:
    """
    Send message to a single MAX user.
    Returns True on success, False on any error.
    """
    if not settings.MAX_BOT_TOKEN:
        logger.warning("MAX_BOT_TOKEN not set, skipping MAX notify")
        return False

    headers = {"Authorization": settings.MAX_BOT_TOKEN}
    payload = {"user_id": user_id, "text": text}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(MAX_API_URL, json=payload, headers=headers)
            resp.raise_for_status()
            return True
    except httpx.HTTPStatusError as e:
        logger.error("MAX API HTTP error for user_id=%s: %s", user_id, e.response.text)
    except httpx.RequestError as e:
        logger.error("MAX API request error for user_id=%s: %s", user_id, e)
    return False


async def notify_max_staff(text: str) -> list[int]:
    """
    Broadcast message to all MAX_STAFF_CHAT_IDS.
    Returns list of user_ids that failed.
    """
    failed: list[int] = []
    for uid in settings.MAX_STAFF_CHAT_IDS:
        ok = await send_max_message(uid, text)
        if not ok:
            failed.append(uid)
    return failed
