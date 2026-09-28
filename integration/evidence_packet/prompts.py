"""
System and user prompts for the evidence-packet LLM.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from integration.evidence_packet.models import QABlock


def build_system_prompt() -> str:
    return (
        "You are an assessment assistant producing a verifiable evidence packet for rubric-based grading.\n\n"
        "Hard rules:\n"
        "1) Only use the provided session data: questions, student answers, screenshot metadata (timestamps/regions), and (if provided) screenshot images. Do not use outside knowledge.\n"
        "2) Any transcript quote you output MUST be an exact substring copied from the provided student answer text.\n"
        "3) Any timestamp you output MUST come from the provided screenshot timestamps or provided answer time ranges. If you do not have a timestamp, set it to null and add a flag explaining what is missing.\n"
        "4) Do NOT invent diagrams, regions, screenshots, or timestamps.\n"
        "5) Output MUST be valid JSON only (no markdown, no extra text).\n"
        "6) Output MUST match the provided JSON schema exactly. Do not add extra keys.\n\n"
        "Anti-gaming / integrity (strict):\n"
        "- Do NOT give credit for answers that only claim understanding (e.g. \"I understand Bayes rule\", \"I get it\", \"I know that\") or agreement (\"yes\", \"I think so\") without explaining, defining, applying a formula, or giving an example. Such answers have no substantive evidence for the criterion—assign score 0 and add flag \"insufficient_explanation_no_substance\".\n"
        "- Substantive evidence means: the student actually explains the concept, states a definition or formula, works through an example, or compares/contrasts—something that can be quoted to show they know the material. A bare claim with no such content is not evidence.\n"
        "- Edge cases that must receive 0 and be flagged: (1) empty or near-empty answers, (2) only a claim of understanding with no explanation, (3) only agreement or filler (\"yes\", \"ok\", \"I think so\"), (4) no transcript quote that actually demonstrates the criterion—if the only possible quote is a claim with no substance, score 0 and add \"insufficient_explanation_no_substance\".\n"
        "- Partial credit (1 or middle anchor) is only when the student provides some substantive content that partially addresses the criterion (e.g. incomplete formula, partial explanation, one correct term). It is NOT for merely \"touching on\" the topic with no actual explanation.\n\n"
        "Grading tone: Be fair. When the student clearly meets the criterion with substantive explanation, definition, formula, or example, assign full marks (max score for that criterion). Do not be overly strict: a clear, correct explanation in the student's own words deserves full credit. Reserve score 0 only when there is no relevant evidence, only a claim of understanding with no substance, the answer is off-topic, or clearly wrong. Use partial credit when there is real but incomplete substantive content. Use the flags array to record concerns (e.g. insufficient_explanation_no_substance, no_relevant_quotes, answer_off_topic) so reviewers can see why a low score was given."
    )


def build_user_prompt(
    rubric: Dict[str, Any],
    criterion: Dict[str, Any],
    recording_uri: str,
    blocks: List[QABlock],
    output_schema: Dict[str, Any],
    lecture_material: str = "",
) -> str:
    payload_blocks: List[Dict[str, Any]] = []
    for b in blocks:
        payload_blocks.append(
            {
                "block_id": b.block_id,
                "question": b.question,
                "student_answer": b.student_answer,
                "main_response": b.main_response,
                "follow_up_responses": b.follow_up_responses,
                "screenshots": [
                    {"timestamp": s.timestamp, "image_id": s.image_id, "region": s.region}
                    for s in b.screenshots
                ],
            }
        )

    c_max = criterion.get("max", rubric.get("scale", {}).get("max", 2))
    anchors = criterion.get("anchors", {})
    anchors_text = "\n".join(
        f"- {k}: {anchors.get(str(k), '')}" for k in range(int(c_max) + 1)
    )

    lecture_block = ""
    if lecture_material.strip():
        lecture_block = (
            f"\nLecture/source material for this exam (use to judge correctness and align grading):\n"
            f"{lecture_material.strip()}\n\n"
        )

    return (
        f"Rubric:\n"
        f"- rubric_id: {rubric.get('rubric_id', '')}\n"
        f"- criterion_id: {criterion.get('id', '')}\n"
        f"- criterion_name: {criterion.get('name', '')}\n"
        f"- description: {criterion.get('description', '')}\n"
        f"Scoring anchors (0 to {c_max}):\n"
        f"{anchors_text}\n\n"
        f"Session ground-truth artifact:\n"
        f"- full_recording_uri: {recording_uri}\n\n"
        f"{lecture_block}"
        f"Session QA blocks (ONLY sources of quotes and timestamps):\n"
        f"Each block has: question (the question asked), main_response (the student's initial answer to that question), "
        f"follow_up_responses (answers to any follow-up questions), and student_answer (full text = main + follow-ups). "
        f"You MUST grade using the ENTIRE content: the main response AND all follow-up responses. Do NOT grade only on follow-up answers; "
        f"the student's initial answer to the main question counts equally.\n"
        f"{json.dumps(payload_blocks, ensure_ascii=False)}\n\n"
        f"Task:\n"
        f"1) Assign a score from 0 to {c_max} using the anchors. Consider the student's main answer to the question AND any follow-up answers when deciding the score. When the student clearly meets the criterion with substantive explanation, definition, formula, or example (in their main answer and/or follow-ups), give full marks. Give partial credit when they provide real but incomplete substantive content. Do NOT give credit for answers that only claim understanding (e.g. \"I understand X\") or agreement (\"yes\", \"I think so\") with no explanation, definition, formula, or example—score those 0 and add flag \"insufficient_explanation_no_substance\". Reserve 0 only when there is no relevant evidence, only a claim with no substance, or the answer is clearly wrong or off-topic.\n"
        f"2) Provide evidence: one or more exact transcript quotes copied from student_answer (from main_response and/or follow_up_responses) that actually demonstrate the criterion (explanation, definition, formula, or example). If the only possible quote is a bare claim of understanding with no substance, do not cite it as supporting a positive score—assign 0 and add \"insufficient_explanation_no_substance\" to flags.\n"
        f"   - If a quote relates to a diagram reference, use the nearest screenshot timestamp(s).\n"
        f"   - If no relevant screenshot exists, set t0/t1 to null and add a flag \"missing_timestamp_for_quote\".\n"
        f"3) Optionally include video evidence using screenshot(s) (type=\"video_event\") with tag=\"screenshot\" and region if provided.\n"
        f"4) Provide llm_confidence in [0,1]. This is dependent on how confident you feel about your grading. The less confident you feel, the smaller this score should be. Similarly, the more confident, the higher this score should be. Don't be afraid to be expressive - this should be a genuine confidence level. \n"
        f"5) Provide missing_evidence list if needed (e.g. \"No explanation or formula provided\", \"Only claimed understanding\").\n"
        f"6) In the flags array, include any of: insufficient_explanation_no_substance, no_relevant_quotes, answer_off_topic, missing_timestamp_for_quote—when they apply, so reviewers see why the score was assigned.\n"
        f"7) Provide exactly ONE suggested_followup_question.\n\n"
        f"Output JSON matching this schema exactly:\n"
        f"{json.dumps(output_schema, ensure_ascii=False)}"
    )
