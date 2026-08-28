/**
 * Regression tests for semantic.ts refactor.
 *
 * These tests pin behavior required by the user spec:
 *   BASE priority:      ERROR > REPAIRING > WAITING > role-specific > IDLE > fallback
 *   Role mapping:       ATLAS(planning|dispatching|reporting)
 *                       SCOUT(researching|reporting)
 *                       FORGE(coding|building|reporting)
 *                       QA(testing|repairing)
 *                       PULSE(monitoring|error)
 *   TRANSIENT priority: ERROR > REPAIRING > SUCCESS > REPORTING
 *
 * Word-boundary safety: "prefix" must NOT match "fix".
 */

import { describe, it, expect } from "vitest";

import {
  deriveAgentVisualState,
  applyTransientVisualState,
  containsAny,
  type AgentVisualMode,
  type AgentVisualState,
  type TransientAgentVisual,
} from "@/components/office-3d/semantic";
import type { ActivityItem, AgentRecord, AgentStatus } from "@/lib/types";

// ---------- helpers -------------------------------------------------------

function makeAgent(
  overrides: Partial<AgentRecord> & Pick<AgentRecord, "agent_id" | "status" | "activity">,
): AgentRecord {
  return {
    name: overrides.agent_id.toUpperCase(),
    role: "tester",
    color: "#000",
    last_event_at: 0,
    ...overrides,
  };
}

function makeEvent(overrides: Partial<ActivityItem> & Pick<ActivityItem, "agent_id" | "message" | "kind">): ActivityItem {
  return {
    id: overrides.id ?? `evt-${Math.random()}`,
    at: 0,
    agent_name: overrides.agent_id.toUpperCase(),
    task_id: null,
    ...overrides,
  };
}

// We test the hook's PURE resolver indirectly through deriveAgentVisualState,
// since the hook is a thin React wrapper. For TTL/idempotency/replacement
// we use a dedicated hook harness below.

// =========================================================================
// 1. Word-boundary safety (RED: "prefix" must NOT match "fix")
// =========================================================================

describe("containsAny word-boundary safety", () => {
  it('"prefix" does NOT match "fix"', () => {
    expect(containsAny("prefix", ["fix"])).toBe(false);
  });

  it('"the fix is in" DOES match "fix"', () => {
    expect(containsAny("the fix is in", ["fix"])).toBe(true);
  });

  it('"routed back" matches exactly', () => {
    expect(containsAny("routed back to forge", ["routed back"])).toBe(true);
  });
});

// =========================================================================
// 2. BASE priority: ERROR > REPAIRING > WAITING > role-specific > IDLE > fallback
// =========================================================================

describe("BASE: ERROR always wins regardless of activity text", () => {
  it("FORGE status ERROR with any activity → error", () => {
    expect(
      deriveAgentVisualState(
        makeAgent({ agent_id: "forge", status: "ERROR", activity: "Compiling" }),
      ).mode,
    ).toBe("error");
  });

  it("status ERROR must override role-specific dispatching text", () => {
    expect(
      deriveAgentVisualState(
        makeAgent({ agent_id: "atlas", status: "ERROR", activity: "Dispatching FORGE" }),
      ).mode,
    ).toBe("error");
  });
});

describe("BASE: REPAIRING wins over role-specific", () => {
  it('forge WORKING "Repair attempt 1" → repairing', () => {
    expect(
      deriveAgentVisualState(
        makeAgent({ agent_id: "forge", status: "WORKING", activity: "Repair attempt 1" }),
      ).mode,
    ).toBe("repairing");
  });

  it('forge WORKING "Compiling" beats role-default coding if activity implies repair', () => {
    expect(
      deriveAgentVisualState(
        makeAgent({ agent_id: "forge", status: "WORKING", activity: "Compiling after repair" }),
      ).mode,
    ).toBe("repairing");
  });
});

