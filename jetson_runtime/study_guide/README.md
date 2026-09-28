## Study guide (paper → camera → feedback)

This folder is **additive**: it does not modify the existing `jetson_runtime` exam pipeline.

### Goal (first milestone)

Capture a photo of a student's written work (paper) using the Jetson-attached camera and ask the LLM to return **fast, structured feedback**.

### Quickstart

1. Ensure your camera is available at `config/settings.py` `CAMERA_DEVICE` (default: `/dev/video0`).
2. Ensure `OPENAI_API_KEY` is set (either export it or use `jetson_runtime/.env`).
3. Run:

```bash
python3 -m study_guide.run_paper_feedback --question study_guide/example_questions/cs109_probability.json
```

### Outputs

Runs create a session folder under `jetson_runtime/sessions/<session_id>/paper/` containing:

- `paper_*.jpg` captured image(s)
- `paper_feedback.json` structured feedback from the LLM
- `paper_feedback.md` human-readable feedback

