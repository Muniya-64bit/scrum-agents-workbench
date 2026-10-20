import type { ReactNode } from "react";

/** A titled block of the Results page. Every section says what it shows, right under its title. */
export function Section({
  id,
  title,
  description,
  actions,
  children,
}: {
  id: string;
  title: string;
  description: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section id={id} className="panel results-section" aria-labelledby={`${id}-title`}>
      <header className="results-section-head">
        <div>
          <h2 id={`${id}-title`} className="results-section-title">
            {title}
          </h2>
          <p className="muted results-section-desc">{description}</p>
        </div>
        {actions}
      </header>
      {children}
    </section>
  );
}
