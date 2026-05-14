import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional

from config import Config

# set up logger
logger = logging.getLogger("smart_env_monitor.database")

# Resolve to an absolute path (Config.DB_PATH already anchors relative names
# to the project root). Keep DB_NAME as the public alias for back-compat.
DB_PATH = Path(getattr(Config, "DB_PATH", Config.DB_NAME))
DB_NAME = str(DB_PATH)


def _ensure_parent_dir() -> None:
    """Create the directory holding the SQLite file if it does not exist."""
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning("Could not create DB parent directory %s: %s", DB_PATH.parent, exc)


# open a new sqlite connection
def create_connection() -> sqlite3.Connection:
    """
    Create a new SQLite connection with row factory enabled.

    Cross-platform: uses an absolute path derived from PROJECT_ROOT so the
    same DB is used regardless of the caller's working directory.
    """
    _ensure_parent_dir()
    # `check_same_thread=False` lets the background sensor thread share the
    # connection layer safely (we open a fresh connection per call anyway).
    conn = sqlite3.connect(DB_NAME, timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# database connection wrapper
@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """
    Context-managed SQLite connection.

    Automatically commits or rolls back transactions.
    """
    conn = create_connection()
    try:
        yield conn
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("Database transaction failed: %s", exc)
        raise
    finally:
        conn.close()

# create tables and default settings
def init_db() -> None:
    """
    Initialize database schema and default values.

    Safe to call multiple times; uses CREATE TABLE IF NOT EXISTS / INSERT OR
    IGNORE so it is idempotent.
    """
    _ensure_parent_dir()
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS sensor_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                temperature REAL NOT NULL,
                humidity REAL NOT NULL,
                pressure REAL NOT NULL
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                temp_min REAL NOT NULL,
                temp_max REAL NOT NULL,
                humidity_min REAL NOT NULL,
                humidity_max REAL NOT NULL,
                pressure_min REAL NOT NULL,
                pressure_max REAL NOT NULL
            )
            """)

            cursor.execute("""
            INSERT OR IGNORE INTO settings
            (id, temp_min, temp_max, humidity_min, humidity_max, pressure_min, pressure_max)
            VALUES (1, 0, 40, 10, 90, 970, 1030)
            """)

        logger.info("Database initialized successfully.")

    except Exception as exc:
        logger.exception("Database initialization failed: %s", exc)


# save one reading
def insert_sensor_data(
    temperature: float,
    humidity: float,
    pressure: float,
    timestamp: Optional[str] = None,
) -> bool:
    """
    Insert one sensor reading into the database.

    If `timestamp` is omitted, a local-time wall-clock string in the form
    "YYYY-MM-DD HH:MM:SS" is generated. Using an explicit timestamp keeps
    the values stored in SQLite in sync with what Python's logger prints
    (both use the local clock).
    """
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with get_connection() as conn:
            conn.execute("""
            INSERT INTO sensor_data (timestamp, temperature, humidity, pressure)
            VALUES (?, ?, ?, ?)
            """, (timestamp, temperature, humidity, pressure))

        logger.debug(
            "Inserted sensor data @ %s: T=%.2f H=%.2f P=%.2f",
            timestamp, temperature, humidity, pressure,
        )
        return True
    except Exception as exc:
        logger.warning("Insert sensor data failed: %s", exc)
        return False

# get one row from query
def fetch_one(query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
    """
    Execute a query and return a single row.
    """
    try:
        with create_connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchone()
    except Exception as exc:
        logger.exception("fetch_one failed: %s", exc)
        return None
# get all rows from query
def fetch_all(query: str, params: tuple = ()) -> List[sqlite3.Row]:
    """
    Execute a query and return all rows.
    """
    try:
        with create_connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall()
    except Exception as exc:
        logger.exception("fetch_all failed: %s", exc)
        return []

# get latest reading
def get_latest_data() -> Optional[sqlite3.Row]:
    """
    Get the latest sensor reading.
    """
    return fetch_one("""
        SELECT *
        FROM sensor_data
        ORDER BY id DESC
        LIMIT 1
    """)
# get recent temperature data
def get_recent_temperature_data(limit: int = 20) -> List[sqlite3.Row]:
    """
    Get recent temperature history in chronological order.
    """
    rows = fetch_all("""
        SELECT timestamp, temperature
        FROM sensor_data
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))

    return list(reversed(rows))

# get recent sensor data
def get_recent_sensor_data(limit: int = 10) -> List[sqlite3.Row]:
    """
    Get recent sensor readings in chronological order.
    """
    rows = fetch_all("""
        SELECT *
        FROM sensor_data
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))

    return list(reversed(rows))
# read current settings
def get_settings() -> Optional[sqlite3.Row]:
    """
    Get current threshold settings.
    """
    return fetch_one("SELECT * FROM settings WHERE id = 1")

# update threshold values
def update_settings(
    temp_min: float,
    temp_max: float,
    humidity_min: float,
    humidity_max: float,
    pressure_min: float,
    pressure_max: float
) -> bool:
    """
    Update threshold settings.
    """
    try:
        with get_connection() as conn:
            conn.execute("""
            UPDATE settings
            SET temp_min = ?,
                temp_max = ?,
                humidity_min = ?,
                humidity_max = ?,
                pressure_min = ?,
                pressure_max = ?
            WHERE id = 1
            """, (
                temp_min,
                temp_max,
                humidity_min,
                humidity_max,
                pressure_min,
                pressure_max
            ))

        logger.info("Settings updated successfully.")
        return True

    except Exception as exc:
        logger.exception("Update settings failed: %s", exc)
        return False