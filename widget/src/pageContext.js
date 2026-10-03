// Suggestion chips for the empty state, chosen from the part of the RMIT site the student is on. This is the
// widget's lightest form of integration with the page around it: it reads only location.pathname.

const DEFAULT_CHIPS = [
  "Plan my study week",
  "What's due this week?",
  "Book a study room tomorrow at 10am",
];

const SECTIONS = [
  { match: /library/i, chips: ["What do I have on loan?", "Renew everything I can", "When are my books due?"] },
  {
    match: /international|visa/i,
    chips: ["Am I allowed to study part-time on my student visa?", "What are my fees and how do I pay?", "What week is it?"],
  },
  {
    match: /(courses|study|program|degree)/i,
    chips: ["What are my compulsory courses?", "What subjects should I enrol in next semester?", "Can I finish part-time?"],
  },
  {
    match: /(students|student|life-at-rmit|support)/i,
    chips: ["What's my print balance?", "Book a study room tomorrow at 10am", "Log an IT ticket: my wifi keeps dropping"],
  },
];

export function chipsForPath(pathname = "") {
  const section = SECTIONS.find((s) => s.match.test(pathname));
  return section ? section.chips : DEFAULT_CHIPS;
}
