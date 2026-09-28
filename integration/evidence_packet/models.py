"""
Shared data structures for the evidence packet pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Screenshot:
    timestamp: float
    image_id: str
    region: Optional[str] = None


@dataclass
class QABlock:
    block_id: str
    question: str
    student_answer: str
    screenshots: List[Screenshot]
    # Explicit parts so grading considers main answer, not only follow-ups
    main_response: str = ""
    follow_up_responses: Optional[List[str]] = None

    def __post_init__(self):
        if self.follow_up_responses is None:
            self.follow_up_responses = []
