"""Minimal financial calculation module used by the Stage 0 benchmark."""


def calculate_return(start_price, end_price):
    """Return the percentage change between two prices."""
    raise NotImplementedError


def calculate_drawdown(peak_price, current_price):
    """Return the drawdown from a peak price to a current price."""
    raise NotImplementedError
