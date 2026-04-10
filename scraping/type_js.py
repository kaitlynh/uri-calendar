"""JavaScript-rendered page scraper type — Playwright + BeautifulSoup."""

from bs4 import BeautifulSoup


def scrape(source: dict, extracted_at: str) -> list:
    from playwright.sync_api import sync_playwright

    from scraping import Event

    sel = source.get("selectors", {})

    source_name = source.get("source_name") or source.get("name")
    base_url = source.get("base_url") or source["url"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(source["url"], wait_until="networkidle")
        soup = BeautifulSoup(page.content(), "html.parser")
        browser.close()

    events = []
    for item in soup.select(sel.get("container", ".event")):
        title_el = item.select_one(sel.get("title", "h3"))
        date_el = item.select_one(sel.get("date", "time"))
        loc_el = item.select_one(sel.get("location", ".location"))
        link_el = item.select_one(sel.get("link", "a"))

        events.append(
            Event(
                source_name=source_name,
                source_url=link_el["href"] if link_el else source["url"],
                base_url=base_url,
                event_title=title_el.text.strip() if title_el else "",
                start_date=(
                    date_el.get("datetime", date_el.text.strip()) if date_el else None
                ),
                start_time=None,
                end_datetime=None,
                location=loc_el.text.strip() if loc_el else None,
                description=None,
                extracted_at=extracted_at,
                priority=source["priority"],
            )
        )
    return events
