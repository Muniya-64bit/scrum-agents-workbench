import { api } from "../../api/client";
import type { ReleaseCheck } from "../../api/types";
import { useResource } from "../../lib/useResource";
import { Badge, ErrorState, Loading, type Tone } from "../ui";
import { Section } from "./Section";

const TONE: Record<ReleaseCheck["status"], Tone> = {
  passed: "done",
  met: "done",
  failed: "danger",
  "not met": "danger",
  skipped: "todo",
  unverified: "todo",
};

/** The requirement checks name a requirement; the others check the app as a whole. */
const isRequirement = (c: ReleaseCheck) => ["met", "not met", "unverified"].includes(c.status);

/** What was checked on the latest release: does the app run, does it serve its contract, are the
 *  non-functional requirements met, is the code free of common security mistakes. */
export function ReleaseChecks({ projectId, version }: { projectId: number; version: number }) {
  const res = useResource(() => api.releaseChecks(projectId), [projectId, version]);
  const all = res.data ?? [];
  const latest = all.length > 0 ? all[all.length - 1].version : null;
  const checks = all.filter((c) => c.version === latest);

  return (
    <Section
      id="checks"
      title={latest ? `Release checks (${latest})` : "Release checks"}
      description="Run on the generated app when a sprint is released: it is started, compared with the API contract, timed against the non-functional requirements and scanned for security mistakes."
    >
      {res.error && !res.data ? (
        <ErrorState error={res.error} onRetry={res.reload} />
      ) : !res.data ? (
        <Loading label="Loading release checks" />
      ) : checks.length === 0 ? (
        <p className="muted results-note">
          No release checks yet. They run when a sprint is released with a real model; a mock run
          has no app to check.
        </p>
      ) : (
        <>
          <CheckTable title="The app" checks={checks.filter((c) => !isRequirement(c))} />
          <CheckTable
            title="Non-functional requirements"
            checks={checks.filter(isRequirement)}
          />
        </>
      )}
    </Section>
  );
}

function CheckTable({ title, checks }: { title: string; checks: ReleaseCheck[] }) {
  if (checks.length === 0) return null;
  return (
    <div className="table-scroll">
      <table className="data-table">
        <caption className="check-caption">{title}</caption>
        <thead>
          <tr>
            <th scope="col">Check</th>
            <th scope="col">Result</th>
            <th scope="col">Detail</th>
          </tr>
        </thead>
        <tbody>
          {checks.map((c) => (
            <tr key={c.name}>
              <th scope="row">{c.name}</th>
              <td>
                <Badge tone={TONE[c.status]}>{c.status}</Badge>
              </td>
              <td className="muted">{c.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
