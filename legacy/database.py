"""SQLite local cache — optional fallback, not the primary data store."""

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional

from config import Config

logger = logging.getLogger("smart_env_monitor.database")

DB_PATH = Path(getattr(Config, "DB_PATH", Config.DB_NAME))
DB_NAME = str(DB_PATH)


def _ensure_parent_dir() -> None:
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning("Could not create DB parent directory %s: %s", DB_PATH.parent, exc)


def create_connection() -> sqlite3.Connection:
    _ensure_parent_dir()
    conn = sqlite3.connect(DB_NAME, timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
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


def init_db() -> None:
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


def insert_sensor_data(
    temperature: float,
    humidity: float,
    pressure: float,
    timestamp: Optional[str] = None,
) -> bool:
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with get_connection() as conn:
            conn.execute("""
            INSERT INTO sensor_data (timestamp, temperature, humidity, pressure)
            VALUES (?, ?, ?, ?)
            """, (timestamp, temperature, humidity, pressure))
        return True
    except Exception as exc:
        logger.warning("Insert sensor data failed: %s", exc)
        return False


def fetch_one(query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
    try:
        with create_connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchone()
    except Exception as exc:
        logger.exception("fetch_one failed: %s", exc)
        return None


def fetch_all(query: str, params: tuple = ()) -> List[sqlite3.Row]:
    try:
        with create_connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall()
    except Exception as exc:
        logger.exception("fetch_all failed: %s", exc)
        return []


def get_latest_data() -> Optional[sqlite3.Row]:
    return fetch_one("SELECT * FROM sensor_data ORDER BY id DESC LIMIT 1")


def get_recent_temperature_data(limit: int = 20) -> List[sqlite3.Row]:
    rows = fetch_all("""
        SELECT timestamp, temperature FROM sensor_data ORDER BY id DESC LIMIT ?
    """, (limit,))
    return list(reversed(rows))


def get_recent_sensor_data(limit: int = 10) -> List[sqlite3.Row]:
    rows = fetch_all("SELECT * FROM sensor_data ORDER BY id DESC LIMIT ?", (limit,))
    return list(reversed(rows))


def get_settings() -> Optional[sqlite3.Row]:
    return fetch_one("SELECT * FROM settings WHERE id = 1")


def update_settings(
    temp_min: float,
    temp_max: float,
    humidity_min: float,
    humidity_max: float,
    pressure_min: float,
    pressure_max: float
) -> bool:
    try:
        with get_connection() as conn:
            conn.execute("""
            UPDATE settings
            SET temp_min = ?, temp_max = ?,
                humidity_min = ?, humidity_max = ?,
                pressure_min = ?, pressure_max = ?
            WHERE id = 1
            """, (temp_min, temp_max, humidity_min, humidity_max, pressure_min, pressure_max))
        logger.info("Settings updated successfully.")
        return True
    except Exception as exc:
        logger.exception("Update settings failed: %s", exc)
        return False
