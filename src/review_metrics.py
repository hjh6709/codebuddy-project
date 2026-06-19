_PERCENTAGE_FACTOR: int = 100
_DECIMAL_PLACES: int = 2


def calculate_pass_rate(passed: int, total: int) -> float:
    """Return the percentage of passed review checks.

    Args:
        passed: Number of checks that passed.
        total: Total number of checks. Must be greater than zero.

    Returns:
        Pass rate as a percentage rounded to two decimal places.

    Raises:
        TypeError: If either count is not an integer.
        ValueError: If total is not positive, passed is negative, or passed
            exceeds total.
    """
    if type(passed) is not int:
        raise TypeError("passed must be an integer")
    if type(total) is not int:
        raise TypeError("total must be an integer")
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
