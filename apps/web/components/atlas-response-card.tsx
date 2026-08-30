"use client";

import { intentLabel, latestAtlasResponse, planSummaryLines } from "@/lib/atlas-response";
import type { Task } from "@/lib/types";

/**
 * Compact, readable answer from ATLAS (Phase 4.1): intent + message (+ a few
 * plan highlights). Lets the user read ATLAS's reply without reading raw
 * Activity Feed telemetry. Deliberately minimal wiring — no big UI redesign.
 */
export default function AtlasResponseCard({ tasks }: { tasks: Task[] }) {
  const response = latestAtlasResponse(tasks);
  if (!response) return null;

  const planLines = planSummaryLines(response);

  return (
    <div className="pointer-events-auto w-[min(680px,calc(100%-48px))] rounded-2xl border border-white/[0.12] bg-[#0c121c]/95 p-3 shadow-2xl backdrop-blur-xl">
      <div className="flex items-center gap-2">
        <span className="rounded-md bg-emerald-400/15 px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider text-emerald-300">
          ATLAS
        </span>
        <span className="rounded-md border border-white/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-slate-400">
          {intentLabel(response.intent)}
        </span>
        {response.needs_input ? (
          <span className="rounded-md bg-amber-400/15 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-amber-300">
            needs input
          </span>
        ) : null}
      </div>

      <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
        {response.message}
      </p>

      {planLines.length > 0 && (
        <ul className="mt-2 space-y-1">
          {planLines.map((line) => (
            <li
              key={line}
              className="flex items-start gap-1.5 text-[11px] leading-snug text-slate-400"
            >
              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-emerald-400/70" />
              <span className="min-w-0 break-words">{line}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
