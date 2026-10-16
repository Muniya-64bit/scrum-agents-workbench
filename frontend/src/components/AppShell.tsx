import { useState } from "react";
import { NavLink, Outlet, useMatch } from "react-router-dom";

import { applyTheme, effectiveTheme, type Theme } from "../lib/theme";
import { IconBoard, IconFolder, IconList, IconMoon, IconSun } from "./icons";

/** Sidebar + main area. On narrow screens the sidebar becomes a top bar. */
export function AppShell() {
  const match = useMatch("/projects/:projectId/*");
  const projectId = match?.params.projectId;

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
          {projectId && (
            <>
              <div className="nav-section">Project</div>
              <NavLink to={`/projects/${projectId}/backlog`} className="nav-link">
                <IconList /> <span>Backlog</span>
              </NavLink>
              <NavLink to={`/projects/${projectId}/board`} className="nav-link">
                <IconBoard /> <span>Sprint board</span>
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
