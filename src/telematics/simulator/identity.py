"""Synthetic vehicle identifiers and Luhn-valid, zero-prefixed IMEIs."""


def synthetic_imei(global_index: int) -> str:
    """Return a unique synthetic 15-digit IMEI for a one-based fleet index."""
    if not 1 <= global_index <= 99_999_999_999_999:
        raise ValueError("IMEI index must fit in the 14-digit payload")
    payload = f"{global_index:014d}"
    total = 0
    for index, character in enumerate(payload):
        digit = int(character)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    check_digit = (-total) % 10
    return f"{payload}{check_digit}"
