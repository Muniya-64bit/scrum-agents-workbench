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
| `/projects/:id/activity` | Live activity feed with agent filters, and the approval card at a gate |
| `/projects/:id/metrics` | GQM dashboard: KPI tiles, burndown, velocity, quality, AI cost and the GQM goals ([metrics.md](metrics.md)) |
| `/projects/:id/traceability` | Story → design → code → tests matrix with results, gaps and an artifact viewer. Filters (`?sprint=`, `?status=`, `?gaps=1`) are kept in the URL |
| `/inbox` | Approval inbox: every project waiting at a gate, across projects |

Every project page shows the phase bar and the phase controls: **Start &lt;next phase&gt;**, or
**Approve / Reject** when the project waits at a gate.

On the board, drag a card to another column or use the status menu on the card (keyboard
friendly). The card moves at once; if saving fails it moves back and an error toast explains why.

## Live updates
Each project page opens one Server-Sent Events connection (`useEventStream`): it loads the history
from `GET /projects/{id}/events`, then listens on `/projects/{id}/stream?after=<last id>`. The
browser's `EventSource` reconnects by itself and resumes after the last event it saw.

- New events appear at the top of the Activity feed, with the agent's avatar and a readable sentence
  (`lib/events.ts` turns event kinds into text).
- Pages (backlog, board) reload shortly after a burst of events, so you see the agents' work
  without refreshing. Phase and gate events refresh the header and phase bar at once.
- While a phase runs, the header shows what the agents are doing right now.
- The sidebar's **Inbox** count updates as soon as a gate opens or is decided, and every 10 s.

## Approvals
At sprint planning and sprint review the project waits for a human. The approval card shows what
the agents produced (sprint goal, stories, points, tasks done), with **Approve** and **Reject…**.
Rejecting asks for an optional reason, which is saved as the message of the `rejected` event
(`POST /projects/{id}/approve?approved=false&comment=...`).

## Structure
```
frontend/src/
  api/          client.ts (typed fetch wrapper, ApiError), types.ts (mirrors workbench/api/views.py)
  components/   AppShell (sidebar), PhaseBar, ActivityFeed, ApprovalCard, Avatar, Toast,
                ArtifactDrawer (side panel with focus trap and Copy),
                ui.tsx (Button, Badge, states), icons
  components/charts/  ChartFrame (axes, ticks), BurndownChart, BarChart (SVG, no library)
  lib/          format.ts (pct, usd, tokens, delta, duration), scrum.ts (labels),
                events.ts (event text, times), useEventStream.ts (SSE),
                useResource.ts (data loading), usePolling.ts, projectsChanged.ts, theme.ts
  pages/        ProjectsPage, ProjectLayout (header, phase controls, live stream), BacklogPage,
                BoardPage, ActivityPage, MetricsPage, TraceabilityPage, InboxPage
  styles/       tokens.css (colors, light/dark), app.css
  test/         fake API (mockApi), fake EventSource, render helper, fixtures
```
When you change a response model in `workbench/api/views.py`, update `src/api/types.ts` too.

## Charts
The charts are plain SVG with no chart library. Each one has a title and description for screen
readers, points and bars can be reached with Tab and show a tooltip on focus or hover, and
colors come from the design tokens so light and dark mode both work. The burndown plots time
since the sprint started, or the step number when the sprint lasted less than a second (mock
runs). Change values and wording in `lib/format.ts`; the numbers come ready-made from the API.

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
