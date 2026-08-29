import { describe, expect, it } from "vitest";

import {
  nextPosture,
  completeStandingUp,
  completeSittingDown,
  isSeatedPosture,
  type AgentPosture,
} from "../components/office-3d/navigation/posture";
import {
  routeTo,
  routeAvoidsDesk,
  segmentIntersectsDesk,
} from "../components/office-3d/navigation/routing";
import { AGENT_HOME } from "../components/office-3d/navigation/waypoints";
import type { HandoffRole } from "../components/office-3d/navigation/handoff";

const ROLES: HandoffRole[] = ["scout", "forge", "qa", "pulse"];

describe("gated sit/stand — single-owner state machine", () => {
  it("a seated agent can only leave via STANDING_UP, never straight to MOVING", () => {
    for (const seated of ["HOME_SEATED", "WORKING_SEATED"] as const) {
      // Even with a stand goal present, it must stand up first.
      expect(nextPosture(seated, { wantsStand: true, nearHome: true, nearStand: false })).toBe(
        "STANDING_UP",
      );
      expect(isSeatedPosture(seated)).toBe(true);
    }
  });

  it("Standing only becomes possible after SitToStand completes", () => {
    // While still STANDING_UP the state does NOT advance to MOVING/idle.
    expect(nextPosture("STANDING_UP", { wantsStand: true, nearHome: true, nearStand: false })).toBe(
      "STANDING_UP",
    );
    // Once the one-shot completes, the agent is standing.
    expect(completeStandingUp()).toBe("STANDING_IDLE");
    // ... and only then can it walk to the stand point.
    expect(
      nextPosture("STANDING_IDLE", { wantsStand: true, nearHome: true, nearStand: false }),
    ).toBe("MOVING");
  });

  it("a returning agent cannot enter seated state before arrival home", () => {
    expect(
      nextPosture("RETURNING_HOME", { wantsStand: false, nearHome: false, nearStand: false }),
    ).toBe("RETURNING_HOME");
    expect(
      nextPosture("CONVERSATION", { wantsStand: false, nearHome: false, nearStand: false }),
    ).toBe("RETURNING_HOME");
    expect(
      nextPosture("MOVING", { wantsStand: false, nearHome: false, nearStand: false }),
    ).toBe("RETURNING_HOME");
  });

  it("seated state is only re-entered via SITTING_DOWN after arrival + stand->sit", () => {
    // At home and goal cleared while BETWEEN desks → still returns home first.
    expect(
      nextPosture("STANDING_IDLE", { wantsStand: false, nearHome: false, nearStand: false }),
    ).toBe("RETURNING_HOME");
    // Arrived home → SITTING_DOWN begins.
    expect(
      nextPosture("RETURNING_HOME", { wantsStand: false, nearHome: true, nearStand: false }),
    ).toBe("SITTING_DOWN");
    // SITTING_DOWN waits for the stand->sit clip.
    expect(
      nextPosture("SITTING_DOWN", { wantsStand: false, nearHome: true, nearStand: false }),
    ).toBe("SITTING_DOWN");
    expect(completeSittingDown()).toBe("WORKING_SEATED");
  });

  it("cancel mid-route returns smoothly home, never teleports to seated or stand", () => {
    // Moving to a stand point, then the goal is cleared mid-route.
    expect(
      nextPosture("MOVING", { wantsStand: false, nearHome: false, nearStand: false }),
    ).toBe("RETURNING_HOME");
    // Conversation with stand goal cleared while away → returns home.
    expect(
      nextPosture("CONVERSATION", { wantsStand: false, nearHome: false, nearStand: false }),
    ).toBe("RETURNING_HOME");
  });

  it("directive removal does not snap or reseat — state stays continuous", () => {
    // Removing a stand goal while standing away from home keeps it returning
    // (continuous), NOT seated.
    expect(
      nextPosture("STANDING_IDLE", { wantsStand: false, nearHome: false, nearStand: false }),
    ).toBe("RETURNING_HOME");
    // Removing the goal while already seated keeps it seated (no churn).
    expect(
      nextPosture("WORKING_SEATED", { wantsStand: false, nearHome: true, nearStand: false }),
    ).toBe("WORKING_SEATED");
  });

  it("repeated frame updates do not restart the seated sequence", () => {
    // A seated agent that keeps being queried stays seated (stable), it does
    // not bounce between seated states or to standing.
    const ctx = { wantsStand: false, nearHome: true, nearStand: false };
    let state: AgentPosture = "WORKING_SEATED";
    for (let i = 0; i < 100; i++) {
      state = nextPosture(state, ctx);
    }
    expect(state).toBe("WORKING_SEATED");
  });

  it("transient semantic changes do not reset locomotion", () => {
    // Semantic flashes only alter bubbles, never the posture goal: without a
    // stand goal the working agent keeps working (unaffected by rerenders).
    expect(
      nextPosture("WORKING_SEATED", { wantsStand: false, nearHome: true, nearStand: false }),
    ).toBe("WORKING_SEATED");
    expect(
      nextPosture("CONVERSATION", { wantsStand: true, nearHome: false, nearStand: true }),
    ).toBe("CONVERSATION");
  });
});

describe("desk-avoiding corridor routing (kept for ambient/demo)", () => {
  const atlasHome = AGENT_HOME.atlas; // world

  it("every seated seat anchor is itself outside the shared desk", () => {
    for (const role of ROLES) {
      const p = AGENT_HOME[role];
      expect(segmentIntersectsDesk([p[0], p[2]], [p[0], p[2]])).toBe(false);
    }
    expect(
      segmentIntersectsDesk([atlasHome[0], atlasHome[2]], [atlasHome[0], atlasHome[2]]),
    ).toBe(false);
  });

  it("ATLAS route (home → specialist seat) avoids the shared desk", () => {
    for (const role of ROLES) {
      const goal = AGENT_HOME[role];
      const route = routeTo([atlasHome[0], atlasHome[2]], [goal[0], goal[2]]);
      expect(routeAvoidsDesk(route)).toBe(true);
      // Ends exactly at the specialist seat.
      const last = route[route.length - 1];
      expect(last[0]).toBeCloseTo(goal[0], 6);
      expect(last[1]).toBeCloseTo(goal[2], 6);
    }
  });

  it("return route (specialist seat → ATLAS home) avoids the shared desk", () => {
    for (const role of ROLES) {
      const start = AGENT_HOME[role];
      const route = routeTo([start[0], start[2]], [atlasHome[0], atlasHome[2]]);
      expect(routeAvoidsDesk(route)).toBe(true);
      // Arrival home ends at the exact ATLAS home.
      const last = route[route.length - 1];
      expect(last[0]).toBeCloseTo(atlasHome[0], 6);
      expect(last[1]).toBeCloseTo(atlasHome[2], 6);
    }
  });

  it("specialist home return (own desk) avoids the desk", () => {
    for (const role of ROLES) {
      const start: [number, number] = [
        AGENT_HOME[role][0],
        AGENT_HOME[role][2],
      ];
      // From a far away point (south corridor) back to a specialist's seat.
      const route = routeTo([0, 4.0], start);
      expect(routeAvoidsDesk(route)).toBe(true);
    }
  });
});
