import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  toICSDateTime,
  toICSDate,
  escapeICS,
  addMinutes,
  nextDateStr,
  googleCalendarUrl,
  downloadICS,
} from '../ics';
import {
  allDayEvent,
  timedEvent,
  timedEventNoEnd,
  specialCharsEvent,
} from './fixtures';

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

describe('toICSDateTime', () => {
  it('formats a date as YYYYMMDDTHHMMSS', () => {
    const date = new Date(2026, 3, 10, 14, 30, 0); // April 10, 2026 14:30
    expect(toICSDateTime(date)).toBe('20260410T143000');
  });

  it('zero-pads single-digit months and days', () => {
    const date = new Date(2026, 0, 5, 9, 5, 3); // Jan 5, 2026 09:05:03
    expect(toICSDateTime(date)).toBe('20260105T090503');
  });

  it('handles midnight', () => {
    const date = new Date(2026, 11, 31, 0, 0, 0);
    expect(toICSDateTime(date)).toBe('20261231T000000');
  });
});

describe('toICSDate', () => {
  it('removes hyphens from YYYY-MM-DD', () => {
    expect(toICSDate('2026-04-10')).toBe('20260410');
  });

  it('handles single-digit months in string form', () => {
    expect(toICSDate('2026-01-05')).toBe('20260105');
  });
});

describe('escapeICS', () => {
  it('escapes backslashes', () => {
    expect(escapeICS('path\\to\\file')).toBe('path\\\\to\\\\file');
  });

  it('escapes semicolons', () => {
    expect(escapeICS('A; B; C')).toBe('A\\; B\\; C');
  });

  it('escapes commas', () => {
    expect(escapeICS('30, 40, 50 CHF')).toBe('30\\, 40\\, 50 CHF');
  });

  it('escapes newlines', () => {
    expect(escapeICS('Line 1\nLine 2')).toBe('Line 1\\nLine 2');
  });

  it('handles multiple special characters at once', () => {
    expect(escapeICS('A; B, C\nD\\E')).toBe('A\\; B\\, C\\nD\\\\E');
  });

  it('returns plain text unchanged', () => {
    expect(escapeICS('Jass-Treff im Park')).toBe('Jass-Treff im Park');
  });
});

describe('addMinutes', () => {
  it('adds minutes to a date', () => {
    const base = new Date(2026, 3, 10, 14, 0, 0);
    const result = addMinutes(base, 30);
    expect(result.getHours()).toBe(14);
    expect(result.getMinutes()).toBe(30);
  });

  it('does not mutate the original date', () => {
    const base = new Date(2026, 3, 10, 14, 0, 0);
    const original = base.getTime();
    addMinutes(base, 30);
    expect(base.getTime()).toBe(original);
  });

  it('rolls over past midnight', () => {
    const base = new Date(2026, 3, 10, 23, 50, 0);
    const result = addMinutes(base, 20);
    expect(result.getDate()).toBe(11);
    expect(result.getHours()).toBe(0);
    expect(result.getMinutes()).toBe(10);
  });
});

describe('nextDateStr', () => {
  it('advances to the next day', () => {
    expect(nextDateStr('2026-04-10')).toBe('2026-04-11');
  });

  it('rolls over month boundaries', () => {
    expect(nextDateStr('2026-01-31')).toBe('2026-02-01');
  });

  it('rolls over year boundaries', () => {
    expect(nextDateStr('2026-12-31')).toBe('2027-01-01');
  });

  it('handles leap year', () => {
    expect(nextDateStr('2028-02-28')).toBe('2028-02-29');
    expect(nextDateStr('2028-02-29')).toBe('2028-03-01');
  });
});

// ---------------------------------------------------------------------------
// Google Calendar URL
// ---------------------------------------------------------------------------

