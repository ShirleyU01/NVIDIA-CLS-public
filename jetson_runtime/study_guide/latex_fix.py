"""
Fix common LLM-generated LaTeX so KaTeX (remark-math) renders it correctly.

Applied to every feedback markdown string before it is returned to the caller
or saved to disk. Mirrors ``web/src/utils/studyMarkdownPrep.ts#fixLatexForKatex``.
"""

from __future__ import annotations

import re


# ── delimiter regexes ────────────────────────────────────────────────────────

_INLINE_PAREN_RE = re.compile(r"\\\((.+?)\\\)", re.DOTALL)
_DISPLAY_BRACKET_RE = re.compile(r"\\\[(.+?)\\\]", re.DOTALL)

# Splits text into alternating [prose, math_span, prose, math_span, ...]
# math_span includes the surrounding $ / $$ delimiters.
_MATH_SPAN_SPLIT_RE = re.compile(
    r"(\$\$[\s\S]*?\$\$"   # display math $$...$$
    r"|\$(?:[^$\\]|\\.)+\$)"  # inline math $...$
)

# ── per-span fix regexes ─────────────────────────────────────────────────────

# Double backslash before a command letter/punctuation → single backslash.
# e.g. \\frac → \frac,  \\le → \le,  \\, → \,
_DOUBLE_BACKSLASH_CMD_RE = re.compile(r"\\\\([A-Za-z,;.!])")

# Malformed commands without the required curly-brace groups.
_BINOM_DIGITS_RE = re.compile(r"\\binom(?!\{)(\d+)")
_FRAC_DIGITS_RE = re.compile(r"\\frac(?!\{)(\d{2,})")

# ── prose fix regexes ────────────────────────────────────────────────────────

# Bare sub/superscripts in prose → wrap in $...$
# Only matches letter_X_{...} / letter_X_digit — avoids URLs and normal text.
_BARE_SUBSCRIPT_RE = re.compile(
    r"(?<!\$)(?<![\\A-Za-z])([A-Za-z])_(\{[^}]+\}|\d+)"
)
_BARE_SUPERSCRIPT_RE = re.compile(
    r"(?<!\$)(?<![\\A-Za-z\d])([A-Za-z\d])\^(\{[^}]+\}|\d+)"
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    pos = index - 1
    while pos >= 0 and text[pos] == "\\":
        backslashes += 1
        pos -= 1
    return backslashes % 2 == 1


def _close_unclosed_dollar_spans(text: str) -> str:
    """Append a closing ``$`` when a single-dollar span was left open."""
    in_math = False
    display = False
    pos = 0
    while pos < len(text):
        if text[pos] != "$" or _is_escaped(text, pos):
            pos += 1
            continue
        is_display = pos + 1 < len(text) and text[pos + 1] == "$"
        width = 2 if is_display else 1
        if not in_math:
            in_math = True
            display = is_display
        elif is_display == display:
            in_math = False
        pos += width
    if in_math and not display:
        return text + "$"
    return text


def _fix_math_span(span: str) -> str:
    """Fix common issues inside a math span (delimiters included)."""
    span = _DOUBLE_BACKSLASH_CMD_RE.sub(r"\\\1", span)
    span = _BINOM_DIGITS_RE.sub(
        lambda m: (
            f"\\binom{{{m.group(1)[:-1]}}}{{{m.group(1)[-1]}}}"
            if len(m.group(1)) >= 2
            else m.group(0)
        ),
        span,
    )
    span = _FRAC_DIGITS_RE.sub(
        lambda m: (
            f"\\frac{{{m.group(1)[:-1]}}}{{{m.group(1)[-1]}}}"
            if len(m.group(1)) >= 2
            else m.group(0)
        ),
        span,
    )
    return span


def _fix_prose(prose: str) -> str:
    """Fix common issues in prose (outside math delimiters)."""
    prose = _BARE_SUBSCRIPT_RE.sub(r"$\1_\2$", prose)
    prose = _BARE_SUPERSCRIPT_RE.sub(r"$\1^\2$", prose)
    return prose


# ── public API ───────────────────────────────────────────────────────────────

def fix_latex_for_katex(text: str) -> str:
    """
    Normalize LLM-generated markdown so remark-math + KaTeX can render it.

    Steps (in order):
    1. Convert ``\\(...\\)`` / ``\\[...\\]`` → ``$...$`` / ``$$...$$``
    2. Close any unclosed ``$`` spans
    3. Inside math spans: fix double-backslash commands, malformed \\binom / \\frac
    4. In prose: wrap bare subscripts/superscripts in ``$...$``
    """
    if not text:
        return text
    s = text.replace("\r\n", "\n")
    s = _DISPLAY_BRACKET_RE.sub(lambda m: f"$${m.group(1).strip()}$$", s)
    s = _INLINE_PAREN_RE.sub(lambda m: f"${m.group(1).strip()}$", s)
    s = _close_unclosed_dollar_spans(s)
    parts = _MATH_SPAN_SPLIT_RE.split(s)
    out: list[str] = []
    for i, part in enumerate(parts):
        out.append(_fix_math_span(part) if i % 2 == 1 else _fix_prose(part))
    return "".join(out)
