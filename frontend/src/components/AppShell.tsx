import { useState } from "react";
import { NavLink, Outlet, useLocation, useMatch } from "react-router-dom";

import { api } from "../api/client";
import { applyTheme, effectiveTheme, type Theme } from "../lib/theme";
import { useOnProjectsChanged } from "../lib/projectsChanged";
import { usePolling } from "../lib/usePolling";
import { useResource } from "../lib/useResource";
import {
  IconActivity,
  IconBoard,
  IconChart,
  IconFolder,
  IconInbox,
  IconLink,
  IconList,
  IconMoon,
  IconSun,
} from "./icons";

/** Sidebar + main area. On narrow screens the sidebar becomes a top bar. */
export function AppShell() {
  const match = useMatch("/projects/:projectId/*");
  const projectId = match?.params.projectId;
  const location = useLocation();
  // Pending approvals across projects, refreshed on navigation and every 10 s.
  const projects = useResource(() => api.listProjects(), [location.pathname]);
  usePolling(projects.reload, 10_000);
  useOnProjectsChanged(projects.reload);
  const waiting = projects.data?.filter((p) => p.awaiting_approval).length ?? 0;

  return (
    <div className="shell">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <aside className="sidebar">
        <NavLink to="/" className="brand">
          <img src="/favicon.svg" alt="" width={24} height={24} />
          <span>Scrum Workbench</span>
        </NavLink>
        <nav className="nav" aria-label="Main">
          <NavLink to="/" end className="nav-link">
            <IconFolder /> <span>Projects</span>
          </NavLink>
          <NavLink to="/inbox" className="nav-link">
            <IconInbox /> <span>Inbox</span>
            {waiting > 0 && (
              <span className="nav-count" aria-label={`${waiting} waiting for approval`}>
                {waiting}
              </span>
            )}
          </NavLink>
          {projectId && (
            <>
              <div className="nav-section">Project</div>
              <NavLink to={`/projects/${projectId}/backlog`} className="nav-link">
                <IconList /> <span>Backlog</span>
              </NavLink>
              <NavLink to={`/projects/${projectId}/board`} className="nav-link">
                <IconBoard /> <span>Sprint board</span>
              </NavLink>
              <NavLink to={`/projects/${projectId}/activity`} className="nav-link">
                <IconActivity /> <span>Activity</span>
              </NavLink>
              <NavLink to={`/projects/${projectId}/metrics`} className="nav-link">
                <IconChart /> <span>Metrics</span>
              </NavLink>
              <NavLink to={`/projects/${projectId}/traceability`} className="nav-link">
                <IconLink /> <span>Traceability</span>
              </NavLink>
            </>
          )}
        </nav>
        <ThemeToggle />
      </aside>
      <main id="main" className="main">
        <Outlet />
      </main>
    </div>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(effectiveTheme);
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => {
        applyTheme(next);
        setTheme(next);
      }}
      aria-label={`Switch to ${next} mode`}
    >
      {theme === "dark" ? <IconSun /> : <IconMoon />}
      <span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>
    </button>
  );
}
