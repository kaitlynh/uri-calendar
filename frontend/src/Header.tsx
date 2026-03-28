import type { Component } from 'solid-js';

type HeaderProps = {
  onToggleFilters: () => void;
};

const Header: Component<HeaderProps> = (props) => {
  return (
    <header class="hidden max-md:flex justify-between items-center px-4 py-3 bg-[var(--card-bg)] border-b border-[var(--border-color)] sticky top-0 z-50">
      <h1 class="text-lg font-bold">Veranstaltungen im Kanton Uri</h1>
      <div class="flex items-center gap-2">
        <a
          href="/admin"
          class="text-sm font-medium px-3 py-1.5 border border-[var(--border-color)] rounded-md text-[var(--text-muted)] hover:text-[var(--text-main)] hover:border-[var(--text-muted)] transition-colors"
        >
          Admin
        </a>
        <button
          onClick={props.onToggleFilters}
          class="text-sm font-medium px-3 py-1.5 border border-[var(--border-color)] rounded-md text-[var(--text-muted)] hover:text-[var(--text-main)] hover:border-[var(--text-muted)] transition-colors"
        >
          Filter
        </button>
      </div>
    </header>
  );
};

export default Header;
