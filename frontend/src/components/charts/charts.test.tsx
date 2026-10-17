import { fireEvent, render, screen, within } from "@testing-library/react";

import { burndown } from "../../test/fixtures";
import { BarChart } from "./BarChart";
import { BurndownChart } from "./BurndownChart";
import { niceTicks } from "./ChartFrame";

describe("niceTicks", () => {
  it("starts at 0 and uses round steps that cover the maximum", () => {
    expect(niceTicks(8, 4)).toEqual([0, 2, 4, 6, 8]);
    expect(niceTicks(10, 4)).toEqual([0, 5, 10]);
    expect(niceTicks(3, 4)).toEqual([0, 1, 2, 3]);
    expect(niceTicks(0.04, 4)).toEqual([0, 0.01, 0.02, 0.03, 0.04]);
  });

  it("handles an empty range", () => {
    expect(niceTicks(0)).toEqual([0, 1]);
  });
});

describe("BurndownChart", () => {
  it("draws one point per series entry, the ideal line and an accessible name", () => {
    const { container } = render(<BurndownChart data={burndown} />);
    expect(container.querySelectorAll("circle")).toHaveLength(burndown.series.length);
    expect(container.querySelector("path[stroke-dasharray]")).not.toBeNull();
    expect(screen.getByRole("img", { name: /Burndown, sprint 2/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Sprint 2: 5 committed, 0 left/ })).toBeInTheDocument();
  });

  it("shows a tooltip for the focused point", () => {
    const { container } = render(<BurndownChart data={burndown} />);
    expect(screen.queryByRole("tooltip")).toBeNull();
    fireEvent.focus(container.querySelectorAll("g[tabindex='0']")[1]);
    const tip = screen.getByRole("tooltip");
    expect(within(tip).getByText("Done: C: reset password")).toBeInTheDocument();
    expect(within(tip).getByText("2 points left")).toBeInTheDocument();
    expect(within(tip).getByText("20s")).toBeInTheDocument();
    fireEvent.blur(container.querySelectorAll("g[tabindex='0']")[1]);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("plots steps when the sprint was instant", () => {
    const instant = { ...burndown, duration_s: 0.2, series: burndown.series.map((p) => ({ ...p, t: 0 })) };
    const { container } = render(<BurndownChart data={instant} />);
    expect(container.textContent).toContain("steps");
    fireEvent.focus(container.querySelectorAll("g[tabindex='0']")[2]);
    expect(screen.getByRole("tooltip")).toHaveTextContent("step 2");
  });

  it("says so when there is no progress to draw", () => {
    render(<BurndownChart data={{ ...burndown, series: burndown.series.slice(0, 1) }} />);
    expect(screen.getByText("No progress recorded yet")).toBeInTheDocument();
  });
});

describe("BarChart", () => {
  const groups = [
    {
      label: "Sprint 1",
      values: [
        { name: "Committed", value: 8, tone: "muted" as const },
        { name: "Completed", value: 5, tone: "accent" as const },
      ],
    },
    {
      label: "Sprint 2",
      values: [
        { name: "Committed", value: 5, tone: "muted" as const },
        { name: "Completed", value: 5, tone: "accent" as const },
      ],
    },
  ];

  it("draws a bar and a value label for every value, and a legend", () => {
    const { container } = render(<BarChart groups={groups} unit="points" title="Velocity" desc="d" />);
    expect(container.querySelectorAll("rect")).toHaveLength(4);
    const chart = screen.getByRole("img", { name: /Velocity/ });
    expect(within(chart).getAllByText("5").length).toBeGreaterThanOrEqual(3);
    expect(within(chart).getAllByText("8").length).toBeGreaterThan(0);
    const legend = screen.getByRole("list", { name: "Legend" });
    expect(within(legend).getByText("Committed")).toBeInTheDocument();
    expect(within(legend).getByText("Completed")).toBeInTheDocument();
  });

  it("makes bars focusable with a text alternative", () => {
    const { container } = render(<BarChart groups={groups} unit="points" title="Velocity" desc="d" />);
    const bars = container.querySelectorAll("g[tabindex='0']");
    expect(bars).toHaveLength(4);
    expect(bars[0].querySelector("title")?.textContent).toBe("Sprint 1, Committed: 8 points");
  });
});
