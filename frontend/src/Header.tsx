import type { Component } from 'solid-js';

type HeaderProps = {
  onToggleFilters: () => void;
};

const Header: Component<HeaderProps> = (props) => {
  return (
    <header class="hidden max-md:flex justify-between items-center px-4 py-3 bg-[var(--card-bg)] border-b border-[var(--border-color)] sticky top-0 z-50">
      <h1 class="text-lg font-bold">Events in Uri</h1>
      <button
        onClick={props.onToggleFilters}
        class="text-sm font-medium px-3 py-1.5 border border-[var(--border-color)] rounded-md text-[var(--text-muted)] hover:text-[var(--text-main)] hover:border-[var(--text-muted)] transition-colors"
      >
        Filter
      </button>
    </header>
  );
};

export default Header;