describe("BASE: WAITING is an explicit state", () => {
  it('forge status WAITING "Waiting QA" → waiting', () => {
    expect(
      deriveAgentVisualState(
        makeAgent({ agent_id: "forge", status: "WAITING", activity: "Waiting QA" }),
      ).mode,
    ).toBe("waiting");
  });
});

// =========================================================================
// 3. Role mapping - exact spec cases
// =========================================================================

describe("Role mapping - exact spec cases", () => {
  const cases: Array<[string, AgentStatus, string, AgentVisualMode]> = [
    ["atlas", "WORKING", "Planning implementation strategy", "planning"],
    ["atlas", "WORKING", "Dispatching FORGE", "dispatching"],
    ["forge", "WAITING", "Waiting QA", "waiting"],
    ["forge", "WORKING", "Repair attempt 1", "repairing"],
    ["qa", "WORKING", "Running test suite", "testing"],
    ["pulse", "WORKING", "Scanning runtime error logs", "monitoring"],
    ["pulse", "WORKING", "Runtime unhealthy", "error"],
    ["forge", "ERROR", "Something", "error"],
  ];

  for (const [agent_id, status, activity, expected] of cases) {
    it(`${agent_id} ${status} "${activity}" → ${expected}`, () => {
      expect(
        deriveAgentVisualState(makeAgent({ agent_id, status, activity })).mode,
      ).toBe(expected);
    });
  }
});

describe("Role mapping - extras", () => {
  it('atlas WORKING "Reviewing QA" → reporting', () => {
    expect(
      deriveAgentVisualState(
        makeAgent({ agent_id: "atlas", status: "WORKING", activity: "Reviewing QA" }),
      ).mode,
    ).toBe("reporting");
  });

  it('atlas WORKING "Reporting to user" → reporting', () => {
    expect(
      deriveAgentVisualState(
        makeAgent({ agent_id: "atlas", status: "WORKING", activity: "Reporting to user" }),
      ).mode,
    ).toBe("reporting");
  });

  it('scout WORKING "Reading documentation" → researching', () => {
    expect(
      deriveAgentVisualState(
        makeAgent({ agent_id: "scout", status: "WORKING", activity: "Reading documentation" }),
      ).mode,
    ).toBe("researching");
  });

  it('scout WORKING "Hand off brief" → reporting', () => {
    expect(
      deriveAgentVisualState(
        makeAgent({ agent_id: "scout", status: "WORKING", activity: "Hand off brief" }),
      ).mode,
    ).toBe("reporting");
  });

  it('forge WORKING "Compiling changes" → building', () => {
    expect(
      deriveAgentVisualState(
        makeAgent({ agent_id: "forge", status: "WORKING", activity: "Compiling changes" }),
      ).mode,
    ).toBe("building");
  });

  it('forge WORKING "Editing app/dashboard/page.tsx" → coding', () => {
    expect(
      deriveAgentVisualState(
        makeAgent({ agent_id: "forge", status: "WORKING", activity: "Editing app/dashboard/page.tsx" }),
      ).mode,
    ).toBe("coding");
  });
});

// =========================================================================
// 4. BASE: IDLE fallback + status IDLE + empty activity
// =========================================================================

describe("BASE: IDLE", () => {
  it("status IDLE + empty activity → idle", () => {
    expect(
      deriveAgentVisualState(
        makeAgent({ agent_id: "atlas", status: "IDLE", activity: "" }),
      ).mode,
    ).toBe("idle");
  });

  it("atlas WORKING with no matching phrase → role-fallback (planning)", () => {
    expect(
      deriveAgentVisualState(
        makeAgent({ agent_id: "atlas", status: "WORKING", activity: "" }),
      ).mode,
    ).toBe("planning");
  });
});

// =========================================================================
// 5. TRANSIENT priority: ERROR > REPAIRING > SUCCESS > REPORTING
// =========================================================================

