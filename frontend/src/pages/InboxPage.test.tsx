import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { project } from "../test/fixtures";
import { mockApi, renderApp } from "../test/utils";

const waiting = { ...project, id: 2, name: "Recipes", phase: "review" as const, awaiting_approval: true };

describe("InboxPage", () => {
  it("lists only projects waiting for approval and shows the count in the sidebar", async () => {
    mockApi({ "GET /projects": [project, waiting], "GET /projects/2/sprints": [] });
    renderApp("/inbox");

    const card = await screen.findByRole("region", { name: /Recipes/ });
    expect(within(card).getByText(/Approve the increment/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /Todo app/ })).not.toBeInTheDocument();
    expect(await screen.findByLabelText("1 waiting for approval")).toBeInTheDocument();
  });

  it("approves and clears the inbox", async () => {
    const user = userEvent.setup();
    let approved = false;
    mockApi({
      "GET /projects": () => ({ body: [approved ? { ...waiting, awaiting_approval: false } : waiting] }),
      "GET /projects/2/sprints": [],
      "POST /projects/2/approve": () => {
        approved = true;
        return { body: { ...waiting, awaiting_approval: false } };
      },
    });
    renderApp("/inbox");

    await user.click(await screen.findByRole("button", { name: "Approve Review" }));
    expect(await screen.findByText("You're all caught up")).toBeInTheDocument();
    expect(screen.queryByLabelText(/waiting for approval/)).not.toBeInTheDocument();
  });

  it("shows an empty state when nothing waits", async () => {
    mockApi({ "GET /projects": [project] });
    renderApp("/inbox");
    expect(await screen.findByText("You're all caught up")).toBeInTheDocument();
  });
});
