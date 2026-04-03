import os
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.exc import DisconnectionError
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# Connection pooling with proper settings
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    echo=os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true",
)


@event.listens_for(engine, "connect")
def on_connect(dbapi_conn, connection_record):
    logger.debug("Database connection established")


@event.listens_for(engine, "checkout")
def on_checkout(dbapi_conn, connection_record, connection_proxy):
    logger.debug("Database connection checked out from pool")


@event.listens_for(engine, "checkin")
def on_checkin(dbapi_conn, connection_record):
    logger.debug("Database connection returned to pool")


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


# Retry decorator for database operations
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry_error_callback=lambda retry_state: logger.error(
        f"Database operation failed after {retry_state.attempt_number} attempts"
    ),
)
def execute_with_retry(session, operation):
    """Execute database operation with retry logic"""
    try:
        return operation()
    except DisconnectionError:
        logger.warning("Database disconnection detected, retrying...")
        raise
