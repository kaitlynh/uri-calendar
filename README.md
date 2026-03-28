# URI Calendar

A centralized event calendar for Canton Uri, Switzerland. Events are automatically scraped from local organization websites and enriched with AI-powered web search, so residents have one place to find what's happening in the canton.

## Stack

| Layer | Technology |
|---|---|
| Frontend | Solid.js + Vite + Tailwind CSS |
| Backend API | Flask + PostgreSQL |
| Scraping | Python + OpenAI GPT-5 (web search) |
| Reverse proxy | Nginx |
| Hosting | Hetzner Cloud VPS |
| CI/CD | GitHub Actions |

## Project Structure

```
uri-calendar/
├── frontend/        # Solid.js + Vite app
├── api/             # Flask REST API
├── scraping/        # Scrapers + AI enrichment
├── events/          # Scraped event data (events.json)
├── db/              # PostgreSQL schema + import utility
├── nginx/           # Nginx site config
└── .github/         # GitHub Actions deploy workflow
```

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL

### Environment Variables

Create a `.env` file at the project root:

```env
OPENAI_API_KEY=...
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

### Backend API

```bash
cd api
pip install -r requirements.txt
python app.py
```

API runs on `http://localhost:5000`.

| Endpoint | Description |
|---|---|
| `GET /api/events?date=YYYY-MM-DD` | Events for a given date |
| `GET /api/sources` | List all scraped sources |

### Scraping

```bash
bash scraping/run.sh
```

Creates a Python venv on first run, then:
1. Scrapes all sources in parallel → `events/events.json`
2. Runs GPT-5 web search for additional events in the next 14 days → merges into `events/events.json`

See [scraping/Doc.md](scraping/Doc.md) for full scraping documentation.

## Sources

| Source | Type |
|---|---|
| Urner Wochenblatt | Custom scraper |
| Kantonsbibliothek Uri | HTML scraper |
| Musikschule Uri | HTML scraper |
| Schulen Altdorf | RSS feed |
| Gemeinde Altdorf | JSON-in-HTML + detail pages |
| Gemeinde Andermatt | HTML scraper |
| Eventfrog | REST API |

## Deployment

Pushes to `main` trigger the GitHub Actions workflow, which SSHs into the server, pulls the latest code, rebuilds the frontend, and reloads Nginx.

Required GitHub secrets: `SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY`.

Nginx proxies `/api/` to the Flask backend and serves the frontend static files from `frontend/dist/`.
