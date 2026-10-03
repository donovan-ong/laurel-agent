/** A week's items (not counting the plan suggestion) and its plan suggestion, if any. */
export function splitWeek(week) {
  if (!week || !week.found) return { items: [], plan: null };
  return { items: week.items.filter((i) => i.kind !== "plan"), plan: week.items.find((i) => i.kind === "plan") || null };
}
