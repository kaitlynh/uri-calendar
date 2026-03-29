"""
Post-pipeline validation for the uri-calendar scraping + ingest pipeline.

Checks:
  1. events.json exists, is valid JSON, and contains events
  2. Every source in sources.json produced at least 1 event
  3. All events have required fields with correct formats
  4. No duplicate events (title + date + time)
  5. Database connection works (if DB_CONNECTION_STRING is available)
  6. Database sources table has consistent source_name / base_url formats
  7. Every DB source has at least 1 event

Exit code 0 = all checks passed, 1 = failures found.
Results are written to tests/test-results/ with a timestamp.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Resolve project root (works whether called from root or tests/)
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
EVENTS_FILE = PROJECT_ROOT / "events" / "events.json"
SOURCES_FILE = PROJECT_ROOT / "scraping" / "sources.json"
RESULTS_DIR = SCRIPT_DIR / "test-results"

# Try to load .env for DB connection
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
except ImportError:
    pass


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
        lines.append("=" * 60)
        lines.append(f"Pipeline Validation — {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append("=" * 60)

        if self.passes:
            lines.append(f"\nPASSED ({len(self.passes)}):")
            for p in self.passes:
                lines.append(f"  [PASS] {p}")

        if self.warnings:
            lines.append(f"\nWARNINGS ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"  [WARN] {w}")

        if self.failures:
            lines.append(f"\nFAILURES ({len(self.failures)}):")
            for f in self.failures:
                lines.append(f"  [FAIL] {f}")

        lines.append("")
        status = "PASSED" if self.ok else "FAILED"
        lines.append(f"Result: {status} — {len(self.passes)} passed, {len(self.warnings)} warnings, {len(self.failures)} failures")
        lines.append("=" * 60)
        return "\n".join(lines)


def check_events_file(result):
    """Check that events.json exists, is valid, and has events."""
    if not EVENTS_FILE.exists():
        result.fail("events/events.json does not exist")
        return None

    try:
        with open(EVENTS_FILE) as f:
            events = json.load(f)
    except json.JSONDecodeError as e:
        result.fail(f"events/events.json is invalid JSON: {e}")
        return None

    if not isinstance(events, list):
        result.fail("events/events.json is not a JSON array")
        return None

    if len(events) == 0:
        result.fail("events/events.json is empty (0 events)")
        return None

    result.passed(f"events/events.json is valid with {len(events)} events")
    return events


def check_required_fields(events, result):
    """Check that all events have required fields."""
    required = ["source_name", "base_url", "event_title", "start_date"]
    missing_counts = {}

    for i, event in enumerate(events):
        for field in required:
            val = event.get(field)
            if val is None or (isinstance(val, str) and val.strip() == ""):
                key = f"{field} (e.g. event #{i}: {event.get('event_title', '???')!r})"
                missing_counts[field] = missing_counts.get(field, 0) + 1

    if missing_counts:
        for field, count in missing_counts.items():
            result.fail(f"{count} events missing required field '{field}'")
    else:
        result.passed("All events have required fields (source_name, base_url, event_title, start_date)")


def check_source_name_format(events, result):
    """Check that source_name is a bare domain (no www., no https://, no path)."""
    bad = set()
    for event in events:
        name = event.get("source_name", "")
        if name.startswith("http") or name.startswith("www.") or "/" in name:
            bad.add(name)

    if bad:
        result.fail(f"source_name not bare domain: {', '.join(sorted(bad))}")
    else:
        result.passed("All source_name values are bare domains")


def check_base_url_format(events, result):
    """Check that base_url starts with https://."""
    bad = set()
    for event in events:
        url = event.get("base_url", "")
        if not url.startswith("https://"):
            bad.add(url)

    if bad:
        result.fail(f"base_url missing https:// prefix: {', '.join(sorted(bad))}")
    else:
        result.passed("All base_url values start with https://")


def check_date_format(events, result):
    """Check that start_date is YYYY-MM-DD."""
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    bad_count = 0
    for event in events:
        d = event.get("start_date")
        if d and not date_re.match(d):
            bad_count += 1

    if bad_count:
        result.fail(f"{bad_count} events have invalid start_date format (expected YYYY-MM-DD)")
    else:
        result.passed("All start_date values are valid YYYY-MM-DD")


def check_duplicates(events, result):
    """Check for duplicate events (same title + date + time)."""
    seen = {}
    dupes = 0
    for event in events:
        key = (event.get("event_title"), event.get("start_date"), event.get("start_time"))
        if key in seen:
            dupes += 1
        else:
            seen[key] = True

    if dupes:
        result.warn(f"{dupes} duplicate events (same title + date + time)")
    else:
        result.passed("No duplicate events")


def check_per_source_events(events, result):
    """Check that every source in sources.json produced at least 1 event."""
    if not SOURCES_FILE.exists():
        result.warn("scraping/sources.json not found — skipping per-source check")
        return

    with open(SOURCES_FILE) as f:
        sources = json.load(f)

    source_names_in_config = {s["name"] for s in sources}
    source_names_in_events = {e.get("source_name") for e in events}

    # Count events per source_name
    counts = {}
    for event in events:
        name = event.get("source_name", "unknown")
        counts[name] = counts.get(name, 0) + 1

    # The source_name in events is a bare domain, but sources.json uses human names.
    # We check by looking at which scraper types produced events.
    # Simpler: just report any source_name with 0 events.
    all_source_names = source_names_in_events
    zero_sources = []

    # Map source type to expected source_name in events output
    type_to_domain = {
        "urnerwochenblatt": "urnerwochenblatt.ch",
        "kbu": "kbu.ch",
        "musikschule": "musikschule-uri.ch",
        "rss": "schule-altdorf.ch",
        "altdorf": "altdorf.ch",
        "andermatt": "gemeinde-andermatt.ch",
        "eventfrog": "eventfrog.ch",
        "floorballuri": "floorballuri.ch",
        "myswitzerland": "uri.swiss",
    }

    # Sources that legitimately may have 0 events (seasonal, API key issues, etc.)
    warn_only = {"floorballuri.ch", "uri.swiss"}

    has_zero = False
    for source in sources:
        expected_domain = type_to_domain.get(source["type"])
        if expected_domain and expected_domain not in counts:
            label = f"{source['name']} ({expected_domain})"
            if expected_domain in warn_only:
                result.warn(f"0 events from source: {label}")
            else:
                result.fail(f"0 events from source: {label}")
            has_zero = True

    if not has_zero:
        result.passed("All configured sources produced at least 1 event")

    # Report per-source counts
    for name in sorted(counts.keys()):
        result.passed(f"  {name}: {counts[name]} events")


def check_database(result):
    """Check database connection and data consistency."""
    dsn = os.getenv("DB_CONNECTION_STRING")
    if not dsn:
        result.warn("DB_CONNECTION_STRING not set — skipping database checks")
        return

    try:
        import psycopg2
    except ImportError:
        result.warn("psycopg2 not installed — skipping database checks")
        return

    try:
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        result.passed("Database connection successful")
    except Exception as e:
        result.fail(f"Database connection failed: {e}")
        return

    # Check sources table
    cur.execute("SELECT source_name, base_url FROM sources ORDER BY source_name")
    sources = cur.fetchall()

    if not sources:
        result.fail("Sources table is empty")
    else:
        result.passed(f"Sources table has {len(sources)} rows")

    # Check source_name format in DB
    bad_names = [name for name, _ in sources if name.startswith("http") or name.startswith("www.") or "/" in name]
    if bad_names:
        result.fail(f"DB source_name not bare domain: {', '.join(bad_names)}")
    else:
        result.passed("DB source_name values are all bare domains")

    # Check base_url format in DB
    bad_urls = [url for _, url in sources if not url.startswith("https://")]
    if bad_urls:
        result.fail(f"DB base_url missing https://: {', '.join(bad_urls)}")
    else:
        result.passed("DB base_url values all start with https://")

    # Check total event count
    cur.execute("SELECT count(*) FROM events")
    event_count = cur.fetchone()[0]
    if event_count == 0:
        result.fail("Events table is empty")
    else:
        result.passed(f"Events table has {event_count} rows")

    # Check per-source event counts in DB
    cur.execute("""
        SELECT s.source_name, s.display_name, count(e.event_id) as cnt
        FROM sources s
        LEFT JOIN events e ON e.source_id = s.source_id
        GROUP BY s.source_id, s.source_name, s.display_name
        ORDER BY s.source_name
    """)
    for source_name, display_name, cnt in cur.fetchall():
        label = display_name or source_name
        if cnt == 0:
            result.fail(f"DB: 0 events for source '{label}' ({source_name})")
        else:
            result.passed(f"  DB: {source_name}: {cnt} events")

    # Check for events with future dates (sanity check — should have some)
    cur.execute("SELECT count(*) FROM events WHERE start_date >= CURRENT_DATE")
    future_count = cur.fetchone()[0]
    if future_count == 0:
        result.warn("No future events in database — all events are in the past")
    else:
        result.passed(f"{future_count} events are today or in the future")

    cur.close()
    conn.close()


def main():
    result = ValidationResult()

    # --- File checks ---
    events = check_events_file(result)

    if events:
        check_required_fields(events, result)
        check_source_name_format(events, result)
        check_base_url_format(events, result)
        check_date_format(events, result)
        check_duplicates(events, result)
        check_per_source_events(events, result)

    # --- Database checks ---
    check_database(result)

    # --- Output ---
    report = result.summary()
    print(report)

    # Write timestamped log
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = RESULTS_DIR / f"validation_{timestamp}.log"
    with open(log_file, "w") as f:
        f.write(report + "\n")
    print(f"\nLog written to: {log_file}")

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
