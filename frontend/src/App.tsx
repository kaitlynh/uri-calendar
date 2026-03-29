import { createSignal, createMemo, createEffect, For, Show, onMount, onCleanup, type Component } from 'solid-js';
import Header from './Header';
import Card from './Card';
import type { Event } from './event';
import { getSourceIcon } from './sources';

const API_BASE = 'http://178.104.80.19/api';
const DAYS_PER_BATCH = 14;

/** "2026-03-28" → "Samstag, 28. März 2026" */
function formatDateHeading(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00');
  return date.toLocaleDateString('de-CH', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

/** Format a Date to "YYYY-MM-DD" for the date input */
function toDateString(d: Date): string {
  return d.toISOString().slice(0, 10);
}

type DayGroup = {
  date: string;
  events: Event[];
};

type SourceInfo = {
  name: string;
  display_name: string | null;
  icon_filename: string | null;
  category: string | null;
};

/** Fetch events for a date range in a single API call, return non-empty day groups */
async function fetchDateRange(startDate: Date, days: number): Promise<DayGroup[]> {
  const endDate = new Date(startDate);
  endDate.setDate(endDate.getDate() + days - 1);
  const start = toDateString(startDate);
  const end = toDateString(endDate);

  const resp = await fetch(`${API_BASE}/events?start_date=${start}&end_date=${end}`);
  const events: Event[] = await resp.json();

  // Group events by start_date
  const grouped = new Map<string, Event[]>();
  for (const event of events) {
    const d = event.start_date;
    if (!grouped.has(d)) grouped.set(d, []);
    grouped.get(d)!.push(event);
  }

  // Return sorted day groups (API already sorts by date, but ensure order)
  return [...grouped.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, events]) => ({ date, events }));
}

