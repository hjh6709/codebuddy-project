_PERCENTAGE_FACTOR = 100
_DECIMAL_PLACES = 2


def calculate_pass_rate(passed: int, total: int) -> float:
    """Return the percentage of passed review checks.

    Args:
        passed: Number of checks that passed.
        total: Total number of checks. Must be greater than zero.

    Raises:
        ValueError: If the counts cannot describe a valid pass rate.
    """
    if total <= 0:
        raise ValueError("total must be greater than zero")
    if passed < 0:
        raise ValueError("passed must not be negative")
    if passed > total:
        raise ValueError("passed must not exceed total")
    return round(
        passed / total * _PERCENTAGE_FACTOR,
        _DECIMAL_PLACES,
    )
