import type { Event } from './event';

/** @internal Format a Date to ICS datetime string: 20260328T140000 */
export function toICSDateTime(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    date.getFullYear().toString() +
    pad(date.getMonth() + 1) +
    pad(date.getDate()) +
    'T' +
    pad(date.getHours()) +
    pad(date.getMinutes()) +
    pad(date.getSeconds())
  );
}

/** @internal Format "YYYY-MM-DD" to ICS date string: 20260328 */
export function toICSDate(dateStr: string): string {
  return dateStr.replace(/-/g, '');
}

/** @internal Escape text for ICS (newlines, commas, semicolons, backslashes) */
export function escapeICS(text: string): string {
  return text
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\n/g, '\\n');
}

/** @internal Add minutes to a Date and return new Date */
export function addMinutes(date: Date, minutes: number): Date {
  return new Date(date.getTime() + minutes * 60 * 1000);
}

/** @internal Add one day to a YYYY-MM-DD string without timezone conversion. */
export function nextDateStr(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number);
  const next = new Date(y, m - 1, d + 1); // local date arithmetic
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(next.getDate())}`;
}

/** Generate a Google Calendar URL for the event */
export function googleCalendarUrl(event: Event): string {
  const params = new URLSearchParams();
  params.set('action', 'TEMPLATE');
  params.set('text', event.event_title);

  if (!event.start_time) {
    // All-day event: dates only, no times
    const startStr = toICSDate(event.start_date);
    const endStr = toICSDate(nextDateStr(event.start_date));
    params.set('dates', `${startStr}/${endStr}`);
  } else {
    const start = new Date(`${event.start_date}T${event.start_time}`);
    const end = event.end_datetime
      ? new Date(event.end_datetime)
      : addMinutes(start, 5);
    params.set('dates', `${toICSDateTime(start)}/${toICSDateTime(end)}`);
  }

  params.set('ctz', 'Europe/Zurich');
  if (event.location) params.set('location', event.location);
  if (event.description) params.set('details', event.description);

  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

/** Generate an .ics file and trigger download */
export function downloadICS(event: Event): void {
  const lines: string[] = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Uri Calendar//Events//DE',
    'BEGIN:VEVENT',
    `UID:${event.event_id}@uri-calendar.ch`,
    `SUMMARY:${escapeICS(event.event_title)}`,
  ];

  if (event.location) {
    lines.push(`LOCATION:${escapeICS(event.location)}`);
  }

  if (event.description) {
    lines.push(`DESCRIPTION:${escapeICS(event.description)}`);
  }

  if (event.source_url) {
    lines.push(`URL:${event.source_url}`);
  }

  if (!event.start_time) {
    // All-day event
    lines.push(`DTSTART;VALUE=DATE:${toICSDate(event.start_date)}`);
    // All-day end is the next day (exclusive per ICS spec)
    lines.push(`DTEND;VALUE=DATE:${toICSDate(nextDateStr(event.start_date))}`);
  } else {
    // Timed event — all times are Europe/Zurich
    const start = new Date(`${event.start_date}T${event.start_time}`);
    lines.push(`DTSTART;TZID=Europe/Zurich:${toICSDateTime(start)}`);

    if (event.end_datetime) {
      const end = new Date(event.end_datetime);
      lines.push(`DTEND;TZID=Europe/Zurich:${toICSDateTime(end)}`);
    } else {
      // No end time: 5 minute placeholder
      const end = addMinutes(start, 5);
      lines.push(`DTEND;TZID=Europe/Zurich:${toICSDateTime(end)}`);
    }
  }

  lines.push('END:VEVENT', 'END:VCALENDAR');

  const content = lines.join('\r\n');
  const blob = new Blob([content], { type: 'text/calendar;charset=utf-8' });
  const url = URL.createObjectURL(blob);

  const a = document.createElement('a');
  a.href = url;
  a.download = `${event.event_title.slice(0, 50).replace(/[^a-zA-Z0-9äöüÄÖÜ ]/g, '')}.ics`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
