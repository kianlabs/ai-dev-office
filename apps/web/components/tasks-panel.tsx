import { useState } from "react";
import type { Task, TaskStatus } from "@/lib/types";

const TASK_STYLE: Record<TaskStatus, string> = {
  QUEUED: "text-slate-400 border-slate-600 bg-slate-800/40",
  PLANNING: "text-accent border-accent/40 bg-accent/10",
  RUNNING: "text-accent border-accent/50 bg-accent/15",
  REVIEW: "text-amber border-amber/40 bg-amber/10",
  DONE: "text-mint border-mint/40 bg-mint/10",
  FAILED: "text-red-400 border-red-500/40 bg-red-500/10",
  INTERRUPTED: "text-slate-500 border-slate-600 bg-slate-800/40",
};

const CANCELLABLE: TaskStatus[] = ["PLANNING", "RUNNING", "REVIEW"];

export default function TasksPanel({ tasks }: { tasks: Task[] }) {
  const [cancelling, setCancelling] = useState<string | null>(null);

  async function cancelTask(id: string) {
    setCancelling(id);
    try {
      const res = await fetch(`/api/tasks/${id}`, { method: "DELETE" });
      if (!res.ok && res.status !== 409) {
        // 409 = already in a terminal/non-cancellable state; ignore.
        console.error(`Cancel failed: ${res.status}`);
      }
    } catch (err) {
      console.error("Cancel error", err);
    } finally {
      setCancelling(null);
    }
  }

  return (
    <div className="flex h-full flex-col rounded-xl border border-line bg-panel">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="font-mono text-sm font-semibold uppercase tracking-wider text-slate-300">
          Tasks
        </h2>
        <span className="rounded bg-panel2 px-2 py-0.5 font-mono text-xs text-slate-400">
          {tasks.length}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {tasks.length === 0 ? (
          <p className="p-3 text-sm text-slate-500">No tasks yet.</p>
        ) : (
          <ul className="space-y-2">
            {tasks.map((task) => (
              <li key={task.id} className="rounded-lg border border-line bg-panel2 p-3">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-sm font-medium text-slate-100">
                    {task.title}
                  </span>
                  <div className="flex shrink-0 items-center gap-2">
                    <span
                      className={`rounded-full border px-2 py-0.5 font-mono text-[10px] font-semibold ${TASK_STYLE[task.status]}`}
                    >
                      {task.status}
                    </span>
                    {CANCELLABLE.includes(task.status) && (
                      <button
                        type="button"
                        disabled={cancelling === task.id}
                        onClick={() => cancelTask(task.id)}
                        className="rounded-full border border-red-500/40 px-2 py-0.5 font-mono text-[10px] font-semibold text-red-400 transition hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-40"
                        title="Batalkan Tugas"
                      >
                        {cancelling === task.id ? "…" : "Batalkan"}
                      </button>
                    )}
                  </div>
                </div>
                {task.subtasks.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {task.subtasks.map((s) => (
                      <div key={s.id} className="flex items-center gap-2 font-mono text-[11px] text-slate-400">
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${
                            s.status === "DONE"
                              ? "bg-mint"
                              : s.status === "QUEUED"
                                ? "bg-slate-600"
                                : "bg-accent"
                          }`}
                        />
                        <span className="w-16 shrink-0 uppercase text-slate-500">{s.agent_id}</span>
                        <span className="truncate">{s.title}</span>
                      </div>
                    ))}
                  </div>
                )}
                {task.error && (
                  <div className="mt-2 rounded border border-red-500/30 bg-red-500/10 p-2 font-mono text-[11px] text-red-300">
                    {task.error}
                  </div>
                )}
                {task.summary && task.status === "DONE" && (
                  <div className="mt-2 text-[11px] text-mint/80">{task.summary}</div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
