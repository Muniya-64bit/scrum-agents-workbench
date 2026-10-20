import type {
  ActivityEvent,
  Artifact,
  Backlog,
  Burndown,
  ImprovementRow,
  ProcessInfo,
  Project,
  ProjectMetrics,
  Release,
  ReleaseCheck,
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

const TOKEN_KEY = "workbench-api-token";

/** Fired when the API answers 401, so the app can ask for a token. */
export const UNAUTHORIZED_EVENT = "workbench:unauthorized";

/** The API token the person typed in, kept in this browser only ("" when there is none). */
export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setToken(token: string): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // storage is blocked: the token only lasts until the page is reloaded
  }
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { authorization: `Bearer ${token}` } : {};
}

async function fail(res: Response): Promise<never> {
  if (res.status === 401) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  throw new ApiError(await errorMessage(res), res.status);
}

async function send(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(API_BASE + path, init);
  } catch {
    throw new ApiError("Cannot reach the API. Is the backend running on port 8000?", 0);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await send(path, {
    ...init,
    headers: { "content-type": "application/json", ...authHeaders(), ...init.headers },
  });
  if (!res.ok) return fail(res);
  return (await res.json()) as T;
}

/** Download a file from the API (it needs the token, so a plain link cannot do it). */
export async function download(path: string, filename: string): Promise<void> {
  const res = await send(path, { headers: authHeaders() });
  if (!res.ok) return fail(res);
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
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
  requestMaintenance: (id: number, body: { title: string; description: string; points: number }) =>
    request<Project>(`/projects/${id}/maintenance`, { method: "POST", body: JSON.stringify(body) }),
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
  releases: (id: number) => request<Release[]>(`/projects/${id}/releases`),
  releaseChecks: (id: number) => request<ReleaseCheck[]>(`/projects/${id}/release-checks`),
  process: (id: number) => request<ProcessInfo>(`/projects/${id}/process`),
  improvement: (id: number) => request<ImprovementRow[]>(`/projects/${id}/improvement`),
};

/** URL for the live event stream (Server-Sent Events). */
export function streamUrl(projectId: number, after: number): string {
  // an EventSource cannot send headers, so the token goes in the query
  const token = getToken();
  const auth = token ? `&token=${encodeURIComponent(token)}` : "";
  return `${API_BASE}/projects/${projectId}/stream?after=${after}${auth}`;
}
