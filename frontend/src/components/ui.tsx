import type { ButtonHTMLAttributes, ReactNode } from "react";

import { roleLabel } from "../lib/scrum";
import { IconAlert, IconRefresh } from "./icons";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

export function Button({
  variant = "secondary",
  loading = false,
  icon,
  children,
  className = "",
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  loading?: boolean;
  icon?: ReactNode;
}) {
  return (
    <button
      type="button"
      className={`btn btn-${variant} ${className}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Spinner small /> : icon}
      {children}
    </button>
  );
}

export type Tone = "neutral" | "accent" | "todo" | "doing" | "testing" | "done" | "danger";

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function RoleTag({ role }: { role: string }) {
  return (
    <span className="role-tag" title={roleLabel(role)}>
      <span className="role-dot" style={{ background: `var(--role-${role || "devops"})` }} />
      {roleLabel(role)}
    </span>
  );
}

export function Spinner({ small = false, label }: { small?: boolean; label?: string }) {
  return (
    <span className={`spinner ${small ? "spinner-sm" : ""}`} role={label ? "status" : undefined}>
      {label && <span className="sr-only">{label}</span>}
    </span>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="state state-loading">
      <Spinner label={label} />
      <span className="state-text">{label}…</span>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="state state-empty">
      {icon && <div className="state-icon">{icon}</div>}
      <h3 className="state-title">{title}</h3>
      {children && <p className="state-text">{children}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div className="state state-error" role="alert">
      <div className="state-icon">
        <IconAlert size={22} />
      </div>
      <h3 className="state-title">Something went wrong</h3>
      <p className="state-text">{error.message}</p>
      {onRetry && (
        <Button icon={<IconRefresh />} onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
