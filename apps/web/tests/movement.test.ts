import { describe, expect, it } from "vitest";

import {
  advanceCursor,
  arrived,
  distance2d,
  facingYaw,
  moveToward,
  patrolPause,
} from "../components/office-3d/navigation/movement";
import {
  ARRIVAL_DISTANCE,
  DEMO_ROUTES,
  PATROL_PAUSES,
  WALK_SPEED,
  resolveRoute,
} from "../components/office-3d/navigation/routes";
import type { Vec2 } from "../components/office-3d/navigation/movement";
import {
  AGENT_HOME,
  WAYPOINTS,
  type AgentId,
} from "../components/office-3d/navigation/waypoints";

describe("distance2d", () => {
  it("measures horizontal plane distance", () => {
    expect(distance2d([0, 0], [3, 4])).toBeCloseTo(5, 10);
  });

  it("returns zero for coincident points", () => {
    expect(distance2d([1, -2], [1, -2])).toBe(0);
  });
});

describe("arrived", () => {
  it("is true within the threshold", () => {
    expect(arrived([0, 0], [0.05, 0], 0.1)).toBe(true);
  });

  it("is false beyond the threshold", () => {
    expect(arrived([0, 0], [0.5, 0], 0.1)).toBe(false);
  });

  it("is true on the boundary", () => {
    expect(arrived([0, 0], [0.1, 0], 0.1)).toBe(true);
  });
});

describe("moveToward", () => {
  it("moves along the travel direction (axis-aligned)", () => {
    const step = moveToward([0, 0], [10, 0], 1, 2);
    expect(step.position[0]).toBeCloseTo(2, 10);
    expect(step.position[1]).toBeCloseTo(0, 10);
    expect(step.moved).toBe(true);
    expect(step.remaining).toBeCloseTo(8, 10);
  });

  it("moves toward -Z (x constant, z decreases)", () => {
    const step = moveToward([0, 0], [0, -10], 1, 2);
    expect(step.position[0]).toBeCloseTo(0, 10);
    expect(step.position[1]).toBeCloseTo(-2, 10);
  });

  it("never overshoots even with huge dt or speed", () => {
    const step = moveToward([0, 0], [1, 0], 10, 1000);
    expect(step.position[0]).toBeCloseTo(1, 10);
    expect(step.position[1]).toBeCloseTo(0, 10);
    expect(step.remaining).toBeCloseTo(0, 10);
  });

  it("reports no movement once the target is reached", () => {
    const reached = moveToward([1, 1], [1, 1], 1, 5);
    expect(reached.moved).toBe(false);
    expect(reached.position).toEqual([1, 1]);
  });

  it("reports no movement for a zero/negative step", () => {
    const step = moveToward([0, 0], [3, 0], -0.1, 2);
    expect(step.moved).toBe(false);
    expect(step.remaining).toBeCloseTo(3, 10);
  });
});

describe("facingYaw", () => {
  const facing = (dx: number, dz: number) => {
    const yaw = facingYaw(dx, dz);
    const r = Math.hypot(dx, dz);
    return [(-Math.sin(yaw) * r), (-Math.cos(yaw) * r)];
  };

  it("returns 0-ish heading when moving toward -Z", () => {
    const [fx, fz] = facing(0, -1);
    expect(fx).toBeCloseTo(0, 10);
    expect(fz).toBeCloseTo(-1, 10);
  });

  it("turns -PI/2 when moving toward +X", () => {
    expect(facingYaw(1, 0)).toBeCloseTo(-Math.PI / 2, 10);
  });

  it("faces +Z when moving toward +Z", () => {
    const [fx, fz] = facing(0, 1);
    expect(fx).toBeCloseTo(0, 10);
    expect(fz).toBeCloseTo(1, 10);
  });

  it("turns PI/2 when moving toward -X", () => {
    expect(facingYaw(-1, 0)).toBeCloseTo(Math.PI / 2, 10);
  });

  it("projects front (-Z) onto the movement direction", () => {
    const [fx, fz] = facing(1, 1);
    expect(fx).toBeCloseTo(1, 10);
    expect(fz).toBeCloseTo(1, 10);
  });
});

describe("advanceCursor", () => {
  it("walks forward through a 5-waypoint loop", () => {
    let cursor = 0;
    const expected = [1, 2, 3, 4, 0];
    for (const next of expected) {
      cursor = advanceCursor(cursor, 5);
      expect(cursor).toBe(next);
    }
  });

  it("wraps the last waypoint back toward the start", () => {
    expect(advanceCursor(4, 5)).toBe(0);
  });
});

