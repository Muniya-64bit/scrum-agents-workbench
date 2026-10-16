import type {
  ActivityEvent,
  Artifact,
  Backlog,
  Burndown,
  Project,
  ProjectMetrics,
  Sprint,
  SprintDetail,
  Task,
  TaskStatus,
  TraceRow,
} from "./types";

/** All requests go to /api; the Vite dev server proxies that to the FastAPI backend. */
export const API_BASE = "/api";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_BASE + path, {
      ...init,
      headers: { "content-type": "application/json", ...init.headers },
    });
  } catch {
    throw new ApiError("Cannot reach the API. Is the backend running on port 8000?", 0);
  }
  if (!res.ok) {
    throw new ApiError(await errorMessage(res), res.status);
  }
  return (await res.json()) as T;
}

/** FastAPI errors look like {"detail": "..."} or, for validation, {"detail": [{msg}]}. */
async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) return body.detail[0].msg;
  } catch {
    // not JSON; fall through
  }
  return `Request failed (${res.status})`;
}

export const api = {
  listProjects: () => request<Project[]>("/projects"),
  getProject: (id: number) => request<Project>(`/projects/${id}`),
  createProject: (name: string, idea: string) =>
    request<Project>("/projects", { method: "POST", body: JSON.stringify({ name, idea }) }),
  advance: (id: number) => request<Project>(`/projects/${id}/advance`, { method: "POST" }),
  approve: (id: number, approved: boolean, comment = "") =>
    request<Project>(
      `/projects/${id}/approve?approved=${approved}&comment=${encodeURIComponent(comment)}`,
      { method: "POST" },
    ),
  events: (id: number, after = 0) =>
    request<ActivityEvent[]>(`/projects/${id}/events?after=${after}`),

  backlog: (id: number) => request<Backlog>(`/projects/${id}/backlog`),
  sprints: (id: number) => request<Sprint[]>(`/projects/${id}/sprints`),
  sprint: (sprintId: number) => request<SprintDetail>(`/sprints/${sprintId}`),
  tasks: (id: number) => request<Task[]>(`/projects/${id}/tasks`),
  updateTask: (taskId: number, status: TaskStatus) =>
    request<Task>(`/tasks/${taskId}`, { method: "PATCH", body: JSON.stringify({ status }) }),

  burndown: (sprintId: number) => request<Burndown>(`/sprints/${sprintId}/burndown`),
  metrics: (id: number) => request<ProjectMetrics>(`/projects/${id}/metrics`),
  traceability: (id: number) => request<TraceRow[]>(`/projects/${id}/traceability`),
  artifact: (artifactId: number) => request<Artifact>(`/artifacts/${artifactId}`),
};

/** URL for the live event stream (Server-Sent Events). */
export function streamUrl(projectId: number, after: number): string {
  return `${API_BASE}/projects/${projectId}/stream?after=${after}`;
}
