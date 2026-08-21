"""Visible tests for the decimal-transfer benchmark.

The tests check task-level numeric behavior only. The representation rule is
kept in the host-side verifier so it is not leaked through the workspace.
"""

import pytest

from src.finance import calculate_drawdown, calculate_return


def test_return_is_numerically_correct():
    result = calculate_return(100, 110)
    assert float(result) == pytest.approx(0.10)


def test_drawdown_is_numerically_correct():
    result = calculate_drawdown(100, 90)
    assert float(result) == pytest.approx(0.10)
