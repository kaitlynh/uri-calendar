import { createSignal, createMemo, For, Show, onMount, onCleanup, type Component } from 'solid-js';
import Header from './Header';
import Card from './Card';
import type { Event } from './event';

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

/** Get array of "YYYY-MM-DD" strings starting from a given date */
function getDateRange(startDate: Date, days: number): string[] {
  const dates: string[] = [];
  for (let i = 0; i < days; i++) {
    const d = new Date(startDate);
    d.setDate(startDate.getDate() + i);
    dates.push(d.toISOString().slice(0, 10));
  }
  return dates;
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
  image_url: string;
};

/** Fetch events for a range of dates in parallel, return non-empty groups */
async function fetchDateRange(startDate: Date, days: number): Promise<DayGroup[]> {
  const dates = getDateRange(startDate, days);
  const responses = await Promise.all(
    dates.map(date =>
      fetch(`${API_BASE}/events?date=${date}`)
        .then(r => r.json())
        .then((events: Event[]) => ({ date, events }))
    )
  );
  return responses.filter(group => group.events.length > 0);
}

const App: Component = () => {
  const [dayGroups, setDayGroups] = createSignal<DayGroup[]>([]);
  const [loading, setLoading] = createSignal(true);
  const [loadingMore, setLoadingMore] = createSignal(false);
  const [showFab, setShowFab] = createSignal(false);
  const [showFilters, setShowFilters] = createSignal(false);

  // Source filter state: set of enabled source names
  const [enabledSources, setEnabledSources] = createSignal<Set<string>>(new Set());
  // All known sources (accumulated as we fetch)
  const [knownSources, setKnownSources] = createSignal<SourceInfo[]>([]);

  // Track how far ahead we've fetched
  let nextStartDate = new Date();
  // The date the feed starts from (for date picker resets)
  const [feedStartDate, setFeedStartDate] = createSignal(toDateString(new Date()));

  // Track all source names we've ever seen (so we don't re-enable user-disabled ones)
  const seenSourceNames = new Set<string>();

  /** Extract unique sources from a batch and merge into known sources */
  function updateKnownSources(groups: DayGroup[]) {
    const existing = new Map(knownSources().map(s => [s.name, s]));
    const newNames: string[] = [];
    for (const group of groups) {
      for (const event of group.events) {
        if (!existing.has(event.source_name)) {
          existing.set(event.source_name, {
            name: event.source_name,
            image_url: event.image_url || '',
          });
        }
        if (!seenSourceNames.has(event.source_name)) {
          seenSourceNames.add(event.source_name);
          newNames.push(event.source_name);
        }
      }
    }
    const sorted = [...existing.values()].sort((a, b) => a.name.localeCompare(b.name));
    setKnownSources(sorted);
    // Only auto-enable sources we're seeing for the very first time
    if (newNames.length > 0) {
      setEnabledSources(prev => {
        const next = new Set(prev);
        for (const name of newNames) {
          next.add(name);
        }
        return next;
      });
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

  async function loadNextBatch() {
    if (loadingMore()) return;
    setLoadingMore(true);
    try {
      const newGroups = await fetchDateRange(nextStartDate, DAYS_PER_BATCH);
      setDayGroups(prev => [...prev, ...newGroups]);
      updateKnownSources(newGroups);
      // Advance the start date for next batch
      nextStartDate = new Date(nextStartDate);
      nextStartDate.setDate(nextStartDate.getDate() + DAYS_PER_BATCH);
    } finally {
      setLoadingMore(false);
    }
  }

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
          updateKnownSources(newGroups);
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
    await loadNextBatch();
    setLoading(false);
  });

  // Infinite scroll: load more when near bottom
  function handleScroll() {
    const scrolledDown = window.scrollY > 400;
    setShowFab(scrolledDown);

    const nearBottom =
      window.innerHeight + window.scrollY >= document.body.offsetHeight - 800;
    if (nearBottom && !loadingMore() && !loading()) {
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

        <h2 class="text-base font-semibold mb-3">🏢 Quellen</h2>
        <ul class="list-none space-y-2">
          <For each={knownSources()}>
            {(source) => (
              <li>
                <label class="flex items-center gap-2 cursor-pointer text-[0.95rem]">
                  <input
                    type="checkbox"
                    checked={enabledSources().has(source.name)}
                    onChange={() => toggleSource(source.name)}
                    class="accent-[var(--alpine-blue)]"
                  />
                  <Show when={source.image_url}>
                    <img
                      src={source.image_url}
                      alt=""
                      class="w-5 h-5 rounded object-cover"
                    />
                  </Show>
                  {source.name}
                </label>
              </li>
            )}
          </For>
        </ul>
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
        <h1 class="text-2xl font-bold">Events in Uri</h1>
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

            {/* Empty state when all sources filtered out */}
            <Show when={filteredDayGroups().length === 0 && dayGroups().length > 0}>
              <div class="text-center py-16">
                <p class="text-[var(--text-muted)] text-lg">Keine Events für diese Filter.</p>
              </div>
            </Show>

            {/* Loading more indicator */}
            <Show when={loadingMore()}>
              <p class="text-[var(--text-muted)] text-center py-8">Mehr laden...</p>
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
