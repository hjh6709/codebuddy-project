def calculate_pass_rate(passed: int, total: int) -> float:
    """Return the percentage of passed review checks."""
    return round(passed / total * 100, 2)
