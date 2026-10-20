import { useState } from "react";

/** A paragraph that shows three lines of a long text and a button for the rest. */
export function ClampedText({
  text,
  className = "",
  limit = 240,
}: {
  text: string;
  className?: string;
  /** Texts up to this many characters are always shown in full. */
  limit?: number;
}) {
  const [open, setOpen] = useState(false);
  const long = text.length > limit;
  return (
    <>
      <p className={`${className} ${long && !open ? "clamped" : ""}`.trim()}>{text}</p>
      {long && (
        <button type="button" className="clamp-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? "Show less" : "Show more"}
        </button>
      )}
    </>
  );
}
