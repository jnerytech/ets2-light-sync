"""Quick manual test – prints live ETS2 telemetry + light curve output every second.

Run on the Windows machine with ETS2 + scs-sdk-plugin running:
    python test_telemetry.py
"""

import time
import sys
from telemetry import get_telemetry
from light_curve import calculate_light

print(f"Platform: {sys.platform}")
print("Polling telemetry every 1 s  (Ctrl-C to stop)\n")
print(f"  {'Time':>5}   {'Paused':>6}   {'Bright':>6}   {'Kelvin':>6}")
print(f"  {'-'*5}   {'-'*6}   {'-'*6}   {'-'*6}")

try:
    while True:
        telemetry = get_telemetry()
        if telemetry is None:
            print("  -> None  (game not running / plugin inactive / non-Windows)")
        else:
            h, m = divmod(telemetry.game_time, 60)
            brightness, kelvin = calculate_light(telemetry.game_time)
            paused = "YES" if telemetry.paused else "-"
            print(f"  {h:02d}:{m:02d}   {paused:>6}   {brightness:>5}/255   {kelvin:>5}K")
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopped.")
