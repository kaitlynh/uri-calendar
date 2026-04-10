"""
Post-pipeline validation for the uri-calendar scraping + ingest pipeline.

Checks (JSON):
  1.  events.json exists, is valid JSON, and contains events
  2.  Every event has required fields (source_name, base_url, event_title, start_date)
  3.  source_name is a bare domain (no www., https://, or path)
  4.  base_url starts with https://
  5.  start_date is valid YYYY-MM-DD
  6.  source_url is non-empty on every event
  7.  No duplicate events (title + date + time)
  8.  Every configured source produced at least 1 event
  9.  No dates far in the past (>1 year) or absurdly far in the future (>2 years)
  10. Event titles are non-empty, not too long, and don't contain HTML tags
  11. Per-source description/location fill rate
  12. Kino dedup — no cinema events from aggregator sources
  13. Cinema Leuzinger titles not ALL CAPS
  14. Cinema Leuzinger descriptions use newlines (not pipe separators)
  15. altdorf.ch events have start times (detail page extraction working)
  16. uri.swiss events have plausible local times (not raw UTC)
  17. uri.swiss locations include venue names (not just town names)
  18b. KBU dedup — no Kantonsbibliothek events from aggregator sources
  18c. OL dedup — no OL-Cup/OLG/Orientierungslauf events from aggregator sources
  18d. Theater Uri dedup — no Theater Uri events from aggregator sources

Checks (DB):
  18. Database connection works
  19. Sources table has rows, formats are correct
  20. Every DB source has at least 1 event
  21. Future events exist
  22. Ingest freshness — events with extracted_at in the last hour
  23. JSON ↔ DB event count consistency
  24. DB sources match JSON sources (no orphans, no missing)
  25. AI enrichment — some events have ai_flag = true
  26. No duplicate events in DB (title + date)

API checks run separately on the server — see tests/validate_api.py.

Exit code 0 = all checks passed, 1 = failures found.
Results are written to tests/test-results/ with a timestamp.
"""

import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
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

# HTML tag pattern for detecting leaked markup
HTML_TAG_RE = re.compile(r"<[a-zA-Z/][^>]*>")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
END_DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


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


# ─── JSON checks ─────────────────────────────────────────────


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
    bad_count = 0
    for event in events:
        d = event.get("start_date")
        if d and not DATE_RE.match(d):
            bad_count += 1

    if bad_count:
        result.fail(f"{bad_count} events have invalid start_date format (expected YYYY-MM-DD)")
    else:
        result.passed("All start_date values are valid YYYY-MM-DD")


def check_time_formats(events, result):
    """Check that start_time is HH:MM:SS and end_datetime is YYYY-MM-DDTHH:MM:SS (no timezone)."""
    bad_start = []
    bad_end = []
    for event in events:
        st = event.get("start_time")
        if st and not TIME_RE.match(st):
            bad_start.append(f"{event.get('source_name')}: {st}")
        ed = event.get("end_datetime")
        if ed and not END_DT_RE.match(ed):
            bad_end.append(f"{event.get('source_name')}: {ed}")

    if bad_start:
        examples = "; ".join(bad_start[:5])
        result.fail(f"{len(bad_start)} events have invalid start_time format (expected HH:MM:SS): {examples}")
    else:
        result.passed("All start_time values are valid HH:MM:SS")

    if bad_end:
        examples = "; ".join(bad_end[:5])
        result.fail(f"{len(bad_end)} events have invalid end_datetime format (expected YYYY-MM-DDTHH:MM:SS, no timezone): {examples}")
    else:
        result.passed("All end_datetime values are valid YYYY-MM-DDTHH:MM:SS (no timezone)")


def check_source_url(events, result):
    """Check that every event has a non-empty source_url."""
    missing = 0
    for event in events:
        val = event.get("source_url")
        if not val or (isinstance(val, str) and val.strip() == ""):
            missing += 1

    if missing:
        result.fail(f"{missing} events have empty or missing source_url")
    else:
        result.passed("All events have a non-empty source_url")


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
        result.warn(f"{dupes} duplicate events in JSON (same title + date + time)")
    else:
        result.passed("No duplicate events in JSON")