describe('googleCalendarUrl', () => {
  it('generates a valid Google Calendar URL', () => {
    const url = googleCalendarUrl(timedEvent);
    expect(url).toContain('https://calendar.google.com/calendar/render');
    expect(url).toContain('action=TEMPLATE');
  });

  it('encodes the event title', () => {
    const url = googleCalendarUrl(timedEvent);
    expect(url).toContain('text=Konzert+im+Park');
  });

  it('sets timezone to Europe/Zurich', () => {
    const url = googleCalendarUrl(timedEvent);
    expect(url).toContain('ctz=Europe%2FZurich');
  });

  it('includes location when present', () => {
    const url = googleCalendarUrl(timedEvent);
    expect(url).toContain('location=');
    expect(url).toContain('Stadtpark');
  });

  it('includes description when present', () => {
    const url = googleCalendarUrl(timedEvent);
    expect(url).toContain('details=');
  });

  it('uses date-only format for all-day events', () => {
    const url = googleCalendarUrl(allDayEvent);
    // All-day: dates=YYYYMMDD/YYYYMMDD (next day, exclusive)
    expect(url).toContain('dates=20260410%2F20260411');
  });

  it('uses datetime format for timed events', () => {
    const url = googleCalendarUrl(timedEvent);
    // Timed: dates=YYYYMMDDTHHMMSS/YYYYMMDDTHHMMSS
    expect(url).toMatch(/dates=\d{8}T\d{6}%2F\d{8}T\d{6}/);
  });

  it('falls back to +5 minutes when no end time', () => {
    const url = googleCalendarUrl(timedEventNoEnd);
    // start: 14:00 → end should be 14:05
    expect(url).toContain('T140500');
  });
});

// ---------------------------------------------------------------------------
// ICS file download
// ---------------------------------------------------------------------------

describe('downloadICS', () => {
  let clickSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    clickSpy = vi.fn();
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = document.createElement.bind(document, tag)
        ? Object.assign(document.createElementNS('http://www.w3.org/1999/xhtml', tag), {
            click: clickSpy,
            href: '',
            download: '',
          })
        : (document.createElementNS('http://www.w3.org/1999/xhtml', tag) as HTMLElement);
      return el as HTMLElement;
    });
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock-url');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
  });

  it('triggers a file download', () => {
    downloadICS(timedEvent);
    expect(clickSpy).toHaveBeenCalled();
  });

  it('creates a blob URL and revokes it after download', () => {
    downloadICS(timedEvent);
    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url');
  });
});

describe('ICS content generation', () => {
  // Capture the ICS content by intercepting Blob creation
  function captureICS(event: Parameters<typeof downloadICS>[0]): string {
    let captured = '';
    const origBlob = globalThis.Blob;
    globalThis.Blob = class extends origBlob {
      constructor(parts: BlobPart[], options?: BlobPropertyBag) {
        super(parts, options);
        captured = parts.join('');
      }
    } as typeof Blob;

    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});

    downloadICS(event);
    globalThis.Blob = origBlob;
    return captured;
  }

  it('wraps content in VCALENDAR/VEVENT', () => {
    const ics = captureICS(timedEvent);
    expect(ics).toContain('BEGIN:VCALENDAR');
    expect(ics).toContain('END:VCALENDAR');
    expect(ics).toContain('BEGIN:VEVENT');
    expect(ics).toContain('END:VEVENT');
  });

  it('includes SUMMARY from event title', () => {
    const ics = captureICS(timedEvent);
    expect(ics).toContain('SUMMARY:Konzert im Park');
  });

  it('includes LOCATION when present', () => {
    const ics = captureICS(timedEvent);
    expect(ics).toContain('LOCATION:Stadtpark\\, Altdorf');
  });

  it('includes URL from source_url', () => {
    const ics = captureICS(timedEvent);
    expect(ics).toContain('URL:https://altdorf.ch/events/123');
  });

  it('uses VALUE=DATE for all-day events', () => {
    const ics = captureICS(allDayEvent);
    expect(ics).toContain('DTSTART;VALUE=DATE:20260410');
    expect(ics).toContain('DTEND;VALUE=DATE:20260411');
  });

  it('uses TZID=Europe/Zurich for timed events', () => {
    const ics = captureICS(timedEvent);
    expect(ics).toContain('DTSTART;TZID=Europe/Zurich:');
    expect(ics).toContain('DTEND;TZID=Europe/Zurich:');
  });

  it('escapes special characters in description', () => {
    const ics = captureICS(specialCharsEvent);
    expect(ics).toContain('\\n');
    expect(ics).toContain('\\;');
    expect(ics).toContain('\\,');
  });

  it('uses CRLF line endings per RFC 5545', () => {
    const ics = captureICS(timedEvent);
    expect(ics).toContain('\r\n');
  });

  it('generates a unique UID per event', () => {
    const ics = captureICS(timedEvent);
    expect(ics).toContain('UID:timed-001@uri-calendar.ch');
  });
});
