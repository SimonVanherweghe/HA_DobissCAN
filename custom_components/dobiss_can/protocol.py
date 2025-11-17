"""
Dobiss CAN protocol helpers for building messages and conversions.
"""
from typing import Tuple


def to_dobiss_brightness(ha_brightness: int) -> int:
    """Convert HA 0-255 brightness to Dobiss 0-100 scale."""
    if ha_brightness is None:
        return 100
    v = int(round((max(0, min(255, ha_brightness)) * 100) / 255))
    return max(0, min(100, v))


def to_ha_brightness(dobiss_value: int) -> int:
    """Convert Dobiss 0-100 brightness to HA 0-255 scale."""
    v = int(round((max(0, min(100, dobiss_value)) * 255) / 100))
    return max(0, min(255, v))


def build_set_command(module: int, output: int, action: int, value: int = 0x64, delay_on: int = 0xFF,
                      delay_off: int = 0xFF, softdim: int = 0xFF) -> Tuple[int, bytes]:
    """
    Build a SET command for a module/output.

    action: 0x00=Off, 0x01=On, 0x02=Toggle
    value:  percentage 0-100 for dim level (0x64 used commonly for on/toggle)
    softdim: 0xFF for instant, or speed value (scale hardware dependent)
    """
    arb_id = 0x01FC0002 | (module << 8)
    data = bytes((module, output, action, delay_on & 0xFF, delay_off & 0xFF, value & 0xFF, softdim & 0xFF, 0xFF))
    return arb_id, data


def build_get_command(module: int, output: int) -> Tuple[int, bytes]:
    """Build a GET command to request status for a module/output."""
    return 0x01FCFF01, bytes((module, output))
