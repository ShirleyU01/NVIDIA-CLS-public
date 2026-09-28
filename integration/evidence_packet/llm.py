"""
LLM completion for evidence packet pipeline.

Replace llm_complete() implementation with your provider (OpenAI, Ollama, etc.).
"""

from __future__ import annotations


def llm_complete(system_prompt: str, user_prompt: str, **_kwargs) -> str:
    """
    Call the LLM with system and user prompts; return raw response text.

    Override this module or replace the implementation to use your LLM.
    """
    raise NotImplementedError(
        "Connect your LLM here (e.g. OpenAI, Ollama). "
        "Set OPENAI_API_KEY and use integration.evidence_packet.llm_openai.llm_complete for OpenAI."
    )
