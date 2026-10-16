import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { ActivityEvent } from "../api/types";
import { MockEventSource } from "../test/eventSource";
import { project, sprintDetail, sprint } from "../test/fixtures";
import { mockApi, renderApp } from "../test/utils";

const at = new Date().toISOString();
const history: ActivityEvent[] = [
  { id: 1, agent: "orchestrator", kind: "phase_started", message: "backlog", payload: {}, at },
  { id: 2, agent: "product_owner", kind: "story_created", message: "Create an item", payload: {}, at },
  { id: 3, agent: "developer", kind: "task_updated", message: "Build API -> doing", payload: {}, at },
];

const feedTexts = () => within(screen.getByRole("list", { name: "Activity" })).getAllByRole("listitem").map((li) => li.textContent);

describe("ActivityPage", () => {
  it("shows history newest first, then live events without reloading", async () => {
    mockApi({ "GET /projects/1": project, "GET /projects/1/events": history });
    renderApp("/projects/1/activity");

    expect(await screen.findByText(/Moved “Build API” to In progress/)).toBeInTheDocument();
    expect(feedTexts()[0]).toMatch(/Developer/);
    expect(feedTexts()[2]).toMatch(/Backlog phase/);
    expect(MockEventSource.latest().url).toBe("/api/projects/1/stream?after=3");

    act(() => MockEventSource.latest().open());
    expect(screen.getByRole("status")).toHaveTextContent("Live");
    act(() =>
      MockEventSource.latest().emit({
        id: 4, agent: "qa", kind: "bug_reported", message: "500 on empty title", payload: {}, at,
      }),
    );
    expect(feedTexts()[0]).toMatch(/QA.*Reported a bug: 500 on empty title/);
  });

  it("filters by agent", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /projects/1": project, "GET /projects/1/events": history });
    renderApp("/projects/1/activity");

    await user.click(await screen.findByRole("button", { name: /Product Owner/ }));
    expect(feedTexts()).toEqual([expect.stringMatching(/Added story “Create an item”/)]);
    await user.click(screen.getByRole("button", { name: "All" }));
    expect(feedTexts()).toHaveLength(3);
  });

  it("shows reconnecting when the stream drops", async () => {
    mockApi({ "GET /projects/1": project, "GET /projects/1/events": history });
    renderApp("/projects/1/activity");
    await screen.findByText(/Added story/);
    act(() => MockEventSource.latest().fail());
    expect(screen.getByRole("status")).toHaveTextContent("Reconnecting");
  });

  it("asks for approval at a gate and sends the reject reason", async () => {
    const user = userEvent.setup();
    const calls = mockApi({
      "GET /projects/1": { ...project, phase: "sprint_planning", awaiting_approval: true },
      "GET /projects/1/events": history,
      "GET /projects/1/sprints": [sprint],
      "GET /sprints/5": sprintDetail,
      "POST /projects/1/approve": { ...project, phase: "sprint_planning", awaiting_approval: false },
    });
    renderApp("/projects/1/activity");

    const card = await screen.findByRole("region", { name: "Planning is waiting for you" });
    expect(await within(card).findByText("Users can add items")).toBeInTheDocument();
    expect(within(card).getByText("Create an item")).toBeInTheDocument();

    await user.click(within(card).getByRole("button", { name: "Reject…" }));
    await user.type(within(card).getByLabelText("Reason (optional)"), "Too big");
    await user.click(within(card).getByRole("button", { name: "Reject Planning" }));

    expect(await screen.findByText(/Rejected Planning for Todo app/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Planning is waiting for you" })).not.toBeInTheDocument();
    const fetchMock = vi.mocked(fetch);
    const url = fetchMock.mock.calls.map((c) => String(c[0])).find((u) => u.includes("/approve"));
    expect(url).toBe("/api/projects/1/approve?approved=false&comment=Too%20big");
    expect(calls.some((c) => c.path === "/projects/1/approve")).toBe(true);
  });
});
