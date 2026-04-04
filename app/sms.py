"""
SMS notifications via smsc.ru.
Parallel staff notification channel.
"""

import logging
import httpx
from config.settings import settings

logger = logging.getLogger(__name__)

SMSC_URL = "https://smsc.ru/sys/send.php"
_TIMEOUT = 10.0
_SMS_MAX_LEN = 70  # 1 СМС кириллицей


def _truncate(text: str) -> str:
    return text[:_SMS_MAX_LEN]


async def send_sms(phone: str, text: str) -> bool:
    """
    Send SMS to a single phone via smsc.ru.
    phone — E.164 format (+79XXXXXXXXX).
    Returns True on success, False on any error.
    """
    if not settings.SMSC_LOGIN or not settings.SMSC_PASSWORD:
        logger.warning("SMSC credentials not set, skipping SMS")
        return False

    params = {
        "login": settings.SMSC_LOGIN,
        "psw": settings.SMSC_PASSWORD,
        "phones": phone,
        "mes": _truncate(text),
        "charset": "utf-8",
        "fmt": "3",  # JSON response
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(SMSC_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                logger.error("SMSC error for %s: %s", phone, data)
                return False
            return True
    except httpx.HTTPStatusError as e:
        logger.error("SMSC HTTP error for %s: %s", phone, e.response.text)
    except httpx.RequestError as e:
        logger.error("SMSC request error for %s: %s", phone, e)
    return False


async def notify_sms_staff(text: str) -> list[str]:
    """
    Send SMS to all STAFF_PHONES.
    Returns list of phones that failed.
    """
    failed: list[str] = []
    for phone in settings.STAFF_PHONES:
        ok = await send_sms(phone, text)
        if not ok:
            failed.append(phone)
    return failed
