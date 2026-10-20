import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { UNAUTHORIZED_EVENT, getToken, setToken } from "../api/client";
import { AuthGate } from "./AuthGate";

describe("AuthGate", () => {
  const reload = vi.fn();

  beforeEach(() => {
    reload.mockClear();
    vi.stubGlobal("location", { ...window.location, reload });
  });

  afterEach(() => {
    setToken("");
    vi.unstubAllGlobals();
  });

  it("stays out of the way until the API refuses a request", () => {
    render(<AuthGate />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("asks for the token when the API answers 401", () => {
    render(<AuthGate />);
    act(() => {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    });
    expect(screen.getByRole("dialog", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByLabelText("API token")).toHaveAttribute("type", "password");
  });

  it("keeps the token and reloads to use it", async () => {
    const user = userEvent.setup();
    render(<AuthGate />);
    act(() => {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    });
    await user.type(screen.getByLabelText("API token"), "  s3cret  ");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(getToken()).toBe("s3cret");
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("stops listening when it is removed", () => {
    const { unmount } = render(<AuthGate />);
    unmount();
    act(() => {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
