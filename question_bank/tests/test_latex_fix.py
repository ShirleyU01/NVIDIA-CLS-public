from __future__ import annotations

from question_bank.latex_fix import fix_latex_for_katex
from question_bank.latex_validation import latex_issues


def test_converts_paren_delimiters_to_dollars() -> None:
    text = fix_latex_for_katex(r"Use \(P(A \mid B)\) to solve this.")

    assert r"\(" not in text
    assert "$P(A \\mid B)$" in text
    assert latex_issues(text) == []


def test_fixes_malformed_binom_digits() -> None:
    text = fix_latex_for_katex("Explain what $\\binom103$ means.")

    assert "\\binom{10}{3}" in text
    assert latex_issues(text) == []


def test_closes_unclosed_dollar_span() -> None:
    text = fix_latex_for_katex("Explain why $P(A|B) = P(A \\cap B) / P(B).")

    assert text.endswith("$") or text.count("$") % 2 == 0
    assert "unclosed_math_delimiter" not in latex_issues(text)


def test_wraps_bare_subscripts() -> None:
    text = fix_latex_for_katex("Compare x_1 and x_2.")

    assert "$x_1$" in text
    assert "$x_2$" in text
    assert "bare_subscript_or_superscript" not in latex_issues(text)
