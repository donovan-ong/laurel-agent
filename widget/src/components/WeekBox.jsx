import { useState } from "react";
import { CalendarIcon, ChevronDownIcon } from "../icons";
import WeekItems from "./WeekItems";

// "Coming up", minimised to a count by default so it doesn't crowd the chips; open, it lists every item.
// Each row (and the plan row) sends its ready-made question.
export default function WeekBox({ week, onAsk }) {
  const [open, setOpen] = useState(false);
  if (!week || !week.found) return null;
  const items = week.items.filter((i) => i.kind !== "plan");
  const plan = week.items.find((i) => i.kind === "plan");
  if (!items.length && !plan) return null;
  const overdue = items.filter((i) => i.urgency === "overdue" || i.urgency === "action").length;
  const summary = [week.week_label, overdue ? `${overdue} need${overdue === 1 ? "s" : ""} attention` : null]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="lw-weekbox" data-open={open ? "true" : "false"}>
      <button
        type="button"
        className="lw-weekbox-toggle"
        aria-expanded={open}
        aria-controls="lw-weekbox-list"
        onClick={() => setOpen(!open)}
      >
        <CalendarIcon size={18} />
        <span className="lw-weekbox-label">
          <strong>Coming up</strong>
          {summary && <span>{summary}</span>}
        </span>
        <span className="lw-weekbox-count" aria-label={`${items.length} items`}>
          {items.length}
        </span>
        <span className="lw-weekbox-chevron">
          <ChevronDownIcon size={16} />
        </span>
      </button>
      {open && (
        <div className="lw-weekbox-list" id="lw-weekbox-list">
          <WeekItems week={week} onAsk={onAsk} />
        </div>
      )}
    </div>
  );
}
