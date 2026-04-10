import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@solidjs/testing-library';
import Card from '../Card';
import { timedEvent, allDayEvent, specialCharsEvent, eventWithIcon, eventWithoutIcon } from './fixtures';

describe('Card', () => {
  // ── Rendering ────────────────────────────────────────────────────────────

  // Card renders mobile + desktop variants, so titles/text may appear twice

  it('renders the event title', () => {
    render(() => <Card event={timedEvent} />);
    expect(screen.getAllByText('Konzert im Park').length).toBeGreaterThan(0);
  });

  it('renders the event location', () => {
    render(() => <Card event={timedEvent} />);
    expect(screen.getByText(/Stadtpark, Altdorf/)).toBeInTheDocument();
  });

  it('renders the source name', () => {
    render(() => <Card event={timedEvent} />);
    expect(screen.getAllByText('altdorf.ch').length).toBeGreaterThan(0);
  });

  it('renders formatted start time (HH:MM)', () => {
    render(() => <Card event={timedEvent} />);
    // Time is inside a span with the clock emoji prefix
    expect(screen.getByText(/19:30/)).toBeInTheDocument();
  });

  it('does not render time for all-day events', () => {
    render(() => <Card event={allDayEvent} />);
    expect(screen.queryByText(/\d{2}:\d{2}/)).toBeNull();
  });

  // ── Links & buttons ─────────────────────────────────────────────────────

  it('links to the event source', () => {
    render(() => <Card event={timedEvent} />);
    const links = screen.getAllByRole('link', { name: /Zum Event/i });
    expect(links[0]).toHaveAttribute('href', timedEvent.source_url);
  });

  it('opens external links in a new tab', () => {
    render(() => <Card event={timedEvent} />);
    const links = screen.getAllByRole('link', { name: /Zum Event/i });
    expect(links[0]).toHaveAttribute('target', '_blank');
    expect(links[0]).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('has a Google Calendar link', () => {
    render(() => <Card event={timedEvent} />);
    const links = screen.getAllByRole('link', { name: /Google Calendar/i });
    expect(links[0]).toHaveAttribute('href', expect.stringContaining('calendar.google.com'));
  });

  it('has an ICS download button', () => {
    render(() => <Card event={timedEvent} />);
    expect(screen.getByText('ICS')).toBeInTheDocument();
  });

  // ── Expand/collapse ─────────────────────────────────────────────────────

  it('shows expand button when event has a description', () => {
    render(() => <Card event={timedEvent} />);
    expect(screen.getByLabelText('Mehr anzeigen')).toBeInTheDocument();
  });

  it('does not show expand button when description is empty', () => {
    const noDesc = { ...timedEvent, description: '' };
    render(() => <Card event={noDesc} />);
    expect(screen.queryByLabelText('Mehr anzeigen')).toBeNull();
    expect(screen.queryByLabelText('Weniger anzeigen')).toBeNull();
  });

  it('toggles aria-expanded on click', async () => {
    render(() => <Card event={timedEvent} />);
    const btn = screen.getByLabelText('Mehr anzeigen');

    expect(btn).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(btn);
    expect(btn).toHaveAttribute('aria-expanded', 'true');
    expect(btn).toHaveAttribute('aria-label', 'Weniger anzeigen');

    fireEvent.click(btn);
    expect(btn).toHaveAttribute('aria-expanded', 'false');
    expect(btn).toHaveAttribute('aria-label', 'Mehr anzeigen');
  });

  // ── Date display ────────────────────────────────────────────────────────

  it('shows date when showDate prop is true', () => {
    render(() => <Card event={timedEvent} showDate={true} />);
    // Should contain a formatted date (German locale)
    expect(screen.getByText(/Apr/)).toBeInTheDocument();
  });

  it('hides date when showDate prop is false', () => {
    render(() => <Card event={timedEvent} showDate={false} />);
    expect(screen.queryByText(/Apr.*2026/)).toBeNull();
  });

  // ── Icon fallback ───────────────────────────────────────────────────────

  it('renders display name when no icon is available', () => {
    render(() => <Card event={eventWithoutIcon} />);
    expect(screen.getAllByText('Unbekannte Quelle').length).toBeGreaterThan(0);
  });

  // ── Accessibility ───────────────────────────────────────────────────────

  it('marks external links with sr-only text', () => {
    render(() => <Card event={timedEvent} />);
    const srTexts = screen.getAllByText('(öffnet neues Fenster)');
    expect(srTexts.length).toBeGreaterThan(0);
    srTexts.forEach(el => expect(el).toHaveClass('sr-only'));
  });

  it('renders as an article element', () => {
    render(() => <Card event={timedEvent} />);
    expect(screen.getByRole('article')).toBeInTheDocument();
  });
});
