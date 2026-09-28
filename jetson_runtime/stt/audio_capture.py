"""
Audio capture — records WAV slices via arecord, merges via sox or ffmpeg.
"""
import logging
import os
import subprocess
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

logger = logging.getLogger(__name__)


class AudioCapture:
    def _write_silence_wav(self, path: str, duration_sec: int) -> None:
        """
        Best-effort fallback when `arecord` is unavailable.

        Writes a valid WAV file containing silence so downstream merge/transcribe
        steps don't crash on missing files (useful for UI dev on non-Linux hosts).
        """
        import wave

        sample_rate = int(getattr(settings, "SAMPLE_RATE", 16000))
        channels = int(getattr(settings, "CHANNELS", 1))
        n_frames = max(1, int(sample_rate * max(0, duration_sec)))
        with wave.open(path, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(sample_rate)
            wf.writeframes(b"\x00\x00" * n_frames * channels)

    def record(self, duration_sec: int) -> str:
        """Record `duration_sec` seconds; returns path to temp WAV file."""
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        cmd = [
            "arecord",
            "-D", settings.AUDIO_DEVICE,
            "-d", str(duration_sec),
            "-r", str(settings.SAMPLE_RATE),
            "-f", settings.AUDIO_FORMAT,
            "-c", str(settings.CHANNELS),
            "-t", "wav",
            "-q",
            path,
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            logger.error(
                "arecord not found on this system. "
                "Audio capture is unavailable; writing silence WAV as fallback."
            )
            try:
                self._write_silence_wav(path, duration_sec)
            except Exception as e:
                logger.error("Failed to write silence WAV fallback: %s", e)
        except subprocess.CalledProcessError as e:
            # During shutdown or transient device handoffs, arecord can return
            # non-zero; keep this non-fatal and avoid noisy error logs.
            logger.warning("arecord failed: %s", e)
        return path

    def merge_wavs(self, paths: list, output_path: str):
        """Concatenate WAV files into output_path using ffmpeg."""
        if not paths:
            return
        if len(paths) == 1:
            import shutil
            shutil.copy2(paths[0], output_path)
            return
        # Build ffmpeg concat
        fd, list_file = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            with open(list_file, "w") as f:
                for p in paths:
                    f.write(f"file '{p}'\n")
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", list_file,
                "-ar", str(settings.SAMPLE_RATE),
                "-ac", str(settings.CHANNELS),
                output_path,
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as e:
            logger.error("ffmpeg merge failed: %s", e)
        finally:
            try:
                os.unlink(list_file)
            except Exception:
                pass


_instance: AudioCapture = None


def get_audio_capture() -> AudioCapture:
    global _instance
    if _instance is None:
        _instance = AudioCapture()
    return _instance
