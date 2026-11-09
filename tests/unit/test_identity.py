"""Synthetic fleet identifiers never resemble real IMEIs."""

import pytest

from telematics.simulator.identity import synthetic_imei


def luhn_valid(value: str) -> bool:
    total = 0
    for index, character in enumerate(value):
        digit = int(character)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


@pytest.mark.unit
def test_synthetic_imei_is_zero_prefixed_unique_and_luhn_valid() -> None:
    identifiers = [synthetic_imei(index) for index in range(1, 5001)]

    assert identifiers[0] == "000000000000018"
    assert all(len(identifier) == 15 and identifier.startswith("000") for identifier in identifiers)
    assert len(set(identifiers)) == len(identifiers)
    assert all(luhn_valid(identifier) for identifier in identifiers)
