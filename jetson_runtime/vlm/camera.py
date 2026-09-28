"""
Camera — trigger-word screenshots + continuous session video recording.
Copied from V1 camera.py and updated to use V2 settings.
"""
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

logger = logging.getLogger(__name__)


class Camera:
    def __init__(self):
        self._cap = None
        self._latest_frame = None
        self._lock = threading.Lock()
        self._recording = False
        self._record_thread = None
        self._out = None

    def open(self):
        try:
            import cv2
            self._cap = cv2.VideoCapture(settings.CAMERA_DEVICE)
            if not self._cap.isOpened():
                logger.warning("Camera not available: %s", settings.CAMERA_DEVICE)
                self._cap = None
                return
            w, h = settings.CAMERA_RESOLUTION
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            self._cap.set(cv2.CAP_PROP_FPS, settings.CAMERA_FPS)
            # Start frame-reader thread to keep _latest_frame fresh
            t = threading.Thread(target=self._frame_reader, daemon=True)
            t.start()
            # Wait up to 2s for the first frame so capture_frame works immediately after open()
            deadline = time.time() + 2.0
            while self._latest_frame is None and time.time() < deadline:
                time.sleep(0.05)
            logger.info("Camera opened: %s", settings.CAMERA_DEVICE)
        except Exception as e:
            logger.warning("Camera open failed: %s", e)
            self._cap = None

    def _frame_reader(self):
        import cv2
        while self._cap and self._cap.isOpened():
            ret, frame = self._cap.read()
            if ret:
                with self._lock:
                    self._latest_frame = frame
            time.sleep(0.05)

    def capture_frame(self, output_path: str) -> str:
        """Capture current frame; return output_path on success, else ''."""
        import cv2
        with self._lock:
            frame = self._latest_frame
        if frame is None and self._cap and self._cap.isOpened():
            ret, frame = self._cap.read()
            if not ret:
                frame = None
        if frame is None:
            logger.warning("No frame available for capture")
            return ""
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(output_path, frame)
            return output_path
        except Exception as e:
            logger.error("Frame write failed: %s", e)
            return ""

    def start_recording(self, output_path: str):
        if self._recording or self._cap is None:
            return
        import cv2
        w, h = settings.VIDEO_RECORDING_RESOLUTION
        fourcc = cv2.VideoWriter_fourcc(*settings.VIDEO_RECORDING_FOURCC)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        self._out = cv2.VideoWriter(str(output_path), fourcc, settings.VIDEO_RECORDING_FPS, (w, h))
        self._recording = True
        self._record_thread = threading.Thread(target=self._record_loop, daemon=True)
        self._record_thread.start()
        logger.info("Video recording started: %s", output_path)

    def _record_loop(self):
        import cv2
        interval = 1.0 / settings.VIDEO_RECORDING_FPS
        w, h = settings.VIDEO_RECORDING_RESOLUTION
        while self._recording:
            with self._lock:
                frame = self._latest_frame
            if frame is not None:
                resized = cv2.resize(frame, (w, h))
                self._out.write(resized)
            time.sleep(interval)

    def stop_recording(self):
        self._recording = False
        if self._record_thread:
            self._record_thread.join(timeout=3)
        if self._out:
            self._out.release()
            self._out = None
        logger.info("Video recording stopped")

    def is_recording(self) -> bool:
        return self._recording

    def close(self):
        self.stop_recording()
        if self._cap:
            self._cap.release()
            self._cap = None


_instance: Camera = None


def get_camera() -> Camera:
    global _instance
    if _instance is None:
        _instance = Camera()
    return _instance
