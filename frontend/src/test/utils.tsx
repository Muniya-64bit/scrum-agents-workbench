import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "../App";
import { ToastProvider } from "../components/Toast";

type Handler = (body: unknown) => { status?: number; body: unknown };
export type Routes = Record<string, Handler | unknown>;

/** Replace fetch with a fake API. Keys are "METHOD /path" (path without /api and query). */
export function mockApi(routes: Routes) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const fetchMock = vi.fn(async (url: string, init: RequestInit = {}) => {
    const method = init.method ?? "GET";
    const path = url.replace(/^\/api/, "").split("?")[0];
    const body = init.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, path, body });
    const route = routes[`${method} ${path}`];
    if (route === undefined) {
      return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
    }
    const res = typeof route === "function" ? (route as Handler)(body) : { body: route };
    return new Response(JSON.stringify(res.body), { status: res.status ?? 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

export function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ToastProvider>
        <App />
      </ToastProvider>
    </MemoryRouter>,
  );
}
