"""Imunify360 anti-bot challenge handling for the cyon-hosted sources.

Nine sources (altdorf, erstfeld, silenen, attinghausen, flueelen, seedorf,
volleyuri, cinema-leuzinger, musikschule) live on cyon's shared hosting,
which fronts every site with Imunify360 WebShield.  When the GitHub
runner's IP is on Imunify360's greylist, each request is answered with a
challenge instead of the page: an HTML stub that runs a script and
reloads (HTTP 200), a JSON "Access denied by Imunify360 bot-protection"
message, or HTTP 415 when the Accept header is not text/*.  A plain
requests client cannot run the script, so every scraper on that host
reports zero events, all on the same day.

The challenge is not a CAPTCHA.  A browser that runs JavaScript and keeps
cookies passes it with no interaction, and Imunify360 then removes the IP
from its greylist (Imunify360 docs, "Greylist and Anti-Bot Challenge").

Usage:
    resp = antibot.get(url, headers=HEADERS, timeout=15)
        Same as requests.get, but raises BotChallenge when the response is
        the challenge.  Cookies from a solved challenge are sent along.

    antibot.solve(url)
        Opens the site's root in headless Chrome, waits for the challenge
        to clear, and keeps the cookies.  The orchestrator calls this once
        per blocked host, then retries the scraper right away.

Chrome: uses the Google Chrome that GitHub's Ubuntu runners ship (and the
one on a Mac).  If no Chrome is found, Playwright's own Chromium is
downloaded at that moment, so clean runs never pay for it.
"""

import logging
import re
import subprocess
import sys
import threading
import time
from typing import Optional
from urllib.parse import urlsplit

import requests

log = logging.getLogger(__name__)

# The HTML stub is an English-language page of about 12 KB whose only job
# is to run a script and reload; the real pages are 100 KB and up.
_IMUNIFY_RE = re.compile(r"imunify360|bot-protection", re.I)
_RELOAD_RE = re.compile(
    r"setTimeout\(\s*function\s*\(\s*\)\s*\{\s*window\.location\.reload", re.S
)
_STUB_MAX_BYTES = 40_000
_HEAD_BYTES = 4_000

_lock = threading.Lock()
_cookies: dict[str, dict[str, str]] = {}   # bare hostname -> cookie jar
_solved: set[str] = set()


class BotChallenge(RuntimeError):
    """The server answered with the Imunify360 challenge, not the page."""

    def __init__(self, url: str, kind: str, status: int, snippet: str):
        self.url = url
        self.host = _host(url)
        self.kind = kind
        self.status = status
        super().__init__(
            f"Imunify360 bot challenge ({kind}, HTTP {status}) from {self.host}: {snippet!r}"
        )


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _bare(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def detect(status: int, body: str) -> Optional[str]:
    """Return the challenge kind ("json", "html" or "415"), or None."""
    head = body[:_HEAD_BYTES]
    if _IMUNIFY_RE.search(head):
        return "json" if head.lstrip().startswith("{") else "html"
    if status == 415:
        return "415"
    if len(body) <= _STUB_MAX_BYTES and _RELOAD_RE.search(head):
        return "html"
    return None


def get(url: str, **kwargs) -> requests.Response:
    """requests.get that raises BotChallenge instead of returning the stub."""
    kwargs.setdefault("timeout", 15)
    jar = _cookies.get(_bare(_host(url)))
    if jar:
        merged = dict(jar)
        merged.update(kwargs.get("cookies") or {})
        kwargs["cookies"] = merged
    resp = requests.get(url, **kwargs)
    kind = detect(resp.status_code, resp.text)
    if kind:
        snippet = resp.text[:160].replace("\n", " ")
        raise BotChallenge(url, kind, resp.status_code, snippet)
    return resp


def solve(url: str, timeout: float = 30.0) -> bool:
    """Pass the challenge for url's host in headless Chrome.

    Returns True once the host serves real content to the browser.  Runs
    one host at a time; a second caller for an already cleared host
    returns at once.
    """
    parts = urlsplit(url)
    host = _bare(_host(url))
    origin = f"{parts.scheme}://{parts.netloc}/"

    with _lock:
        if host in _solved:
            return True
        t0 = time.monotonic()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.error("playwright is not installed, cannot pass the challenge for %s", host)
            return False
        try:
            with sync_playwright() as p:
                browser = _launch(p)
                try:
                    context = browser.new_context(locale="de-CH")
                    page = context.new_page()
                    page.goto(origin, wait_until="domcontentloaded", timeout=timeout * 1000)
                    passed = _wait_for_real_page(page, timeout)
                    cookies = {c["name"]: c["value"] for c in context.cookies()}
                finally:
                    browser.close()
        except Exception as e:
            log.error("headless Chrome failed on %s: %s", origin, e)
            return False

        elapsed = time.monotonic() - t0
        if passed:
            _cookies[host] = cookies
            _solved.add(host)
            log.info("passed the Imunify360 challenge on %s in %.1fs (%d cookies)",
                     host, elapsed, len(cookies))
        else:
            log.error("Imunify360 challenge on %s did not clear within %.0fs", host, timeout)
        return passed


def _launch(p):
    """Prefer the installed Google Chrome; fall back to downloading Chromium."""
    try:
        return p.chromium.launch(channel="chrome", headless=True)
    except Exception as e:
        first_line = str(e).splitlines()[0][:100] if str(e) else e.__class__.__name__
        log.info("no system Chrome (%s), downloading Playwright's Chromium", first_line)
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True, timeout=300,
        )
        return p.chromium.launch(headless=True)


def _wait_for_real_page(page, timeout: float) -> bool:
    """Poll until the page content is no longer the challenge stub."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
            if detect(200, page.content()) is None:
                return True
        except Exception:
            # The stub reloads itself; a navigation in progress throws here.
            pass
        page.wait_for_timeout(1000)
    return False
