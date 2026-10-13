"""Tests for the orchestrator's handling of antibot.BotChallenge.

Drives scraping._run_scraper with a fake scraper type so no network is
touched.  Run from the project root:
    scraping/.venv/bin/python tests/test_orchestrator_challenge.py
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scraping"))

import antibot  # noqa: E402
import scraping  # noqa: E402

URL = "https://erstfeld.ch/portrait/veranstaltungen"
SOURCE = {"name": "Fake", "type": "fake", "source_name": "erstfeld.ch", "url": URL, "priority": 3}


def challenge():
    return antibot.BotChallenge(URL, "html", 200, "<!DOCTYPE html> <html lang=\"en\">")


class FakeScraper:
    """Returns the queued outcomes in order; an exception instance is raised."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, source, extracted_at):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ChallengeRetryTests(unittest.TestCase):
    def run_with(self, fake, solve_result):
        with mock.patch.dict(scraping.SCRAPERS, {"fake": fake}), \
             mock.patch.object(scraping, "RETRY_DELAY", 0), \
             mock.patch.object(antibot, "solve", return_value=solve_result) as solve:
            name, events, err = scraping._run_scraper(SOURCE, "2026-10-13T00:00:00+00:00")
        return events, err, solve, fake.calls

    def test_challenge_then_success(self):
        events, err, solve, calls = self.run_with(FakeScraper(challenge(), ["event"]), True)
        self.assertIsNone(err)
        self.assertEqual(events, ["event"])
        self.assertEqual(calls, 2)
        solve.assert_called_once_with(URL)

    def test_challenge_on_last_regular_attempt_still_gets_a_retry(self):
        fake = FakeScraper(RuntimeError("timeout"), challenge(), ["event"])
        events, err, solve, calls = self.run_with(fake, True)
        self.assertIsNone(err)
        self.assertEqual(calls, 3)
        solve.assert_called_once_with(URL)

    def test_challenge_not_passed_fails_without_retry(self):
        events, err, solve, calls = self.run_with(FakeScraper(challenge()), False)
        self.assertIn("Imunify360", err)
        self.assertEqual(events, [])
        self.assertEqual(calls, 1)
        solve.assert_called_once()

    def test_second_challenge_after_passing_is_a_failure(self):
        events, err, solve, calls = self.run_with(FakeScraper(challenge(), challenge()), True)
        self.assertIn("Imunify360", err)
        self.assertEqual(calls, 2)
        solve.assert_called_once()

    def test_ordinary_errors_still_retry_as_before(self):
        fake = FakeScraper(RuntimeError("boom"), ["event"])
        events, err, solve, calls = self.run_with(fake, True)
        self.assertIsNone(err)
        self.assertEqual(calls, 2)
        solve.assert_not_called()

    def test_ordinary_errors_still_give_up_after_two(self):
        fake = FakeScraper(RuntimeError("one"), RuntimeError("two"))
        events, err, solve, calls = self.run_with(fake, True)
        self.assertEqual(err, "ERROR: two")
        self.assertEqual(calls, 2)
        solve.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
