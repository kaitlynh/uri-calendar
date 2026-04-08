import { createResource, For, Show, type Component } from 'solid-js';

const API_BASE = '/api';

type SourceStatus = {
  source_name: string;
  base_url: string;
  event_count: number;
  last_extracted_at: string | null;
  latest_event_date: string | null;
  earliest_event_date: string | null;
};

function formatDateTime(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('de-CH', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—';
  return new Date(dateStr + 'T00:00:00').toLocaleDateString('de-CH', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

/** Returns how stale a scrape is: fresh (<6h), stale (6-48h), or old (>48h / never). */
function freshnessStatus(lastExtracted: string | null): 'fresh' | 'stale' | 'old' {
  if (!lastExtracted) return 'old';
  const hoursAgo = (Date.now() - new Date(lastExtracted).getTime()) / 3_600_000;
  if (hoursAgo < 6) return 'fresh';
  if (hoursAgo < 48) return 'stale';
  return 'old';
}

const STATUS_STYLES = {
  fresh: { dot: 'bg-green-500', badge: 'bg-green-50 text-green-700 border-green-200', label: 'Aktuell' },
  stale: { dot: 'bg-yellow-500', badge: 'bg-yellow-50 text-yellow-700 border-yellow-200', label: 'Veraltet' },
  old:   { dot: 'bg-red-500',   badge: 'bg-red-50 text-red-700 border-red-200',       label: 'Fehlt' },
};

const Admin: Component = () => {
  const [status] = createResource<SourceStatus[]>(() =>
    fetch(`${API_BASE}/admin/scraping-status`).then(r => r.json())
  );

  return (
    <div class="min-h-screen bg-[var(--bg-color)]">
      {/* Header */}
      <div class="border-b border-[var(--border-color)] bg-[var(--card-bg)]">
        <div class="max-w-[1200px] mx-auto px-8 py-4 flex items-center gap-4 max-md:px-4">
          <a
            href="/"
            class="text-[var(--text-muted)] hover:text-[var(--text-main)] text-sm transition-colors"
          >
            ← Zurück
          </a>
          <h1 class="text-xl font-semibold">Admin — Scraping Status</h1>
        </div>
      </div>

      <div class="max-w-[1200px] mx-auto px-8 py-8 max-md:px-4">
        {/* Summary bar */}
        <Show when={status()}>
          {(data) => {
            const total = data().reduce((s, r) => s + r.event_count, 0);
            const fresh = data().filter(r => freshnessStatus(r.last_extracted_at) === 'fresh').length;
            const stale = data().filter(r => freshnessStatus(r.last_extracted_at) === 'stale').length;
            const old   = data().filter(r => freshnessStatus(r.last_extracted_at) === 'old').length;
            return (
              <div class="grid grid-cols-4 gap-4 mb-8 max-md:grid-cols-2">
                <div class="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-xl p-5">
                  <p class="text-[var(--text-muted)] text-sm mb-1">Quellen gesamt</p>
                  <p class="text-2xl font-bold">{data().length}</p>
                </div>
                <div class="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-xl p-5">
                  <p class="text-[var(--text-muted)] text-sm mb-1">Events gesamt</p>
                  <p class="text-2xl font-bold">{total.toLocaleString('de-CH')}</p>
                </div>
                <div class="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-xl p-5">
                  <p class="text-[var(--text-muted)] text-sm mb-1">Aktuell (&lt;6h)</p>
                  <p class="text-2xl font-bold text-green-600">{fresh}</p>
                </div>
                <div class="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-xl p-5">
                  <p class="text-[var(--text-muted)] text-sm mb-1">Veraltet / Fehlt</p>
                  <p class="text-2xl font-bold text-red-600">{stale + old}</p>
                </div>
              </div>
            );
          }}
        </Show>

        {/* Source table */}
        <div class="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-xl overflow-hidden">
          <Show when={status.loading}>
            <p class="text-[var(--text-muted)] text-center py-12">Laden...</p>
          </Show>

          <Show when={status.error}>
            <p class="text-red-600 text-center py-12">Fehler beim Laden der Daten.</p>
          </Show>

          <Show when={status()}>
            {(data) => (
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b border-[var(--border-color)] text-[var(--text-muted)] text-left">
                    <th class="px-6 py-3 font-medium">Quelle</th>
                    <th class="px-6 py-3 font-medium">Status</th>
                    <th class="px-6 py-3 font-medium">Letzter Scrape</th>
                    <th class="px-6 py-3 font-medium max-md:hidden">Frühestes Event</th>
                    <th class="px-6 py-3 font-medium max-md:hidden">Letztes Event</th>
                    <th class="px-6 py-3 font-medium text-right">Events</th>
                  </tr>
                </thead>
                <tbody>
                  <For each={data()}>
                    {(source, i) => {
                      const freshness = freshnessStatus(source.last_extracted_at);
                      const style = STATUS_STYLES[freshness];
                      return (
                        <tr class={`border-b border-[var(--border-color)] last:border-0 ${i() % 2 === 1 ? 'bg-[var(--bg-color)]/50' : ''}`}>
                          <td class="px-6 py-4">
                            <p class="font-medium text-[var(--text-main)]">{source.source_name}</p>
                            <a
                              href={source.base_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              class="text-[var(--text-muted)] hover:text-[var(--alpine-blue)] truncate max-w-[200px] block transition-colors"
                            >
                              {source.base_url}
                            </a>
                          </td>
                          <td class="px-6 py-4">
                            <span class={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium ${style.badge}`}>
                              <span class={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
                              {style.label}
                            </span>
                          </td>
                          <td class="px-6 py-4 text-[var(--text-muted)]">
                            {formatDateTime(source.last_extracted_at)}
                          </td>
                          <td class="px-6 py-4 text-[var(--text-muted)] max-md:hidden">
                            {formatDate(source.earliest_event_date)}
                          </td>
                          <td class="px-6 py-4 text-[var(--text-muted)] max-md:hidden">
                            {formatDate(source.latest_event_date)}
                          </td>
                          <td class="px-6 py-4 text-right font-mono font-medium">
                            {source.event_count.toLocaleString('de-CH')}
                          </td>
                        </tr>
                      );
                    }}
                  </For>
                </tbody>
              </table>
            )}
          </Show>
        </div>

        <p class="text-[var(--text-muted)] text-xs mt-4">
          <span class="inline-flex items-center gap-1.5 mr-4"><span class="w-2 h-2 rounded-full bg-green-500 inline-block" /> Aktuell: letzter Scrape vor weniger als 6 Stunden</span>
          <span class="inline-flex items-center gap-1.5 mr-4"><span class="w-2 h-2 rounded-full bg-yellow-500 inline-block" /> Veraltet: letzter Scrape vor 6–48 Stunden</span>
          <span class="inline-flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-red-500 inline-block" /> Fehlt: noch nie gescrapt oder vor mehr als 48 Stunden</span>
        </p>
      </div>
    </div>
  );
};

export default Admin;
