/**
 * Demo configuration for agent navigation.
 *
 * Enable the walking demo with the query flag `?movementDemo=1`. Each agent
 * loops: home -> waypoint(s) -> home, idling where it stands when parked.
 * Without the flag, agents never move (routes are empty).
 */

import type { Vec2 } from "./movement";
import type { AgentId } from "./waypoints";
import { waypointPosition } from "./waypoints";

export const MOVEMENT_DEMO_QUERY = "movementDemo";

/** Walking speed in metres per second (a relaxed office stroll). */
export const WALK_SPEED = 1.15;

/** Distance under which a waypoint counts as reached. */
export const ARRIVAL_DISTANCE = 0.1;

/** Idle pauses in seconds while walking the demo route. */
export const HOME_PAUSE_SECONDS = 1.2;
export const TARGET_PAUSE_SECONDS = 1.6;
export const WAYPOINT_PAUSE_SECONDS = 1.05;

export const PATROL_PAUSES = {
  home: HOME_PAUSE_SECONDS,
  target: TARGET_PAUSE_SECONDS,
  waypoint: WAYPOINT_PAUSE_SECONDS,
} as const;

/**
 * Symmetric routes: home -> ... -> destination -> ... -> home. Only the
 * waypoint ids are listed; positions come from WAYPOINTS.
 */
export const DEMO_ROUTES: Record<AgentId, readonly string[]> = {
  atlas: [
    "atlas_home",
    "meeting_approach",
    "meeting",
    "meeting_approach",
    "atlas_home",
  ],
  scout: ["scout_home", "pantry", "scout_home"],
  forge: ["forge_home", "desk_south", "center", "desk_south", "forge_home"],
  qa: ["qa_home", "meeting_approach", "meeting", "meeting_approach", "qa_home"],
  pulse: [
    "pulse_home",
    "server_approach",
    "server",
    "server_approach",
    "pulse_home",
  ],
};

export function isMovementDemoEnabled(): boolean {
  if (typeof window === "undefined") return false;
  return (
    new URLSearchParams(window.location.search).get(MOVEMENT_DEMO_QUERY) === "1"
  );
}

export function demoRouteFor(agentId: AgentId): readonly string[] | undefined {
  return isMovementDemoEnabled() ? DEMO_ROUTES[agentId] : undefined;
}

/** Resolves a route of waypoint ids into walkable (x, z) coordinates. */
export function resolveRoute(route: readonly string[]): readonly Vec2[] {
  return route.map((id) => {
    const [x, , z] = waypointPosition(id);
    return [x, z];
  });
}