"""
Low Priority Fix: Application constants
"""
from datetime import time

# Version
VERSION = "3.0.0"

# Order Limits
MAX_QTY_PER_ITEM = 20
MAX_ITEMS_IN_CART = 50

# Delivery Slots
DELIVERY_SLOTS = [
    "10:00-12:00",
    "12:00-14:00",
    "14:00-16:00",
    "16:00-18:00",
    "18:00-20:00",
]

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
