import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { artifact } from "../test/fixtures";
import { mockApi } from "../test/utils";
import { ArtifactDrawer } from "./ArtifactDrawer";
import { ToastProvider } from "./Toast";

function Host() {
  const [id, setId] = useState<number | null>(null);
  return (
    <ToastProvider>
      <button type="button" onClick={() => setId(2)}>
        Open artifact
      </button>
      <ArtifactDrawer artifactId={id} onClose={() => setId(null)} />
    </ToastProvider>
  );
}

describe("ArtifactDrawer", () => {
  it("shows the artifact, closes on Escape and returns focus to the opener", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /artifacts/2": artifact });
    render(<Host />);
    const opener = screen.getByRole("button", { name: "Open artifact" });
    await user.click(opener);

    const dialog = await screen.findByRole("dialog", { name: "app/a.py" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(await screen.findByText(/y = 2/)).toBeInTheDocument();
    expect(screen.getByText("v1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
    expect(document.body.style.overflow).toBe("hidden");

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opener).toHaveFocus();
    expect(document.body.style.overflow).toBe("");
  });

  it("closes when the backdrop is clicked", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /artifacts/2": artifact });
    const { container } = render(<Host />);
    await user.click(screen.getByRole("button", { name: "Open artifact" }));
    await screen.findByRole("dialog");
    await user.click(container.ownerDocument.querySelector(".drawer-backdrop") as Element);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("keeps Tab inside the dialog", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /artifacts/2": artifact });
    render(<Host />);
    await user.click(screen.getByRole("button", { name: "Open artifact" }));
    await screen.findByText(/y = 2/);
    const close = screen.getByRole("button", { name: "Close" });
    const copy = screen.getByRole("button", { name: "Copy" });
    expect(close).toHaveFocus();
    await user.tab();
    expect(copy).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();
    await user.tab({ shift: true });
    expect(copy).toHaveFocus();
  });

  it("copies the content and confirms with a toast", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /artifacts/2": artifact });
    render(<Host />);
    await user.click(screen.getByRole("button", { name: "Open artifact" }));
    await screen.findByText(/y = 2/);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    await user.click(screen.getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith(artifact.content);
    expect(await screen.findByText("Copied to clipboard")).toBeInTheDocument();
  });

  it("tells the user when copying fails", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /artifacts/2": artifact });
    render(<Host />);
    await user.click(screen.getByRole("button", { name: "Open artifact" }));
    await screen.findByText(/y = 2/);
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    await user.click(screen.getByRole("button", { name: "Copy" }));
    expect(await screen.findByText("Could not copy to the clipboard")).toBeInTheDocument();
  });

  it("shows an error when the artifact does not exist", async () => {
    const user = userEvent.setup();
    mockApi({});
    render(<Host />);
    await user.click(screen.getByRole("button", { name: "Open artifact" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not found");
    expect(screen.getByRole("dialog", { name: "Artifact" })).toBeInTheDocument();
  });
});
