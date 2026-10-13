"""Tests for scraping/scrape_olg_ktv.py (ClubDesk pages, no network).

Run from the project root:
    scraping/.venv/bin/python tests/test_olg_ktv.py
"""

import os
import sys
import unittest
from unittest import mock

import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scraping"))

import scrape_olg_ktv as olg  # noqa: E402

TILE = (
    '<div class="cd-tile-h-box" onclick="window.location.href=\'/?b=1&amp;e=42\'">'
    '<div class="cd-tile-h-main-heading">Clubabend</div>'
    '<div class="cd-tile-h-main-subheading">Mi 05.11.2026 19:00 - 21:00</div>'
    '</div>'
)
VEREINS_PAGE = f"<html><body><div class='cd-list'>{TILE}</div></body></html>"
NACHWUCHS_PAGE = (
    "<html><body><h3>Mittwoch 12.11.2026</h3>"
    '<div class="cd-tile-h-box">'
    '<div class="cd-tile-h-main-heading">Training</div>'
    '<div class="cd-tile-h-main-subheading">17:30 - 19:00</div>'
    '<div class="cd-tile-h-detail-value">Altdorf</div>'
    "</div></body></html>"
)
# What ClubDesk served on 2026-06-17: a normal looking page with no tiles
EMPTY_PAGE = "<html><body><div class='cd-list'></div></body></html>"


class FakeResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Server Error")


def fetch_with(*responses):
    with mock.patch.object(olg.requests, "get", side_effect=list(responses)):
        return olg.fetch_events()


class OlgTests(unittest.TestCase):
    def test_both_pages_empty_raises_so_the_orchestrator_retries(self):
        with self.assertRaises(ValueError) as ctx:
            fetch_with(FakeResponse(200, EMPTY_PAGE), FakeResponse(200, EMPTY_PAGE))
        self.assertIn("no event tiles on either page", str(ctx.exception))

    def test_http_error_propagates(self):
        with self.assertRaises(requests.HTTPError):
            fetch_with(FakeResponse(500, "error"), FakeResponse(200, NACHWUCHS_PAGE))

    def test_one_empty_page_is_a_legitimate_zero(self):
        events = fetch_with(FakeResponse(200, VEREINS_PAGE), FakeResponse(200, EMPTY_PAGE))
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["title"], "Clubabend")
        self.assertEqual(ev["date"], "2026-11-05")
        self.assertEqual(ev["start_time"], "19:00:00")
        self.assertEqual(ev["end_time"], "21:00:00")
        self.assertEqual(ev["detail_url"], "https://olg-ktv-altdorf.ch/?b=1&e=42")

    def test_nachwuchs_page_takes_date_from_heading(self):
        events = fetch_with(FakeResponse(200, EMPTY_PAGE), FakeResponse(200, NACHWUCHS_PAGE))
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["title"], "Training (Nachwuchstrainings)")
        self.assertEqual(ev["date"], "2026-11-12")
        self.assertEqual(ev["start_time"], "17:30:00")
        self.assertEqual(ev["location"], "Altdorf")

    def test_duplicate_across_pages_is_merged(self):
        dup = NACHWUCHS_PAGE.replace("Training", "Clubabend").replace("12.11.2026", "05.11.2026")
        events = fetch_with(FakeResponse(200, VEREINS_PAGE), FakeResponse(200, dup))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "Clubabend")
        self.assertEqual(events[0]["location"], "Altdorf")  # filled in from the trainings page


if __name__ == "__main__":
    unittest.main(verbosity=2)
