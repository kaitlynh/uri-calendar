"""Shared parsing utilities for Swiss German event data.

Swiss German event pages use a mix of date/time conventions that differ
from both ISO standards and English-language defaults:

    Dates:  "2. April", "15. Mär.", "02.04.2026"
    Times:  "19.30 Uhr", "13.30 - 14.15 Uhr"

This module centralizes that parsing so individual scrapers stay clean.
"""

import re
from datetime import date
from typing import Optional

# German month mapping — covers full names, standard abbreviations (with
# and without trailing period), and typos seen in the wild (e.g. "Marz"
# without umlaut, common in CMS-generated content).
MONTHS_DE = {
    # Full names
    "Januar": 1,    "Februar": 2,   "März": 3,      "April": 4,
    "Mai": 5,       "Juni": 6,      "Juli": 7,      "August": 8,
    "September": 9, "Oktober": 10,  "November": 11, "Dezember": 12,
    # Abbreviations with period
    "Jan.": 1,  "Feb.": 2,  "Mär.": 3,  "Apr.": 4,
    "Jun.": 6,  "Jul.": 7,  "Aug.": 8,
    "Sep.": 9,  "Sept.": 9, "Okt.": 10, "Nov.": 11, "Dez.": 12,
    # Abbreviations without period
    "Jan": 1,   "Feb": 2,   "Mär": 3,   "Apr": 4,
    "Jun": 6,   "Jul": 7,   "Aug": 8,
    "Sep": 9,   "Okt": 10,  "Nov": 11,  "Dez": 12,
    # Typos seen in the wild
    "Marz": 3,
}


def parse_german_date(day: int, month_str: str, year: int = None) -> Optional[str]:
    """Parse a day + German month name into YYYY-MM-DD.

    If year is omitted, infers it: dates before the current month are
    assumed to be next year (events are always in the future).
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

    Handles three common formats:
        "02.04.2026"        — numeric DD.MM.YYYY
        "2. April 2026"     — with explicit year
        "2. April"          — year inferred from context

    Searches within the string, so surrounding text (day names, etc.) is OK.
    """
    date_str = date_str.strip()

    # Numeric: DD.MM.YYYY
    m = re.search(r"(\d{1,2})\.(\d{2})\.(\d{4})", date_str)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1).zfill(2)}"

    # With year: "2. April 2026"
    m = re.search(r"(\d{1,2})\.\s*([A-Za-zäöüÄÖÜ]+\.?)\s+(\d{4})", date_str)
    if m:
        return parse_german_date(int(m.group(1)), m.group(2), int(m.group(3)))

    # Without year: "2. April" or "15. Mär."
    m = re.search(r"(\d{1,2})\.\s*([A-Za-zäöüÄÖÜ]+\.?)", date_str)
    if m:
        return parse_german_date(int(m.group(1)), m.group(2))

    return None


def parse_time(time_str: str) -> Optional[str]:
    """Parse Swiss time formats into HH:MM:SS.

    Handles "19.30 Uhr", "19:30", "9.30", etc.
    Swiss German uses a period as the hour:minute separator.
    """
    if not time_str or time_str.strip() in ("–", "-", ""):
        return None
    m = re.search(r"(\d{1,2})[.:](\d{2})", time_str)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}:00"
    return None


def parse_end_time(time_str: str) -> Optional[str]:
    """Extract end time from a range like "13.30 - 14.15 Uhr".

    Returns the second time as HH:MM:SS, or None if no range found.
    Both en-dash (–) and hyphen (-) separators are supported.
    """
    if not time_str:
        return None
    m = re.search(r"\d{1,2}[.:]\d{2}\s*[-–]\s*(\d{1,2})[.:](\d{2})", time_str)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}:00"
    return None
