import { useEffect, useState, type FormEvent } from "react";

import { UNAUTHORIZED_EVENT, setToken } from "../api/client";
import { Button } from "./ui";

/**
 * Asks for the API token when the backend refuses a request (it was started with
 * WORKBENCH_API_TOKEN). The token is kept in this browser; the page reloads to use it.
 */
export function AuthGate() {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");

  useEffect(() => {
    const show = () => setOpen(true);
    window.addEventListener(UNAUTHORIZED_EVENT, show);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, show);
  }, []);

  if (!open) return null;

  function submit(e: FormEvent) {
    e.preventDefault();
    setToken(value.trim());
    window.location.reload();
  }

  return (
    <div className="auth-backdrop">
      <form className="panel auth-dialog" role="dialog" aria-modal="true" aria-labelledby="auth-title" onSubmit={submit}>
        <h2 id="auth-title" className="results-section-title">
          Sign in
        </h2>
        <p className="muted">This workbench needs an API token. Ask whoever started it for the value of WORKBENCH_API_TOKEN.</p>
        <label className="field">
          <span className="field-label">API token</span>
          <input
            className="input"
            type="password"
            autoComplete="off"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            required
            autoFocus
          />
        </label>
        <Button variant="primary" type="submit">
          Sign in
        </Button>
      </form>
    </div>
  );
}
