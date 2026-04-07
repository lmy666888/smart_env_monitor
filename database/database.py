import sqlite3
from typing import Optional, List

from config import Config

DB_NAME = Config.DB_NAME


def get_connection() -> sqlite3.Connection:
    """
    Create and return a SQLite connection.
    """
    conn = sqlite3.connect(DB_NAME, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """
    Initialize the database and create required tables if they do not exist.
    Also insert default threshold settings.
    """
    conn = None
    try:
        conn = get_connection()
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

        conn.commit()
    except Exception as e:
        print(f"[DB INIT ERROR] {e}")
    finally:
        if conn:
            conn.close()


def insert_sensor_data(temperature: float, humidity: float, pressure: float) -> bool:
    """
    Insert one sensor reading into the database.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO sensor_data (temperature, humidity, pressure)
        VALUES (?, ?, ?)
        """, (temperature, humidity, pressure))
        conn.commit()
        return True
    except Exception as e:
        print(f"[DB INSERT ERROR] {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_latest_data() -> Optional[sqlite3.Row]:
    """
    Get the latest sensor reading.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT *
        FROM sensor_data
        ORDER BY id DESC
        LIMIT 1
        """)
        return cursor.fetchone()
    except Exception as e:
        print(f"[DB FETCH LATEST ERROR] {e}")
        return None
    finally:
        if conn:
            conn.close()


def get_recent_temperature_data(limit: int = 20) -> List[sqlite3.Row]:
    """
    Get recent temperature history for chart display.
    Results are returned in chronological order.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT timestamp, temperature
        FROM sensor_data
        ORDER BY id DESC
        LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return list(reversed(rows))
    except Exception as e:
        print(f"[DB FETCH TEMP HISTORY ERROR] {e}")
        return []
    finally:
        if conn:
            conn.close()


def get_recent_sensor_data(limit: int = 10) -> List[sqlite3.Row]:
    """
    Get recent full sensor readings in chronological order.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT *
        FROM sensor_data
        ORDER BY id DESC
        LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return list(reversed(rows))
    except Exception as e:
        print(f"[DB FETCH SENSOR HISTORY ERROR] {e}")
        return []
    finally:
        if conn:
            conn.close()


def get_settings() -> Optional[sqlite3.Row]:
    """
    Get current warning threshold settings.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM settings WHERE id = 1")
        return cursor.fetchone()
    except Exception as e:
        print(f"[DB FETCH SETTINGS ERROR] {e}")
        return None
    finally:
        if conn:
            conn.close()


def update_settings(
    temp_min: float,
    temp_max: float,
    humidity_min: float,
    humidity_max: float,
    pressure_min: float,
    pressure_max: float
) -> bool:
    """
    Update warning threshold settings.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
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
        conn.commit()
        return True
    except Exception as e:
        print(f"[DB UPDATE SETTINGS ERROR] {e}")
        return False
    finally:
        if conn:
            conn.close()