import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { IconFolder } from "./components/icons";
import { EmptyState } from "./components/ui";
import { ActivityPage } from "./pages/ActivityPage";
import { BacklogPage } from "./pages/BacklogPage";
import { BoardPage } from "./pages/BoardPage";
import { InboxPage } from "./pages/InboxPage";
import { ProjectLayout } from "./pages/ProjectLayout";
import { ProjectsPage } from "./pages/ProjectsPage";

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<ProjectsPage />} />
        <Route path="inbox" element={<InboxPage />} />
        <Route path="projects/:projectId" element={<ProjectLayout />}>
          <Route index element={<Navigate to="backlog" replace />} />
          <Route path="backlog" element={<BacklogPage />} />
          <Route path="board" element={<BoardPage />} />
          <Route path="activity" element={<ActivityPage />} />
        </Route>
        <Route
          path="*"
          element={
            <EmptyState icon={<IconFolder size={22} />} title="Page not found">
              That page does not exist. Pick a project from the sidebar.
            </EmptyState>
          }
        />
      </Route>
    </Routes>
  );
}
