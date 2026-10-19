/** Bold the Given / When / Then / And keywords so criteria are easy to scan. */
export function Gherkin({ text }: { text: string }) {
  const parts = text.split(/\b(Given|When|Then|And)\b/);
  return (
    <>
      {parts.map((part, i) =>
        /^(Given|When|Then|And)$/.test(part) ? (
          <strong key={i} className="gherkin">
            {part}
          </strong>
        ) : (
          part
        ),
      )}
    </>
  );
}
