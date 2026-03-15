# Hackdays URI - Project Proposal

**Kaitlyn Hanrahan**
kaitlyn@kait.us

I'm a software developer based in Altdorf with a computer science degree from Northeastern University. I previously worked on Adobe Acrobat in San Francisco and am now self-employed at my own mobile app company, Simply Digital.

## Overview

A centralized calendar for Canton Uri that helps residents track events from schools, communes, churches, and other local organizations they already follow. Instead of checking many separate websites, people can see these local organization calendars in one place.

This project complements existing submission-based event portals such as uri.ch. Rather than asking organizers to post events again, it aggregates events that organizations have already published for their own communities.

An AI-powered script will scrape existing public event data and populate the central calendar automatically, keeping it up to date with minimal human maintenance. The website will be in German.

---

## Problem Statement

We are lucky in Uri to have so many events happening throughout the year: town markets, school parades, church events, Kinderfests, library events, festivals, Christmas markets, open air cinema, and more. Event details are spread across the organizer websites, so residents need to check several calendars each week to stay informed.

Uri already has public event submission channels, which are valuable for broad promotion. This project fills a different gap: giving residents one place to follow the calendars they already rely on.

The project will also solve a secondary problem. Event organizers currently have no easy way to check what else is already scheduled when planning an event. For example, recently both Altdorf and Bürglen had their school ski days on the same day at the same location.

---

## Connection to Theme: Digital Sovereignty

A project like this could easily end up depending on big tech platforms for hosting, AI, or calendar infrastructure. We will show that it is possible to build something convenient and useful without giving up digital sovereignty in the process.

The project will use a self-hosted open source stack: Python for scraping and processing, a relational database for event storage, and a custom web frontend. For AI, it will use Switzerland's own Apertus model through PublicAI. Hosting will be on a European VPS under EU data protection law. The result is a useful community tool built on sovereign, open infrastructure with no dependence on big tech platforms.

---

## Proposed Solution

The system has three layers:

```
┌─────────────────────────────────────────────┐
│  Website (public, read-only)                │
│  Displays the calendar, lists sources,      │
│  and provides contact for feature requests  │
├─────────────────────────────────────────────┤
│  Data Processing (middle layer)             │
│  Converts AI output into database events,   │
│  deduplicates and resolves update conflicts  │
├─────────────────────────────────────────────┤
│  Scraping + AI (base layer)                 │
│  Scrapes organization websites,             │
│  sends content to PublicAI (Apertus),       │
│  outputs structured JSON                    │
└─────────────────────────────────────────────┘
         ▲ runs automatically (daily/weekly)
```

**Base layer: Scraping + AI.** A script scrapes event information from local organization websites and sends the content to the Apertus AI model via PublicAI. The AI extracts event details and returns structured JSON. This script runs automatically on a daily or weekly schedule.

**Middle layer: Data processing.** The JSON output is used to create or update events in the project database. This layer must correctly identify when a scraped event already exists, updating the record rather than creating a duplicate.

**Frontend: Website.** A public website displays all upcoming events in one place. The site also lists the scraped sources and provides a way to submit feature requests.

---

## Technologies

- **PublicAI (Apertus model)** for AI processing of scraped content. Apertus is a multilingual model developed by EPFL, ETH Zurich, and CSCS, released under the Apache 2.0 license.
- **Python** for scraping and data processing scripts
- **PostgreSQL or SQLite** for event storage (final choice based on team preference and deployment constraints)
- **Web scraper** to be chosen by the team, likely Jina Reader, Crawl4AI, or Firecrawl
- **GitHub** for version control and collaboration, with the scraper scheduled either by **GitHub Actions** or a server-side **cron job**
- **Frontend framework** to be chosen by whoever works on the website. A calendar rendering library such as FullCalendar (open source, supports iCal feeds) is recommended as a starting point.
- **Hosting** on a Hetzner Cloud VPS in a German datacenter, covered by EU/German data protection law. The website, processing service, and database will be hosted on the same server.

---

## Maintenance Costs

Estimated ongoing costs to keep the project running after the hackathon: approximately **44–63 CHF per year**. All core software is open source and free.

As project lead, I am prepared to fund these costs. In the future, an optional sponsored section on the website (separate from the calendar itself) could be offered to local businesses to cover ongoing maintenance.