describe("patrolPause", () => {
  it("pauses at home (both ends of a symmetric route)", () => {
    expect(patrolPause(0, 5, PATROL_PAUSES)).toBe(PATROL_PAUSES.home);
    expect(patrolPause(4, 5, PATROL_PAUSES)).toBe(PATROL_PAUSES.home);
  });

  it("pauses longest at the outbound target (midpoint)", () => {
    expect(patrolPause(2, 5, PATROL_PAUSES)).toBe(PATROL_PAUSES.target);
  });

  it("uses the short pause for transit waypoints", () => {
    expect(patrolPause(1, 5, PATROL_PAUSES)).toBe(PATROL_PAUSES.waypoint);
    expect(patrolPause(3, 5, PATROL_PAUSES)).toBe(PATROL_PAUSES.waypoint);
  });

  it("handles 3-waypoint routes", () => {
    expect(patrolPause(0, 3, PATROL_PAUSES)).toBe(PATROL_PAUSES.home);
    expect(patrolPause(1, 3, PATROL_PAUSES)).toBe(PATROL_PAUSES.target);
    expect(patrolPause(2, 3, PATROL_PAUSES)).toBe(PATROL_PAUSES.home);
  });
});

describe("demo routes", () => {
  const REQUIRED_WAYPOINTS = [
    "atlas_home",
    "scout_home",
    "forge_home",
    "qa_home",
    "pulse_home",
    "meeting",
    "server",
    "pantry",
    "lounge",
    "center",
  ] as const;

  const routeLength = (coords: readonly Vec2[]) => {
    let total = 0;
    for (let i = 0; i < coords.length - 1; i++) {
      total += distance2d(coords[i], coords[i + 1]);
    }
    return total;
  };

  it("defines every required waypoint", () => {
    for (const id of REQUIRED_WAYPOINTS) {
      expect(WAYPOINTS[id], id).toBeDefined();
    }
  });

  it("defines a route for every agent", () => {
    const agents = Object.keys(AGENT_HOME) as AgentId[];
    expect(agents.sort()).toEqual(["atlas", "forge", "pulse", "qa", "scout"]);
    for (const agentId of agents) {
      expect(DEMO_ROUTES[agentId], agentId).toBeDefined();
    }
  });

  it("routes are symmetric home -> destination -> home loops", () => {
    for (const agentId of Object.keys(DEMO_ROUTES) as AgentId[]) {
      const route = DEMO_ROUTES[agentId];
      expect(route.length % 2, agentId).toBe(1);
      expect(route.length, agentId).toBeGreaterThanOrEqual(3);
      expect(route[0], agentId).toBe(route[route.length - 1]);
    }
  });

  it("all route waypoints resolve and nothing lies on the shared desk", () => {
    for (const agentId of Object.keys(DEMO_ROUTES) as AgentId[]) {
      const coords = resolveRoute(DEMO_ROUTES[agentId]);
      for (const [x, z] of coords) {
        expect(Number.isFinite(x)).toBe(true);
        expect(Number.isFinite(z)).toBe(true);
        // Shared desk footprint is x [-1.575, 1.575] / z [-3.2, 3.6].
        expect(Math.abs(x) > 1.575 || z < -3.2 || z > 3.6, agentId).toBe(true);
      }
    }
  });

  it("home waypoints match AGENT_HOME exactly", () => {
    for (const agentId of Object.keys(DEMO_ROUTES) as AgentId[]) {
      const [hx, , hz] = AGENT_HOME[agentId];
      const coords = resolveRoute(DEMO_ROUTES[agentId]);
      expect(distance2d(coords[0], [hx, hz]), agentId).toBe(0);
      expect(distance2d(coords[coords.length - 1], [hx, hz]), agentId).toBe(0);
    }
  });

  it("walks each route to the end without teleporting", () => {
    const maxStep = WALK_SPEED / 60 + 1e-9;
    for (const agentId of Object.keys(DEMO_ROUTES) as AgentId[]) {
      const coords = resolveRoute(DEMO_ROUTES[agentId]);
      let current = coords[0];
      let travelled = 0;
      let frameGuard = 0;

      for (let i = 1; i < coords.length; i++) {
        const target = coords[i];
        while (
          distance2d(current, target) > ARRIVAL_DISTANCE &&
          frameGuard < 100_000
        ) {
          const step = moveToward(current, target, 1 / 60, WALK_SPEED);
          const stepDistance = distance2d(current, step.position);
          // Never teleport: each frame covers at most speed * dt.
          expect(stepDistance, agentId).toBeLessThanOrEqual(maxStep);
          expect(stepDistance, agentId).toBeGreaterThan(0);
          travelled += stepDistance;
          current = step.position;
          frameGuard++;
        }
      }

      // The walk covers the full route length.
      const expected = routeLength(coords);
      expect(Math.abs(travelled - expected), agentId).toBeLessThanOrEqual(
        ARRIVAL_DISTANCE * coords.length,
      );
    }
  });
});