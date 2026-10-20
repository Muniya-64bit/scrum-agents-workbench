import type { GqmGoal } from "../../api/types";
import { Section } from "./Section";

/** Why these metrics: each goal, the questions that test it and the metrics that answer them. */
export function GqmSection({ gqm }: { gqm: GqmGoal[] }) {
  return (
    <Section
      id="method"
      title="How the metrics were chosen"
      description="Goal-Question-Metric (GQM) starts from a goal, asks the questions that show whether it is reached, and only then picks the metrics that answer them."
    >
      <details className="results-help">
        <summary>Show goals, questions and metrics</summary>
        <div className="gqm">
          {gqm.map((goal) => (
            <div key={goal.id} className="gqm-goal">
              <h3>
                <span className="gqm-id">{goal.id}</span> {goal.goal}{" "}
                <span className="muted">({goal.viewpoint})</span>
              </h3>
              {goal.questions.map((q) => (
                <div key={q.id} className="gqm-question">
                  <h4>
                    <span className="gqm-id">{q.id}</span> {q.text}
                  </h4>
                  <ul>
                    {q.metrics.map((m) => (
                      <li key={m.key}>
                        <strong>{m.name}</strong> <span className="muted">({m.unit})</span>: {m.definition}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ))}
        </div>
      </details>
    </Section>
  );
}
