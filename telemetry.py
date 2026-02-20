"""
telemetry.py – ETS2 shared memory reader.

Reads game time from the RenCloud scs-sdk-plugin's named shared memory
(Local\\SCSTelemetry).  Only works when run on the same Windows machine
as Euro Truck Simulator 2 with the telemetry plugin installed.

Plugin: https://github.com/RenCloud/scs-sdk-plugin

Shared memory layout (scsTelemetryMap_s, no #pragma pack):
  Zone 1  (offsets 0–39)
    0   bool      sdkActive
    1   char[3]   placeholder
    4   bool      paused
    5   char[3]   placeholder2
    8   u64       time            ← sync timestamp only, NOT game time
    16  u64       simulatedTime
    24  u64       renderTime
    32  i64       multiplayerTimeOffset
  Zone 2  (offsets 40+)
    40  u32       telemetry_plugin_revision   ┐
    44  u32       version_major               │ scs_values
    48  u32       version_minor               │ (6 × u32 = 24 bytes)
    52  u32       game                        │
    56  u32       telemetry_version_game_major│
    60  u32       telemetry_version_game_minor┘
    64  u32       time_abs    ← in-game time in MINUTES since game epoch ✓
"""

import logging
import struct
import sys
from typing import Any, Optional, cast

log = logging.getLogger(__name__)

_SHARED_MEM_NAME = "Local\\SCSTelemetry"
_SHARED_MEM_SIZE = 32 * 1024  # struct is ~6 KB; 32 KB gives headroom

_SDK_ACTIVE_OFFSET = 0   # bool  sdkActive
_TIME_ABS_OFFSET = 64    # u32   time_abs – in-game minutes since epoch


def get_game_time() -> Optional[int]:
    """Return current in-game time-of-day in minutes (0–1439), or None.

    Returns None when:
    - Not running on Windows (development / CI environment), or
    - ETS2 is not running / telemetry plugin not active.
    """
    if sys.platform != "win32":
        log.debug("Non-Windows platform – telemetry unavailable")
        return None
    return _read_shared_memory()


def _read_shared_memory() -> Optional[int]:
    try:
        import ctypes

        FILE_MAP_READ = 0x0004
        kernel32 = cast(Any, ctypes.WinDLL("kernel32", use_last_error=True))  # type: ignore[attr-defined]

        handle = cast(int, kernel32.OpenFileMappingW(FILE_MAP_READ, False, _SHARED_MEM_NAME))
        if not handle:
            return None  # Game not running or plugin not installed

        try:
            ptr = cast(int, kernel32.MapViewOfFile(handle, FILE_MAP_READ, 0, 0, _SHARED_MEM_SIZE))
            if not ptr:
                log.warning("MapViewOfFile failed (error %d)", ctypes.get_last_error())  # type: ignore[attr-defined]
                return None

            try:
                # Read just enough bytes to cover time_abs (offset 64, 4 bytes)
                raw = (ctypes.c_char * 68).from_address(ptr)
                data = bytes(raw)

                sdk_active = struct.unpack_from("?", data, _SDK_ACTIVE_OFFSET)[0]
                if not sdk_active:
                    return None  # Game running but telemetry not active

                time_abs = struct.unpack_from("<I", data, _TIME_ABS_OFFSET)[0]
                return time_abs % 1440  # Normalize to minutes-since-midnight
            finally:
                kernel32.UnmapViewOfFile(ptr)
        finally:
            kernel32.CloseHandle(handle)

    except Exception as exc:
        log.warning("Shared memory read error: %s", exc)
        return None
