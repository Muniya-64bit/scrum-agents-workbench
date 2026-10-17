import { expect, test, type Page } from "@playwright/test";

// The backup demo: one tour through the whole scripted todo-app project. Every step expects
// text that only the right state shows, so a broken run fails instead of recording nonsense.

const actions = (page: Page) => page.locator(".phase-actions");

/** Click the header button and wait until the agents are done and the next state is shown. */
async function start(page: Page, label: string | RegExp, next: string | RegExp) {
  await actions(page).getByRole("button", { name: label }).click();
  await expect(
    actions(page).getByRole("button", { name: next, exact: typeof next === "string" }),
  ).toBeVisible({ timeout: 120_000 });
}

async function approve(page: Page, next: string | RegExp) {
  await actions(page).getByRole("button", { name: "Approve", exact: true }).click();
  await expect(actions(page).getByRole("button", { name: next })).toBeVisible();
}

const open = (page: Page, name: string) => page.getByRole("link", { name, exact: true }).click();
const pause = (page: Page, ms = 1500) => page.waitForTimeout(ms);

/** One sprint after the backlog: planning gate, execution on the board, review gate, retro,
 * release. `last` is true when the project ends after this sprint. */
async function runSprint(page: Page, n: number, planning: string | RegExp, last: boolean) {
  await open(page, "Sprint board");
  await start(page, planning, "Approve");
  await open(page, "Activity");
  await expect(page.getByText("Planning is waiting for you")).toBeVisible();
  await pause(page);
  await approve(page, "Start Execution");

  // execution happens while the board is open: tasks move across the columns
  await open(page, "Sprint board");
  await expect(page.getByText(`SPRINT ${n}`, { exact: false }).first()).toBeVisible();
  await start(page, "Start Execution", "Start Review");
  await expect(page.getByRole("heading", { name: "Done", level: 3 })).toBeVisible();
  await pause(page);
  await open(page, "Activity");
  await expect(page.getByText("Test run:", { exact: false }).first()).toBeVisible();
  await pause(page);

  await start(page, "Start Review", "Approve");
  await expect(page.getByText("Review is waiting for you")).toBeVisible();
  await pause(page);
  await approve(page, "Start Retro");
  await start(page, "Start Retro", "Start Release");
  await start(page, "Start Release", last ? "Finish project" : "Start Sprint planning");
}

test("the scripted todo-app project, from idea to three releases", async ({ page }) => {
  test.setTimeout(900_000);

  // Projects -> open the demo project
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Projects", level: 1 })).toBeVisible();
  await pause(page);
  await page.getByRole("link", { name: /Todo app/ }).click();
  await expect(page.getByText("No backlog yet")).toBeVisible();
  await pause(page);

  // Backlog
  await start(page, "Start Backlog", "Start Planning");
  await expect(page.getByText("Create item").first()).toBeVisible();
  await expect(page.getByText("Filter by status").first()).toBeVisible();
  await page.getByText("Create item").first().click(); // show the acceptance criteria
  await expect(page.getByText("empty title", { exact: false }).first()).toBeVisible();
  await pause(page, 2500);

  // Sprint 1: ten points are planned, seven are finished, the retro changes the process
  await runSprint(page, 1, "Start Planning", false);
  await open(page, "Metrics");
  await expect(page.getByRole("heading", { name: "Burndown" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Velocity" })).toBeVisible();
  await expect(page.getByText("70.0%").first()).toBeVisible();
  await pause(page, 3000);

  // Sprint 2 runs with the levers from the retro
  await open(page, "Backlog");
  await expect(page.getByText(/Next sprint:.*capacity.*7/i)).toBeVisible();
  await expect(page.getByText(/Next sprint:.*test-first/i)).toBeVisible();
  await pause(page, 3000);
  await runSprint(page, 2, "Start Sprint planning", false);

  // Sprint 3 finishes the backlog
  await runSprint(page, 3, "Start Sprint planning", true);
  await actions(page).getByRole("button", { name: "Finish project" }).click();
  await expect(page.getByText("Completed").first()).toBeVisible();

  // Metrics again: velocity per sprint, releases and the Plan-Do-Check-Act comparison
  await open(page, "Metrics");
  await expect(page.getByRole("heading", { name: "Process improvement (PDCA)" })).toBeVisible();
  await expect(page.getByText("v0.3.0")).toBeVisible();
  await expect(page.getByText("Capacity 7 · Fix retries 2 · Test-first").first()).toBeVisible();
  await expect(page.getByText("+30.0 pp").first()).toBeVisible();
  await page.getByRole("heading", { name: "Releases", exact: true }).scrollIntoViewIfNeeded();
  await pause(page, 3000);
  await page.getByRole("heading", { name: "Process improvement (PDCA)" }).scrollIntoViewIfNeeded();
  await pause(page, 4000);

  // Traceability: story -> design -> code -> tests -> release; open one artifact
  await open(page, "Traceability");
  await expect(page.getByText("Trace completeness")).toBeVisible();
  await expect(page.getByText("100.0%").first()).toBeVisible();
  await pause(page, 2000);
  await page.locator(".artifact-chip", { hasText: "app/main.py v5" }).first().click();
  const drawer = page.getByRole("dialog");
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText("title must not be empty")).toBeVisible();
  await pause(page, 3500);
  await drawer.getByRole("button", { name: "Close" }).click();
  await expect(drawer).toBeHidden();
  await pause(page, 1500);
});
