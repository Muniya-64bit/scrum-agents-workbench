import { ApiError, UNAUTHORIZED_EVENT, api, download, getToken, setToken, streamUrl } from "./client";
import { artifact, burndown, metrics, traceRows } from "../test/fixtures";
import { mockApi } from "../test/utils";

describe("api client", () => {
  it("calls the API through the /api prefix", async () => {
    const calls = mockApi({ "GET /projects": [] });
    await expect(api.listProjects()).resolves.toEqual([]);
    expect(calls).toEqual([{ method: "GET", path: "/projects", body: undefined }]);
  });

  it("turns FastAPI error details into ApiError messages", async () => {
    mockApi({
      "POST /projects/1/advance": () => ({
        status: 409,
        body: { detail: "Awaiting human approval; call approve() first" },
      }),
    });
    const err = await api.advance(1).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 409, message: "Awaiting human approval; call approve() first" });
  });

  it("uses the first message of a validation error", async () => {
    mockApi({
      "PATCH /tasks/1": () => ({ status: 422, body: { detail: [{ msg: "Input should be 'todo'" }] } }),
    });
    await expect(api.updateTask(1, "done")).rejects.toThrow("Input should be 'todo'");
  });

  it("explains when the backend is not running", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.listProjects()).rejects.toThrow(/Cannot reach the API/);
  });

  it("reads metrics, burndown, traceability and artifacts", async () => {
    const calls = mockApi({
      "GET /projects/1/metrics": metrics,
      "GET /sprints/6/burndown": burndown,
      "GET /projects/1/traceability": traceRows,
      "GET /artifacts/2": artifact,
    });
    await expect(api.metrics(1)).resolves.toEqual(metrics);
    await expect(api.burndown(6)).resolves.toEqual(burndown);
    await expect(api.traceability(1)).resolves.toEqual(traceRows);
    await expect(api.artifact(2)).resolves.toEqual(artifact);
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "GET /projects/1/metrics",
      "GET /sprints/6/burndown",
      "GET /projects/1/traceability",
      "GET /artifacts/2",
    ]);
  });
});


describe("api token", () => {
  afterEach(() => {
    setToken("");
    vi.unstubAllGlobals();
  });

  it("sends no authorization header without a token", async () => {
    const fetchMock = vi.fn(async () => new Response("[]"));
    vi.stubGlobal("fetch", fetchMock);
    await api.listProjects();
    const headers = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].headers as Record<string, string>;
    expect(headers.authorization).toBeUndefined();
  });

  it("sends the stored token as a bearer token", async () => {
    setToken("s3cret");
    const fetchMock = vi.fn(async () => new Response("[]"));
    vi.stubGlobal("fetch", fetchMock);
    await api.listProjects();
    const headers = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].headers as Record<string, string>;
    expect(headers.authorization).toBe("Bearer s3cret");
    expect(getToken()).toBe("s3cret");
  });

  it("asks for a token when the API answers 401", async () => {
    mockApi({ "GET /projects": () => ({ status: 401, body: { detail: "A valid API token is required" } }) });
    const seen = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, seen);
    const err = await api.listProjects().catch((e) => e);
    window.removeEventListener(UNAUTHORIZED_EVENT, seen);
    expect(err).toMatchObject({ status: 401, message: "A valid API token is required" });
    expect(seen).toHaveBeenCalledTimes(1);
  });

  it("puts the token in the event stream URL, which cannot send headers", () => {
    expect(streamUrl(3, 9)).toBe("/api/projects/3/stream?after=9");
    setToken("a b&c");
    expect(streamUrl(3, 9)).toBe("/api/projects/3/stream?after=9&token=a%20b%26c");
  });

  it("forgets the token when it is cleared", () => {
    setToken("x");
    setToken("");
    expect(getToken()).toBe("");
  });
});

describe("download", () => {
  afterEach(() => {
    setToken("");
    vi.unstubAllGlobals();
  });

  function stubBrowser() {
    const create = vi.fn(() => "blob:report");
    const revoke = vi.fn();
    vi.stubGlobal("URL", { createObjectURL: create, revokeObjectURL: revoke });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    return { create, revoke, click };
  }

  it("fetches the file with the token and saves it under the given name", async () => {
    setToken("s3cret");
    const { create, revoke, click } = stubBrowser();
    const fetchMock = vi.fn(async () => new Response("# report"));
    vi.stubGlobal("fetch", fetchMock);

    await download("/projects/1/report", "todo-report.md");

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/projects/1/report");
    expect((init.headers as Record<string, string>).authorization).toBe("Bearer s3cret");
    expect(create).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(revoke).toHaveBeenCalledWith("blob:report");
    expect(document.querySelector("a[download]")).toBeNull(); // the link is removed again
    click.mockRestore();
  });

  it("explains a refused download", async () => {
    stubBrowser();
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "project not found" }), { status: 404 })));
    await expect(download("/projects/9/export", "x.zip")).rejects.toMatchObject({
      status: 404,
      message: "project not found",
    });
  });

  it("asks for a token when a download is refused with 401", async () => {
    stubBrowser();
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "A valid API token is required" }), { status: 401 })));
    const seen = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, seen);
    await download("/projects/1/export", "x.zip").catch(() => {});
    window.removeEventListener(UNAUTHORIZED_EVENT, seen);
    expect(seen).toHaveBeenCalledTimes(1);
  });
});
