"""Number and date formatting shared by the app and the email renderer.

One module so a figure reads identically on screen and in the email: same
thousands separators, same decimal places per instrument, same signed
convention. Everything here returns display strings — never values to compute
with.

Not part of the data contract; the Rust port needs its own presentation layer,
but the rules below are the ones to mirror.
"""

from __future__ import annotations

from datetime import date, datetime

from models import Direction

#: Shown wherever a value is genuinely absent.
EMPTY = "—"

# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------


def fmt_number(value: float | int | None, decimals: int = 0, signed: bool = False) -> str:
    """Thousands-separated number, optionally with an explicit + sign."""
    if value is None:
        return EMPTY
    return f"{value:{'+' if signed else ''},.{decimals}f}"


def fmt_price(value: float | None, decimals: int) -> str:
    """A price in USD per troy ounce, at the instrument's own decimals."""
    return fmt_number(value, decimals)


def fmt_pct(value: float | None, decimals: int = 2, signed: bool = True) -> str:
    """A percentage already expressed as ``12.5`` for 12.5%."""
    if value is None:
        return EMPTY
    return f"{value:{'+' if signed else ''},.{decimals}f}%"


def fmt_usd(value: float | None, decimals: int = 0, signed: bool = False) -> str:
    """A full-precision USD figure, e.g. ``$1,234,568``."""
    if value is None:
        return EMPTY
    sign = "+" if signed and value > 0 else "-" if value < 0 else ""
    return f"{sign}${abs(value):,.{decimals}f}"


def fmt_usd_compact(value: float | None, signed: bool = False) -> str:
    """USD scaled to bn / m / k so columns stay skimmable.

    Scale is chosen per value, so the unit is always written out rather than
    carried in the column header.
    """
    if value is None:
        return EMPTY
    magnitude = abs(value)
    sign = "+" if signed and value > 0 else "-" if value < 0 else ""
    if magnitude >= 1_000_000_000:
        return f"{sign}${magnitude / 1_000_000_000:,.2f}bn"
    if magnitude >= 1_000_000:
        return f"{sign}${magnitude / 1_000_000:,.1f}m"
    if magnitude >= 1_000:
        return f"{sign}${magnitude / 1_000:,.1f}k"
    return f"{sign}${magnitude:,.0f}"


def fmt_oz(value: float | None, decimals: int = 0, signed: bool = False) -> str:
    """Troy ounces. The unit belongs in the column header, not here."""
    return fmt_number(value, decimals, signed)


def fmt_tonnes(value: float | None, decimals: int = 1, signed: bool = False) -> str:
    """Metric tonnes."""
    return fmt_number(value, decimals, signed)


def fmt_lots(value: int | None, signed: bool = False) -> str:
    """Exchange contracts."""
    return fmt_number(value, 0, signed)


# ---------------------------------------------------------------------------
# Direction
# ---------------------------------------------------------------------------

#: Text indicator paired with colour, so direction never rests on colour alone.
DIRECTION_MARKS: dict[Direction, str] = {
    Direction.UP: "▲",
    Direction.DOWN: "▼",
    Direction.FLAT: "■",
}


def direction_mark(direction: Direction) -> str:
    return DIRECTION_MARKS[direction]


def direction_for(value: float) -> Direction:
    return Direction.from_change(value)


def direction_colour(direction: Direction, palette: dict[str, str]) -> str:
    """Look a direction up in a palette carrying ``up``/``down``/``flat``."""
    return palette[direction.value]


# ---------------------------------------------------------------------------
# Dates and times
# ---------------------------------------------------------------------------


def fmt_date(value: date | None) -> str:
    """Unambiguous across the Atlantic: ``24 Aug 2026``."""
    return EMPTY if value is None else f"{value:%d %b %Y}"


def fmt_date_short(value: date | None) -> str:
    """``Mon 24 Aug`` — for calendar rows where the year is implied."""
    return EMPTY if value is None else f"{value:%a %d %b}"


def fmt_datetime_london(value: datetime | None) -> str:
    """``24 Aug 2026, 16:30 London``."""
    return EMPTY if value is None else f"{value:%d %b %Y, %H:%M} London"


def fmt_time(value: str | None) -> str:
    """Pass through an ``HH:MM`` string, or the all-day marker."""
    return value or EMPTY


# ---------------------------------------------------------------------------
# Commentary
# ---------------------------------------------------------------------------


def word_count(text: str) -> int:
    return len(text.split())


def character_count(text: str) -> int:
    return len(text)
