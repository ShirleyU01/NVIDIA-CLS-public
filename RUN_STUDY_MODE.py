#!/usr/bin/env python3
"""
Launch Study Mode stack in three separate terminals.

Services started:
1) Central backend (port 8002)
2) Jetson backend (port 8001)
3) Web frontend (port 5173)

Usage:
  cd /path/to/NVIDIA-CLS-1
  python3 RUN_STUDY_MODE.py

Notes:
- This script does NOT hardcode secrets.
- It expects OPENAI_API_KEY in your environment OR in <project-root>/.env.
- By default, <project-root> is the folder containing this script.
- Override with SOCRATES_PROJECT_ROOT=/path/to/NVIDIA-CLS-1 if needed.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT_ENV = "SOCRATES_PROJECT_ROOT"


def _resolve_root() -> Path:
    """Resolve the checkout root without assuming a fixed username or machine path."""
    override = os.environ.get(PROJECT_ROOT_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent


ROOT = _resolve_root()
VENV_ACTIVATE = ROOT / ".venv" / "bin" / "activate"
ENV_FILE = ROOT / ".env"


def _load_dotenv(path: Path) -> None:
    """Best-effort .env loader (very small parser)."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _terminal_command() -> list[str]:
    """
    Pick an available terminal command.
    Uses macOS Terminal on Darwin; otherwise prefers gnome-terminal, then
    x-terminal-emulator.
    """
    if sys.platform == "darwin":
        return ["osascript"]

    for cmd in (["gnome-terminal"], ["x-terminal-emulator"]):
        try:
            subprocess.run(
                [cmd[0], "--version"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return cmd
        except FileNotFoundError:
            continue
    raise RuntimeError("No supported terminal found (gnome-terminal / x-terminal-emulator).")


def _open_terminal(title: str, shell_cmd: str) -> None:
    """
    Open one terminal window and run shell_cmd.
    Keeps terminal open afterward with `exec bash`.
    """
    terminal = _terminal_command()
    run_cmd = f"{shell_cmd}; echo; echo '[{title}] exited.'; exec bash"

    if terminal[0] == "osascript":
        subprocess.Popen(
            [
                "osascript",
                "-e",
                f'tell application "Terminal" to do script {json.dumps(run_cmd)}',
            ]
        )
        return

    if terminal[0] == "gnome-terminal":
        # gnome-terminal supports --title.
        cmd = terminal + ["--title", title, "--", "bash", "-lc", run_cmd]
    else:
        # x-terminal-emulator (on Debian/Ubuntu) typically accepts -e.
        cmd = terminal + ["-e", f"bash -lc {shlex.quote(run_cmd)}"]

    subprocess.Popen(cmd)


def _has_gui_terminal() -> bool:
    """True when we can open separate GUI terminal windows (local Jetson desktop)."""
    if sys.platform == "darwin":
        return True
    return bool(os.environ.get("DISPLAY"))


def _print_manual_commands(commands: list[tuple[str, str]]) -> None:
    print("No DISPLAY detected — not starting services automatically.")
    print("On the Jetson desktop, run these in three separate terminals:")
    for title, shell_cmd in commands:
        print()
        print(f"# {title}")
        print(shell_cmd)


def main() -> int:
    if not ROOT.is_dir():
        print(f"Project folder not found: {ROOT}")
        return 1
    if not VENV_ACTIVATE.is_file():
        print(f"Virtualenv activate script not found: {VENV_ACTIVATE}")
        return 1

    _load_dotenv(ENV_FILE)

    openai_api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not openai_api_key:
        print(f"OPENAI_API_KEY not found in environment or {ENV_FILE}")
        return 1

    cmd_backend = (
        f"cd {shlex.quote(str(ROOT))} && "
        f"source {shlex.quote(str(VENV_ACTIVATE))} && "
        f"export OPENAI_API_KEY={shlex.quote(openai_api_key)} && "
        "uvicorn backend.main:app --reload --port 8002"
    )
    cmd_jetson = (
        f"cd {shlex.quote(str(ROOT))} && "
        f"source {shlex.quote(str(VENV_ACTIVATE))} && "
        "cd jetson_runtime && "
        "export CENTRAL_API_BASE_URL='http://localhost:8002' && "
        f"export OPENAI_API_KEY={shlex.quote(openai_api_key)} && "
        "python jetson_backend.py"
    )
    cmd_web = (
        f"cd {shlex.quote(str(ROOT / 'web'))} && "
        "export VITE_JETSON_API_BASE_URL='http://localhost:8001' && "
        "export VITE_CENTRAL_API_BASE_URL='http://localhost:8002' && "
        "npm run dev -- --host 0.0.0.0 --port 5173"
    )

    commands = [
        ("central", cmd_backend),
        ("jetson", cmd_jetson),
        ("web", cmd_web),
    ]

    if not _has_gui_terminal():
        _print_manual_commands(commands)
        print()
        print("URLs (after you start the three services):")
    else:
        print("Starting Study Mode stack in separate terminals...")
        _open_terminal("Socrates Central Backend", cmd_backend)
        time.sleep(0.4)
        _open_terminal("Socrates Jetson Backend", cmd_jetson)
        time.sleep(0.4)
        _open_terminal("Socrates Web UI", cmd_web)
        print("Launched.")

    print()
    print("Central backend: http://localhost:8002")
    print("Jetson backend:  http://localhost:8001")
    print("Web UI:          http://localhost:5173")
    return 0


if __name__ == "__main__":
    sys.exit(main())
