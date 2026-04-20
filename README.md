# URI Calendar

A community event calendar for Canton Uri, Switzerland. Events are pulled every night from 21+ local websites and shown in one searchable feed at **[urikalender.ch](https://urikalender.ch)**.

## Why it exists

Uri is small, but plenty happens every week: town events, school parades, church gatherings, Kinderfests, library talks, open air cinema, concerts. The catch is that each organizer publishes their own calendar on their own website. To stay informed, you have to check a dozen of them every week.

The existing aggregator calendars for Uri are *submission-based*: organizers manually post their events to get promoted. That means those calendars mostly show the events someone wanted to promote. This project fills a different gap. It gathers events from the calendars each organization already publishes publicly on their own website, so even events that aren't heavily promoted (the ones you'd only see if you knew to check the organizer's own calendar) still show up.

A secondary benefit: organizers trying to avoid conflicts (say, two towns scheduling their Skitag on the same day at the same venue) now have one place to check.

## Origin

Originally built at [**Hackdays Uri 2026**](https://hack.digital-cluster-uri.ch/project/52/log) by a four-person team:

- [@kaitlynh](https://github.com/kaitlynh) — proposed, led, and now maintains the project (software engineer)
- [@Daaiid](https://github.com/Daaiid) — built the first web app and worked on data processing (software engineer)
- [@flawas](https://github.com/flawas) — owned the scraping pipeline (software engineer)
- [@arnoldsimETHZ](https://github.com/arnoldsimETHZ) — designed the database and set up data processing (ETH Zürich student)

The work was divided into three tracks so each member could own their area and work in parallel: scraping, data processing, and frontend. Over the hackathon weekend we landed the core goal: a working pipeline (scrapers, database, public web app), with GitHub Actions handling the daily scrape and push-to-main deploying the frontend. Original proposal: [`docs/hackdays-uri-event/proposal/proposal.md`](docs/hackdays-uri-event/proposal/proposal.md).

Since the hackathon I've added every Uri gemeinde with at least 1,000 residents, search, improved deduplication (so cinema events from the theater aren't double-listed from aggregator sites), a test suite, automatic GitHub Issues when a scraper fails so we notice problems fast, timezone fixes, bug fixes, consistent data structures and variable names across the project, and general polish. `git log` covers the rest.

## Things we learned

**AI moved from runtime to authoring.** The original proposal planned an AI-at-runtime architecture: scrape raw HTML, hand it to an LLM, get structured JSON back. Web scrapers have a reputation for being fragile, so an AI interpreter felt like a safer bet than dozens of source-specific parsers. It turned out to be unnecessary. Every site we pointed at had structured-enough HTML (JSON-LD, a clean REST API, or predictable CSS selectors) that a small parser did the job reliably. AI still plays a role, but on the *authoring* side: an AI-assisted workflow can produce a clean BeautifulSoup or JSON-LD parser for a new source in a few minutes.

**Deduplication was the real engineering.** Scraping 21 sources that all list the same concert with 5 slightly different titles is the easy part. Matching them against each other, so the calendar doesn't show "Kino: Super Mario" and "Super Mario Bros (Kinoprogramm)" as two different events, is harder. We handle it at three points in the pipeline: scrapers skip events when we already have them from a more direct source, the database merges matching events on upsert, and the validation suite flags any duplicates that leak through. None of these layers is clever alone. Together they catch the cases where a simple match would miss.

**Validation catches what unit tests miss.** Unit tests are not enough for a scraping pipeline. Websites change, and small bugs can slip through for days before anyone notices. So after every nightly run, the pipeline checks its own output: does every source have events today? Are there duplicate titles on the same date? Do the times look local, not UTC? These checks catch problems the unit tests can't see, like a site quietly changing its HTML or an aggregator starting to list events we already have from the original source. Most bugs in this project were caught this way, before reaching the live site.

## Stack

| Layer | Technology |
|---|---|
| Frontend | SolidJS + Vite + Tailwind CSS |
| Backend API | Flask + PostgreSQL |
| Scraping | Python (BeautifulSoup, feedparser, Playwright) |
| AI enrichment | OpenAI GPT-5 with web search |
| Reverse proxy | Nginx with Let's Encrypt SSL |
| Hosting | Hetzner Cloud VPS (Ubuntu 24.04) |
| CI/CD | GitHub Actions |

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│ GitHub Actions (daily 3am UTC)                           │
│                                                          │
│  scraping.py → open-ai.py → parse_json.py → validate    │
│  (20+ sources)  (optional)   (DB upsert)    (26 checks) │
└──────────────┬───────────────────────────────────────────┘
               │ SSH tunnel + SCP
               ▼
┌──────────────────────────────────────────────────────────┐
│ Hetzner VPS                                              │
│                                                          │
│  Nginx ──► /api/* ──► Flask (localhost:5000)              │
│        └── /*     ──► frontend/dist/ (static SPA)        │
│                                                          │
│  PostgreSQL ──► events + sources tables                   │
└──────────────────────────────────────────────────────────┘
```

## Project Structure

```
uri-calendar/
├── frontend/          SolidJS + Vite app
├── api/               Flask REST API
├── scraping/          Scrapers, orchestrator, AI enrichment
│   ├── scraping.py    Orchestrator — dispatches all sources in parallel
│   ├── sources.json   Source configuration (URLs, types, priorities)
│   ├── scrape_*.py    Custom scrapers (one per source)
│   ├── type_*.py      Built-in scraper types (static, rss, js, icms)
│   ├── open-ai.py     AI enrichment (GPT web search)
│   └── run.sh         Pipeline entry point
├── db/                PostgreSQL schema + ingestion script
├── events/            Scraper output (events.json)
├── docs/              Project documentation and event schema templates
├── tests/             Pipeline and API validation
├── nginx/             Nginx site configuration
└── .github/workflows/ CI/CD (deploy + daily scrape pipeline)
```

## Local Development

### Prerequisites

- Python 3.12+
- Node.js 20+

### Environment Variables

Create a `.env` file at the project root:

```env
PUBLICAI_API_KEY=...
EVENTFROG_API_KEY=...
DB_CONNECTION_STRING=postgresql://user:password@host/dbname
```

### Frontend

```bash
cd frontend
npm install
npm run dev       # dev server on http://localhost:3000
npm run build     # production build → frontend/dist/
```

The dev server proxies `/api` requests to `https://urikalender.ch`.

### API

```bash
cd api
pip install flask psycopg2-binary python-dotenv
python app.py     # runs on http://localhost:5000
```

| Endpoint | Description |
|---|---|
| `GET /api/events?date=YYYY-MM-DD` | Events for a single date |
| `GET /api/events?start_date=...&end_date=...` | Events in a date range |
| `GET /api/events/search?q=query` | Search events by title/description/location |
| `GET /api/sources` | All event sources with metadata |
| `GET /api/admin/scraping-status` | Per-source event counts and freshness |

### Scraping

```bash
bash scraping/run.sh
```

Creates a Python venv on first run, then:
1. Scrapes all sources in parallel → `events/events.json`
2. Runs AI web search for additional events (optional, non-fatal)
3. Ingests into PostgreSQL
4. Runs validation checks

See [docs/scraping.md](docs/scraping.md) for the full scraping documentation, including how to add new sources.

## CI/CD

### Deploy (`deploy.yml`)

Triggered on push to `main`:
1. **Build** — checks out code, runs `npm install` and `npm run build` on the GitHub runner
2. **Deploy** — `rsync`s the built `dist/` to the server, updates nginx config, reloads nginx

The server only receives pre-built static files. No build tooling runs there.

### Daily Pipeline (`scrape-and-ingest.yml`)

Runs daily at 3:00 AM UTC via cron (or manually via `workflow_dispatch`):
1. **Scrape** — runs all scrapers + AI enrichment on the GitHub runner
2. **Ingest** — opens SSH tunnel to PostgreSQL, upserts events
3. **Validate** — checks JSON structure, field formats, deduplication, DB consistency
4. **Validate API** — hits live API endpoints on the server
5. **Report** — creates/updates a GitHub Issue on any failure

### Required GitHub Secrets

`SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY`, `DB_CONNECTION_STRING`, `PUBLICAI_API_KEY`, `EVENTFROG_API_KEY`
