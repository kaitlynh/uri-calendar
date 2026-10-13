"""Unit tests for scraping/antibot.py (challenge detection and fetch wrapper).

Run from the project root:
    scraping/.venv/bin/python tests/test_antibot.py
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scraping"))

import antibot  # noqa: E402

# Verbatim from the 2026-09-07 run log (Flüelen and Seedorf DPCalendar endpoints)
JSON_DENIAL = (
    '{ \t"message": "Access denied by Imunify360 bot-protection. '
    'IPs used for automation should be whitelisted" }'
)

# The first 200 bytes of the altdorf.ch listing on the same run, padded to a
# plausible stub; the real listing is over 1 MB and starts with an HTML comment.
HTML_STUB = (
    '<!DOCTYPE html> <html lang="en"> <head> <meta charset="utf8"> '
    '<meta name="viewport" content="width=device-width,initial-scale=1.0"> '
    '<script> (function(){ setTimeout(function(){ window.location.reload(); }, 1000); })(); '
    '</script> </head> <body></body> </html>'
)

REAL_PAGE = (
    "<!-- banner -->\n<html lang='de'><body>"
    + '<div class="grid col cols-1 event-item">Anlass</div>' * 400
    + "</body></html>"
)


class FakeResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


class DetectTests(unittest.TestCase):
    def test_json_denial_is_a_challenge(self):
        self.assertEqual(antibot.detect(200, JSON_DENIAL), "json")

    def test_html_stub_is_a_challenge(self):
        self.assertEqual(antibot.detect(200, HTML_STUB), "html")

    def test_415_is_a_challenge(self):
        self.assertEqual(antibot.detect(415, ""), "415")

    def test_real_page_is_not(self):
        self.assertIsNone(antibot.detect(200, REAL_PAGE))

    def test_small_real_page_without_reload_is_not(self):
        self.assertIsNone(antibot.detect(200, "<html><body><p>Keine Anlässe</p></body></html>"))

    def test_large_page_with_a_late_reload_script_is_not(self):
        body = REAL_PAGE + "<script>setTimeout(function(){ window.location.reload() }, 60000)</script>"
        self.assertIsNone(antibot.detect(200, body))

    def test_empty_body_is_not(self):
        self.assertIsNone(antibot.detect(200, ""))


class GetTests(unittest.TestCase):
    def setUp(self):
        antibot._cookies.clear()
        antibot._solved.clear()

    def test_raises_on_challenge(self):
        with mock.patch.object(antibot.requests, "get", return_value=FakeResponse(200, JSON_DENIAL)):
            with self.assertRaises(antibot.BotChallenge) as ctx:
                antibot.get("https://flueelen.ch/index.php?option=com_dpcalendar")
        self.assertEqual(ctx.exception.kind, "json")
        self.assertEqual(ctx.exception.host, "flueelen.ch")
        self.assertIn("Imunify360", str(ctx.exception))

    def test_passes_real_response_through(self):
        fake = FakeResponse(200, REAL_PAGE)
        with mock.patch.object(antibot.requests, "get", return_value=fake) as m:
            resp = antibot.get("https://altdorf.ch/aktuelles/veranstaltungen", headers={"X": "1"})
        self.assertIs(resp, fake)
        self.assertEqual(m.call_args.kwargs["headers"], {"X": "1"})
        self.assertEqual(m.call_args.kwargs["timeout"], 15)
        self.assertNotIn("cookies", m.call_args.kwargs)

    def test_sends_cookies_after_solve(self):
        antibot._cookies["seedorf-uri.ch"] = {"imunify_ok": "1"}
        with mock.patch.object(antibot.requests, "get", return_value=FakeResponse(200, REAL_PAGE)) as m:
            antibot.get("https://www.seedorf-uri.ch/index.php", cookies={"other": "2"})
        self.assertEqual(m.call_args.kwargs["cookies"], {"imunify_ok": "1", "other": "2"})

    def test_solve_short_circuits_for_a_cleared_host(self):
        antibot._solved.add("volleyuri.ch")
        self.assertTrue(antibot.solve("https://volleyuri.ch/veranstaltungen"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
