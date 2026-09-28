#!/usr/bin/env python3
"""
Ollama LLM client for Socrates AI Oral Examiner.

Provides generate() and stream_generate() against a local Ollama server
(designed for Jetson Orin Nano running Phi-3).

Usage:
    # Non-streaming
    python llm_ollama.py --prompt "Explain Bayes' rule"

    # Streaming
    python llm_ollama.py --prompt "Explain Bayes' rule" --stream

    # Custom model / host
    python llm_ollama.py --prompt "hello" --model phi3 --host http://192.168.1.50:11434
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Generator, List, Optional

import requests


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "phi3"
DEFAULT_TIMEOUT = 120  # seconds


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------
class OllamaConnectionError(RuntimeError):
    """Raised when Ollama is unreachable."""


def _check_ollama(host: str, timeout: float = 5.0) -> None:
    """Ping the Ollama server; raise a clear message if it's down."""
    try:
        resp = requests.get(f"{host}/api/tags", timeout=timeout)
        resp.raise_for_status()
    except requests.ConnectionError:
        raise OllamaConnectionError(
            f"\n❌ Cannot connect to Ollama at {host}\n"
            f"   Make sure Ollama is running:\n"
            f"     1. Install Ollama:  curl -fsSL https://ollama.com/install.sh | sh\n"
            f"     2. Start server:    ollama serve          (or it may auto-start)\n"
            f"     3. Pull the model:  ollama pull phi3\n"
            f"     4. Verify:          curl {host}/api/tags\n"
        )
    except requests.Timeout:
        raise OllamaConnectionError(
            f"\n❌ Ollama at {host} timed out. Is the server overloaded?\n"
        )


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------
def generate(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    host: str = DEFAULT_HOST,
    system: Optional[str] = None,
    messages: Optional[List[Dict[str, str]]] = None,
    temperature: float = 0.7,
    max_tokens: int = 512,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Non-streaming generation.

    Supports two modes:
      - Simple: pass ``prompt`` (and optional ``system``) for a one-shot call.
      - Chat:   pass ``messages`` (list of {role, content} dicts) for multi-turn.

    Returns the full Ollama JSON response as a dict.  The generated text is
    in ``response["response"]`` (generate) or ``response["message"]["content"]``
    (chat).
    """
    _check_ollama(host)

    if messages is not None:
        # ---- /api/chat (multi-turn) ----
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        url = f"{host}/api/chat"
    else:
        # ---- /api/generate (single-turn) ----
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system:
            payload["system"] = system
        url = f"{host}/api/generate"

    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def stream_generate(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    host: str = DEFAULT_HOST,
    system: Optional[str] = None,
    messages: Optional[List[Dict[str, str]]] = None,
    temperature: float = 0.7,
    max_tokens: int = 512,
    timeout: float = DEFAULT_TIMEOUT,
) -> Generator[str, None, None]:
    """
    Streaming generation — yields tokens as they arrive.

    Same two modes as generate() (simple prompt vs. chat messages).
    """
    _check_ollama(host)

    if messages is not None:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        url = f"{host}/api/chat"
        content_key = ("message", "content")  # nested
    else:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system:
            payload["system"] = system
        url = f"{host}/api/generate"
        content_key = ("response",)  # top-level

    resp = requests.post(url, json=payload, stream=True, timeout=timeout)
    resp.raise_for_status()

    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        chunk = json.loads(line)

        # Extract token text depending on endpoint
        if len(content_key) == 2:
            token = chunk.get(content_key[0], {}).get(content_key[1], "")
        else:
            token = chunk.get(content_key[0], "")

        if token:
            yield token

        # Stop if Ollama signals done
        if chunk.get("done", False):
            return


def chat_generate(
    messages: List[Dict[str, str]],
    *,
    model: str = DEFAULT_MODEL,
    host: str = DEFAULT_HOST,
    temperature: float = 0.7,
    max_tokens: int = 512,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """
    Convenience wrapper: multi-turn chat, returns just the assistant text.
    """
    result = generate(
        prompt="",
        model=model,
        host=host,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    return result.get("message", {}).get("content", "")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test Ollama LLM generation (Phi-3 on Jetson Orin)"
    )
    parser.add_argument("--prompt", required=True, help="Prompt text")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model name (default: {DEFAULT_MODEL})")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Ollama host (default: {DEFAULT_HOST})")
    parser.add_argument("--system", default=None, help="Optional system prompt")
    parser.add_argument("--stream", action="store_true", help="Stream tokens")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    args = parser.parse_args()

    try:
        if args.stream:
            print("--- streaming ---")
            for token in stream_generate(
                args.prompt,
                model=args.model,
                host=args.host,
                system=args.system,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                timeout=args.timeout,
            ):
                print(token, end="", flush=True)
            print("\n--- done ---")
        else:
            result = generate(
                args.prompt,
                model=args.model,
                host=args.host,
                system=args.system,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                timeout=args.timeout,
            )
            print(result.get("response", "(no response key — full JSON below)"))
            if "response" not in result:
                print(json.dumps(result, indent=2))
    except OllamaConnectionError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
