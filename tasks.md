# Hackdays URI Calendar - Task List

## ASAP

- [x] Finalize and submit proposal
- [x] Find a web host. Hetzner Cloud CX23 in Nuremberg (`nbg1`), €3.49/month. Ubuntu 24.04, 2 vCPU, 4 GB RAM, 40 GB SSD. Firewall configured (SSH/HTTP/HTTPS). IP: 178.104.80.19.

## After Proposal Is Approved

- [x] Get a PublicAI API key. Check `publicai.co` vs. `publicai.ch` — verify which one keeps data in Switzerland and what the current rate limits and pricing are outside of promotional periods.
- [x] Confirm the PublicAI API key is valid and the Apertus model responds. ✓ Key works. Use full model name `swiss-ai/apertus-8b-instruct` (or `swiss-ai/apertus-70b-instruct`). Endpoint: `https://api.publicai.co/v1`. The real integration and prompt testing is Track 2's job.
- [x] Set up the web host (VPS). Installed Nginx, Python 3.12, PostgreSQL 16, and certbot.
- [x] Configure server timezone to `Europe/Zurich`
- [x] Set up environment variables and secrets for API keys and deployment
- [ ] Pick a frontend calendar technology. Recommendation: FullCalendar (open source, can consume iCal feeds) with plain HTML/JS, or a lightweight framework like Astro for server rendering.
- [x] Initialize the Git repository and push to GitHub.
- [ ] Set up automated database backups
- [ ] Prepare mock data: a hand-written JSON file with 5-10 sample events matching the planned schema. This lets the Data Formatting and Website teams start working immediately at the hackathon without waiting for the AI pipeline.
- [ ] Finalize 3-5 target websites for the MVP. Document each URL and what kind of events it contains.

## During the Event

### Track 1: Admin & Setup

No programming required.

- [ ] Register a `.ch` domain and configure DNS to point to 178.104.80.19.
- [ ] Configure SSL via Let's Encrypt (requires domain to be registered and DNS propagated first).
- [ ] Add GitHub Secrets to the repository: `PUBLICAI_API_KEY`, `DB_CONNECTION_STRING` (or equivalent)
- [ ] Distribute the mock data JSON file to the Data Formatting and Website teams so they can start immediately
- [ ] Coordinate end-to-end integration testing: once all tracks have their pieces working, wire the full pipeline together (scrape → AI → JSON → calendar → website) and verify it works
- [ ] **Test with real data** (no programming required): As the other teams populate events into the database, verify that each event displays correctly on the website. Check timezone rendering, special characters in German text (umlauts), and events that span multiple days.
- [ ] Prepare the final demo/presentation for the end of the hackathon
- [ ] As a stretch goal, set up a GitHub Actions failure notification (email or webhook) so pipeline failures don't go unnoticed

### Track 2: AI & Scraping

- [ ] **Target selection** (no programming required): Confirm the 3-5 target websites. For each one, open the page, identify where event data lives (is it a list? a calendar widget? a PDF?), and note any complications.
- [ ] **Tool selection**: Evaluate Jina Reader, Crawl4AI, and Firecrawl. Key question: which one handles German-language content and Swiss website structures well? Pick one and move on quickly — don't over-optimize this choice.
- [ ] **Build the scraper**: Write a Python script that fetches each target URL and converts the raw HTML to clean text using the chosen tool.
- [ ] **Build the AI prompt**: Write system instructions for the Apertus model. The prompt must:
  - Define the exact JSON schema (coordinate with the Data Formatting team)
  - Instruct the model to assume `Europe/Zurich` timezone for all events unless otherwise specified
  - Instruct the model to return only raw JSON with no markdown formatting or explanation
  - Include the source URL in the output for each event (needed for deduplication)
- [ ] **Connect to PublicAI API**: Send scraped text to the Apertus model and receive structured JSON back. Use the OpenAI-compatible endpoint at `https://api.publicai.co/v1`. Model name: `swiss-ai/apertus-8b-instruct` (or `swiss-ai/apertus-70b-instruct`). API key is in the `.env` file.
- [ ] **Add output verification**: Validate that the AI response is valid JSON and matches the expected schema. Handle common failure modes: markdown-wrapped JSON, missing fields, hallucinated fields, partial responses. Add retry logic (re-prompt on invalid output, up to 2-3 retries).
- [ ] **Test end-to-end**: Run the full scrape-and-extract pipeline against all target websites. Review the output manually for accuracy.
- [ ] **Event update detection**: Detect and flag source-side changes (rescheduled, cancelled, or removed events) in the AI output so the Data Formatting team can apply reliable update logic.
- [ ] **Automate execution**: Set up either a GitHub Actions scheduled workflow or a server-side cron job to run the script automatically (daily or weekly). Use the secrets configured by the Admin team.

### Track 3: Data Formatting (JSON to Database)

- [x] **Define the data schema** (do this first — Track 2 needs it before they can build the AI prompt): Specify the exact JSON structure the AI must return. At minimum: `source_url`, `event_title`, `start_datetime`, `end_datetime` (optional), `location`, `description`, `category` (optional). Share this schema with the AI & Scraping team immediately.
- [x] **Design and build the event database**: Implement persistent storage for events using PostgreSQL or SQLite. Include lifecycle tracking (active, rescheduled, cancelled), version history for debugging, and confirm backup automation is in place with Track 1.
- [ ] **Build the deduplication and update logic**: Match incoming scraped events to existing database records to determine create vs. update vs. duplicate. Note: not every event will have a stable source URL — text-only listing pages require fuzzy matching on title, location, and approximate date.
- [ ] **Data transformation and publishing (Python)**: Parse the AI JSON, validate it, and write normalized event records into the live database.
- [ ] **Test with mock data**: Use the prepared mock JSON to verify the full flow from JSON to database before the AI pipeline is ready.
- [ ] ** Update db according to data**: BUGS

### Track 4: Website

- [ ] **Design the website** (no programming required): Plan the layout. Key pages/sections: calendar view, event list, list of sources, contact/feature request section. Write any copy in German.
- [ ] **Scaffold the frontend**: Set up the website using the chosen technology. Deploy it on the same VPS as the backend and database to avoid CORS issues.
- [ ] **Connect to the data layer**: Fetch events from the project backend/database API and display them in the public calendar.
- [ ] **Build the calendar UI**: Render events in a calendar view. Add list/agenda view as an alternative.
- [ ] **Add search and filtering**: Filter by category, date range, or keyword search.
- [ ] **Polish** (stretch goal): Responsive design for mobile, link back to original source for each event.
- [ ] **iCal export** (stretch goal, low priority): Publish a public `.ics` feed from the database so users can subscribe from Apple Calendar, Google Calendar, or Outlook.
