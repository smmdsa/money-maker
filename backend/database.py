"""
Database connection and session management
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from backend.models.database import Base
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./trading.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# Enable WAL mode for SQLite — allows concurrent reads while writing
# and prevents "database is locked" errors under multi-thread access.
if "sqlite" in DATABASE_URL:
    from sqlalchemy import event as sa_event

    @sa_event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database tables and run lightweight migrations."""
    Base.metadata.create_all(bind=engine)
    _run_migrations()


def _run_migrations():
    """Add missing columns to existing tables (safe for re-runs)."""
    migrations = [
        ("portfolio", "trailing_stop_pct", "REAL DEFAULT 0"),
        ("portfolio", "price_extreme", "REAL DEFAULT 0"),
        ("trading_agents", "trailing_enabled", "BOOLEAN DEFAULT 1"),
        # CCXT / execution-mode support
        ("trading_agents", "execution_mode", "TEXT DEFAULT 'paper'"),
        ("trades", "exchange_order_id", "TEXT"),
        ("trades", "exchange_fill_price", "REAL"),
        ("trades", "exchange_commission", "REAL DEFAULT 0"),
    ]
    with engine.connect() as conn:
        for table, column, col_type in migrations:
            try:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                ))
                conn.commit()
                logger.info(f"Migration: added {table}.{column}")
            except Exception:
                # Column already exists — safe to ignore
                pass

        # Backfill trailing stops for existing positions missing them
        try:
            result = conn.execute(text(
                "UPDATE portfolio "
                "SET trailing_stop_pct = CASE "
                "  WHEN stop_loss_price > 0 AND avg_buy_price > 0 "
                "    THEN ABS(stop_loss_price - avg_buy_price) / avg_buy_price * 100 "
                "  ELSE 0 END, "
                "price_extreme = avg_buy_price "
                "WHERE (trailing_stop_pct IS NULL OR trailing_stop_pct = 0) "
                "AND stop_loss_price > 0 AND amount > 0"
            ))
            conn.commit()
            if result.rowcount > 0:
                logger.info(f"Migration: backfilled trailing stops for {result.rowcount} positions")
        except Exception as e:
            logger.debug(f"Trailing backfill skipped: {e}")


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