def check_date_sanity(events, result):
    """Check for dates far in the past or absurdly far in the future."""
    today = date.today()
    one_year_ago = today - timedelta(days=365)
    two_years_ahead = today + timedelta(days=730)

    old_count = 0
    future_count = 0
    old_examples = []
    future_examples = []

    for event in events:
        d = event.get("start_date")
        if not d or not DATE_RE.match(d):
            continue
        try:
            event_date = date.fromisoformat(d)
        except ValueError:
            continue

        if event_date < one_year_ago:
            old_count += 1
            if len(old_examples) < 3:
                old_examples.append(f"{event.get('event_title', '???')!r} ({d})")
        elif event_date > two_years_ahead:
            future_count += 1
            if len(future_examples) < 3:
                future_examples.append(f"{event.get('event_title', '???')!r} ({d})")

    if old_count:
        examples = "; ".join(old_examples)
        result.warn(f"{old_count} events have start_date > 1 year in the past — e.g. {examples}")
    else:
        result.passed("No events with start_date > 1 year in the past")

    if future_count:
        examples = "; ".join(future_examples)
        result.warn(f"{future_count} events have start_date > 2 years in the future — e.g. {examples}")
    else:
        result.passed("No events with start_date > 2 years in the future")


def check_title_quality(events, result):
    """Check event titles for emptiness, excessive length, or HTML tags."""
    empty_count = 0
    long_count = 0
    html_count = 0
    html_examples = []

    for event in events:
        title = event.get("event_title", "")
        if not title or not title.strip():
            empty_count += 1
            continue
        if len(title) > 300:
            long_count += 1
        if HTML_TAG_RE.search(title):
            html_count += 1
            if len(html_examples) < 3:
                html_examples.append(title[:80])

    if empty_count:
        result.fail(f"{empty_count} events have empty titles")
    else:
        result.passed("No events with empty titles")

    if long_count:
        result.warn(f"{long_count} events have titles > 300 characters (possible scraping bug)")
    else:
        result.passed("No excessively long event titles")

    if html_count:
        examples = "; ".join(html_examples)
        result.fail(f"{html_count} events have HTML tags in title — e.g. {examples}")
    else:
        result.passed("No HTML tags leaked into event titles")


def check_field_fill_rates(events, result):
    """Warn if a source has very low description or location fill rates."""
    # Group events by source
    by_source = {}
    for event in events:
        name = event.get("source_name", "unknown")
        if name not in by_source:
            by_source[name] = {"total": 0, "has_desc": 0, "has_loc": 0}
        by_source[name]["total"] += 1
        if event.get("description") and str(event["description"]).strip():
            by_source[name]["has_desc"] += 1
        if event.get("location") and str(event["location"]).strip():
            by_source[name]["has_loc"] += 1

    low_fill = []
    for name, stats in sorted(by_source.items()):
        total = stats["total"]
        if total == 0:
            continue
        desc_pct = (stats["has_desc"] / total) * 100
        loc_pct = (stats["has_loc"] / total) * 100
        if desc_pct < 10:
            low_fill.append(f"{name}: {desc_pct:.0f}% descriptions")
        if loc_pct < 10:
            low_fill.append(f"{name}: {loc_pct:.0f}% locations")

    if low_fill:
        result.warn(f"Low field fill rate: {'; '.join(low_fill)}")
    else:
        result.passed("All sources have reasonable description/location fill rates (>10%)")


