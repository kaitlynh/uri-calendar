import type { Event } from '../event';

/** Minimal event with only required fields — extend per test as needed. */
function baseEvent(overrides: Partial<Event> = {}): Event {
  return {
    event_id: 'test-001',
    source_name: 'altdorf.ch',
    source_url: 'https://altdorf.ch/events/123',
    event_title: 'Jass-Treff',
    start_date: '2026-04-10',
    location: 'Altdorf',
    description: '',
    extracted_at: '2026-04-09T12:00:00',
    ...overrides,
  };
}

/** All-day event without a start time. */
export const allDayEvent: Event = baseEvent({
  event_id: 'allday-001',
  event_title: 'Dorffest Altdorf',
  start_time: null,
  location: 'Dorfplatz, Altdorf',
  description: 'Ein Fest für alle.',
});

/** Timed event with start time and end datetime. */
export const timedEvent: Event = baseEvent({
  event_id: 'timed-001',
  event_title: 'Konzert im Park',
  start_time: '19:30:00',
  end_datetime: '2026-04-10T22:00:00',
  location: 'Stadtpark, Altdorf',
  description: 'Live-Musik mit lokalen Bands.',
});

/** Timed event without an end time — should fall back to +5 minutes. */
export const timedEventNoEnd: Event = baseEvent({
  event_id: 'timed-002',
  event_title: 'Vortrag',
  start_time: '14:00:00',
  end_datetime: null,
  location: 'Bibliothek',
});

/** Event with special characters that need ICS escaping. */
export const specialCharsEvent: Event = baseEvent({
  event_id: 'special-001',
  event_title: 'Theater: Romeo & Julia; Premiere',
  start_time: '20:00:00',
  location: 'Theater Uri, Altdorf',
  description: 'Regie: M. Müller\nMit Pause;\nEintritt: 30, 40, 50 CHF',
});

/** Event with icon filename. */
export const eventWithIcon: Event = baseEvent({
  event_id: 'icon-001',
  icon_filename: 'altdorf-geminde.png',
  display_name: 'Gemeinde Altdorf',
});

/** Event without icon. */
export const eventWithoutIcon: Event = baseEvent({
  event_id: 'noicon-001',
  icon_filename: null,
  display_name: 'Unbekannte Quelle',
});
