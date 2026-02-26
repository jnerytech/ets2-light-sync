"""
telemetry.py – ETS2 shared memory reader.

Reads game time and truck world position from the RenCloud scs-sdk-plugin's
named shared memory (Local\\SCSTelemetry).  Only works when run on the same
Windows machine as Euro Truck Simulator 2 with the telemetry plugin installed.

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
  Zone 8  (offsets 2200+)  – truck world placement (double precision)
    2200  double  coordinateX   ← World East  (game units ≈ metres at 1:19 scale)
    2208  double  coordinateY   ← World Up    (altitude; not used here)
    2216  double  coordinateZ   ← World South (game units)
"""

import logging
import struct
import sys
from typing import Any, NamedTuple, Optional, cast

log = logging.getLogger(__name__)

_SHARED_MEM_NAME = "Local\\SCSTelemetry"
_SHARED_MEM_SIZE = 32 * 1024  # struct is ~6 KB; 32 KB gives headroom

_SDK_ACTIVE_OFFSET = 0   # bool    sdkActive
_PAUSED_OFFSET = 4       # bool    paused
_TIME_ABS_OFFSET = 64    # u32     time_abs – in-game minutes since epoch
_TRUCK_X_OFFSET = 2200   # double  truck_dp.coordinateX – World East
_TRUCK_Z_OFFSET = 2216   # double  truck_dp.coordinateZ – World South
_SHARED_MEM_READ_SIZE = 2224  # 2216 + 8 bytes for the Z double


class Telemetry(NamedTuple):
    game_time: int   # minutes since midnight, 0–1439
    paused: bool     # True when game simulation is paused
    truck_x: float   # World East coordinate (game units); float('nan') when unavailable
    truck_z: float   # World South coordinate (game units); float('nan') when unavailable


def get_telemetry() -> Optional[Telemetry]:
    """Return current telemetry, or None if game/plugin not active."""
    if sys.platform != "win32":
        return None
    return _read_shared_memory()


def get_game_time() -> Optional[int]:
    """Return current in-game time-of-day in minutes (0–1439), or None.

    Returns None when:
    - Not running on Windows (development / CI environment), or
    - ETS2 is not running / telemetry plugin not active.
    """
    if sys.platform != "win32":
        log.debug("Non-Windows platform – telemetry unavailable")
        return None
    result = _read_shared_memory()
    return result.game_time if result is not None else None


def _read_shared_memory() -> Optional[Telemetry]:
    try:
        import ctypes

        FILE_MAP_READ = 0x0004
        kernel32 = cast(Any, ctypes.WinDLL("kernel32", use_last_error=True))  # type: ignore[attr-defined]

        # Must declare restype AND argtypes for pointer-sized values.
        # The default c_int (32-bit) truncates 64-bit pointers on Win64 both
        # when receiving return values and when passing handles back as args.
        HANDLE = ctypes.c_void_p  # type: ignore[attr-defined]
        LPVOID = ctypes.c_void_p  # type: ignore[attr-defined]
        kernel32.OpenFileMappingW.restype = HANDLE  # type: ignore[attr-defined]
        kernel32.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]  # type: ignore[attr-defined]
        kernel32.MapViewOfFile.restype = LPVOID  # type: ignore[attr-defined]
        kernel32.MapViewOfFile.argtypes = [HANDLE, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t]  # type: ignore[attr-defined]
        kernel32.UnmapViewOfFile.argtypes = [LPVOID]  # type: ignore[attr-defined]
        kernel32.CloseHandle.argtypes = [HANDLE]  # type: ignore[attr-defined]

        handle = kernel32.OpenFileMappingW(FILE_MAP_READ, False, _SHARED_MEM_NAME)
        if not handle:
            return None  # Game not running or plugin not installed

        try:
            ptr = kernel32.MapViewOfFile(handle, FILE_MAP_READ, 0, 0, _SHARED_MEM_SIZE)
            if not ptr:
                log.warning("MapViewOfFile failed (error %d)", ctypes.get_last_error())  # type: ignore[attr-defined]
                return None

            try:
                # Read enough bytes to cover truck world position (offset 2216 + 8)
                raw = (ctypes.c_char * _SHARED_MEM_READ_SIZE).from_address(ptr)
                data = bytes(raw)

                sdk_active = struct.unpack_from("?", data, _SDK_ACTIVE_OFFSET)[0]
                if not sdk_active:
                    return None  # Game running but telemetry not active

                paused = struct.unpack_from("?", data, _PAUSED_OFFSET)[0]
                time_abs = struct.unpack_from("<I", data, _TIME_ABS_OFFSET)[0]
                truck_x = struct.unpack_from("<d", data, _TRUCK_X_OFFSET)[0]
                truck_z = struct.unpack_from("<d", data, _TRUCK_Z_OFFSET)[0]
                return Telemetry(
                    game_time=time_abs % 1440,
                    paused=paused,
                    truck_x=truck_x,
                    truck_z=truck_z,
                )
            finally:
                kernel32.UnmapViewOfFile(ptr)
        finally:
            kernel32.CloseHandle(handle)

    except Exception as exc:
        log.warning("Shared memory read error: %s", exc)
        return None
