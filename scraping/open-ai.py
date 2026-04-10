"""AI enrichment step — discovers additional events via OpenAI web search.

This script supplements the deterministic scrapers by asking an LLM with
web-search capabilities to find events in Canton Uri that our scrapers
might miss (one-off events, small venues, etc.).

It runs as an optional step in the GitHub Actions pipeline with
continue-on-error: true — the calendar works fine without it, but AI
events fill in gaps.  Discovered events are merged into events.json
with ai_flag=true so the frontend can distinguish them.

Writes ai_status.json alongside events.json so the validation script
can check whether AI enrichment ran and what it found.
"""

import datetime
import json
import logging
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# ── Paths ───────────────────────────────────────────────────────────────

EVENTS_PATH = os.path.join(os.path.dirname(__file__), "..", "events", "events.json")
AI_STATUS_PATH = os.path.join(os.path.dirname(__file__), "..", "events", "ai_status.json")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "event-schema-ai.json")

# ── OpenAI client ───────────────────────────────────────────────────────

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

with open(SCHEMA_PATH, encoding="utf-8") as f:
    template_data = json.load(f)

today = datetime.datetime.now().strftime("%Y-%m-%d")


# ── Helpers ─────────────────────────────────────────────────────────────


def write_status(status: str, message: str, events_added: int = 0):
    """Write AI enrichment status for the validation script to read."""
    with open(AI_STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "status": status,
            "message": message,
            "events_added": events_added,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }, f)


def extract_json(text: str) -> str:
    """Strip markdown fencing if the model wraps its response in ```json."""
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if match:
        text = match.group(1)
    return text.strip()


# ── Prompt ──────────────────────────────────────────────────────────────

PROMPT = f"""
Find events taking place on {today} and the next 14 days in the canton of Uri, Switzerland.
Only include real, verifiable events from official sources (e.g., tourism boards, municipality websites, official event platforms).

Return the result strictly as a JSON array. Each object must follow this exact schema:
{json.dumps(template_data, indent=2)}

CRITICAL OUTPUT RULES:
- Output ONLY valid JSON
- Do NOT use markdown or ```json
- Response MUST start with [ and end with ]
- No text before or after JSON
- Must be parseable by json.loads()

DATA RULES:
- Only events on {today}
- No duplicates
- Do NOT invent events
- If none found, return []

FORMATTING:
- Use null for unknown values
- ISO 8601 for dates/times
- Location: "City, Uri, Switzerland"
"""

# ── Main ────────────────────────────────────────────────────────────────

log.info("sending request to OpenAI (web_search enabled)")
try:
    response = client.responses.create(
        model="gpt-5",
        tools=[{"type": "web_search"}],
        instructions="You are a strict JSON generator. Any deviation from valid JSON is a failure.",
        input=PROMPT,
    )
except Exception as e:
    error_msg = f"OpenAI API call failed: {e}"
    log.error(error_msg)
    write_status("error", error_msg)
    raise SystemExit(1)

raw_output = response.output_text
cleaned = extract_json(raw_output)

# Parse and validate the AI response
log.info("received response, parsing JSON")
try:
    parsed = json.loads(cleaned)
    log.info("parsed %d events from AI response", len(parsed))
except json.JSONDecodeError:
    log.error("JSON parsing failed\nRAW: %s\nCLEANED: %s", raw_output, cleaned)
    write_status("error", "AI response was not valid JSON")
    parsed = []

# Merge new events into events.json, deduplicating on (title, date, time)
if parsed:
    if os.path.exists(EVENTS_PATH):
        with open(EVENTS_PATH, encoding="utf-8") as f:
            existing_events = json.load(f)
    else:
        existing_events = []

    # Build a set of existing event keys for O(1) dedup lookups
    seen = {
        (e["event_title"].lower().strip(), (e.get("start_date") or "")[:10], e.get("start_time") or "")
        for e in existing_events
    }

    ai_now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    new_events = []
    for e in parsed:
        key = (e["event_title"].lower().strip(), (e.get("start_date") or "")[:10], e.get("start_time") or "")
        if key not in seen:
            seen.add(key)
            e["ai_flag"] = True
            e["ai_flag_at"] = ai_now
            new_events.append(e)

    merged = existing_events + new_events
    merged.sort(key=lambda e: e.get("start_date") or "")

    with open(EVENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    log.info("%d new AI events added (%d dupes skipped) → %s",
             len(new_events), len(parsed) - len(new_events), EVENTS_PATH)
    write_status("ok", f"{len(new_events)} new events added, {len(parsed) - len(new_events)} dupes skipped",
                 len(new_events))
else:
    log.info("no AI events found")
    write_status("ok", "No new AI events found", 0)
