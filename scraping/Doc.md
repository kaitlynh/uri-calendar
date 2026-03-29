# Scraping Documentation

## Overview

The scraping pipeline collects events from multiple sources in Canton Uri, deduplicates them, and enriches the result with AI-powered web search. The final output is `events/events.json`, consumed by the frontend.

## Running

```bash
bash scraping/run.sh
```

On the first run, `run.sh` creates a Python virtual environment and installs dependencies automatically. Subsequent runs reuse the existing venv.

The two steps run sequentially (scraping must finish before the AI merge):

```
1. scraping/scraping.py   → fetch all sources → events/events.json
2. scraping/open-ai.py    → AI web search for next 14 days → merge into events/events.json
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DB_CONNECTION_STRING` | Yes (parse_json.py) | PostgreSQL connection string (e.g. `postgresql://user:pass@localhost:5432/db`) |
| `OPENAI_API_KEY` | Yes (open-ai.py) | OpenAI API key for GPT-5 web search |
| `EVENTFROG_API_KEY` | Yes (eventfrog) | Eventfrog REST API key |

Place these in a `.env` file at the project root.

> **Secrets on the server vs in CI:**
> - **Scheduled GitHub Actions** (scrape-and-ingest workflow) use **GitHub Secrets** — these are injected as environment variables during the workflow run.
> - **Manual runs on the server** (`ssh` + `bash scraping/run.sh`) use the **`.env` file** at `/opt/uri-calendar/.env`. This file is gitignored and persists across deploys.

---

## Step 1 — Scraping (`scraping.py`)

Entry point: `collect_all_events()`

1. Loads source definitions from `sources.json`
2. Dispatches all sources in parallel via `ThreadPoolExecutor`
3. Each source runs `_run_scraper()`, which calls the matching scraper function
4. Results are merged, deduplicated (by title + date + time), sorted by `start_date`, and written to `events/events.json`

### Sources

| Name | Type | File | Notes |
|---|---|---|---|
| Urner Wochenblatt | `urnerwochenblatt` | `scrape_urnerwochenblatt.py` | Scrapes 4 weeks of listings |
| Kantonsbibliothek Uri | `kbu` | `scrape_kbu.py` | HTML scrape, category-mapped |
| Musikschule Uri | `musikschule` | `scrape_musikschule.py` | HTML scrape |
| Schulen Altdorf | `rss` | *(generic)* | RSS feed via `feedparser` |
| Gemeinde Altdorf | `altdorf` | `scrape_altdorf.py` | JSON embedded in HTML + parallel detail page fetch |
| Gemeinde Andermatt | `andermatt` | `scrape_andermatt.py` | HTML scrape |
| Eventfrog | `eventfrog` | `scrape_eventfrog.py` | REST API, paginated, filtered by all Uri ZIP codes |

> **Adding a new source:** When a new scraper is added, the source row is automatically
> created in the `sources` database table during the first ingest (`db/parse_json.py`).
> However, three fields must be set **manually** in the database afterward:
> - `display_name` — the human-friendly name shown in the frontend filter (e.g. "Gemeinde Altdorf")
> - `icon_filename` — the filename of the 1:1 source icon in `frontend/public/source-icons/` (e.g. "altdorf-geminde.png")
> - `category` — the filter group: `Gemeinden`, `Schulen`, `Organisationen`, or `NULL` for ungrouped
>
> Until these are set, the frontend will fall back to the raw `source_name` with no icon and no category grouping.

### Scraper types

- **`static`** — plain HTTP + BeautifulSoup CSS selectors (configured in `sources.json`)
- **`rss`** — RSS/Atom feed via `feedparser`
- **`js`** — JavaScript-rendered pages via Playwright (headless Chromium)
- **Named scrapers** — custom logic per source (altdorf, kbu, musikschule, etc.)

### Gemeinde Altdorf — detail page parallelism

Altdorf embeds event list JSON in the page HTML but descriptions require individual detail page requests. These are fetched in parallel (up to 8 workers) to avoid serial slowdown.

