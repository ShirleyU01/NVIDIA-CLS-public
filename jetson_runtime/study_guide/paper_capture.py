from __future__ import annotations

import time
from pathlib import Path


def capture_paper_image(
    *,
    camera_device: str,
    output_path: Path,
    width: int = 1280,
    height: int = 720,
) -> Path:
    """
    Capture a single still frame suitable for paper/handwriting.

    This intentionally does NOT reuse `vlm/camera.py` because that class is tuned
    for low-res screenshots + low-FPS recording for the oral exam pipeline.
    """
    import cv2

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Prefer V4L2 on Linux/Jetson; fall back to default backend. Retry if another client
    # (e.g. the browser) just released the device.
    last_err = RuntimeError(f"Camera not available: {camera_device}")
    cap = None
    for _attempt in range(8):
        cap_try = None
        if camera_device.startswith("/dev/video"):
            try:
                idx = int(camera_device.replace("/dev/video", ""))
            except ValueError:
                idx = None
            v4l2 = getattr(cv2, "CAP_V4L2", None)
            if idx is not None and v4l2 is not None:
                cap_try = cv2.VideoCapture(idx, v4l2)
            if cap_try is None or not cap_try.isOpened():
                if cap_try is not None:
                    cap_try.release()
                cap_try = cv2.VideoCapture(idx) if idx is not None else cv2.VideoCapture(camera_device)
            if cap_try is None or not cap_try.isOpened():
                if cap_try is not None:
                    cap_try.release()
                cap_try = cv2.VideoCapture(camera_device)
        else:
            cap_try = cv2.VideoCapture(camera_device)

        if cap_try is not None and cap_try.isOpened():
            cap = cap_try
            break
        if cap_try is not None:
            cap_try.release()
        time.sleep(0.15)

    if cap is None or not cap.isOpened():
        raise last_err

    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))

        # Let auto-exposure settle a bit (especially important for white paper).
        deadline = time.time() + 1.0
        frame = None
        while time.time() < deadline:
            ok, fr = cap.read()
            if ok:
                frame = fr

        if frame is None:
            ok, frame = cap.read()
            if not ok or frame is None:
                raise RuntimeError("Failed to read frame from camera")

        ok = cv2.imwrite(str(output_path), frame)
        if not ok:
            raise RuntimeError(f"Failed to write image to {output_path}")
        return output_path
    finally:
        cap.release()

