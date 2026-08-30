import { describe, expect, it } from "vitest";

import { intentLabel, latestAtlasResponse, planSummaryLines } from "../lib/atlas-response";
import type { Task } from "../lib/types";

function taskWith(partial: Partial<Task>): Task {
  return {
    id: "t",
    title: "t",
    description: "",
    status: "DONE",
    subtasks: [],
    created_at: 0,
    updated_at: 0,
    ...partial,
  };
}

describe("latestAtlasResponse", () => {
  it("returns null when no task carries an ATLAS response", () => {
    expect(latestAtlasResponse([])).toBeNull();
    expect(latestAtlasResponse([taskWith({ id: "a" })])).toBeNull();
  });

  it("returns the most recent (first) task response, not telemetry", () => {
    const tasks = [
      taskWith({
        id: "newest",
        atlas_response: { intent: "chat", message: "Halo 👋" },
      }),
      taskWith({
        id: "older",
        atlas_response: { intent: "plan", message: "Plan dibuat" },
      }),
    ];
    expect(latestAtlasResponse(tasks)?.message).toBe("Halo 👋");
  });

  it("skips tasks whose response has no message", () => {
    const tasks = [
      taskWith({ id: "a", atlas_response: null }),
      taskWith({ id: "b", atlas_response: { intent: "plan", message: "ok" } }),
    ];
    expect(latestAtlasResponse(tasks)?.message).toBe("ok");
  });
});

describe("intentLabel", () => {
  it("maps the intent contract to readable labels", () => {
    expect(intentLabel("chat")).toBe("Chat");
    expect(intentLabel("plan")).toBe("Planning");
    expect(intentLabel("needs_input")).toBe("Butuh Input");
    expect(intentLabel("weird")).toBe("weird");
    expect(intentLabel(undefined)).toBe("ATLAS");
  });
});

describe("planSummaryLines", () => {
  it("is empty without a plan", () => {
    expect(planSummaryLines(null)).toEqual([]);
    expect(
      planSummaryLines({ intent: "chat", message: "hi", plan: null }),
    ).toEqual([]);
  });

  it("extracts a bounded number of plan lines", () => {
    const lines = planSummaryLines({
      intent: "plan",
      message: "Plan dibuat",
      plan: {
        goal: "Merencanakan aplikasi booking",
        known_requirements: ["aplikasi booking"],
        features: ["A", "B", "C", "D"],
      },
    });
    expect(lines.length).toBeLessThanOrEqual(3);
    expect(lines).toContain("aplikasi booking");
  });
});
