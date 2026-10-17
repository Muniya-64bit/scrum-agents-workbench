import { render, screen, within } from "@testing-library/react";

import type { ProcessInfo } from "../api/types";
import { processInfo } from "../test/fixtures";
import { ProcessChips } from "./ProcessChips";

const info: ProcessInfo = {
  ...processInfo,
  current: {
    capacity: 10,
    max_fix_retries: 3,
    test_first: false,
    guidelines: ["Keep functions small", "Review every diff"],
  },
};

describe("ProcessChips", () => {
  it("shows capacity, fix retries and the agreements, and Test-first only when on", () => {
    const { rerender } = render(<ProcessChips info={info} phase="execution" />);
    const bar = screen.getByRole("region", { name: "Sprint process" });
    expect(within(bar).getByText("Capacity 10")).toBeInTheDocument();
    expect(within(bar).getByText("Fix retries 3")).toBeInTheDocument();
    expect(within(bar).queryByText("Test-first")).toBeNull();
    expect(within(bar).getByText("Agreements (2)")).toBeInTheDocument();
    expect(within(bar).getByText("Keep functions small")).toBeInTheDocument();

    rerender(<ProcessChips info={{ ...info, current: { ...info.current, test_first: true } }} phase="execution" />);
    expect(screen.getByText("Test-first")).toBeInTheDocument();
  });

  it("announces the next sprint's change at the retro and the release only", () => {
    const { rerender } = render(<ProcessChips info={info} phase="execution" />);
    expect(screen.queryByText(/Next sprint/)).toBeNull();

    rerender(<ProcessChips info={info} phase="retro" />);
    expect(screen.getByText("Next sprint: capacity 10 → 7, test-first on")).toBeInTheDocument();
    rerender(<ProcessChips info={info} phase="release" />);
    expect(screen.getByText(/Next sprint: capacity 10 → 7/)).toBeInTheDocument();
    rerender(<ProcessChips info={{ ...info, next_changes: {} }} phase="retro" />);
    expect(screen.queryByText(/Next sprint/)).toBeNull();
  });

  it("renders nothing before the first sprint or while loading", () => {
    const { container, rerender } = render(<ProcessChips info={null} phase="idea" />);
    expect(container).toBeEmptyDOMElement();
    rerender(<ProcessChips info={{ ...info, current_sprint_number: null }} phase="backlog" />);
    expect(container).toBeEmptyDOMElement();
  });
});
