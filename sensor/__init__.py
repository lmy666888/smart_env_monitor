"""
Sensor package.

Import submodules directly to avoid import cycles, e.g.:

    from sensor.reader import read_from_emulator
    from sensor.collector import collect_reading_and_upload
"""

from sensor.reader import get_sensor_source_name, read_from_emulator, read_sensor_data

__all__ = [
    "get_sensor_source_name",
    "read_from_emulator",
    "read_sensor_data",
]
