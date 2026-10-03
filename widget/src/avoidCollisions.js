// A widget on someone else's site lands in a corner the site may already use: RMIT's Library page has its own
// "Ask the Library" chat button fixed bottom-right, and cookie banners sit along the bottom edge. This samples
// the launcher's default footprint and, if another fixed-position element is there, reports how far up to move
// so the launcher sits just above it instead of on top of it.

const LAUNCHER = 60;
const MARGIN = 24;
const GAP = 12;

function fixedAncestor(el) {
  for (let node = el; node && node !== document.documentElement && node !== document.body; node = node.parentElement) {
    const position = getComputedStyle(node).position;
    if (position === "fixed" || position === "sticky") return node;
  }
  return null;
}

/** The bottom offset (px) the launcher should use, given what else is fixed in its corner. */
export function measureBottom(host) {
  const w = window.innerWidth;
  const h = window.innerHeight;
  let bottom = MARGIN;
  for (const dx of [10, LAUNCHER / 2, LAUNCHER - 10]) {
    for (const dy of [10, LAUNCHER / 2, LAUNCHER - 10]) {
      const stack = document.elementsFromPoint(w - MARGIN - dx, h - MARGIN - dy);
      for (const el of stack) {
        if (el === host || host.contains(el)) continue;
        const fixed = fixedAncestor(el);
        if (!fixed) continue;
        const rect = fixed.getBoundingClientRect();
        // A backdrop or full-screen overlay is not a neighbour to sit above.
        if (rect.width > w * 0.6 && rect.height > h * 0.5) continue;
        bottom = Math.max(bottom, h - rect.top + GAP);
        break;
      }
    }
  }
  return Math.min(bottom, h * 0.5);
}

/** Measure now and again shortly after load (other widgets often appear late) and on resize. Returns a cleanup. */
export function watchCorner(host, apply) {
  const run = () => apply(measureBottom(host));
  run();
  const timers = [setTimeout(run, 1500), setTimeout(run, 4000)];
  window.addEventListener("resize", run);
  window.addEventListener("load", run);
  return () => {
    timers.forEach(clearTimeout);
    window.removeEventListener("resize", run);
    window.removeEventListener("load", run);
  };
}
