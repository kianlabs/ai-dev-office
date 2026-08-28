import type { ActivityItem, EventKind } from "@/lib/types";

const KIND_STYLE: Record<EventKind, string> = {
  STATUS: "text-slate-400",
  LOG: "text-slate-300",
  SUBTASKS: "text-accent",
  QA_RESULT: "text-mint",
  HEALTH: "text-cyan-300",
  REVIEW: "text-amber",
  RESULT: "text-mint",
};

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export default function ActivityFeed({ items }: { items: ActivityItem[] }) {
  return (
    <div className="flex h-full flex-col rounded-xl border border-line bg-panel">
      <div className="border-b border-line px-4 py-3">
        <h2 className="font-mono text-sm font-semibold uppercase tracking-wider text-slate-300">
          Activity Feed
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto p-2 font-mono text-xs">
        {items.length === 0 ? (
          <p className="p-3 text-slate-500">No activity yet — submit a task.</p>
        ) : (
          <ul className="space-y-1">
            {items.map((item) => (
              <li key={item.id} className="flex gap-2 rounded px-2 py-1.5 hover:bg-panel2">
                <span className="shrink-0 tabular-nums text-slate-500">
                  {formatTime(item.at)}
                </span>
                <span className="shrink-0 font-semibold text-slate-200">
                  {item.agent_name}
                </span>
                <span className={`truncate ${KIND_STYLE[item.kind] ?? "text-slate-300"}`}>
                  {item.message}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}