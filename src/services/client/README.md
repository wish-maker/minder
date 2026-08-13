# minder-client

Minder's **own management SPA** — the one non-Python service (`minder.bundle=core`).
React 18 + Vite + React Router 7 + Tailwind 4, ~6.3k LOC. Served on `:8009`
(loopback + Traefik `client.minder.local`, forward-auth gated).

> Distinct from **OpenWebUI** (that's the chat UI). This is the plugin-config /
> knowledge-base / pipeline / model / graph / voice **management** UI. It talks to
> the api-gateway (`:8000`) through a thin typed fetch layer (`src/lib/api.ts`);
> it never calls downstream services directly.

## Run / check

```bash
npm install
npm run dev          # Vite dev server (localhost:5173)

# The CI-mirroring checks (green locally ⇒ green in the "Frontend Lint &
# Typecheck (client)" job). Run all four before pushing a client PR:
npm run typecheck    # tsc -b --noEmit
npm run lint         # eslint .
npm run test         # vitest run  (jsdom; pure-logic + hook/component tests)
npm run build        # tsc -b && vite build
```

## Build-time configuration (`VITE_*`)

`VITE_*` vars are baked in at **image build time** (Vite convention), not read at
container start — changing one means **rebuilding the image**, not just
restarting. Set via the compose `build.args` (which read `CLIENT_*` from `.env`);
each also has a matching `ARG` default in the `Dockerfile`.

| Var | Default | Meaning |
|-----|---------|---------|
| `VITE_API_BASE_URL` | `http://localhost:8000` | api-gateway base for all `fetch()` calls. Works over the direct-port bypass. |
| `VITE_OIDC_LOGIN_URL` | *(empty)* | SSO login entry (full-page nav into Authelia's OIDC flow). **No default** — only a real Traefik + DNS + TLS deployment has it. When unset, the SSO button is **hidden** and local login is the only option (over localhost the `*.minder.local` host can't resolve, so a baked URL would dead-end). |
| `VITE_AUTHELIA_PORTAL_URL` | *(empty)* | Authelia self-service portal link on the Settings page. Same opt-in rule; plain text shown when unset. |

> Both `*.minder.local` URLs are empty-by-default on purpose (a recurring
> localhost dead-link class): render the link only when the deployment configures
> it. See `src/lib/api.ts`.

## Layout

```
src/
├── main.tsx                 # entry: BrowserRouter + <App/>
├── App.tsx                  # shell (sidebar/header) + Routes, wrapped in <ErrorBoundary>
├── pages/                   # one component per route (14 pages)
├── components/              # shared UI building blocks (below)
└── lib/                     # framework-agnostic helpers + hooks (below)
```

### `components/` — shared UI

- **`ErrorBoundary.tsx`** — top-level render-crash guard (class component; no hook
  equivalent). Wraps `<Routes>` keyed by pathname, so any page throw shows a
  recoverable "Try again / Reload" fallback instead of blanking the app.
- **`StatusLine.tsx`** — accessible status/error line (aria-live: polite for info,
  assertive for errors). The standard way pages surface load/mutation status.
- **`EmptyState.tsx`** — the "nothing here yet" line for empty lists (one voice).
- **`PageHeader.tsx`**, **`InfoCallout.tsx`**, **`ConfirmDialog.tsx`** (via
  `useConfirm()`), **`Sidebar.tsx`**, **`UserMenu.tsx`**.

### `lib/` — helpers & hooks

- **`api.ts`** — `apiFetch<T>` / `apiFetchBlob` (bearer injection, JSON/error
  handling, optional `AbortSignal`), `ApiError`, `friendlyErrorMessage`, and the
  `Paginated<T>` list envelope (`{items,total,limit,offset}`, matches the backend
  `shared.models.PaginatedList` — #501).
- **`auth.tsx`** — `AuthProvider` / `useAuth` (JWT in sessionStorage; SSO callback
  + local login). Pure claim helpers live in **`jwt.ts`** (`decodeJwtClaims`,
  `isExpired`) so they're testable without rendering the provider.
- **`useAsyncResource.ts`** — declarative data-fetch hook: AbortController
  cancellation + **stale-response race guard** + opt-in `timeoutMs`. Replaces the
  hand-rolled `data/status/isError/loadX/useEffect` boilerplate. Adopt it when a
  page has deps-driven reloads or already re-fetches after mutations; skip it for
  a mount-only load that uses local optimistic add/filter (reload would only add
  round-trips).
- **`usePaginatedList.ts`** — "load a page, then Load More" offset pagination for
  the marketplace catalog.
- **`ui.ts`** — Tailwind class constants (`inputClass`, `primaryButtonClass`,
  `cardClass`, `badgeClass`, …), the `badgeTone` {success,warn,danger} palette,
  `confidenceBadgeColor`, `fieldHintClass`, `mutedTextClass`. Change a style once
  here instead of N pages.
- **`stt.ts`** (`matchingSttLanguage`), **`browser.ts`**, **`links.ts`**
  (`openWebUiUrl`), **`useDebouncedValue.ts`**, **`useElapsedSeconds.ts`**.

## Tests

Vitest (jsdom). Currently **pure logic + hooks + one component** (`api`, `jwt`,
`stt`, `ui`, `browser`, `usePaginatedList`, `useAsyncResource`, `ErrorBoundary`).
The config is intentionally plugin-less (esbuild transforms JSX); component/hook
tests via `@testing-library/react` work, but add an explicit `cleanup()` in
`afterEach` — there's no global setup file, so auto-cleanup isn't registered.
Fake-timer tests must use `vi.advanceTimersByTimeAsync` (not `waitFor`, which
deadlocks under fake timers).
