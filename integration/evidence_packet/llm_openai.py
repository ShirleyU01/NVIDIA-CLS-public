"""
Optional OpenAI-backed llm_complete for the evidence packet pipeline.

Use when OPENAI_API_KEY is set. Install: pip install openai
"""

from __future__ import annotations

from integration.evidence_packet import llm as _llm


def llm_complete(system_prompt: str, user_prompt: str, *, images=None, **_kwargs) -> str:
    try:
        from openai import OpenAI
    except ImportError as e:
        raise NotImplementedError(
            "OpenAI backend requires: pip install openai"
        ) from e

    import os
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise NotImplementedError(
            "Set OPENAI_API_KEY to use the OpenAI evidence-packet backend."
        )

    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    user_message: dict
    if images:
        content = [{"type": "text", "text": user_prompt}]
        for img in images:
            image_id = str(img.get("image_id", ""))
            timestamp = img.get("timestamp", None)
            region = img.get("region", None)
            data_url = str(img.get("data_url", ""))
            if not data_url:
                continue
            content.append(
                {
                    "type": "text",
                    "text": f"Screenshot image_id={image_id} timestamp={timestamp} region={region}",
                }
            )
            content.append({"type": "image_url", "image_url": {"url": data_url}})
        user_message = {"role": "user", "content": content}
    else:
        user_message = {"role": "user", "content": user_prompt}

    response = client.chat.completions.create(
        model=os.environ.get("EVIDENCE_PACKET_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": system_prompt},
            user_message,
        ],
        temperature=0.2,
    )
    return (response.choices[0].message.content or "").strip()
