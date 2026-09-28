from __future__ import annotations

from question_bank.latex_validation import latex_issues


def test_accepts_katex_safe_latex() -> None:
    text = "Compute $\\frac{3}{5}$ and explain why $\\binom{10}{3}$ means 10 choose 3."

    assert latex_issues(text) == []


def test_rejects_malformed_binom_command() -> None:
    issues = latex_issues("How would you interpret $\\binom103$ in this setting?")

    assert "malformed_latex_command:binom" in issues


def test_rejects_unbalanced_delimiters() -> None:
    issues = latex_issues("Explain why $P(A|B) = P(A \\cap B) / P(B).")

    assert "unclosed_math_delimiter" in issues


def test_rejects_unsupported_math_delimiters() -> None:
    issues = latex_issues(r"Use \(P(A \mid B)\) to solve this.")

    assert "unsupported_math_delimiter" in issues


def test_rejects_bare_subscripts_and_superscripts() -> None:
    assert "bare_subscript_or_superscript" in latex_issues("Compare x_1 and x_2.")
    assert "bare_subscript_or_superscript" not in latex_issues("Compare $x_1$ and $x_2$.")
