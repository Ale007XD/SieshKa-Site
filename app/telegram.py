import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

# Circuit breaker pattern for external service
class CircuitBreaker:
    """Circuit breaker pattern to prevent cascading failures"""
    
    def __init__(self, failure_threshold=5, timeout=60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._lock = asyncio.Lock()
    
    async def call(self, func, *args, **kwargs):
        async with self._lock:
            if self.state == "OPEN":
                if self.last_failure_time and datetime.now() - self.last_failure_time > timedelta(seconds=self.timeout):
                    self.state = "HALF_OPEN"
                    logger.info("Circuit breaker entering HALF_OPEN state")
                else:
                    raise Exception("Circuit breaker is OPEN")
            # Capture state to avoid race condition
            initial_state = self.state
        
        try:
            result = await func(*args, **kwargs)
            async with self._lock:
                # Use captured state instead of current state to avoid race
                if initial_state == "HALF_OPEN" or self.state == "HALF_OPEN":
                    self.state = "CLOSED"
                    self.failure_count = 0
                    logger.info("Circuit breaker closed after successful call")
            return result
        except Exception as e:
            async with self._lock:
                self.failure_count += 1
                self.last_failure_time = datetime.now()
                
                if self.failure_count >= self.failure_threshold:
                    self.state = "OPEN"
                    logger.error(f"Circuit breaker opened after {self.failure_count} failures")
            raise

telegram_circuit = CircuitBreaker(failure_threshold=3, timeout=300)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
MANAGER_CHAT = os.getenv("TG_MANAGER_CHAT_ID", "")
KITCHEN_CHAT = os.getenv("TG_KITCHEN_CHAT_ID", "")

# Dead letter queue for failed notifications
failed_notifications = []
MAX_FAILED_QUEUE_SIZE = 100

def _enabled() -> bool:
    return bool(BOT_TOKEN and MANAGER_CHAT and KITCHEN_CHAT)

async def send_message(chat_id: str, text: str, max_retries: int = 3) -> Optional[bool]:
    """Send message to Telegram with circuit breaker and retry logic"""
    if not _enabled():
        logger.warning("Telegram not configured, skipping notification")
        return None
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    async def _send():
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                url, 
                json={
                    "chat_id": chat_id, 
                    "text": text,
                    "parse_mode": "HTML"
                }
            )
            response.raise_for_status()
            return response.json()
    
    for attempt in range(max_retries):
        try:
            result = await telegram_circuit.call(_send)
            logger.info(f"Telegram message sent to {chat_id}")
            return True
        except httpx.TimeoutException:
            logger.warning(f"Telegram timeout (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        except httpx.HTTPError as e:
            logger.error(f"Telegram HTTP error: {e}")
            break
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            if "Circuit breaker is OPEN" in str(e):
                _add_to_dlq(chat_id, text)
            break
    
    _add_to_dlq(chat_id, text)
    return False

def _add_to_dlq(chat_id: str, text: str):
    """Add failed notification to dead letter queue"""
    global failed_notifications
    failed_notifications.append({
        "chat_id": chat_id,
        "text": text,
        "timestamp": datetime.now().isoformat()
    })
    
    if len(failed_notifications) > MAX_FAILED_QUEUE_SIZE:
        failed_notifications = failed_notifications[-MAX_FAILED_QUEUE_SIZE:]
    
    logger.warning(f"Added notification to DLQ. Queue size: {len(failed_notifications)}")

async def notify_both(text: str) -> None:
    """Send notification to both manager and kitchen"""
    safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    await send_message(MANAGER_CHAT, safe_text)
    await send_message(KITCHEN_CHAT, safe_text)

async def notify_order_status(order_id: int, status: str) -> None:
    """Notify about order status change"""
    text = f"Заказ #{order_id}: статус → {status}"
    await notify_both(text)

async def retry_failed_notifications() -> int:
    """Retry sending failed notifications from DLQ"""
    global failed_notifications
    
    if not failed_notifications:
        return 0
    
    successful = 0
    still_failed = []
    
    for notification in failed_notifications:
        result = await send_message(notification["chat_id"], notification["text"], max_retries=1)
        if result:
            successful += 1
        else:
            still_failed.append(notification)
    
    failed_notifications = still_failed
    logger.info(f"Retry complete. Successful: {successful}, Still failed: {len(still_failed)}")
    return successful

def get_failed_notifications_count() -> int:
    """Get count of failed notifications in DLQ"""
    return len(failed_notifications)
