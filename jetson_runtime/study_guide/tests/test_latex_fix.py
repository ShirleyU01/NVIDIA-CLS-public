"""Tests for jetson_runtime/study_guide/latex_fix.py"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_jetson_runtime = _HERE.parents[2]
if str(_jetson_runtime) not in sys.path:
    sys.path.insert(0, str(_jetson_runtime))

from study_guide.latex_fix import fix_latex_for_katex  # noqa: E402


def test_converts_paren_delimiters():
    out = fix_latex_for_katex(r"Use \(P(A \mid B)\) here.")
    assert r"\(" not in out
    assert "$P(A \\mid B)$" in out


def test_converts_bracket_delimiters():
    out = fix_latex_for_katex(r"Display \[\frac{1}{2}\] inline.")
    assert r"\[" not in out
    assert "$$\\frac{1}{2}$$" in out


def test_fixes_double_backslash_commands_in_display_math():
    src = r"$$P(3.5\\le X)=\\int_{3.5}^{6}\\frac{1}{6}\\,dx.$$"
    out = fix_latex_for_katex(src)
    assert r"\\le" not in out
    assert r"\\int" not in out
    assert r"\\frac" not in out
    assert r"\\," not in out
    assert r"\le" in out
    assert r"\int" in out
    assert r"\frac" in out
    assert r"\," in out


def test_fixes_double_backslash_in_inline_math():
    src = r"The value is $\\frac{a}{b}$."
    out = fix_latex_for_katex(src)
    assert r"\\frac" not in out
    assert r"\frac{a}{b}" in out


def test_double_backslash_not_changed_in_prose():
    # A literal \\ in prose (unusual but should not be mangled by accident).
    # The double-backslash regex only fires inside math spans.
    src = "Use latex: \\\\command outside math."
    out = fix_latex_for_katex(src)
    # Prose is not touched by the double-backslash math fixer,
    # but the bare subscript/superscript regexes also shouldn't affect it.
    assert out == src


def test_fixes_malformed_binom_inside_math():
    src = r"Try $\binom103$."
    out = fix_latex_for_katex(src)
    assert r"\binom{10}{3}" in out


def test_closes_unclosed_dollar():
    src = r"See $\alpha and end."
    out = fix_latex_for_katex(src)
    assert out.count("$") % 2 == 0


def test_wraps_bare_subscripts_in_prose():
    out = fix_latex_for_katex("Compare x_1 and x_{n}.")
    assert "$x_1$" in out
    assert "$x_{n}$" in out


def test_wraps_bare_superscripts_in_prose():
    out = fix_latex_for_katex("Time is O(n^2) or O(n^{k}).")
    assert "$n^2$" in out
    assert "$n^{k}$" in out


def test_does_not_double_wrap_math():
    src = "See $x^2 + y_1$ here."
    out = fix_latex_for_katex(src)
    # Should not be changed — already inside math
    assert out == src


def test_real_broken_feedback_example():
    src = (
        "The density is constant on $[2,8]$, so $f(x)=\\\\frac{1}{6}$.\n"
        "$$P(3.5\\\\le X\\\\le 6)=\\\\int_{3.5}^{6}\\\\frac{1}{6}\\\\,dx.$$"
    )
    out = fix_latex_for_katex(src)
    assert r"\\frac" not in out
    assert r"\\le" not in out
    assert r"\\int" not in out
    assert r"\\," not in out
    assert r"\frac{1}{6}" in out
    assert r"\le" in out
