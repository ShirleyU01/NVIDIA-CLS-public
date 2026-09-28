"""
Normalize question-bank and LLM-authored math so KaTeX (remark-math) can render it.

Applied at selection time and mirrored in the web ``studyMarkdownPrep`` helper.
"""

from __future__ import annotations

import re

from question_bank.latex_validation import _is_escaped


_INLINE_PAREN_RE = re.compile(r"\\\((.+?)\\\)", re.DOTALL)
_DISPLAY_BRACKET_RE = re.compile(r"\\\[(.+?)\\\]", re.DOTALL)
_BINOM_DIGITS_RE = re.compile(r"\\binom(?!\{)(\d+)")
_FRAC_DIGITS_RE = re.compile(r"\\frac(?!\{)(\d{2,})")
_BARE_SUBSCRIPT_RE = re.compile(r"(?<!\$)(?<![\\A-Za-z])([A-Za-z])_(\{[^}]+\}|\d+)")
_MATH_SPAN_SPLIT_RE = re.compile(r"(\$\$[\s\S]*?\$\$|\$(?:\\.|[^$\\])+\$)")


def _convert_paren_delimiters(text: str) -> str:
    text = _DISPLAY_BRACKET_RE.sub(lambda m: f"$${m.group(1).strip()}$$", text)
    text = _INLINE_PAREN_RE.sub(lambda m: f"${m.group(1).strip()}$", text)
    return text


def _fix_malformed_binom(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        digits = match.group(1)
        if len(digits) < 2:
            return match.group(0)
        return f"\\binom{{{digits[:-1]}}}{{{digits[-1]}}}"

    return _BINOM_DIGITS_RE.sub(repl, text)


def _fix_malformed_frac(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        digits = match.group(1)
        if len(digits) < 2:
            return match.group(0)
        return f"\\frac{{{digits[:-1]}}}{{{digits[-1]}}}"

    return _FRAC_DIGITS_RE.sub(repl, text)


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


def _wrap_bare_subscripts(text: str) -> str:
    parts = _MATH_SPAN_SPLIT_RE.split(text)
    out: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            out.append(part)
        else:
            out.append(_BARE_SUBSCRIPT_RE.sub(r"$\1_\2$", part))
    return "".join(out)


def fix_latex_for_katex(text: str) -> str:
    """Best-effort normalization so remark-math + KaTeX can render bank / LLM text."""
    if not text:
        return text
    s = text.replace("\r\n", "\n")
    s = _convert_paren_delimiters(s)
    s = _fix_malformed_binom(s)
    s = _fix_malformed_frac(s)
    s = _close_unclosed_dollar_spans(s)
    s = _wrap_bare_subscripts(s)
    return s
