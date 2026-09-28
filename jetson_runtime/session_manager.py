"""
Session ID management.
Counter is persisted in jetson_runtime/sessions/.session_counter so IDs never repeat
across reboots: session_1, session_2, session_3, …
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import settings

_COUNTER_FILE = settings.SESSIONS_DIR / ".session_counter"


def get_next_session_id() -> str:
    try:
        n = int(_COUNTER_FILE.read_text().strip()) if _COUNTER_FILE.exists() else 0
    except ValueError:
        n = 0
    n += 1
    _COUNTER_FILE.write_text(str(n))
    return f"session_{n}"
