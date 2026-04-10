"""Shared parsing utilities for Swiss German event data.

Used by scrapers that parse German month names, Swiss time formats
(e.g. '19.30 Uhr'), and dates with year inference.
"""

import re
from datetime import date
from typing import Optional

# Comprehensive German month mapping — covers full names, abbreviations,
# with/without periods, and common CMS typos (e.g. "Marz" without umlaut).
MONTHS_DE = {
    # Full names
    "Januar": 1, "Februar": 2, "März": 3, "April": 4,
    "Mai": 5, "Juni": 6, "Juli": 7, "August": 8,
    "September": 9, "Oktober": 10, "November": 11, "Dezember": 12,
    # Abbreviations with period
    "Jan.": 1, "Feb.": 2, "Mär.": 3, "Apr.": 4,
    "Jun.": 6, "Jul.": 7, "Aug.": 8,
    "Sep.": 9, "Sept.": 9, "Okt.": 10, "Nov.": 11, "Dez.": 12,
    # Abbreviations without period
    "Jan": 1, "Feb": 2, "Mär": 3, "Apr": 4,
    "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Okt": 10, "Nov": 11, "Dez": 12,
    # Typos seen in the wild
    "Marz": 3,
}


def parse_german_date(day: int, month_str: str, year: int = None) -> Optional[str]:
    """Parse a day + German month string into YYYY-MM-DD.

    If year is not provided, infers it: if the date is before the current
    month, assumes next year.
    """
    month = MONTHS_DE.get(month_str.strip())
    if not month:
        return None
    try:
        if year is None:
            today = date.today()
            year = today.year
            if date(year, month, day) < today.replace(day=1):
                year += 1
        return f"{year:04d}-{month:02d}-{day:02d}"
    except (ValueError, OverflowError):
        return None


def parse_german_date_string(date_str: str) -> Optional[str]:
    """Parse a German date string into YYYY-MM-DD.

    Supports formats:
    - 'DD.MM.YYYY' (numeric)
    - 'DD. MonthName YYYY' (with explicit year)
    - 'DD. MonthName' or 'DD. Abbrev.' (year inferred)

    Searches within the string, so surrounding text (e.g. day names) is OK.
    """
    date_str = date_str.strip()

    # Try numeric: DD.MM.YYYY
    m = re.search(r"(\d{1,2})\.(\d{2})\.(\d{4})", date_str)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1).zfill(2)}"

    # Try with year: '2. April 2026'
    m = re.search(r"(\d{1,2})\.\s*([A-Za-zäöüÄÖÜ]+\.?)\s+(\d{4})", date_str)
    if m:
        return parse_german_date(int(m.group(1)), m.group(2), int(m.group(3)))

    # Try without year: '2. April' or '15. Mär.'
    m = re.search(r"(\d{1,2})\.\s*([A-Za-zäöüÄÖÜ]+\.?)", date_str)
    if m:
        return parse_german_date(int(m.group(1)), m.group(2))

    return None


def parse_time(time_str: str) -> Optional[str]:
    """Parse Swiss time formats into HH:MM:SS.

    Handles '19.30 Uhr', '19:30', '9.30', etc.
    Returns the first time found in the string.
    """
    if not time_str or time_str.strip() in ("–", "-", ""):
        return None
    m = re.search(r"(\d{1,2})[.:](\d{2})", time_str)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}:00"
    return None


def parse_end_time(time_str: str) -> Optional[str]:
    """Extract end time from a range like '13.30 - 14.15 Uhr'.

    Returns the second time in HH:MM:SS, or None if no range found.
    """
    if not time_str:
        return None
    m = re.search(r"\d{1,2}[.:]\d{2}\s*[-–]\s*(\d{1,2})[.:](\d{2})", time_str)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}:00"
    return None
