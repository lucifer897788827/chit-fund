from __future__ import annotations

import math
import re
from typing import Any


WHOLE_AMOUNT_ERROR = "Decimal values are not allowed. Use whole amounts only."
_INTEGER_PATTERN = re.compile(r"^[+-]?\d+$")
_DECIMAL_PATTERN = re.compile(r"^[+-]?\d+\.\d+$")


def _normalize_text(value: Any) -> str:
    return str(value).strip()


def parse_whole_amount(value: Any, *, allow_none: bool = False) -> int | None:
    if value is None:
        return None if allow_none else 0
    if isinstance(value, bool):
        raise ValueError(WHOLE_AMOUNT_ERROR)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError(WHOLE_AMOUNT_ERROR)
        return int(value)

    text = _normalize_text(value)
    if not text:
        return None if allow_none else 0
    if _INTEGER_PATTERN.fullmatch(text):
        return int(text)
    if _DECIMAL_PATTERN.fullmatch(text):
        raise ValueError(WHOLE_AMOUNT_ERROR)
    raise ValueError("Value must be a whole number")


def floor_money(value: Any, *, allow_none: bool = False) -> int | None:
    if value is None:
        return None if allow_none else 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Value must be finite")
        return math.floor(value)

    text = _normalize_text(value)
    if not text:
        return None if allow_none else 0
    if _INTEGER_PATTERN.fullmatch(text):
        return int(text)
    if _DECIMAL_PATTERN.fullmatch(text):
        whole_part, _fraction = text.split(".", 1)
        if text.startswith("-") and any(char != "0" for char in _fraction):
            return int(whole_part) - 1
        return int(whole_part)
    raise ValueError("Value must be numeric")


def money_int(value: Any) -> int:
    normalized = floor_money(value)
    return 0 if normalized is None else normalized


def money_int_or_none(value: Any) -> int | None:
    return floor_money(value, allow_none=True)

