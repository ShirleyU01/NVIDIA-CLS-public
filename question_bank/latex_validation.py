from __future__ import annotations

import re
from dataclasses import dataclass


_DISALLOWED_DELIMITERS = (
    (r"\(", r"\)"),
    (r"\[", r"\]"),
)

_COMMAND_GROUP_COUNTS = {
    "frac": 2,
    "binom": 2,
    "sqrt": 1,
}


@dataclass(frozen=True)
class MathSpan:
    body: str
    display: bool


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    pos = index - 1
    while pos >= 0 and text[pos] == "\\":
        backslashes += 1
        pos -= 1
    return backslashes % 2 == 1


def _extract_dollar_math(text: str) -> tuple[list[MathSpan], list[str]]:
    spans: list[MathSpan] = []
    issues: list[str] = []
    pos = 0
    in_math = False
    display = False
    start = 0

    while pos < len(text):
        if text[pos] != "$" or _is_escaped(text, pos):
            pos += 1
            continue

        is_display = pos + 1 < len(text) and text[pos + 1] == "$"
        width = 2 if is_display else 1
        if not in_math:
            in_math = True
            display = is_display
            start = pos + width
            pos += width
            continue

        if is_display != display:
            issues.append("mixed_math_delimiters")
            pos += width
            continue

        body = text[start:pos]
        if not body.strip():
            issues.append("empty_math_span")
        spans.append(MathSpan(body=body, display=display))
        in_math = False
        pos += width

    if in_math:
        issues.append("unclosed_math_delimiter")
    return spans, issues


def _text_without_math(text: str) -> str:
    out: list[str] = []
    pos = 0
    in_math = False
    display = False

    while pos < len(text):
        if text[pos] != "$" or _is_escaped(text, pos):
            if not in_math:
                out.append(text[pos])
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

    return "".join(out)


def _balanced_grouping(math: str) -> bool:
    stack: list[str] = []
    pairs = {"}": "{", "]": "["}
    for idx, ch in enumerate(math):
        if _is_escaped(math, idx):
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack.pop() != pairs[ch]:
                return False
    return not stack


def _skip_ws(math: str, pos: int) -> int:
    while pos < len(math) and math[pos].isspace():
        pos += 1
    return pos


def _consume_group(math: str, pos: int) -> int | None:
    pos = _skip_ws(math, pos)
    if pos >= len(math) or math[pos] != "{":
        return None

    depth = 0
    while pos < len(math):
        ch = math[pos]
        if not _is_escaped(math, pos):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return pos + 1
        pos += 1
    return None


def _consume_optional_bracket_group(math: str, pos: int) -> int:
    pos = _skip_ws(math, pos)
    if pos >= len(math) or math[pos] != "[":
        return pos

    depth = 0
    while pos < len(math):
        ch = math[pos]
        if not _is_escaped(math, pos):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return pos + 1
        pos += 1
    return pos


def _command_group_issues(math: str) -> list[str]:
    issues: list[str] = []
    for match in re.finditer(r"\\([A-Za-z]+)", math):
        command = match.group(1)
        expected_groups = _COMMAND_GROUP_COUNTS.get(command)
        if expected_groups is None:
            continue

        pos = match.end()
        if command == "sqrt":
            pos = _consume_optional_bracket_group(math, pos)
        for _ in range(expected_groups):
            next_pos = _consume_group(math, pos)
            if next_pos is None:
                issues.append(f"malformed_latex_command:{command}")
                break
            pos = next_pos
    return issues


def latex_issues(text: str) -> list[str]:
    """
    Return lightweight KaTeX-safety issues for generated question-bank text.

    This is intentionally conservative rather than a full LaTeX parser: it catches
    malformed syntax that commonly breaks rendering, while allowing ordinary prose
    with no math.
    """
    if not text:
        return []

    issues: list[str] = []
    for opener, closer in _DISALLOWED_DELIMITERS:
        if opener in text or closer in text:
            issues.append("unsupported_math_delimiter")
            break

    spans, span_issues = _extract_dollar_math(text)
    issues.extend(span_issues)

    prose = _text_without_math(text)
    if re.search(r"(?<!\\)[_^]", prose):
        issues.append("bare_subscript_or_superscript")

    for span in spans:
        if not _balanced_grouping(span.body):
            issues.append("unbalanced_math_grouping")
        issues.extend(_command_group_issues(span.body))

    return sorted(set(issues))


def has_latex_issues(text: str) -> bool:
    return bool(latex_issues(text))
