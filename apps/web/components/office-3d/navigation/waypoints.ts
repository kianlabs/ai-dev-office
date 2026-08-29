/**
 * Named waypoints in world space (Office 3D frame).
 *
 * Agent "home" waypoints are derived from the shared-desk layout (layout.ts)
 * so the navigation demo starts and returns to exactly where each character
 * renders — never drifting from the visual home.
 *
 * All non-home waypoints (meeting, server, pantry, lounge, center, …) are
 * authored here in the office frame.
 */

import { agentHomeWorld } from "./layout";

export type AgentId = "atlas" | "scout" | "forge" | "qa" | "pulse";

export type Vec3 = readonly [number, number, number];

/** Agent rest homes are derived from the shared-desk layout so they always
 *  coincide with the rendered character anchors (see layout.ts). */
export const AGENT_HOME: Record<AgentId, Vec3> = {
  atlas: agentHomeWorld("atlas"),
  scout: agentHomeWorld("scout"),
  forge: agentHomeWorld("forge"),
  qa: agentHomeWorld("qa"),
  pulse: agentHomeWorld("pulse"),
};

/** Rest-facing yaw (world Y-rotation) that reproduces the current seated
 *  orientation — equal to each seat's rotation in SharedDesk. */
export const AGENT_BASE_YAW: Record<AgentId, number> = {
  atlas: Math.PI,
  scout: -Math.PI / 2,
  forge: Math.PI / 2,
  qa: -Math.PI / 2,
  pulse: Math.PI / 2,
};

export const WAYPOINTS: Record<string, Vec3> = {
  // Agent homes (same positions as AGENT_HOME).
  atlas_home: AGENT_HOME.atlas,
  scout_home: AGENT_HOME.scout,
  forge_home: AGENT_HOME.forge,
  qa_home: AGENT_HOME.qa,
  pulse_home: AGENT_HOME.pulse,

  // Meeting room entrance. The door is on the room's -Z wall (world z =
  // -5.55); standing 0.5 m in front in the back corridor keeps the agent out
  // of the glass. meeting_approach routes around the room's east corner.
  meeting: [-7.55, 0, -6.1],
  meeting_approach: [-4.6, 0, -6.2],

  // Server room entrance, mirrored on the east side (door wall at z = -5.5).
  server: [7.65, 0, -6.1],
  server_approach: [4.9, 0, -6.3],

  // Pantry — open lounge area; waypoint is clear of the round table, chairs
  // and the counter.
  pantry: [-6.0, 0, 5.2],

  // Lounge — front edge of the rug, clear of console, table and sofa.
  lounge: [7.2, 0, 4.1],

  // Centre of the office, south of the shared desk (desk front is z = 3.6).
  center: [0, 0, 4.3],

  // South-east pass-around point to get from the right-side seats to the
  // centre / south of the office without clipping the desk or foosball table.
  desk_south: [2.1, 0, 3.9],
};

export function waypointPosition(id: string): Vec3 {
  const position = WAYPOINTS[id];
  if (!position) {
    throw new Error(`Unknown waypoint: "${id}"`);
  }
  return position;
}