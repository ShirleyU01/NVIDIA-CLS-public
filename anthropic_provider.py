"""Small Anthropic message helpers for the Socrates Claude path."""

import base64
import mimetypes
from typing import Dict, Final


# Keep the first supported set small and explicit for predictable v1 behavior.
SUPPORTED_IMAGE_MIME_TYPES: Final[set[str]] = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


def build_anthropic_image_block(mime_type: str, data_b64: str) -> Dict[str, object]:
    """Build an Anthropic Messages API image content block from base64 bytes."""
    normalized_mime = mime_type.strip().lower()
    if normalized_mime not in SUPPORTED_IMAGE_MIME_TYPES:
        raise ValueError(
            f"Unsupported image MIME type: {mime_type}. "
            f"Supported: {sorted(SUPPORTED_IMAGE_MIME_TYPES)}"
        )

    # Anthropic expects image content blocks with a nested base64 source object.
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": normalized_mime,
            "data": data_b64,
        },
    }


def load_image_file_for_anthropic(image_path: str) -> tuple[str, str]:
    """Read an image file and return `(mime_type, base64_data)` for Anthropic."""
    guessed_mime, _ = mimetypes.guess_type(image_path) #guess the type from image path
    normalized_mime = (guessed_mime or "").lower()
    if normalized_mime not in SUPPORTED_IMAGE_MIME_TYPES:
        raise ValueError(
            f"Unsupported image file type for {image_path!r}: {guessed_mime!r}"
        )

    # Keep this helper simple for v1 CLI usage: read file bytes and base64 encode.
    with open(image_path, "rb") as f:
        data_b64 = base64.b64encode(f.read()).decode("utf-8")
    return normalized_mime, data_b64

"""
Standardizes payload from one tsudent into Anthropic's message format, which expects it to be in the form of a text and image block. 
"""
def build_student_turn_content_for_anthropic(
    text: str,
    *,
    image_blocks: list[Dict[str, object]] | None = None,
) -> list[Dict[str, object]]:
    """Build one student-turn content list for Anthropic from text/screenshots."""
    normalized_text = text.strip()
    content: list[Dict[str, object]] = []

    # Keep text first so the model gets the student's framing before screenshots.
    if normalized_text:
        content.append({"type": "text", "text": normalized_text})

    if image_blocks:
        content.extend(image_blocks)

    if not content:
        raise ValueError("User content requires non-empty text or at least one image.")

    return content