def check_per_source_events(events, result):
    """Check that every source in sources.json produced at least 1 event."""
    if not SOURCES_FILE.exists():
        result.warn("scraping/sources.json not found — skipping per-source check")
        return

    with open(SOURCES_FILE) as f:
        sources = json.load(f)

    # Count events per source_name
    counts = {}
    for event in events:
        name = event.get("source_name", "unknown")
        counts[name] = counts.get(name, 0) + 1

    # Sources that legitimately may have 0 events (seasonal, API key issues, etc.)
    warn_only = {"floorballuri.ch", "uri.swiss"}

    has_zero = False
    for source in sources:
        source_name = source.get("source_name")
        if not source_name:
            result.warn(f"Source '{source['name']}' missing source_name in sources.json")
            continue
        if source_name not in counts:
            label = f"{source['name']} ({source_name})"
            if source_name in warn_only:
                result.warn(f"0 events from source: {label}")
            else:
                result.fail(f"0 events from source: {label}")
            has_zero = True

    if not has_zero:
        result.passed("All configured sources produced at least 1 event")

    # Report per-source counts
    for name in sorted(counts.keys()):
        result.passed(f"  {name}: {counts[name]} events")


# ─── Dedup & source-specific checks ─────────────────────────


# Sources that should NOT contain cinema, library, or OL events
KINO_DEDUP_SOURCES = {"altdorf.ch", "urnerwochenblatt.ch", "uri.swiss", "uri.ch"}
KBU_DEDUP_SOURCES = {"altdorf.ch", "urnerwochenblatt.ch", "uri.swiss", "eventfrog.ch", "uri.ch"}
OL_DEDUP_SOURCES = {"altdorf.ch", "urnerwochenblatt.ch", "uri.swiss", "seedorf-uri.ch", "eventfrog.ch", "uri.ch"}
THEATER_URI_DEDUP_SOURCES = {"altdorf.ch", "urnerwochenblatt.ch", "eventfrog.ch", "uri.swiss"}


def check_kino_dedup(events, result):
    """Check that kino events have been filtered from aggregator sources."""
    kino_leaks = []
    for event in events:
        source = event.get("source_name", "")
        if source not in KINO_DEDUP_SOURCES:
            continue
        title = event.get("event_title", "")
        location = event.get("location") or ""
        if (title.startswith("Kino:") or title.startswith("Kino ")
                or title.startswith("Kino –") or title.startswith("Kino-")
                or re.search(r"(?i)cinema\s+leuzinger", location)):
            kino_leaks.append(f"{source}: {title!r}")

    if kino_leaks:
        examples = "; ".join(kino_leaks[:5])
        result.fail(f"{len(kino_leaks)} kino events leaked through aggregator filters — e.g. {examples}")
    else:
        result.passed("No kino events from aggregator sources (dedup working)")


def check_kbu_dedup(events, result):
    """Check that Kantonsbibliothek events have been filtered from aggregator sources."""
    kbu_leaks = []
    for event in events:
        source = event.get("source_name", "")
        if source not in KBU_DEDUP_SOURCES:
            continue
        location = event.get("location") or ""
        if re.search(r"(?i)kantonsbibliothek", location):
            kbu_leaks.append(f"{source}: {event.get('event_title', '???')!r}")

    if kbu_leaks:
        examples = "; ".join(kbu_leaks[:5])
        result.fail(f"{len(kbu_leaks)} KBU events leaked through aggregator filters — e.g. {examples}")
    else:
        result.passed("No Kantonsbibliothek events from aggregator sources (dedup working)")


def check_ol_dedup(events, result):
    """Check that OL events have been filtered from aggregator sources."""
    ol_leaks = []
    ol_re = re.compile(r"(?i)OL-Cup|OLG\b|Orientierungslauf")
    for event in events:
        source = event.get("source_name", "")
        if source not in OL_DEDUP_SOURCES:
            continue
        title = event.get("event_title", "")
        if ol_re.search(title):
            ol_leaks.append(f"{source}: {title!r}")

    if ol_leaks:
        examples = "; ".join(ol_leaks[:5])
        result.fail(f"{len(ol_leaks)} OL events leaked through aggregator filters — e.g. {examples}")
    else:
        result.passed("No OL events from aggregator sources (dedup working)")


