# URI Calendar

A community event calendar for Canton Uri, Switzerland. Events are automatically scraped from 20+ local websites, enriched with AI-powered web search, and displayed on a public calendar at [urikalender.ch](https://urikalender.ch).

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
├── events/            Scraped event data (events.json)
├── docs/              Scraping docs, event schema templates
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

The server only receives pre-built static files — no build tooling required.

### Daily Pipeline (`scrape-and-ingest.yml`)

Runs daily at 3:00 AM UTC via cron (or manually via `workflow_dispatch`):
1. **Scrape** — runs all scrapers + AI enrichment on the GitHub runner
2. **Ingest** — opens SSH tunnel to PostgreSQL, upserts events
3. **Validate** — checks JSON structure, field formats, deduplication, DB consistency
4. **Validate API** — hits live API endpoints on the server
5. **Report** — creates/updates a GitHub Issue on any failure

### Required GitHub Secrets

`SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY`, `DB_CONNECTION_STRING`, `PUBLICAI_API_KEY`, `EVENTFROG_API_KEY`
