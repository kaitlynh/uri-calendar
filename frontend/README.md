# Frontend

SolidJS + Vite + Tailwind. Source lives in [src/](src/), tests in [src/__tests__/](src/__tests__/).

## Commands

```bash
npm install
npm run dev      # http://localhost:3000, proxies /api → https://urikalender.ch
npm run build    # outputs to dist/
npm test         # vitest + @solidjs/testing-library
```

## Entry points

- [src/App.tsx](src/App.tsx) — main calendar feed, search, filters, infinite scroll
- [src/Admin.tsx](src/Admin.tsx) — per-source scraping status dashboard at `/admin`
- [src/Card.tsx](src/Card.tsx) — event card, rendered for both mobile and desktop layouts
- [src/ics.ts](src/ics.ts) — ICS file generation and Google Calendar URL builder

The dev server routes `/` to `App` and `/admin` to `Admin` via a path check in [src/index.tsx](src/index.tsx:17). There is no client-side router.

## Dark mode

Handled via a `.dark` class on `<html>`. The class is applied synchronously from an inline `<script>` in [index.html](index.html:8) before hydration, which prevents a flash of the light theme on first paint. The in-app toggle writes to `localStorage`; the OS `prefers-color-scheme` is used as a fallback.

## Deployment

Built by GitHub Actions (see `.github/workflows/deploy.yml` at the repo root) and rsynced to the server's nginx document root. No build tooling runs on the server.
