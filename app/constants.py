"""
Low Priority Fix: Application constants
"""
from datetime import time

# Version
VERSION = "3.0.1"

# Order Limits
MAX_QTY_PER_ITEM = 20
MAX_ITEMS_IN_CART = 50

# Rate Limiting
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_REQUESTS_PER_WINDOW = 100

# Delivery Slots
# DELIVERY_SLOTS = [
#     "10:00-12:00",
#     "12:00-14:00",
#     "14:00-16:00",
#     "16:00-18:00",
#     "18:00-20:00",
# ]

# Menu Periods
MENU_PERIOD_MORNING = "morning"
MENU_PERIOD_EVENING = "evening"
MENU_PERIOD_BOTH = "both"

# Order Statuses
ORDER_STATUS_NEW = "new"
ORDER_STATUS_ACCEPTED = "accepted"
ORDER_STATUS_COOKING = "cooking"
ORDER_STATUS_ON_THE_WAY = "on_the_way"
ORDER_STATUS_DELIVERED = "delivered"
ORDER_STATUS_CANCELLED = "cancelled"

# Payment Methods
PAYMENT_CASH = "cash"
PAYMENT_SBP = "sbp_transfer"
PAYMENT_YOOKASSA = "yookassa_card"

# Delivery Modes
DELIVERY_ASAP = "asap"
DELIVERY_SLOT = "slot"

# Validation
PHONE_PATTERN = r"^\+7\d{10}$"
MIN_ADDRESS_LENGTH = 8
MAX_ADDRESS_LENGTH = 300
MIN_NAME_LENGTH = 1
MAX_NAME_LENGTH = 120
MAX_COMMENT_LENGTH = 500

# Cache Keys
CACHE_KEY_MENU = "menu_{period}_{preview}"
CACHE_KEY_SLOTS = "slots_{date}"

# HTTP Status Codes
HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_TOO_MANY_REQUESTS = 429
HTTP_INTERNAL_ERROR = 500
HTTP_SERVICE_UNAVAILABLE = 503

# ============================================================================
# TIME-FIRST MENU SYSTEM (v4.0)
# ============================================================================

# Dayparts
DAYPART_MORNING = "MORNING"  # 07:00-10:00
DAYPART_EVENING = "EVENING"  # 14:00-21:00
DAYPART_ALLDAY = "ALLDAY"   # Always available

# Default daypart time windows
MORNING_WINDOW_START = time(7, 0)
MORNING_WINDOW_END = time(10, 0)
EVENING_WINDOW_START = time(14, 0)
EVENING_WINDOW_END = time(21, 0)

# Delivery methods
METHOD_DELIVERY = "delivery"
METHOD_PICKUP = "pickup"

# Availability scope types
SCOPE_PRODUCT = "product"
SCOPE_CATEGORY = "category"

# Unavailability reason codes
REASON_OUTSIDE_WINDOW = "OUTSIDE_WINDOW"
REASON_LEAD_TIME = "LEAD_TIME"
REASON_METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
REASON_TOMORROW_CUTOFF = "TOMORROW_CUTOFF"
REASON_INACTIVE = "INACTIVE"
REASON_NO_RULE = "NO_RULE"

# Reason code display text (Russian)
REASON_DISPLAY_TEXT = {
    REASON_OUTSIDE_WINDOW: "Вне времени приема заказов",
    REASON_LEAD_TIME: "Требуется предзаказ",
    REASON_METHOD_NOT_ALLOWED: "Недоступно для этого способа получения",
    REASON_TOMORROW_CUTOFF: "Заказы на завтра принимаются до 23:00",
    REASON_INACTIVE: "Временно недоступно",
    REASON_NO_RULE: "Нет правил доступности",
}

# Slot generation defaults
SLOT_INTERVAL_MINUTES = 15
BASE_BUFFER_MINUTES = 15

# Tomorrow ordering
TOMORROW_CUTOFF_TIME = time(23, 0)
DEFAULT_BUSINESS_TZ = "Asia/Irkutsk"

# Cache TTLs (seconds)
MENU_CACHE_TTL_SECONDS = 60
SLOTS_CACHE_TTL_SECONDS = 60
CACHE_LOCK_TTL_SECONDS = 10

# Cache key patterns
CACHE_KEY_MENU_NEW = "menu:{day}:{method}:{slot}:{tz}:{version}"
CACHE_KEY_SLOTS_NEW = "slots:{day}:{method}:{tz}:{version}"
CACHE_KEY_LOCK = "lock:{key}"
