/**
 * Named waypoints in world space (Office 3D frame).
 *
 * Mandate: agent "home" positions here are the single source of truth for
 * where the characters stand. SharedDesk places the AgentDummy at exactly
 * these coordinates, and the demo routes both start and return to them, so
 * the characters never drift from their rendered seat position.
 *
 * Homes were derived from the SharedDesk seat transforms (seat origin +
 * rotation applied to the agent offset) and the MainOffice offset group
 * `<group position={[0, 0, 0.2]}>` that hosts the desk. Do not change them
 * casually, and never change SharedDesk without updating this file.
 */

export type AgentId = "atlas" | "scout" | "forge" | "qa" | "pulse";

export type Vec3 = readonly [number, number, number];

export const AGENT_HOME: Record<AgentId, Vec3> = {
  atlas: [0, 0, -4.1],
  scout: [-2.325, 0, -1.2],
  forge: [2.325, 0, -1.2],
  qa: [-2.325, 0, 1.6],
  pulse: [2.325, 0, 1.6],
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