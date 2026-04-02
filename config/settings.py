"""
Low Priority Fix: Application configuration module using pydantic-settings
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List, Optional


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # App
    APP_NAME: str = "Sieshka"
    APP_VERSION: str = "3.0.0"
    DEBUG: bool = False
    ENV: str = "production"
    
    # URLs
    BASE_URL: str = "https://siesh-ka.ru"
    
    # Database
    DATABASE_URL: str
    
    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    
    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TG_MANAGER_CHAT_ID: Optional[str] = None
    TG_KITCHEN_CHAT_ID: Optional[str] = None
    
    # Menu Schedule
    TZ_NAME: str = "Asia/Irkutsk"
    MORNING_START: str = "07:00"
    MORNING_END: str = "10:00"
    EVENING_MENU_START: str = "10:00"  # Время показа вечернего меню
    EVENING_START: str = "15:00"  # Время начала доставки вечернего меню
    EVENING_END: str = "21:00"
    
    # Delivery
    ASAP_TEXT: str = "15–25 минут"
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 10
    PHONE_RATE_LIMIT_PER_MINUTE: int = 3
    
    # Cache
    MENU_CACHE_TTL: int = 60  # seconds
    
    # Security
    ALLOWED_HOSTS: List[str] = ["siesh-ka.ru", "*.siesh-ka.ru", "localhost", "127.0.0.1"]
    
    # Backup
    BACKUP_RETENTION_DAYS: int = 7
    
    # Logging
    LOG_LEVEL: str = "INFO"
    SQLALCHEMY_ECHO: bool = False
    
    # Time-First Menu System (v4.0)
    BUSINESS_TZ: str = "Asia/Irkutsk"
    TOMORROW_ORDER_CUTOFF: str = "22:00"
    ENABLE_TOMORROW_ORDERS: bool = True
    SLOT_INTERVAL_MINUTES: int = 15
    BASE_BUFFER_MINUTES: int = 15
    MENU_VERSION: int = 1

    # MAX Messenger
    MAX_BOT_TOKEN: Optional[str] = None
    MAX_STAFF_CHAT_IDS: List[int] = []

    # SMS (smsc.ru)
    SMSC_LOGIN: Optional[str] = None
    SMSC_PASSWORD: Optional[str] = None
    STAFF_PHONES: List[str] = []
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


settings = get_settings()
