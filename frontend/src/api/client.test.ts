import { ApiError, api } from "./client";
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
