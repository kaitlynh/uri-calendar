import os
import json
import logging
import datetime
import re
from openai import OpenAI
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Load env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
)

# Load schema
with open(os.path.join(os.path.dirname(__file__), "..", "template_data_ai.json"), encoding="utf-8") as f:
    template_data = json.load(f)

# Today's date
today = datetime.datetime.now().strftime("%Y-%m-%d")

events_path = os.path.join(os.path.dirname(__file__), "..", "events", "events.json")

# --- Helper: clean markdown ---
def extract_json(text: str):
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if match:
        text = match.group(1)
    return text.strip()

# --- Prompt ---
prompt = f"""
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

# --- API call ---
log.info("sending request to OpenAI (web_search enabled)")
response = client.responses.create(
    model="gpt-5",
    tools=[{"type": "web_search"}],
    instructions="You are a strict JSON generator. Any deviation from valid JSON is a failure.",
    input=prompt,
)

raw_output = response.output_text
cleaned = extract_json(raw_output)

# --- Parse JSON safely ---
log.info("received response, parsing JSON")
try:
    parsed = json.loads(cleaned)
    log.info("parsed %d events from AI response", len(parsed))
except json.JSONDecodeError:
    log.error("JSON parsing failed\nRAW: %s\nCLEANED: %s", raw_output, cleaned)
    parsed = []

# --- Merge into events.json ---
if parsed:
    if os.path.exists(events_path):
        with open(events_path, encoding="utf-8") as f:
            existing_events = json.load(f)
    else:
        existing_events = []

    seen = {
        (e["event_title"].lower().strip(), (e.get("start_date") or "")[:10], e.get("start_time") or "")
        for e in existing_events
    }

    new_events = []
    for e in parsed:
        key = (e["event_title"].lower().strip(), (e.get("start_date") or "")[:10], e.get("start_time") or "")
        if key not in seen:
            seen.add(key)
            new_events.append(e)

    merged = existing_events + new_events
    merged.sort(key=lambda e: e.get("start_date") or "")

    with open(events_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    log.info("%d new AI events added (%d dupes skipped) → %s", len(new_events), len(parsed) - len(new_events), events_path)
else:
    log.info("no AI events found")