"""
Server-side API validation for the uri-calendar pipeline.

This script runs ON THE SERVER after the main pipeline validation runs in
GitHub Actions. It tests the live API endpoints that are only reachable
from the server itself (localhost:5000).

Checks:
  1. /api/events?date=<today> returns 200 with an array
  2. /api/sources returns 200 with source data and expected fields
  3. /api/events date range query works
  4. Every source from /api/sources has a display_name

Exit code 0 = all checks passed, 1 = failures found.
Output is printed to stdout for the GitHub Actions workflow to capture.
"""

import sys
from datetime import date, timedelta

try:
    import requests
except ImportError:
    print("[FAIL] requests not installed — cannot run API checks")
    sys.exit(1)

API_BASE = "http://localhost:5000"


class ValidationResult:
    def __init__(self):
        self.passes = []
        self.warnings = []
        self.failures = []

    def passed(self, msg):
        self.passes.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def fail(self, msg):
        self.failures.append(msg)

    @property
    def ok(self):
        return len(self.failures) == 0

    def summary(self):
        lines = []
        lines.append("-" * 50)
        lines.append("API Validation (server-side)")
        lines.append("-" * 50)

        if self.passes:
            for p in self.passes:
                lines.append(f"  [PASS] {p}")

        if self.warnings:
            for w in self.warnings:
                lines.append(f"  [WARN] {w}")

        if self.failures:
            for f in self.failures:
                lines.append(f"  [FAIL] {f}")

        lines.append("")
        status = "PASSED" if self.ok else "FAILED"
        lines.append(f"API result: {status} — {len(self.passes)} passed, {len(self.warnings)} warnings, {len(self.failures)} failures")
        lines.append("-" * 50)
        return "\n".join(lines)


def check_events_today(result):
    """GET /api/events?date=<today> returns 200 with an array."""
    today_str = date.today().isoformat()
    try:
        resp = requests.get(f"{API_BASE}/api/events?date={today_str}", timeout=5)
    except requests.ConnectionError:
        result.fail(f"API not reachable at {API_BASE}")
        return

    if resp.status_code != 200:
        result.fail(f"/api/events?date={today_str} returned status {resp.status_code}")
        return

    data = resp.json()
    if not isinstance(data, list):
        result.fail(f"/api/events returned non-array: {type(data)}")
        return

    result.passed(f"/api/events?date={today_str} returned {len(data)} events")


def check_events_range(result):
    """GET /api/events with start_date and end_date returns 200."""
    today = date.today()
    end = today + timedelta(days=7)
    try:
        resp = requests.get(
            f"{API_BASE}/api/events",
            params={"start_date": today.isoformat(), "end_date": end.isoformat()},
            timeout=5,
        )
    except requests.ConnectionError:
        result.fail(f"API not reachable at {API_BASE}")
        return

    if resp.status_code != 200:
        result.fail(f"/api/events range query returned status {resp.status_code}")
        return

    data = resp.json()
    if not isinstance(data, list):
        result.fail(f"/api/events range query returned non-array: {type(data)}")
        return

    result.passed(f"/api/events range query (7 days) returned {len(data)} events")


def check_sources(result):
    """GET /api/sources returns 200 with source data."""
    try:
        resp = requests.get(f"{API_BASE}/api/sources", timeout=5)
    except requests.ConnectionError:
        result.fail(f"API not reachable at {API_BASE}")
        return

    if resp.status_code != 200:
        result.fail(f"/api/sources returned status {resp.status_code}")
        return

    data = resp.json()
    if not isinstance(data, list) or len(data) == 0:
        result.fail("/api/sources returned empty or non-array")
        return

    result.passed(f"/api/sources returned {len(data)} sources")

    # Check expected fields on each source
    required_fields = {"source_name", "base_url", "display_name", "icon_filename", "category"}
    first = data[0]
    missing = required_fields - set(first.keys())
    if missing:
        result.fail(f"Source objects missing fields: {', '.join(sorted(missing))}")
    else:
        result.passed("Source objects have all expected fields")

    # Check every source has a display_name
    no_display = [s["source_name"] for s in data if not s.get("display_name")]
    if no_display:
        result.warn(f"Sources missing display_name: {', '.join(no_display)}")
    else:
        result.passed("All sources have a display_name")


def main():
    result = ValidationResult()

    check_events_today(result)
    check_events_range(result)
    check_sources(result)

    report = result.summary()
    print(report)

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