def check_theater_uri_dedup(events, result):
    """Check that Theater Uri events have been filtered from aggregator sources."""
    leaks = []
    for event in events:
        source = event.get("source_name", "")
        if source not in THEATER_URI_DEDUP_SOURCES:
            continue
        location = event.get("location") or ""
        title = event.get("event_title") or ""
        if re.search(r"(?i)theater\s+uri", location) or re.search(r"(?i)theater\s+uri", title):
            leaks.append(f"{source}: {title!r}")

    if leaks:
        examples = "; ".join(leaks[:5])
        result.fail(f"{len(leaks)} Theater Uri events leaked through aggregator filters — e.g. {examples}")
    else:
        result.passed("No Theater Uri events from aggregator sources (dedup working)")


def check_cinema_title_case(events, result):
    """Check that Cinema Leuzinger titles are not ALL CAPS."""
    cinema_events = [e for e in events if e.get("source_name") == "cinema-leuzinger.ch"]
    if not cinema_events:
        result.warn("No cinema-leuzinger.ch events — skipping title case check")
        return

    allcaps = []
    for event in cinema_events:
        title = event.get("event_title", "")
        # Strip parenthetical content before checking (may have mixed-case suffixes)
        core = re.sub(r"\([^)]*\)", "", title).strip()
        if len(core) > 3 and core == core.upper():
            allcaps.append(title)

    if allcaps:
        examples = "; ".join(allcaps[:3])
        result.fail(f"{len(allcaps)} cinema titles still in ALL CAPS — e.g. {examples}")
    else:
        result.passed(f"Cinema Leuzinger titles are properly cased ({len(cinema_events)} events)")


def check_cinema_descriptions(events, result):
    """Check that Cinema Leuzinger descriptions use newlines, not pipe separators."""
    cinema_events = [e for e in events if e.get("source_name") == "cinema-leuzinger.ch"]
    if not cinema_events:
        result.warn("No cinema-leuzinger.ch events — skipping description check")
        return

    pipe_descs = []
    newline_descs = 0
    for event in cinema_events:
        desc = event.get("description", "")
        if not desc:
            continue
        if " | " in desc:
            pipe_descs.append(event.get("event_title", "???"))
        if "\n" in desc:
            newline_descs += 1

    if pipe_descs:
        result.fail(f"{len(pipe_descs)} cinema descriptions use pipe separators instead of newlines")
    else:
        result.passed(f"Cinema descriptions use newlines ({newline_descs} with multi-line content)")


def check_altdorf_times(events, result):
    """Check that altdorf.ch events have start times (extracted from detail pages)."""
    altdorf_events = [e for e in events if e.get("source_name") == "altdorf.ch"]
    if not altdorf_events:
        return

    timed = [e for e in altdorf_events if e.get("start_time")]
    total = len(altdorf_events)
    pct = (len(timed) / total) * 100 if total else 0

    if len(timed) == 0:
        result.fail(
            f"altdorf.ch: 0/{total} events have start_time "
            f"— detail page time extraction may be broken"
        )
    elif pct < 50:
        result.warn(
            f"altdorf.ch: only {pct:.0f}% of events have start_time "
            f"({len(timed)}/{total}) — expected >80%"
        )
    else:
        result.passed(f"altdorf.ch: {len(timed)}/{total} ({pct:.0f}%) events have start_time")


def check_uri_swiss_times(events, result):
    """Check that uri.swiss event times look like local Zurich times, not raw UTC."""
    uri_events = [e for e in events if e.get("source_name") == "uri.swiss"]
    if not uri_events:
        # uri.swiss may legitimately have 0 events
        return

    # Heuristic: evening events (concerts, shows) should not have times like 16:00-17:00
    # when they're actually 18:00-19:00 in Zurich. We can't be 100% sure, but if ALL
    # events with times end at :00 or :30 and cluster suspiciously early, flag it.
    timed = [e for e in uri_events if e.get("start_time")]
    if not timed:
        return

    # Check that at least some events have times >= 18:00 (evening events exist in Uri)
    evening = [e for e in timed if e["start_time"] >= "18:00:00"]
    if len(evening) == 0 and len(timed) >= 5:
        result.warn(
            f"uri.swiss: {len(timed)} timed events but none after 18:00 "
            f"— possible UTC timezone bug"
        )
    else:
        result.passed(f"uri.swiss times look plausible ({len(evening)}/{len(timed)} are evening events)")


