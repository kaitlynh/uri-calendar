import {
  createSignal,
  createMemo,
  createEffect,
  For,
  Show,
  onMount,
  onCleanup,
  type Component,
} from 'solid-js';
import Header from './Header';
import Card from './Card';
import type { Event } from './event';
import { getSourceIcon } from './sources';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const API_BASE = '/api';
const DAYS_PER_BATCH = 14;
const EXTENDED_DAYS = 60;
const SEARCH_DEBOUNCE_MS = 300;
const SCROLL_FAB_THRESHOLD = 400;
const SCROLL_LOAD_THRESHOLD = 800;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** "2026-03-28" -> "Samstag, 28. März 2026" */
function formatDateHeading(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00');
  return date.toLocaleDateString('de-CH', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

/** Format a Date as "YYYY-MM-DD" */
function toDateString(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** Fetch events for a date range and return non-empty day groups. */
async function fetchDateRange(startDate: Date, days: number): Promise<DayGroup[]> {
  const endDate = new Date(startDate);
  endDate.setDate(endDate.getDate() + days - 1);

  const resp = await fetch(
    `${API_BASE}/events?start_date=${toDateString(startDate)}&end_date=${toDateString(endDate)}`
  );
  const events: Event[] = await resp.json();

  // Group events by date
  const grouped = new Map<string, Event[]>();
  for (const event of events) {
    const d = event.start_date;
    if (!grouped.has(d)) grouped.set(d, []);
    grouped.get(d)!.push(event);
  }

  return [...grouped.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, events]) => ({ date, events }));
}

// ---------------------------------------------------------------------------
// App component
// ---------------------------------------------------------------------------

const App: Component = () => {
  // -- Feed state -----------------------------------------------------------
  const [dayGroups, setDayGroups] = createSignal<DayGroup[]>([]);
  const [loading, setLoading] = createSignal(true);
  const [loadingMore, setLoadingMore] = createSignal(false);
  const [loadingExtended, setLoadingExtended] = createSignal(false);
  const [reachedEnd, setReachedEnd] = createSignal(false);

  // -- Error state ----------------------------------------------------------
  const [error, setError] = createSignal<string | null>(null);

  // -- UI state -------------------------------------------------------------
  const [showFab, setShowFab] = createSignal(false);
  const [showFilters, setShowFilters] = createSignal(false);
  const [feedStartDate, setFeedStartDate] = createSignal(toDateString(new Date()));

  // -- Source filters -------------------------------------------------------
  const [enabledSources, setEnabledSources] = createSignal<Set<string>>(new Set());
  const [knownSources, setKnownSources] = createSignal<SourceInfo[]>([]);

  // -- Search ---------------------------------------------------------------
  const [searchQuery, setSearchQuery] = createSignal('');
  const [searchResults, setSearchResults] = createSignal<{ title: Event[]; detail: Event[] } | null>(null);
  const [searchLoading, setSearchLoading] = createSignal(false);
  let searchTimeout: ReturnType<typeof setTimeout> | undefined;

  // Tracks the date up to which we've already fetched events.
  // Mutated only inside loadNextBatch / loadExtended / jumpToDate,
  // all of which are guarded by loadingMore() to prevent concurrent access.
  let nextStartDate = new Date();

  // -- Derived state --------------------------------------------------------

  /** Day groups filtered to only include events from enabled sources. */
  const filteredDayGroups = createMemo(() => {
    const enabled = enabledSources();
    return dayGroups()
      .map(group => ({
        date: group.date,
        events: group.events.filter(e => enabled.has(e.source_name)),
      }))
      .filter(group => group.events.length > 0);
  });

  /** Human-readable end of the currently loaded date range. */
  const loadedUntilDate = () => {
    const d = new Date(nextStartDate);
    d.setDate(d.getDate() - 1);
    return d.toLocaleDateString('de-CH', { day: 'numeric', month: 'long', year: 'numeric' });
  };

  // -- Data fetching --------------------------------------------------------

  /** Fetch all sources from the API and enable them in the filter. */
  async function fetchSources() {
    try {
      const resp = await fetch(`${API_BASE}/sources`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data: {
        source_name: string;
        base_url: string;
        display_name: string | null;
        icon_filename: string | null;
        category: string | null;
      }[] = await resp.json();

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
      setError('Quellen konnten nicht geladen werden.');
    }
  }

  /** Load the next 14-day batch of events. Returns false if no more events. */
  async function loadNextBatch(): Promise<boolean> {
    if (loadingMore()) return false;
    setLoadingMore(true);
    try {
      const newGroups = await fetchDateRange(nextStartDate, DAYS_PER_BATCH);
      setError(null);
      setDayGroups(prev => [...prev, ...newGroups]);

      nextStartDate = new Date(nextStartDate);
      nextStartDate.setDate(nextStartDate.getDate() + DAYS_PER_BATCH);

      if (newGroups.length === 0) {
        setReachedEnd(true);
        return false;
      }
      return true;
    } catch (e) {
      console.error('Failed to load events:', e);
      setError('Veranstaltungen konnten nicht geladen werden.');
      return false;
    } finally {
      setLoadingMore(false);
    }
  }

  /** Load ~2 months in one call — used when normal batches run dry. */
  async function loadExtended() {
    if (loadingExtended()) return;
    setLoadingExtended(true);
    setReachedEnd(false);
    try {
      const newGroups = await fetchDateRange(nextStartDate, EXTENDED_DAYS);
      setError(null);
      setDayGroups(prev => [...prev, ...newGroups]);
      nextStartDate = new Date(nextStartDate);
      nextStartDate.setDate(nextStartDate.getDate() + EXTENDED_DAYS);
      setReachedEnd(true);
    } catch (e) {
      console.error('Failed to load extended events:', e);
      setError('Veranstaltungen konnten nicht geladen werden.');
    } finally {
      setLoadingExtended(false);
    }
  }

  /** Jump to a specific date: fetch ahead if needed, then scroll to it. */
  async function jumpToDate(dateStr: string) {
    setFeedStartDate(dateStr);
    const targetDate = new Date(dateStr + 'T00:00:00');

    // Fetch in batches until we've loaded past the target date
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

    // Scroll to the matching date header (or the nearest one after it)
    await new Promise(r => setTimeout(r, 50));
    requestAnimationFrame(() => {
      let el = document.querySelector(`[data-date="${dateStr}"]`);
      if (!el) {
        const allHeaders = document.querySelectorAll('[data-date]');
        for (const header of allHeaders) {
          if ((header as HTMLElement).dataset.date! >= dateStr) {
            el = header;
            break;
          }
        }
      }
      el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  // -- Search ---------------------------------------------------------------

  /** Debounced search — waits 300ms after typing stops, then queries the API. */
  function handleSearch(query: string) {
    setSearchQuery(query);
    clearTimeout(searchTimeout);

    if (query.length < 2) {
      setSearchResults(null);
      setSearchLoading(false);
      return;
    }

    setSearchLoading(true);
    searchTimeout = setTimeout(async () => {
      try {
        const resp = await fetch(`${API_BASE}/events/search?q=${encodeURIComponent(query)}`);
        const data: (Event & { match_type: string })[] = await resp.json();
        const enabled = enabledSources();
        const filtered = data.filter(e => enabled.has(e.source_name));
        setSearchResults({
          title: filtered.filter(e => e.match_type === 'title'),
          detail: filtered.filter(e => e.match_type === 'detail'),
        });
      } catch (e) {
        console.error('Search failed:', e);
        setSearchResults({ title: [], detail: [] });
        setError('Suche fehlgeschlagen.');
      } finally {
        setSearchLoading(false);
      }
    }, SEARCH_DEBOUNCE_MS);
  }

  function clearSearch() {
    setSearchQuery('');
    setSearchResults(null);
    setSearchLoading(false);
    clearTimeout(searchTimeout);
  }

  // -- Source filter helpers -------------------------------------------------

  function toggleSource(name: string) {
    setEnabledSources(prev => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }

  // -- Lifecycle ------------------------------------------------------------

  onMount(async () => {
    await fetchSources();
    await loadNextBatch();
    setLoading(false);
  });

  // If the filtered results don't fill the viewport, keep loading
  createEffect(() => {
    filteredDayGroups(); // track changes
    if (loading() || loadingMore() || loadingExtended() || reachedEnd()) return;

    requestAnimationFrame(() => {
      if (document.body.offsetHeight <= window.innerHeight + 200) {
        loadNextBatch();
      }
    });
  });

  // Infinite scroll
  function handleScroll() {
    setShowFab(window.scrollY > SCROLL_FAB_THRESHOLD);

    const nearBottom =
      window.innerHeight + window.scrollY >= document.body.offsetHeight - SCROLL_LOAD_THRESHOLD;
    if (nearBottom && !loadingMore() && !loading() && !reachedEnd()) {
      loadNextBatch();
    }
  }

  onMount(() => window.addEventListener('scroll', handleScroll, { passive: true }));
  onCleanup(() => window.removeEventListener('scroll', handleScroll));

  // -- Sidebar (shared between desktop and mobile drawer) -------------------

  function SidebarContent() {
    return (
      <>
        {/* Search */}
        <h2 class="text-base font-semibold mb-3">Suche</h2>
        <div class="relative">
          <input
            type="text"
            value={searchQuery()}
            onInput={(e) => handleSearch(e.currentTarget.value)}
            placeholder="Veranstaltungen suchen..."
            class="w-full p-2 pr-8 border border-[var(--border-color)] rounded-md font-[inherit]"
          />
          <Show when={searchQuery()}>
            <button
              onClick={clearSearch}
              class="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-main)] bg-transparent border-none cursor-pointer text-lg leading-none"
              aria-label="Suche löschen"
            >
              &times;
            </button>
          </Show>
        </div>

        <hr class="border-t border-[var(--border-color)] my-6" />

        {/* Date picker */}
        <h2 class="text-base font-semibold mb-3">Datum wählen</h2>
        <input
          type="date"
          value={feedStartDate()}
          onChange={(e) => jumpToDate(e.currentTarget.value)}
          class="w-full p-2 border border-[var(--border-color)] rounded-md font-[inherit]"
        />

        <hr class="border-t border-[var(--border-color)] my-6" />

        {/* Source filters */}
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-base font-semibold">Quellen</h2>
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
          {/* Uncategorized sources */}
          <For each={knownSources()
            .filter(s => !s.category)
            .sort((a, b) => (a.display_name || a.name).localeCompare(b.display_name || b.name))}
          >
            {(source) => <SourceCheckbox source={source} />}
          </For>

          {/* Categorized sources, grouped by category */}
          <For each={sortedCategories()}>
            {(category) => <CategoryGroup category={category} />}
          </For>
        </ul>

        <hr class="border-t border-[var(--border-color)] my-6" />

        {/* About */}
        <h2 class="text-base font-semibold mb-2">Über</h2>
        <p class="text-sm text-[var(--text-muted)] leading-relaxed">
          Diese Seite sammelt automatisch Veranstaltungen aus den oben aufgeführten
          Quellen im Kanton Uri. Für verbindliche Angaben zu Veranstaltungen gelten
          die Originalwebseiten der jeweiligen Quellen.
          <br /><br />
          Einträge mit dem Hinweis{' '}
          <span class="inline-flex items-center gap-1 text-[0.7rem] font-medium px-1.5 py-0.5 rounded-md bg-[var(--border-color)] text-[var(--text-muted)]">
            KI-ergänzt
          </span>{' '}
          wurden mithilfe von künstlicher Intelligenz ergänzt.
          <br /><br />
          Wir fügen laufend neue Quellen hinzu und hoffen, dass diese Seite für die
          Region nützlich wird.
        </p>

        <hr class="border-t border-[var(--border-color)] my-6" />

        {/* Admin link */}
        <h2 class="text-base font-semibold mb-3">Quelldaten</h2>
        <a
          href="/admin"
          class="text-sm font-medium text-[var(--alpine-blue)] hover:underline"
        >
          Scraping-Status anzeigen &rarr;
        </a>
      </>
    );
  }

  /** A single source checkbox with icon. */
  function SourceCheckbox(props: { source: SourceInfo }) {
    return (
      <li>
        <label class="flex items-center gap-2 cursor-pointer text-[0.95rem]">
          <input
            type="checkbox"
            checked={enabledSources().has(props.source.name)}
            onChange={() => toggleSource(props.source.name)}
            class="accent-[var(--alpine-blue)]"
          />
          <Show when={getSourceIcon(props.source.icon_filename)}>
            <img
              alt=""
              class="w-5 h-5 rounded object-cover"
              // ref pattern: onError doesn't fire for images that fail before hydration
              ref={(el) => {
                el.onerror = () => el.remove();
                el.src = getSourceIcon(props.source.icon_filename)!;
              }}
            />
          </Show>
          {props.source.display_name || props.source.name}
        </label>
      </li>
    );
  }

  /** Category header with indeterminate checkbox + member list. */
  function CategoryGroup(props: { category: string }) {
    const members = () =>
      knownSources()
        .filter(s => s.category === props.category)
        .sort((a, b) => (a.display_name || a.name).localeCompare(b.display_name || b.name));

    const allChecked = () => members().every(s => enabledSources().has(s.name));
    const someChecked = () => members().some(s => enabledSources().has(s.name));

    const toggleCategory = () => {
      setEnabledSources(prev => {
        const next = new Set(prev);
        const action = allChecked() ? 'delete' : 'add';
        members().forEach(s => next[action](s.name));
        return next;
      });
    };

    return (
      <li class="mt-3">
        <label class="flex items-center gap-2 cursor-pointer text-[0.95rem] font-medium text-[var(--text-muted)]">
          <input
            type="checkbox"
            checked={allChecked()}
            ref={(el) => {
              setTimeout(() => (el.indeterminate = someChecked() && !allChecked()), 0);
            }}
            onChange={toggleCategory}
            class="accent-[var(--alpine-blue)]"
          />
          {props.category}
        </label>
        <ul class="list-none ml-6 mt-1 space-y-1">
          <For each={members()}>
            {(source) => <SourceCheckbox source={source} />}
          </For>
        </ul>
      </li>
    );
  }

  /** Categories sorted in display order. */
  /** Sort order for categories — unlisted ones fall to the bottom. */
  const sortedCategories = () => {
    const order = ['Organisationen', 'Gemeinden', 'Schulen', 'Kirchen'];
    const cats = [...new Set(knownSources().filter(s => s.category).map(s => s.category!))];
    return cats.sort((a, b) => {
      const ia = order.indexOf(a);
      const ib = order.indexOf(b);
      return (ia === -1 ? order.length : ia) - (ib === -1 ? order.length : ib);
    });
  };

  // -- Render ---------------------------------------------------------------

  return (
    <>
      {/* Mobile-only sticky header */}
      <Header onToggleFilters={() => setShowFilters(!showFilters())} filtersOpen={showFilters()} />

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
        {/* Sidebar (desktop) */}
        <aside class="w-[280px] shrink-0 max-md:hidden">
          <div class="sticky top-8 max-h-[calc(100vh-4rem)] overflow-y-auto bg-[var(--card-bg)] p-6 rounded-xl shadow-sm border border-[var(--border-color)]">
            <SidebarContent />
          </div>
        </aside>

        {/* Event feed */}
        <main class="grow min-w-0">
          {/* Error banner */}
          <Show when={error()}>
            <div class="mb-4 p-4 rounded-lg bg-red-50 border border-red-200 flex items-center justify-between" aria-live="assertive">
              <p class="text-red-800 text-sm">{error()}</p>
              <button
                onClick={() => { setError(null); loadNextBatch(); }}
                class="text-sm font-medium text-red-700 hover:text-red-900 bg-transparent border-none cursor-pointer whitespace-nowrap ml-4"
              >
                Erneut versuchen
              </button>
            </div>
          </Show>

          <Show
            when={!loading()}
            fallback={<p class="text-[var(--text-muted)] text-center py-12" aria-live="polite">Laden...</p>}
          >
            {/* Search results */}
            <Show when={searchQuery().length >= 2}>
              <Show
                when={!searchLoading()}
                fallback={<p class="text-[var(--text-muted)] text-center py-12" aria-live="polite">Suche...</p>}
              >
                <Show
                  when={searchResults()}
                  fallback={
                    <div class="text-center py-16">
                      <p class="text-[var(--text-muted)] text-lg">Keine Treffer gefunden.</p>
                    </div>
                  }
                >
                  {(results) => (
                    <>
                      <Show when={results().title.length > 0}>
                        <SearchSection title="Beste Treffer" events={results().title} />
                      </Show>
                      <Show when={results().detail.length > 0}>
                        <SearchSection title="Weitere Treffer" events={results().detail} />
                      </Show>
                      <Show when={results().title.length === 0 && results().detail.length === 0}>
                        <div class="text-center py-16">
                          <p class="text-[var(--text-muted)] text-lg">Keine Treffer gefunden.</p>
                        </div>
                      </Show>
                    </>
                  )}
                </Show>
              </Show>
            </Show>

            {/* Date-grouped event feed */}
            <Show when={searchQuery().length < 2}>
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

              {/* Empty state */}
              <Show when={filteredDayGroups().length === 0 && !loading() && !loadingMore()}>
                <div class="text-center py-16">
                  <img src="/uri-lake-drawing.png" alt="Uri Berge" class="w-full mb-6 opacity-60" />
                  <p class="text-[var(--text-muted)] text-lg">
                    Keine Veranstaltungen gefunden. Wie wärs mit einem Ausflug in die Berge?
                  </p>
                </div>
              </Show>

              {/* Loading indicator */}
              <Show when={loadingMore() || loadingExtended()}>
                <p class="text-[var(--text-muted)] text-center py-8">Mehr laden...</p>
              </Show>

              {/* End of feed — offer extended load */}
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
          </Show>
        </main>
      </div>

      {/* Scroll-to-top FAB */}
      <Show when={showFab()}>
        <button
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
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

// ---------------------------------------------------------------------------
// Shared sub-components
// ---------------------------------------------------------------------------

/** A titled section of search results. */
function SearchSection(props: { title: string; events: Event[] }) {
  return (
    <div class="mb-8">
      <h3 class="sticky top-0 max-md:top-[49px] z-10 bg-[var(--bg-color)]/90 backdrop-blur-sm py-4 text-xl font-semibold border-b-2 border-[var(--border-color)] mb-4">
        {props.title}
      </h3>
      <div class="flex flex-col gap-4">
        <For each={props.events}>
          {(event) => <Card event={event} showDate={true} />}
        </For>
      </div>
    </div>
  );
}

export default App;