describe("applyTransientVisualState - TRANSIENT priority", () => {
  const base: AgentVisualState = { mode: "coding", label: "Coding", active: true, attention: false };

  function transient(mode: AgentVisualMode, label = "x"): TransientAgentVisual {
    return { mode, label, attention: mode === "error" || mode === "repairing", expiresAt: Date.now() + 1000 };
  }

  it("empty transient returns base", () => {
    expect(applyTransientVisualState(base, undefined)).toEqual(base);
  });

  it("transient mode replaces base", () => {
    expect(applyTransientVisualState(base, transient("success", "Done")).mode).toBe("success");
  });

  it("transient error wins over base coding", () => {
    expect(applyTransientVisualState(base, transient("error", "Failed")).mode).toBe("error");
  });
});

// =========================================================================
// 6. Transient event resolver (via deriveAgentVisualState of synthetic agent)
//    Note: the resolver is internal. We exercise it indirectly through
//    a hook harness that exposes the resolver.
// =========================================================================

describe("Transient event resolver via hook harness", () => {
  // Lazy import the hook module to test it in isolation.
  it("imports useTransientAgentVisuals", async () => {
    const mod = await import("@/components/office-3d/semantic");
    expect(typeof mod.useTransientAgentVisuals).toBe("function");
  });
});

// =========================================================================
// 7. State merger semantics
// =========================================================================

describe("State merger", () => {
  it("transient attention propagates", () => {
    const base: AgentVisualState = { mode: "coding", label: "Coding", active: true, attention: false };
    const merged = applyTransientVisualState(base, {
      mode: "error",
      label: "Boom",
      attention: true,
      expiresAt: 999,
    });
    expect(merged.attention).toBe(true);
    expect(merged.label).toBe("Boom");
  });
});

// =========================================================================
// 8. Hook behavior: idempotency, replacement, TTL
// =========================================================================

import { renderHook, act } from "@testing-library/react";
import { vi, beforeAll } from "vitest";

describe("useTransientAgentVisuals - lifecycle", () => {
  it("duplicate ActivityItem.id is processed only once", async () => {
    const { useTransientAgentVisuals } = await import("@/components/office-3d/semantic");
    const e1 = makeEvent({ id: "a1", agent_id: "forge", message: "Task failed", kind: "STATUS" });
    const { result, rerender } = renderHook(
      ({ activity }: { activity: ActivityItem[] }) => useTransientAgentVisuals(activity),
      { initialProps: { activity: [e1] } },
    );

    expect(result.current.forge?.mode).toBe("error");

    // Re-render with the same event (same id) — should NOT replace the timer.
    rerender({ activity: [e1] });
    expect(result.current.forge?.mode).toBe("error");
    expect(Object.keys(result.current)).toHaveLength(1);
  });

  it("new event for same agent replaces prior transient", async () => {
    const { useTransientAgentVisuals } = await import("@/components/office-3d/semantic");
    const e1 = makeEvent({ id: "b1", agent_id: "forge", message: "Task failed", kind: "STATUS" });
    const e2 = makeEvent({ id: "b2", agent_id: "forge", message: "Completed successfully", kind: "RESULT" });

    const { result, rerender } = renderHook(
      ({ activity }: { activity: ActivityItem[] }) => useTransientAgentVisuals(activity),
      { initialProps: { activity: [e1] } },
    );

    expect(result.current.forge?.mode).toBe("error");

    rerender({ activity: [e1, e2] });
    expect(result.current.forge?.mode).toBe("success");
    expect(result.current.forge?.label).toBe("Completed successfully");
  });

  it("TTL expiry: transient clears", async () => {
    vi.useFakeTimers();
    const { useTransientAgentVisuals } = await import("@/components/office-3d/semantic");
    const e1 = makeEvent({ id: "c1", agent_id: "forge", message: "Task failed", kind: "STATUS" });

    const { result } = renderHook(
      ({ activity }: { activity: ActivityItem[] }) => useTransientAgentVisuals(activity),
      { initialProps: { activity: [e1] } },
    );

    expect(result.current.forge?.mode).toBe("error");

    act(() => {
      vi.advanceTimersByTime(3500);
    });

    expect(result.current.forge).toBeUndefined();
    vi.useRealTimers();
  });
});
