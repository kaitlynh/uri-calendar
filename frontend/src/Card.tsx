import { createSignal, type Component } from 'solid-js';
import type { Event } from './event';
import { downloadICS, googleCalendarUrl } from './ics';
import { getSourceIcon } from './sources';

type EventProps = {
  event: Event;
};

/** Format "HH:MM:SS" → "HH:MM", or null if missing */
function formatTime(time: string | null | undefined): string | null {
  if (!time) return null;
  return time.slice(0, 5);
}

const Card: Component<EventProps> = (props) => {
  const [expanded, setExpanded] = createSignal(false);
  const time = () => formatTime(props.event.start_time);

  return (
    <article class="bg-[var(--card-bg)] rounded-xl border border-[var(--border-color)] shadow-[0_2px_4px_-1px_rgba(0,0,0,0.03)] flex flex-col transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_10px_15px_-3px_rgba(0,0,0,0.05)] overflow-hidden">

      {/* ── Mobile: icon + title top row ── */}
      <div class="hidden max-md:flex items-center gap-3 px-4 pt-4 pb-3 border-b border-[var(--border-color)]">
        {getSourceIcon(props.event.icon_filename) ? (
          <img
            src={getSourceIcon(props.event.icon_filename)}
            alt={props.event.source_name}
            class="w-8 h-8 rounded-lg object-cover bg-[var(--border-color)] shrink-0"
          />
        ) : (
          <div class="w-8 h-8 rounded-lg bg-[var(--border-color)] flex items-center justify-center text-[0.5rem] font-semibold text-[var(--text-muted)] shrink-0 text-center leading-tight">
            {props.event.base_url?.replace(/^https?:\/\//, '').replace(/\/$/, '') || props.event.source_name}
          </div>
        )}
        <div class="flex items-center gap-2 min-w-0">
          <h4 class="text-[1rem] font-semibold truncate">{props.event.event_title}</h4>
          {props.event.ai_flag && (
            <span class="inline-flex items-center gap-1 text-[0.7rem] font-medium px-1.5 py-0.5 rounded-md bg-[var(--border-color)] text-[var(--text-muted)] shrink-0">
              ✨ KI-ergänzt
            </span>
          )}
        </div>
      </div>

      {/* ── Main row: square icon + content ── */}
      <div class="flex max-md:flex-col">

        {/* Desktop: fixed square icon */}
        <div class="w-[156px] h-[156px] shrink-0 max-md:hidden">
          {getSourceIcon(props.event.icon_filename) ? (
            <img
              src={getSourceIcon(props.event.icon_filename)}
              alt={props.event.source_name}
              class="w-full h-full object-cover bg-[var(--border-color)]"
            />
          ) : (
            <div class="w-full h-full bg-[var(--border-color)] flex items-center justify-center text-xs font-semibold text-[var(--text-muted)] text-center leading-tight p-2">
              {props.event.base_url?.replace(/^https?:\/\//, '').replace(/\/$/, '') || props.event.source_name}
            </div>
          )}
        </div>

        {/* Content */}
        <div class="grow min-w-0 px-6 pt-3 pb-3 max-md:px-4 max-md:pt-3 max-md:pb-4">
          {/* Desktop: title */}
          <div class="flex items-center gap-2 mb-1 max-md:hidden">
            <h4 class="text-[1.15rem] font-semibold">{props.event.event_title}</h4>
            {props.event.ai_flag && (
              <span class="inline-flex items-center gap-1 text-[0.7rem] font-medium px-1.5 py-0.5 rounded-md bg-[var(--border-color)] text-[var(--text-muted)] shrink-0">
                ✨ KI-ergänzt
              </span>
            )}
          </div>

          {/* Source line */}
          <a
            href={props.event.base_url?.startsWith('http') ? props.event.base_url : `https://${props.event.base_url}`}
            target="_blank"
            rel="noopener noreferrer"
            class="text-[0.85rem] text-[var(--text-muted)] mb-1 hover:text-[var(--alpine-blue)] transition-colors block"
          >
            <span class="font-semibold">{props.event.display_name || props.event.source_name}</span>
            {props.event.source_name && (
              <span> | {props.event.source_name}</span>
            )}
          </a>

          {/* Time + location row */}
          <div class="flex items-center gap-3 text-[0.85rem] text-[var(--text-muted)]">
            {time() && (
              <>
                <span class="font-semibold text-[var(--text-main)]">🕐 {time()}</span>
                <span>·</span>
              </>
            )}
            <span>📍 {props.event.location || 'Kein Ort angegeben'}</span>
          </div>

          {/* Actions — always visible */}
          <div class="flex gap-3 items-center flex-wrap mt-4">
            <a
              href={props.event.source_url}
              target="_blank"
              rel="noopener noreferrer"
              class="bg-[var(--alpine-blue)] text-white px-4 py-2 rounded-md font-medium text-[0.9rem] no-underline transition-colors hover:bg-[var(--alpine-blue-hover)]"
            >
              Zum Event
            </a>
            <a
              href={googleCalendarUrl(props.event)}
              target="_blank"
              rel="noopener noreferrer"
              class="bg-transparent text-[var(--text-muted)] border border-[var(--border-color)] px-4 py-2 rounded-md font-medium text-[0.9rem] flex items-center gap-2 cursor-pointer transition-colors hover:text-[var(--text-main)] hover:border-[var(--text-muted)] no-underline"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              Google Calendar
            </a>
            <button
              onClick={() => downloadICS(props.event)}
              class="bg-transparent text-[var(--text-muted)] border border-[var(--border-color)] px-4 py-2 rounded-md font-medium text-[0.9rem] flex items-center gap-2 cursor-pointer transition-colors hover:text-[var(--text-main)] hover:border-[var(--text-muted)]"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/></svg>
              ICS
            </button>
          </div>
        </div>
      </div>

      {/* ── Expand bar: only if there's a description ── */}
      {props.event.description && (
        <div class="border-t border-[var(--border-color)]">
          {/* Expandable description */}
          <div
            class="grid transition-all duration-300 ease-in-out"
            style={{ 'grid-template-rows': expanded() ? '1fr' : '0fr' }}
          >
            <div class="overflow-hidden">
              <p class="text-[0.95rem] text-[var(--text-muted)] px-6 pt-4 pb-2 max-md:px-4">{props.event.description}</p>
            </div>
          </div>

          {/* Chevron toggle */}
          <button
            onClick={() => setExpanded(!expanded())}
            class="w-full flex justify-center cursor-pointer text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-color)] transition-colors py-1.5"
            aria-label={expanded() ? 'Weniger anzeigen' : 'Mehr anzeigen'}
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              class="transition-transform duration-300"
              style={{ transform: expanded() ? 'rotate(180deg)' : 'rotate(0deg)' }}
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
        </div>
      )}
    </article>
  );
};

export default Card;
