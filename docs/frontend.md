# Web UI

React 19 + TypeScript, built with Vite. The code is in `frontend/`.

## Running it
```bash
make run        # terminal 1: API on :8000
make ui-setup   # once: npm ci
make seed       # optional: demo project with a backlog and a sprint board
make ui         # terminal 2: UI on http://localhost:5173
```
The UI calls `/api/...`. The Vite dev server forwards that to `http://localhost:8000`, so no CORS
setup is needed. Set `API_URL` to use a backend elsewhere: `API_URL=http://host:8000 npm run dev`.

| Command (in `frontend/`) | Purpose |
|---|---|
| `npm run dev` | Dev server with hot reload |
| `npm run typecheck` | TypeScript checks |
| `npm test` | Vitest + Testing Library |
| `npm run build` | Production build in `dist/` |

CI runs typecheck, tests and build on every pull request.

## Screens
| Route | Screen |
|---|---|
| `/` | Project list and the new-project form |
| `/projects/:id/backlog` | Vision, stats, epics and stories with Given/When/Then criteria |
| `/projects/:id/board` | Kanban board for the latest sprint (or every task before planning) |

Every project page shows the phase bar and the phase controls: **Start &lt;next phase&gt;**, or
**Approve / Reject** when the project waits at a gate.

On the board, drag a card to another column or use the status menu on the card (keyboard
friendly). The card moves at once; if saving fails it moves back and an error toast explains why.

## Structure
```
frontend/src/
  api/          client.ts (typed fetch wrapper, ApiError), types.ts (mirrors workbench/api/views.py)
  components/   AppShell (sidebar), PhaseBar, Toast, ui.tsx (Button, Badge, states), icons
  lib/          scrum.ts (phase/status/role labels), useResource.ts (data loading), theme.ts
  pages/        ProjectsPage, ProjectLayout (header + phase controls), BacklogPage, BoardPage
  styles/       tokens.css (colors, light/dark), app.css
  test/         fake API (mockApi), render helper, fixtures
```
When you change a response model in `workbench/api/views.py`, update `src/api/types.ts` too.

## Design
Neutral base in the style of Linear, status colors in the style of GitHub Primer, one indigo
accent. All colors are CSS variables in `src/styles/tokens.css`, defined for light and dark mode.
Dark mode follows the OS until the user picks one with the sidebar toggle.

| Token | Use |
|---|---|
| `--accent` `#5B5BD6` | Primary buttons, links, current phase |
| `--status-todo` / `doing` / `testing` / `done` | Board columns and status badges |
| `--danger` | Errors, P1 priority |
| `--role-<role>` | Agent role dots (Product Owner, Scrum Master, ...) |

Font: Inter (bundled with `@fontsource-variable/inter`, no external requests).
