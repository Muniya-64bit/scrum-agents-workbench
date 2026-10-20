import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ClampedText } from "./ClampedText";

describe("ClampedText", () => {
  it("shows a short text in full without a button", () => {
    render(<ClampedText text="A short idea." />);
    expect(screen.getByText("A short idea.")).not.toHaveClass("clamped");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("clamps a long text and expands it on request", async () => {
    const user = userEvent.setup();
    const text = "word ".repeat(80).trim();
    render(<ClampedText text={text} className="page-subtitle" />);
    expect(screen.getByText(text)).toHaveClass("page-subtitle", "clamped");

    await user.click(screen.getByRole("button", { name: "Show more" }));
    expect(screen.getByText(text)).not.toHaveClass("clamped");
    expect(screen.getByRole("button", { name: "Show less" })).toHaveAttribute("aria-expanded", "true");
  });
});
