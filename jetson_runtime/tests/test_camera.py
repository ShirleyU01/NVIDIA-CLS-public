#!/usr/bin/env python3
"""Test camera capture."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vlm.camera import get_camera

print("=" * 50)
print("TEST: Camera capture")
print("=" * 50)

camera = get_camera()
camera.open()

frame_file = "/tmp/v2_test_frame.jpg"
result = camera.capture_frame(frame_file)

if result:
    print(f"✅ Frame captured: {result}")
else:
    print("❌ Camera capture failed")
    sys.exit(1)

print("✅ Camera OK")
camera.close()
