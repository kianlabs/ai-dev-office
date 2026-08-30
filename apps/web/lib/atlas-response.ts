// Pure helpers for surfacing the structured ATLAS response (Phase 4.1).
//
// The Activity Feed stays operational telemetry; these helpers pick the
// human-readable ATLAS answer (intent, message, plan, needs_input) out of
// the task list so the UI can show it directly.

import type { AtlasResponse, Task } from "./types";

const INTENT_LABELS: Record<string, string> = {
  chat: "Chat",
  plan: "Planning",
  research: "Research",
  implement: "Implementation",
  test: "Testing",
  monitor: "Monitoring",
  needs_input: "Butuh Input",
};

export function intentLabel(intent: string | undefined): string {
  if (!intent) return "ATLAS";
  return INTENT_LABELS[intent] ?? intent;
}

/** The most recent task that carries a structured ATLAS response. */
export function latestAtlasResponse(tasks: Task[]): AtlasResponse | null {
  for (const task of tasks) {
    if (task.atlas_response?.message) {
      return task.atlas_response;
    }
  }
  return null;
}

/** Bounded plan summary lines for display (at most `limit` entries). */
export function planSummaryLines(
  response: AtlasResponse | null,
  limit = 3,
): string[] {
  const plan = response?.plan;
  if (!plan) return [];
  const lines: string[] = [];
  for (const key of ["known_requirements", "features", "ui_plan", "open_questions"] as const) {
    const value = plan[key];
    if (Array.isArray(value)) {
      lines.push(...value.map(String));
    }
    if (lines.length >= limit) break;
  }
  return lines.slice(0, limit);
}