### Event schema

All scrapers normalize events to this structure:

| Field | Type | Description |
|---|---|---|
| `source_name` | string | Bare domain identifier (e.g. `kbu.ch`, `altdorf.ch`) — no `www.`, no `https://`, no path |
| `base_url` | string | Full URL (with `https://`) to the source's events listing page — used as fallback link and unique key in DB |
| `source_url` | string | Direct link to the event |
| `event_title` | string | Title of the event |
| `start_date` | string \| null | ISO 8601 date (`YYYY-MM-DD`) |
| `start_time` | string \| null | Time (`HH:MM:SS`) |
| `end_datetime` | string \| null | ISO 8601 end datetime |
| `location` | string \| null | Venue / city |
| `description` | string \| null | Event description |
| `extracted_at` | string | UTC timestamp of extraction |

---

## Step 2 — AI Enrichment (`open-ai.py`)

After scraping, `open-ai.py` runs a GPT-5 web search to find additional events in Canton Uri for the **next 14 days** that may not appear in the scraped sources.

1. Sends a prompt with `template_data_ai.json` (schema + examples) to GPT-5 with `web_search` tool enabled
2. Instructs the model to return only valid JSON — no markdown, no extra text
3. Parses the response, deduplicates against the existing `events/events.json`
4. Appends new events and re-sorts by `start_date`

---

## Architecture Diagram

```mermaid
flowchart TD
    A([Start]) --> B[load_sources<br/>sources.json]
    B --> C[collect_all_events<br/>ThreadPoolExecutor]

    C --> |parallel| D1[_run_scraper<br/>source 1]
    C --> |parallel| D2[_run_scraper<br/>source 2]
    C --> |parallel| Dn[_run_scraper<br/>source N...]

    D1 & D2 & Dn --> E{scraper type?}

    E --> |static| F1[scrape_static<br/>requests + BeautifulSoup]
    E --> |rss| F2[scrape_rss<br/>feedparser]
    E --> |js| F3[scrape_js<br/>Playwright + BeautifulSoup]
    E --> |urnerwochenblatt| F4[scrape_urnerwochenblatt<br/>custom module]
    E --> |kbu| F5[scrape_kbu<br/>custom module]
    E --> |musikschule| F6[scrape_musikschule<br/>custom module]
    E --> |altdorf| F7[scrape_altdorf<br/>custom module]
    E --> |andermatt| F8[scrape_andermatt<br/>custom module]
    E --> |eventfrog| F9[scrape_eventfrog<br/>custom module]
    E --> |floorballuri| F10[scrape_floorballuri<br/>custom module]
    E --> |myswitzerland| F11[scrape_myswitzerland<br/>custom module]
    E --> |unknown| ERR[log warning<br/>skip source]

    F1 & F2 & F3 & F4 & F5 & F6 & F7 & F8 & F9 & F10 & F11 --> G[list of Event dataclasses]

    G --> H{error?}
    H --> |yes| I[log error<br/>discard events]
    H --> |no| J[extend all_events]

    J --> K[sort by start_date]
    K --> L[write events/events.json]

    L --> AI1

    subgraph AI ["Step 2 — AI Enrichment (open-ai.py)"]
        AI1[load template_data_ai.json<br/>+ existing events.json]
        AI1 --> AI2[build prompt<br/>next 14 days, Canton Uri]
        AI2 --> AI3[GPT-5 API call<br/>web_search tool enabled]
        AI3 --> AI4[extract & parse JSON<br/>from response]
        AI4 --> AI5{parse OK?}
        AI5 --> |no| AI6[log error<br/>skip merge]
        AI5 --> |yes| AI7[deduplicate<br/>title + date + time]
        AI7 --> AI8[mark ai_updated=true<br/>ai_updated_at=now]
        AI8 --> AI9[merge + sort by start_date]
        AI9 --> AI10[overwrite events/events.json]
    end

    AI10 --> Z([Done])
```
