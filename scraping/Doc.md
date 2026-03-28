# Scraping

## Data Import

```mermaid
flowchart TD
    A[Script Start] --> B[Load sources.json]
    B --> C[collect_all_events]
    C --> D{For each source}

    D -->|type: urnerwochenblatt| E[scrape_urnerwochenblatt\nurnerwochenblatt.ch]
    D -->|type: kbu| F[scrape_kbu\nkbu.ch]
    D -->|type: musikschule| G[scrape_musikschule\nmusikschule-uri.ch]
    D -->|type: rss| H[scrape_rss\nSchule Altdorf RSS]
    D -->|type: altdorf| I[scrape_altdorf\naltdorf.ch]
    D -->|type: andermatt| J[scrape_andermatt\ngemeinde-andermatt.ch]
    D -->|type: eventfrog| K[scrape_eventfrog\neventfrog.ch]
    D -->|type: static| L[scrape_static\nGeneric HTML]
    D -->|type: js| M[scrape_js\nPlaywright headless]

    E & F & G & H & I & J & K & L & M --> N[List of Event objects]

    N --> O[Deduplicate\nby title + date + time]
    O --> P[Sort by start_date]
    P --> Q[Write events/events.json]
```


# Run the scraping script

```
Run Script: bash scraping/run.sh
```