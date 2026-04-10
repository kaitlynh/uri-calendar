# Pitch

---

## Titel / Title

**Uri-Kalender**

*Image suggestion: a month-view calendar with pins across Uri municipalities, or a browser with too many open tabs of local websites*

---

## Worum geht es / What is it about

**DE:** Ein zentraler Veranstaltungskalender für den Kanton Uri. Schulen, Gemeinden, Kirchen und andere lokale Organisationen veröffentlichen ihre Veranstaltungen bereits auf ihren eigenen Websites — dieses Projekt sammelt diese Daten automatisch an einem Ort. Ein KI-gesteuertes Skript scrapt die öffentlichen Kalender regelmässig und befüllt eine zentrale Datenbank. Eine öffentliche, deutschsprachige Website zeigt alle Veranstaltungen übersichtlich an. Das Projekt ergänzt bestehende Portale wie uri.ch, anstatt sie zu ersetzen.

**EN:** A centralized event calendar for Canton Uri. Schools, communes, churches, and local organizations already publish their events on their own websites — this project automatically collects all of that in one place. An AI-powered script regularly scrapes public calendars and populates a central database. A public, German-language website displays all events in one view. The project complements existing portals like uri.ch rather than replacing them.

---

## Warum? / Why?

**DE:** Im Kanton Uri gibt es das ganze Jahr über viele Veranstaltungen: Stadtmärkte, Schulumzüge, Kirchenanlässe, Kinderfeste, Bibliotheksveranstaltungen, Festivals, Weihnachtsmärkte, Open-Air-Kino und mehr. Die Veranstaltungsdetails sind auf den Websites der Veranstalter verstreut, sodass die Einwohnerinnen und Einwohner jede Woche mehrere Kalender prüfen müssen, um informiert zu bleiben. Das Projekt löst auch ein weiteres Problem: Veranstalter haben derzeit keine einfache Möglichkeit zu prüfen, was bereits geplant ist. So hatten zum Beispiel kürzlich sowohl Altdorf als auch Bürglen ihren Schul-Skitag am selben Tag am selben Ort.

**EN:** We are lucky in Uri to have so many events happening throughout the year: town markets, school parades, church events, Kinderfests, library events, festivals, Christmas markets, open air cinema, and more. Event details are spread across the organizer websites, so residents need to check several calendars each week to stay informed. The project will also solve a secondary problem: event organizers currently have no easy way to check what else is already scheduled when planning an event. For example, recently both Altdorf and Bürglen had their school ski days on the same day at the same location.

---

## Ressourcen und Hilfsmittel / Resources and Tools

**DE:**
- **Daten:** Öffentliche Websites von Schulen, Gemeinden, Kirchen und Vereinen im Kanton Uri
- **KI:** PublicAI API (Apertus-Modell) — Schweizer Open-Source-Sprachmodell von EPFL, ETH Zürich und CSCS
- **Scraping-Tool:** Jina Reader, Crawl4AI oder Firecrawl (Auswahl während der Hackdays)
- **Backend:** Python, PostgreSQL oder SQLite
- **Frontend:** HTML/CSS/JS oder Framework nach Teamwahl; FullCalendar (Open Source) empfohlen
- **Hosting:** Hetzner Cloud VPS (Deutschland, EU-Datenschutz)
- **Versionskontrolle:** GitHub; Automatisierung via GitHub Actions oder Cron-Job

**EN:**
- **Data:** Public websites of schools, communes, churches, and clubs in Canton Uri
- **AI:** PublicAI API (Apertus model) — Swiss open-source language model by EPFL, ETH Zurich, and CSCS
- **Scraping tool:** Jina Reader, Crawl4AI, or Firecrawl (chosen during the hackathon)
- **Backend:** Python, PostgreSQL or SQLite
- **Frontend:** HTML/CSS/JS or framework of the team's choice; FullCalendar (open source) recommended
- **Hosting:** Hetzner Cloud VPS (Germany, EU data protection law)
- **Version control:** GitHub; automation via GitHub Actions or cron job

---

## Erwartungen / Expected Outcome

**DE:**
- Eine live erreichbare Website mit einem funktionierenden Kalender, der Veranstaltungen aus mindestens drei lokalen Quellen automatisch aggregiert.
- Die vollständige Pipeline ist in Betrieb: Scraping → KI → Datenbank → Website.

**EN:**
- A live website with a working calendar that automatically aggregates events from at least three local sources.
- The full pipeline is running end to end: scraping → AI → database → website.

---

## Outlook

**DE:** Das Projekt ist so konzipiert, dass es nach den Hackdays ohne menschliche Wartung weiterläuft. Der Scraper läuft automatisch nach einem Zeitplan, und die Betriebskosten liegen bei ca. 44–63 CHF pro Jahr — ein VPS und ein Domainname. Das ist alles. Die Challenge Ownerin ist bereit, diese Kosten zu tragen; langfristig könnte ein optionaler Sponsorenbereich auf der Website lokale Unternehmen einbinden. Neue Funktionen oder weitere Quellen können bei Bedarf später hinzugefügt werden.

**EN:** The project is designed to keep running after the hackathon with no human maintenance. The scraper runs automatically on a schedule, and the ongoing cost is approximately 44–63 CHF per year — a VPS and a domain name. That's it. The challenge owner is prepared to cover these costs; longer term, an optional sponsored section on the website could involve local businesses. Additional features or more sources can be added later if there is interest.

---

## Challenge Owner

**DE:**
- **Name:** Hanrahan, Kaitlyn
- **Organisation:** Simply Digital (selbstständig / self-employed)
- **E-Mail:** kaitlyn@kait.us
- **Mobil:** *(bitte ergänzen / please add)*
