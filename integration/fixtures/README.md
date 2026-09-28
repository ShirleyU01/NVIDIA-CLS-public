# Fixtures for evidence packet pipeline

**Timestamps**: All timestamps are in **seconds** (float), matching **Whisper** segment output on Jetson.

- **rubric_bayes_oral_v1.json** — Mock rubric: 4 criteria (C1–C4) with **per-criterion max** (C1–C3 max 2, C4 max 1), 0–2 or 0–1 anchors.
- **session_mock_001.json** — Mock session: 2 QA blocks; Q1 has 2 screenshots (timestamps in seconds), Q2 has no screenshots (tests `missing_timestamp_for_quote`).
- **session_mock_002.json** — Edge cases: no screenshots in any block; Q1 very short answer ("I'm not sure."); Q2 long answer (tests all-null timestamps and quote validation).

## Running the pipeline

Default LLM is a stub (raises `NotImplementedError`). Options:

1. **With a real LLM** — Set `OPENAI_API_KEY` and use the OpenAI backend:
   ```bash
   # In code: from integration.evidence_packet.llm_openai import llm_complete
   # Then run_evidence_packet(..., llm_complete_fn=llm_complete)
   ```
   Or install and call: `pip install openai`, then in your script pass `llm_complete_fn` from `integration.evidence_packet.llm_openai`.

2. **CLI** (requires an LLM connected in pipeline or passed via code):
   ```bash
   PYTHONPATH=. python -m integration.evidence_packet \
     --rubric integration/fixtures/rubric_bayes_oral_v1.json \
     --session integration/fixtures/session_mock_001.json \
     --out evidence_packet.json
   ```

3. **Tests** (mock LLM, no API key):
   ```bash
   PYTHONPATH=. pytest integration/test_evidence_packet.py -v
   ```
