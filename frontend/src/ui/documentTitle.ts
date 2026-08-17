export type StudioDocumentTitleTarget =
  | { kind: "home" }
  | { kind: "page"; title: string }
  | { kind: "conversation"; title: string };

function normalizeTitleSegment(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

/** Format browser titles using ChatGPT-style app semantics.
 *
 * The home surface uses the brand by itself, conversations use their own
 * title, and named product surfaces keep the brand as a prefix.
 */
export function formatStudioDocumentTitle(
  siteTitle: string,
  target: StudioDocumentTitleTarget,
): string {
  const brand = normalizeTitleSegment(siteTitle) || "AgentKit Studio";
  if (target.kind === "home") return brand;

  const title = normalizeTitleSegment(target.title);
  if (!title) return brand;
  if (target.kind === "conversation") return title;
  return `${brand} - ${title}`;
}
