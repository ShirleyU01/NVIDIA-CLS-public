"""
Evidence packet pipeline: rubric + session → verifiable evidence packet for grading.

Model-agnostic: plug in any LLM via llm_complete() in llm.py.
"""

from integration.evidence_packet.pipeline import (
    load_rubric,
    load_session,
    normalize_blocks,
    run_evidence_packet,
    assemble_final_packet,
)
from integration.evidence_packet.models import QABlock, Screenshot
from integration.evidence_packet.prompts import build_system_prompt, build_user_prompt
from integration.evidence_packet.validation import validate_packet_item

__all__ = [
    "QABlock",
    "Screenshot",
    "load_rubric",
    "load_session",
    "normalize_blocks",
    "run_evidence_packet",
    "assemble_final_packet",
    "build_system_prompt",
    "build_user_prompt",
    "validate_packet_item",
]