const App: Component = () => {
  const [dayGroups, setDayGroups] = createSignal<DayGroup[]>([]);
  const [loading, setLoading] = createSignal(true);
  const [loadingMore, setLoadingMore] = createSignal(false);
  const [showFab, setShowFab] = createSignal(false);
  const [showFilters, setShowFilters] = createSignal(false);
  const [reachedEnd, setReachedEnd] = createSignal(false);
  const [loadingExtended, setLoadingExtended] = createSignal(false);

  // Source filter state: set of enabled source names
  const [enabledSources, setEnabledSources] = createSignal<Set<string>>(new Set());
  // All known sources (accumulated as we fetch)
  const [knownSources, setKnownSources] = createSignal<SourceInfo[]>([]);

  // Track how far ahead we've fetched
  let nextStartDate = new Date();
  // The date the feed starts from (for date picker resets)
  const [feedStartDate, setFeedStartDate] = createSignal(toDateString(new Date()));

  /** Fetch all sources from the API and populate filters */
  async function fetchSources() {
    try {
      const resp = await fetch(`${API_BASE}/sources`);
      const data: { source_name: string; base_url: string; display_name: string | null; icon_filename: string | null; category: string | null }[] = await resp.json();
      const sources: SourceInfo[] = data.map(s => ({
        name: s.source_name,
        display_name: s.display_name,
        icon_filename: s.icon_filename,
        category: s.category,
      }));
      setKnownSources(sources);
      setEnabledSources(new Set(sources.map(s => s.name)));
    } catch (e) {
      console.error('Failed to fetch sources:', e);
    }
  }

  function toggleSource(name: string) {
    setEnabledSources(prev => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  }

  // Filtered day groups: only show events from enabled sources
  const filteredDayGroups = createMemo(() => {
    const enabled = enabledSources();
    return dayGroups()
      .map(group => ({
        date: group.date,
        events: group.events.filter(e => enabled.has(e.source_name)),
      }))
      .filter(group => group.events.length > 0);
  });

  async function loadNextBatch(): Promise<boolean> {
    if (loadingMore()) return false;
    setLoadingMore(true);
    try {
      const newGroups = await fetchDateRange(nextStartDate, DAYS_PER_BATCH);
      setDayGroups(prev => [...prev, ...newGroups]);

      // Always advance the start date
      nextStartDate = new Date(nextStartDate);
      nextStartDate.setDate(nextStartDate.getDate() + DAYS_PER_BATCH);

      if (newGroups.length === 0) {
        setReachedEnd(true);
        return false;
      }
      return true;
    } finally {
      setLoadingMore(false);
    }
  }

  const EXTENDED_DAYS = 60;

  /** Load ~2 months in one call, used when normal 14-day batches run dry */
  async function loadExtended() {
    if (loadingExtended()) return;
    setLoadingExtended(true);
    setReachedEnd(false);
    try {
      const newGroups = await fetchDateRange(nextStartDate, EXTENDED_DAYS);
      setDayGroups(prev => [...prev, ...newGroups]);
      nextStartDate = new Date(nextStartDate);
      nextStartDate.setDate(nextStartDate.getDate() + EXTENDED_DAYS);
      setReachedEnd(true);
    } finally {
      setLoadingExtended(false);
    }
  }

  /** Format the nextStartDate for display */
  const loadedUntilDate = () => {
    const d = new Date(nextStartDate);
    d.setDate(d.getDate() - 1);
    return d.toLocaleDateString('de-CH', { day: 'numeric', month: 'long', year: 'numeric' });
  };

  /** Jump to a specific date: load up to that date if needed, then scroll to it */
  async function jumpToDate(dateStr: string) {
    setFeedStartDate(dateStr);
    const targetDate = new Date(dateStr + 'T00:00:00');

    // If the target is beyond what we've loaded, fetch in batches until we reach it
    if (targetDate >= nextStartDate) {
      setLoadingMore(true);
      try {
        while (nextStartDate <= targetDate) {
          const newGroups = await fetchDateRange(nextStartDate, DAYS_PER_BATCH);
          setDayGroups(prev => [...prev, ...newGroups]);
    
          nextStartDate = new Date(nextStartDate);
          nextStartDate.setDate(nextStartDate.getDate() + DAYS_PER_BATCH);
        }
      } finally {
        setLoadingMore(false);
      }
    }

    // Scroll to the date header (wait for DOM to update after state change)
    await new Promise(r => setTimeout(r, 50));
    requestAnimationFrame(() => {
      // Try exact date first
      let el = document.querySelector(`[data-date="${dateStr}"]`);
      if (!el) {
        // No events on that exact date — find the nearest date after it
        const allHeaders = document.querySelectorAll('[data-date]');
        for (const header of allHeaders) {
          if ((header as HTMLElement).dataset.date! >= dateStr) {
            el = header;
            break;
          }
        }
      }
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }

  // Initial load
  onMount(async () => {
    await fetchSources();
    await loadNextBatch();
    setLoading(false);
  });

  // Auto-load more when filtered results don't fill the viewport
  createEffect(() => {
    const groups = filteredDayGroups();
    // Access these signals to track them
    const ended = reachedEnd();
    const isLoading = loading() || loadingMore() || loadingExtended();
    if (isLoading || ended) return;

    // Wait for DOM to render, then check if content fills viewport
    requestAnimationFrame(() => {
      if (document.body.offsetHeight <= window.innerHeight + 200) {
        loadNextBatch();
      }
    });
  });

  // Infinite scroll: load more when near bottom
  function handleScroll() {
    const scrolledDown = window.scrollY > 400;
    setShowFab(scrolledDown);

    const nearBottom =
      window.innerHeight + window.scrollY >= document.body.offsetHeight - 800;
    if (nearBottom && !loadingMore() && !loading() && !reachedEnd()) {
      loadNextBatch();
    }
  }

  onMount(() => {
    window.addEventListener('scroll', handleScroll, { passive: true });
  });
  onCleanup(() => {
    window.removeEventListener('scroll', handleScroll);
  });

  function scrollToTop() {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  /** The sidebar content — shared between desktop sidebar and mobile drawer */
  function SidebarContent() {
    return (
      <>
        <h2 class="text-base font-semibold mb-3">📅 Datum wählen</h2>
        <input
          type="date"
          value={feedStartDate()}
          onChange={(e) => jumpToDate(e.currentTarget.value)}
          class="w-full p-2 border border-[var(--border-color)] rounded-md font-[inherit]"
        />

        <hr class="border-t border-[var(--border-color)] my-6" />

        <div class="flex items-center justify-between mb-3">
          <h2 class="text-base font-semibold">🏢 Quellen</h2>
          <div class="flex gap-2 text-xs">
            <button
              onClick={() => setEnabledSources(new Set(knownSources().map(s => s.name)))}
              class="text-[var(--alpine-blue)] hover:underline cursor-pointer bg-transparent border-none font-medium"
            >
              Alle
            </button>
            <span class="text-[var(--text-muted)]">|</span>
            <button
              onClick={() => setEnabledSources(new Set())}
              class="text-[var(--alpine-blue)] hover:underline cursor-pointer bg-transparent border-none font-medium"
            >
              Keine
            </button>
          </div>
        </div>
        <ul class="list-none space-y-1">
          {/* Uncategorized sources first */}
          <For each={knownSources().filter(s => !s.category).sort((a, b) => (a.display_name || a.name).localeCompare(b.display_name || b.name))}>
            {(source) => (
              <li>
                <label class="flex items-center gap-2 cursor-pointer text-[0.95rem]">
                  <input
                    type="checkbox"
                    checked={enabledSources().has(source.name)}
                    onChange={() => toggleSource(source.name)}
                    class="accent-[var(--alpine-blue)]"
                  />
                  <Show when={getSourceIcon(source.icon_filename)}>
                    <img src={getSourceIcon(source.icon_filename)} alt="" class="w-5 h-5 rounded object-cover" />
                  </Show>
                  {source.display_name || source.name}
                </label>
              </li>
            )}
          </For>
          {/* Categorized sources, grouped */}
          <For each={[...new Set(knownSources().filter(s => s.category).map(s => s.category!))].sort()}>
            {(category) => {
              const members = () => knownSources().filter(s => s.category === category).sort((a, b) => (a.display_name || a.name).localeCompare(b.display_name || b.name));
              const allChecked = () => members().every(s => enabledSources().has(s.name));
              const someChecked = () => members().some(s => enabledSources().has(s.name));
              const toggleCategory = () => {
                setEnabledSources(prev => {
                  const next = new Set(prev);
                  if (allChecked()) {
                    members().forEach(s => next.delete(s.name));
                  } else {
                    members().forEach(s => next.add(s.name));
                  }
                  return next;
                });
              };
              return (
                <li class="mt-3">
                  <label class="flex items-center gap-2 cursor-pointer text-[0.95rem] font-medium text-[var(--text-muted)]">
                    <input
                      type="checkbox"
                      checked={allChecked()}
                      ref={(el) => { setTimeout(() => el.indeterminate = someChecked() && !allChecked(), 0); }}
                      onChange={toggleCategory}
                      class="accent-[var(--alpine-blue)]"
                    />
                    {category}
                  </label>
                  <ul class="list-none ml-6 mt-1 space-y-1">
                    <For each={members()}>
                      {(source) => (
                        <li>
                          <label class="flex items-center gap-2 cursor-pointer text-[0.95rem]">
                            <input
                              type="checkbox"
                              checked={enabledSources().has(source.name)}
                              onChange={() => toggleSource(source.name)}
                              class="accent-[var(--alpine-blue)]"
                            />
                            <Show when={getSourceIcon(source.icon_filename)}>
                              <img src={getSourceIcon(source.icon_filename)} alt="" class="w-5 h-5 rounded object-cover" />
                            </Show>
                            {source.display_name || source.name}
                          </label>
                        </li>
                      )}
                    </For>
                  </ul>
                </li>
              );
            }}
          </For>
        </ul>

        <hr class="border-t border-[var(--border-color)] my-6" />

        <h2 class="text-base font-semibold mb-2">ℹ️ Über</h2>
        <p class="text-sm text-[var(--text-muted)] leading-relaxed">
          Diese Seite sammelt automatisch Veranstaltungen aus den oben aufgeführten Quellen im Kanton Uri. Einträge mit dem Hinweis <span class="inline-flex items-center gap-1 text-[0.7rem] font-medium px-1.5 py-0.5 rounded-md bg-[var(--border-color)] text-[var(--text-muted)]">✨ KI-ergänzt</span> wurden mithilfe von künstlicher Intelligenz ergänzt.
        </p>

        <hr class="border-t border-[var(--border-color)] my-6" />

        <h2 class="text-base font-semibold mb-3">📊 Quelldaten</h2>
        <a
          href="/admin"
          class="text-sm font-medium text-[var(--alpine-blue)] hover:underline"
        >
          Scraping-Status anzeigen →
        </a>
      </>
    );
  }

  return (
    <>
      {/* Mobile-only sticky header */}
      <Header onToggleFilters={() => setShowFilters(!showFilters())} />

      {/* Mobile filter drawer */}
      <Show when={showFilters()}>
        <div class="md:hidden bg-[var(--card-bg)] border-b border-[var(--border-color)] px-4 py-4">
          <SidebarContent />
        </div>
      </Show>

      {/* Desktop page title */}
      <div class="max-w-[1200px] mx-auto px-8 pt-8 pb-2 max-md:hidden">
        <h1 class="text-2xl font-bold">Veranstaltungen im Kanton Uri</h1>
      </div>

      <div class="max-w-[1200px] mx-auto flex gap-8 p-8 pt-4 max-md:flex-col max-md:p-4 max-md:pt-0 max-md:gap-0">

        {/* ── Left column: Sidebar (desktop only) ── */}
        <aside class="w-[280px] shrink-0 max-md:hidden">
          <div class="sticky top-8 bg-[var(--card-bg)] p-6 rounded-xl shadow-sm border border-[var(--border-color)]">
            <SidebarContent />
          </div>
        </aside>

        {/* ── Right column: Event feed ── */}
        <main class="grow min-w-0">
          <Show when={!loading()} fallback={
            <p class="text-[var(--text-muted)] text-center py-12">Laden...</p>
          }>
            <For each={filteredDayGroups()}>
              {(group) => (
                <div class="mb-8" data-date={group.date}>
                  <h3 class="sticky top-0 max-md:top-[49px] z-10 bg-[var(--bg-color)]/90 backdrop-blur-sm py-4 text-xl font-semibold border-b-2 border-[var(--border-color)] mb-4">
                    {formatDateHeading(group.date)}
                  </h3>

                  <div class="flex flex-col gap-4">
                    <For each={group.events}>
                      {(event) => <Card event={event} />}
                    </For>
                  </div>
                </div>
              )}
            </For>

            {/* Empty state when no filtered events */}
            <Show when={filteredDayGroups().length === 0 && !loading() && !loadingMore()}>
              <div class="text-center py-16">
                <img src="/uri-lake-drawing.png" alt="Uri Berge" class="w-full mb-6 opacity-60" />
                <p class="text-[var(--text-muted)] text-lg">Keine Veranstaltungen gefunden. Wie wärs mit einem Ausflug in die Berge?</p>
              </div>
            </Show>

            {/* Loading more indicator */}
            <Show when={loadingMore() || loadingExtended()}>
              <p class="text-[var(--text-muted)] text-center py-8">Mehr laden...</p>
            </Show>

            {/* Reached end — show load-more button */}
            <Show when={reachedEnd() && !loadingExtended()}>
              <div class="text-center py-8 border-t border-[var(--border-color)] mt-4">
                <p class="text-[var(--text-muted)] text-sm mb-3">
                  Geladen bis {loadedUntilDate()}
                </p>
                <button
                  onClick={loadExtended}
                  class="px-6 py-2 rounded-lg bg-[var(--alpine-blue)] text-white font-medium text-sm hover:bg-[var(--alpine-blue-hover)] transition-colors cursor-pointer"
                >
                  Weitere Veranstaltungen laden
                </button>
              </div>
            </Show>
          </Show>
        </main>
      </div>

      {/* ── FAB: scroll to top ── */}
      <Show when={showFab()}>
        <button
          onClick={scrollToTop}
          class="fixed bottom-8 right-8 max-md:bottom-4 max-md:right-4 w-12 h-12 rounded-full bg-[var(--card-bg)] border border-[var(--border-color)] shadow-lg flex items-center justify-center cursor-pointer text-[var(--text-main)] hover:bg-[var(--bg-color)] transition-colors z-50"
          aria-label="Nach oben"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="18 15 12 9 6 15" />
          </svg>
        </button>
      </Show>
    </>
  );
};

export default App;
