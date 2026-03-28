import { createSignal, For, Show, onMount, onCleanup, type Component } from 'solid-js';
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

type DayGroup = {
  date: string;
  events: Event[];
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

  // Track how far ahead we've fetched
  let nextStartDate = new Date();

  async function loadNextBatch() {
    if (loadingMore()) return;
    setLoadingMore(true);
    try {
      const newGroups = await fetchDateRange(nextStartDate, DAYS_PER_BATCH);
      setDayGroups(prev => [...prev, ...newGroups]);
      // Advance the start date for next batch
      nextStartDate = new Date(nextStartDate);
      nextStartDate.setDate(nextStartDate.getDate() + DAYS_PER_BATCH);
    } finally {
      setLoadingMore(false);
    }
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

  return (
    <>
      {/* Mobile-only sticky header */}
      <Header onToggleFilters={() => setShowFilters(!showFilters())} />

      {/* Desktop page title */}
      <div class="max-w-[1200px] mx-auto px-8 pt-8 pb-2 max-md:hidden">
        <h1 class="text-2xl font-bold">Events in Uri</h1>
      </div>

      <div class="max-w-[1200px] mx-auto flex gap-8 p-8 pt-4 max-md:flex-col max-md:p-4 max-md:pt-0 max-md:gap-0">

        {/* ── Left column: Sidebar (desktop-only for now) ── */}
        <aside class="w-[280px] shrink-0 max-md:hidden">
          <div class="sticky top-8 bg-[var(--card-bg)] p-6 rounded-xl shadow-sm border border-[var(--border-color)]">
            <h2 class="text-base font-semibold mb-3">📅 Datum wählen</h2>
            <input
              type="date"
              class="w-full p-2 border border-[var(--border-color)] rounded-md font-[inherit]"
            />

            <hr class="border-t border-[var(--border-color)] my-6" />

            <h2 class="text-base font-semibold mb-3">🏢 Quellen</h2>
            <p class="text-sm text-[var(--text-muted)]">Filter kommen bald...</p>
          </div>
        </aside>

        {/* ── Right column: Event feed ── */}
        <main class="grow min-w-0">
          <Show when={!loading()} fallback={
            <p class="text-[var(--text-muted)] text-center py-12">Laden...</p>
          }>
            <For each={dayGroups()}>
              {(group) => (
                <div class="mb-8">
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
