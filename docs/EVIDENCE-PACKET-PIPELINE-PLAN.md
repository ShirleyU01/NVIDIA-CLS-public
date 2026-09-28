# Evidence Packet Pipeline — Build Plan

## 1. Goal

Produce a **verifiable evidence packet** for rubric-based grading from a single exam session. The packet contains per-criterion scores, transcript quotes, timestamped video/screenshot evidence, and optional follow-up questions. The pipeline is **model-agnostic** (plug in any LLM via `llm_complete()`).

---

## 2. Inputs and Outputs

| Input | Description | Format |
|-------|-------------|--------|
| **Rubric** | Scoring criteria and anchors | JSON (see §5) |
| **Session** | One exam session: questions, student answers, screenshots | JSON (see §6) |

| Output | Description | Format |
|--------|-------------|--------|
| **Evidence packet** | Per-criterion scores, evidence, flags, overall score | JSON |

---

## 3. Pipeline Steps (high level)

1. **Load** rubric JSON and session JSON.
2. **Normalize** session into `(session_id, recording_uri, qa_blocks)` with typed `QABlock` / `Screenshot` structures.
3. **For each criterion** in the rubric:
   - Build user prompt (rubric + criterion + recording URI + QA blocks + output schema).
   - Call `llm_complete(system_prompt, user_prompt)`.
   - Parse LLM output as JSON.
   - **Validate** deterministically:
     - Every transcript quote is an exact substring of some `student_answer`.
     - Every timestamp is from the provided screenshot list or `null` (with a flag when null).
     - `llm_confidence` in [0, 1].
     - If score > 0, at least one evidence item.
   - Append validated item (with any validation flags) to per-criterion list.
4. **Assemble** final packet: session_id, rubric_id, recording_uri, total_score, max_score, overall_confidence, criteria array, aggregated flags.
5. **Write** `evidence_packet.json` to disk (or return dict for UI).

---

## 4. Code Layout (proposed)

```
integration/
  evidence_packet/
    __init__.py
    prompts.py      # build_system_prompt(), build_user_prompt()
    validation.py   # validate_packet_item(), quote/timestamp checks
    pipeline.py     # load_rubric, load_session, normalize_blocks, run_evidence_packet, assemble_final_packet
    llm.py          # llm_complete() stub or OpenAI/local implementation
  fixtures/
    rubric_bayes_oral_v1.json   # mock rubric (per-criterion max)
    session_mock_001.json       # mock session (Q1 with screenshots, Q2 none)
    session_mock_002.json       # mock session (edge cases: no screenshots anywhere; short/long answers)
```

- **CLI**: e.g. `python -m integration.evidence_packet.pipeline --rubric ... --session ... --out ...`
- **Optional**: call from live UI when exam completes (pass `exam_results` + paths → build session in memory or write session JSON then run pipeline).

---

## 5. Rubric JSON Structure

- **rubric_id**: string (e.g. `"bayes_oral_v1"`).
- **scale**: optional global `{ "min": 0, "max": 2 }` (fallback when criterion has no **max**).
- **criteria**: array of:
  - **id**: string (e.g. `"C1"`, `"C2"`).
  - **name**: string.
  - **description**: string.
  - **max**: number — **per-criterion maximum score** (e.g. 2 or 1). Anchors must have keys `"0"` through `"max"`.
  - **anchors**: `{ "0": "...", "1": "...", "2": "..." }` (score → description; keys 0..max).
  - **weight**: number (default 1.0).

**Total max score** = sum over criteria of (criterion **max** × **weight**). Example: C1–C3 max 2, C4 max 1 → total max = 2+2+2+1 = 7, or with weights 2+2+2+0.5 = 6.5 if C4 weight 0.5.

One example mock rubric is in `integration/fixtures/rubric_bayes_oral_v1.json`.

---

## 6. Session JSON Structure

- **session_id**: string.
- **recording_uri**: string (path or URI to full recording; may be directory or placeholder for MVP).
- **qa_blocks**: array of:
  - **block_id**: string (e.g. `"Q1"`, `"Q2"`).
  - **question**: string.
  - **student_answer**: string (full transcript text for that answer; concatenation of ASR segments if needed).
  - **screenshots**: array of:
    - **timestamp**: number — **seconds** (float), same format as Whisper segment timestamps (e.g. 12.3, 15.1).
    - **image_id**: string (path or id).
    - **region**: string or null (e.g. `"whiteboard_center"`).

One example mock session is in `integration/fixtures/session_mock_001.json`.

---

## 7. Evidence Packet Output Schema

- **session_id**, **rubric_id**, **recording_uri**
- **total_score**, **max_score** (max_score = sum of criterion max × weight),
 **overall_confidence**
- **criteria**: array of per-criterion objects:
  - **criterion_id**, **score**, **score_rationale_anchor**
  - **llm_confidence**
  - **evidence**: array of:
    - `{ "type": "transcript_quote", "quote", "t0", "t1", "why_it_supports" }`
    - `{ "type": "video_event", "t0", "t1", "tag": "screenshot", "region" }`
  - **missing_evidence**, **suggested_followup_question**, **flags**
- **flags**: aggregated list (e.g. `missing_timestamp_for_quote`, `invalid_quote_not_found_in_answers`).

---

## 8. Timestamps (MVP)

- **Format**: Timestamps are in **seconds** (float), matching **Whisper** segment timestamps from Jetson ASR (e.g. `12.3`, `15.1`). Use the same convention in session JSON and evidence packet.
- No ASR word timestamps yet → no true answer time ranges.
- For each transcript quote:
  - If the QA block has screenshots: set **t0 = t1 = nearest screenshot timestamp** (in same block).
  - If no screenshots in block: set **t0 = t1 = null** and add flag **missing_timestamp_for_quote**.
- Pipeline validation: any timestamp in evidence must appear in the block’s screenshot list or be null.

---

## 9. Mock Data for Testing

- **Mock rubric**: 2–4 criteria, **per-criterion max** (e.g. 2 or 1), clear anchors (see fixture).
- **Mock sessions**:
  - **session_mock_001.json**: 2 QA blocks; Q1 has screenshots, Q2 has none (tests `missing_timestamp_for_quote`).
  - **session_mock_002.json**: Edge cases — no screenshots in any block; one very short answer; one long answer (tests all-null timestamps and quote validation).
- Use these to run the pipeline end-to-end with a stub or real LLM and assert on:
  - Valid JSON output.
  - Quotes present in `student_answer`.
  - Timestamps in screenshot list or null + flag.

---

## 10. Open Questions / Your Choices

1. **Session source**: Should the pipeline only **read** session JSON from disk, or also **generate** it from current `exam_results` + frame paths (e.g. when exam completes in live UI)?
2. **Screenshot set**: For MVP, are “screenshots” per block only the **deictic trigger frames** (from current `records`), or do you want **all frames** in a time range (e.g. every N seconds)? Affects mock session and how we build session from live run.
3. **Student answer text**: Confirm that `student_answer` = concatenation of `events[].text` for that question (e.g. `" ".join(e["text"] for e in events)`).
4. **Recording URI**: Use `audio_path`, `frame_output_dir`, or a single placeholder like `sessions/<session_id>/` until Jetson provides a real video path?
5. **LLM**: First implementation: **OpenAI**, **local (Ollama)**, or **stub** only?
6. **Rubric scale**: **Per-criterion max** — each criterion has its own **max** (and anchors 0..max); total max = sum of (criterion max × weight).

Once these are decided, implementation can follow this plan and the mock files below.