def check_uri_swiss_locations(events, result):
    """Check that uri.swiss locations include venue names, not just town names."""
    uri_events = [e for e in events if e.get("source_name") == "uri.swiss"]
    if not uri_events:
        return

    with_venue = 0
    town_only = 0
    # Town-only locations are typically a single word or very short (e.g. "Altdorf", "Bürglen")
    for event in uri_events:
        loc = event.get("location", "")
        if not loc:
            continue
        # If location contains a comma, it likely has "Venue, Town" format
        if "," in loc:
            with_venue += 1
        else:
            town_only += 1

    total = with_venue + town_only
    if total == 0:
        return

    venue_pct = (with_venue / total) * 100
    if venue_pct < 50 and total >= 5:
        result.warn(
            f"uri.swiss: only {venue_pct:.0f}% of locations have venue names "
            f"({with_venue}/{total} have comma-separated venue+town)"
        )
    else:
        result.passed(f"uri.swiss locations: {with_venue}/{total} ({venue_pct:.0f}%) include venue names")


# ─── Database checks ─────────────────────────────────────────


def check_database(result, json_events=None):
    """Check database connection and data consistency."""
    dsn = os.getenv("DB_CONNECTION_STRING")
    if not dsn:
        result.warn("DB_CONNECTION_STRING not set — skipping database checks")
        return

    try:
        import psycopg2
        import psycopg2.extras
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

    # --- Sources table ---

    cur.execute("SELECT source_name, base_url FROM sources ORDER BY source_name")
    sources = cur.fetchall()

    if not sources:
        result.fail("Sources table is empty")
    else:
        result.passed(f"Sources table has {len(sources)} rows")

    # source_name format
    bad_names = [name for name, _ in sources if name.startswith("http") or name.startswith("www.") or "/" in name]
    if bad_names:
        result.fail(f"DB source_name not bare domain: {', '.join(bad_names)}")
    else:
        result.passed("DB source_name values are all bare domains")

    # base_url format
    bad_urls = [url for _, url in sources if not url.startswith("https://")]
    if bad_urls:
        result.fail(f"DB base_url missing https://: {', '.join(bad_urls)}")
    else:
        result.passed("DB base_url values all start with https://")

    # --- Events table ---

    cur.execute("SELECT count(*) FROM events")
    db_event_count = cur.fetchone()[0]
    if db_event_count == 0:
        result.fail("Events table is empty")
    else:
        result.passed(f"Events table has {db_event_count} rows")

    # Per-source event counts in DB
    cur.execute("""
        SELECT s.source_name, s.display_name, count(e.event_id) as cnt
        FROM sources s
        LEFT JOIN events e ON e.source_id = s.source_id
        GROUP BY s.source_id, s.source_name, s.display_name
        ORDER BY s.source_name
    """)
    db_source_counts = {}
    for source_name, display_name, cnt in cur.fetchall():
        db_source_counts[source_name] = cnt
        label = display_name or source_name
        if cnt == 0:
            result.fail(f"  DB: 0 events for source '{label}' ({source_name})")
        else:
            result.passed(f"  DB: {source_name}: {cnt} events")

    # Future events exist
    cur.execute("SELECT count(*) FROM events WHERE start_date >= CURRENT_DATE")
    future_count = cur.fetchone()[0]
    if future_count == 0:
        result.warn("No future events in database — all events are in the past")
    else:
        result.passed(f"{future_count} DB events are today or in the future")

    # Ingest freshness — events with extracted_at in the last hour
    cur.execute("""
        SELECT count(*) FROM events
        WHERE extracted_at >= NOW() - INTERVAL '1 hour'
    """)
    recent_count = cur.fetchone()[0]
    if recent_count == 0:
        result.fail("DB ingest may have failed — no events with extracted_at in the last hour")
    else:
        result.passed(f"DB ingest confirmed — {recent_count} events updated in the last hour")

    # --- JSON ↔ DB consistency ---

    if json_events is not None:
        json_count = len(json_events)
        # DB should have at least as many events as the JSON (DB accumulates over time)
        if db_event_count < json_count:
            result.warn(
                f"DB has fewer events ({db_event_count}) than JSON ({json_count}) "
                f"— ingest may have skipped duplicates or filtered events"
            )
        else:
            result.passed(f"DB event count ({db_event_count}) >= JSON event count ({json_count})")

        # Check that every source_name in JSON exists in the DB
        json_source_names = {e.get("source_name") for e in json_events if e.get("source_name")}
        db_source_names = {name for name, _ in sources}
        missing_in_db = json_source_names - db_source_names
        if missing_in_db:
            result.fail(f"Sources in JSON but not in DB: {', '.join(sorted(missing_in_db))}")
        else:
            result.passed("All JSON source_names exist in DB sources table")

        # Check for orphaned DB sources (in DB but never in JSON — stale rows)
        extra_in_db = db_source_names - json_source_names
        if extra_in_db:
            result.fail(f"Orphaned sources in DB (not in JSON): {', '.join(sorted(extra_in_db))}")
        else:
            result.passed("No orphaned sources in DB")

    # --- AI enrichment ---

    # Check ai_status.json for specific error info (written by open-ai.py)
    ai_status_file = PROJECT_ROOT / "events" / "ai_status.json"
    if ai_status_file.exists():
        try:
            with open(ai_status_file) as f:
                ai_status = json.load(f)
            if ai_status.get("status") == "error":
                result.warn(f"AI enrichment failed: {ai_status.get('message', 'unknown error')}")
            else:
                result.passed(f"AI enrichment ran: {ai_status.get('message', 'ok')}")
        except (json.JSONDecodeError, KeyError):
            result.warn("AI status file exists but is unreadable")
    else:
        result.warn("AI status file not found — AI enrichment may not have run")

    cur.execute("SELECT count(*) FROM events WHERE ai_flag = true")
    ai_count = cur.fetchone()[0]
    if ai_count == 0 and not ai_status_file.exists():
        result.warn("No events have ai_flag = true")
    elif ai_count > 0:
        ai_pct = (ai_count / db_event_count * 100) if db_event_count > 0 else 0
        result.passed(f"{ai_count} events ({ai_pct:.0f}%) have ai_flag = true")

    # --- DB duplicates ---

    cur.execute("""
        SELECT event_title, start_date, count(*) as cnt
        FROM events
        GROUP BY event_title, start_date
        HAVING count(*) > 1
    """)
    db_dupes = cur.fetchall()
    if db_dupes:
        # This shouldn't happen because of the unique constraint, but check anyway
        result.fail(f"{len(db_dupes)} duplicate title+date combinations in DB (unique constraint may be broken)")
    else:
        result.passed("No duplicate events in DB (title + date)")

    cur.close()
    conn.close()


# ─── Main ────────────────────────────────────────────────────
# Note: API checks run separately on the server (tests/validate_api.py)
# because the API is only reachable from localhost on the server.


def main():
    result = ValidationResult()

    # --- JSON file checks ---
    events = check_events_file(result)

    if events:
        check_required_fields(events, result)
        check_source_name_format(events, result)
        check_base_url_format(events, result)
        check_date_format(events, result)
        check_time_formats(events, result)
        check_source_url(events, result)
        check_duplicates(events, result)
        check_date_sanity(events, result)
        check_title_quality(events, result)
        check_field_fill_rates(events, result)
        check_per_source_events(events, result)

    # --- Dedup & source-specific checks ---
    if events:
        check_kino_dedup(events, result)
        check_kbu_dedup(events, result)
        check_ol_dedup(events, result)
        check_theater_uri_dedup(events, result)
        check_cinema_title_case(events, result)
        check_cinema_descriptions(events, result)
        check_altdorf_times(events, result)
        check_uri_swiss_times(events, result)
        check_uri_swiss_locations(events, result)

    # --- Database checks ---
    check_database(result, json_events=events)

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