| Service | Free tier? | Estimated cost |
|---|---|---|
| **Hetzner Cloud VPS** | No | ~€2.99–3.79/month (~2.85–3.60 CHF/month) |
| **.ch domain name** | No | ~10–20 CHF/year |
| **PublicAI API** (Apertus) | Yes | Free |
| **GitHub** (repo + Actions) | Yes | Free |
| **Total** | | **~44–63 CHF/year** |

The PublicAI API is currently free with a documented rate limit of 20 requests per minute. This project would use roughly 5–15 requests per day, well within that limit. PublicAI plans to keep a free tier long-term, supported by institutional contributions and donated compute.

A small Hetzner VPS tier is likely sufficient for this architecture. A Swiss alternative such as Infomaniak VPS Lite would offer hosting in Switzerland, but at a higher cost for fewer resources. Since the project has no revenue to cover maintenance at this time, the more affordable Hetzner option was chosen. The hosting can be migrated to a Swiss provider in the future if funding allows.

---

## Teams

Work is divided into four tracks, each with an owner. The four tracks cover the three technical layers described above, plus a dedicated admin and setup track.

Depending on team size, one person may cover multiple tracks or a larger group can divide ownership and work in parallel. Not every role requires programming skills. The working language will be English, or a mix of English and High German.

1. **Admin & Setup** - Infrastructure, deployment, and operations
2. **AI & Scraping** - Collecting event data from local websites
3. **Data Formatting** - Converting AI output into persistent event data
4. **Website** - Public calendar interface

---

## Plan

This is a two-day hackathon, so the priority is getting a minimal working version of the full pipeline: scraping to AI to database to website. Features and polish come second. If the core pipeline is working and there is time left, the team can decide together what to improve. But as project lead, I will discourage adding new features until the base version works end to end.

Success would be a live website with a working calendar that automatically aggregates events from at least three sources.

### Track 1: Admin & Setup

**Before the event (project lead):**
- Initialize the Git repository
- Set up the VPS, register a `.ch` domain, and configure DNS
- Set up web server with required installations

**During the event (no programming required):**
- Configure server timezone so event times sync properly
- Set up environment variables and secrets for API keys and deployment
- Set up database backup automation
- Prepare the presentation of the finished project and coordinate the contributions
- Test that each source calendar is displaying correctly on the website

### Track 2: AI & Scraping

- **Target selection (no programming required):** Finalize 3-5 local organization calendars for the MVP (e.g., a school, a church, a commune, or scouts). Organize the URLs and document what kind of event information each site contains.
- **Tool selection:** Evaluate and select the scraping tool (likely Jina Reader, Crawl4AI, or Firecrawl).
- **Build the scraping and AI pipeline (Python):** Fetch the target web pages, convert the raw HTML into clean text, and pass it to the PublicAI API (Apertus model) along with system instructions.
- **Validate and format AI output:** Configure the API call to return only valid JSON matching the schema defined by the Data Formatting team. Verify the response is valid JSON, confirm required fields are present, and retry the request (up to 2-3 times) if output is malformed or incomplete.
- **Event update detection support:** Detect and flag source-side changes (rescheduled, corrected, cancelled, or removed events) in the AI output so the Data Formatting team can apply reliable update logic.
- **Automate execution:** Set up either a GitHub Actions scheduled workflow or a server-side cron job to run the script automatically (daily or weekly).

### Track 3: Data Formatting (JSON to Database)

- **Define the data schema:** Map out the exact JSON structure the AI must return (e.g., `event_title`, `start_time`, `end_time`, `location`, `description`). Share this with the AI & Scraping team.
- **Design and build the event database:** Implement persistent storage for events, including lifecycle tracking, version history, and automated backups.
- **Deduplication and update logic:** Build logic that detects create vs update vs potential duplicate from repeated scraper runs.
- **Data transformation and publishing (Python):** Parse JSON from the AI team, validate it, and write normalized event records into the live database.

### Track 4: Website

- **Design the website (no programming required):** Plan the layout and write any copy for the site, including the list of sources and a contact section for feature requests.
- **Scaffold the frontend:** Set up the website using whichever framework the team prefers (HTML/CSS/JS, React, etc.). The website will be hosted on the same server as the backend and database.
- **Connect to the data layer:** Display events from the project backend/database in the public calendar.
- **Build the UI:** Design the public calendar view with search and category filtering.
- **Stretch goal (low priority):** Publish a public iCal (`.ics`) export feed for calendar app subscriptions after the core pipeline is stable.

---

## Closing

This project has a realistic scope for two days, offers tasks for different skill levels, and could become something genuinely useful for the community. If things go well, I would love to keep the calendar running after the hackathon.