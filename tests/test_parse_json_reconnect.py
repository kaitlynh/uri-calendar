"""Tests for db/parse_json.py's handling of a dropped database connection.

Uses fake connections, no database.  Run from the project root:
    scraping/.venv/bin/python tests/test_parse_json_reconnect.py
"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import psycopg2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "db"))

import parse_json  # noqa: E402

EVENTS = [
    {"source_name": "altdorf.ch", "base_url": "https://altdorf.ch", "event_title": f"Anlass {i}",
     "start_date": "2026-11-0%d" % (i + 1), "priority": 3}
    for i in range(4)
]
DROP = psycopg2.OperationalError("SSL connection has been closed unexpectedly")


class FakeCursor:
    """Records executed statements; raises `fail_with` on the event numbered `fail_at`."""

    def __init__(self, conn, fail_at=None, fail_with=None, closes_conn=True):
        self.conn = conn
        self.fail_at = fail_at
        self.fail_with = fail_with
        self.closes_conn = closes_conn
        self.statements = []
        self.events_done = 0

    def execute(self, sql, params=None):
        self.statements.append(sql.strip().split("\n")[0])
        if sql.strip().startswith("INSERT INTO events"):
            self.events_done += 1
            if self.fail_at == self.events_done and self.fail_with is not None:
                if self.closes_conn:
                    self.conn.closed = 2
                err, self.fail_with = self.fail_with, None
                raise err

    def fetchone(self):
        return (1,)

    def close(self):
        pass


class FakeConn:
    def __init__(self, **cursor_kwargs):
        self.closed = 0
        self.committed = False
        self.cur = FakeCursor(self, **cursor_kwargs)

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = 1

    @property
    def inserted(self):
        return sum(1 for s in self.cur.statements if s.startswith("RELEASE SAVEPOINT"))


class ReconnectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(EVENTS, self.tmp)
        self.tmp.close()

    def tearDown(self):
        os.unlink(self.tmp.name)

    def run_ingest(self, *conns):
        with mock.patch.object(parse_json.psycopg2, "connect", side_effect=list(conns)) as connect, \
             mock.patch.object(parse_json.time, "sleep") as sleep:
            parse_json.ingest_events(self.tmp.name)
        return connect, sleep

    def test_clean_run_uses_one_connection(self):
        c1 = FakeConn()
        connect, _ = self.run_ingest(c1)
        self.assertEqual(connect.call_count, 1)
        self.assertEqual(c1.inserted, 4)
        self.assertTrue(c1.committed)

    def test_dropped_connection_reconnects_and_reruns_the_whole_batch(self):
        c1 = FakeConn(fail_at=2, fail_with=DROP)
        c2 = FakeConn()
        connect, sleep = self.run_ingest(c1, c2)
        self.assertEqual(connect.call_count, 2)
        self.assertEqual(c1.inserted, 1)          # got one event in before the drop
        self.assertFalse(c1.committed)            # nothing from the first attempt is kept
        self.assertEqual(c2.inserted, 4)          # the full batch ran again
        self.assertTrue(c2.committed)
        sleep.assert_not_called()                 # the reconnect worked first time

    def test_second_drop_gives_up_with_both_causes(self):
        c1 = FakeConn(fail_at=2, fail_with=DROP)
        c2 = FakeConn(fail_at=3, fail_with=psycopg2.OperationalError("server closed the connection"))
        with self.assertRaises(RuntimeError) as ctx:
            self.run_ingest(c1, c2)
        self.assertIn("lost twice", str(ctx.exception))
        self.assertIn("SSL connection", str(ctx.exception))
        self.assertIn("server closed", str(ctx.exception))
        self.assertFalse(c2.committed)

    def test_reconnect_waits_for_the_server_to_come_back(self):
        c1 = FakeConn(fail_at=1, fail_with=DROP)
        c2 = FakeConn()
        refused = psycopg2.OperationalError("connection refused")
        connect, sleep = self.run_ingest(c1, refused, refused, c2)
        self.assertEqual(connect.call_count, 4)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(c2.inserted, 4)
        self.assertTrue(c2.committed)

    def test_reconnect_gives_up_after_the_tries(self):
        c1 = FakeConn(fail_at=1, fail_with=DROP)
        refused = [psycopg2.OperationalError("connection refused")] * parse_json.RECONNECT_TRIES
        with self.assertRaises(RuntimeError) as ctx:
            self.run_ingest(c1, *refused)
        self.assertIn("Could not reconnect", str(ctx.exception))

    def test_bad_record_is_skipped_without_reconnecting(self):
        c1 = FakeConn(fail_at=3, fail_with=psycopg2.DataError("invalid input syntax"), closes_conn=False)
        connect, _ = self.run_ingest(c1)
        self.assertEqual(connect.call_count, 1)
        self.assertEqual(c1.inserted, 3)
        self.assertIn("ROLLBACK TO SAVEPOINT ev", c1.cur.statements)
        self.assertTrue(c1.committed)

    def test_operational_error_with_live_connection_is_a_skip_not_a_drop(self):
        timeout = psycopg2.OperationalError("canceling statement due to statement timeout")
        c1 = FakeConn(fail_at=2, fail_with=timeout, closes_conn=False)
        connect, _ = self.run_ingest(c1)
        self.assertEqual(connect.call_count, 1)
        self.assertEqual(c1.inserted, 3)
        self.assertTrue(c1.committed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
