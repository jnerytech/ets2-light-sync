"""Quick manual test – prints live ETS2 telemetry every second.

Run on the Windows machine with ETS2 + scs-sdk-plugin running:
    python test_telemetry.py
"""

import time
import sys
from telemetry import get_game_time

print(f"Platform: {sys.platform}")
print("Polling telemetry every 1 s  (Ctrl-C to stop)\n")

try:
    while True:
        minutes = get_game_time()
        if minutes is None:
            print("  -> None  (game not running / plugin inactive / non-Windows)")
        else:
            h, m = divmod(minutes, 60)
            print(f"  -> {minutes:4d} min  ({h:02d}:{m:02d})")
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopped.")
