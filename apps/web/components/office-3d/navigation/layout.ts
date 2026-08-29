/**
 * Office / shared-desk layout config.
 *
 * Single source of truth for where each desk agent stands/sits and for the
 * shared desk's world frame offset. The office frame and the desk frame come
 * from MainOffice: the desk group lives at world <group position={[0, 0, 0.2]}>,
 * and route waypoints (routes.ts / waypoints.ts) are authored in world space.
 *
 * The agent's rest anchor and its navigation home both derive from this file so
 * a ?movementDemo=1 patrol STARTS and ENDS exactly where the character renders
 * (no few-cm scoot between the seated posture and the nav home).
 */
import type { AgentId, Vec3 } from "./waypoints";

/** World-space offset of the SharedDesk group (the desk agents' parent frame).
 *  Subtract this from world-space waypoints to reach desk-local coordinates;
 *  add it to a desk-local anchor to reach world space. */
export const SHARED_DESK_WORLD_OFFSET: Vec3 = [0, 0, 0.2];

/** Desk agent seat geometry — the canonical input for the character anchor.
 *  Values mirror the accepted workstation seats (kept in sync with the chair
 *  rendering in SharedDesk); only the character placement derives from here. */
export interface AgentSeat {
  /** Chair position in SharedDesk local space. */
  chairPosition: readonly [number, number, number];
  /** Seat-facing world yaw (also the seat rotation in SharedDesk). */
  rotation: number;
}

export const AGENT_SEATS: Record<AgentId, AgentSeat> = {
  atlas: { chairPosition: [0, 0, -4.0], rotation: Math.PI },
  scout: { chairPosition: [-1.9, 0, -1.4], rotation: -Math.PI / 2 },
  forge: { chairPosition: [1.9, 0, -1.4], rotation: Math.PI / 2 },
  qa: { chairPosition: [-1.9, 0, 1.4], rotation: -Math.PI / 2 },
  pulse: { chairPosition: [1.9, 0, 1.4], rotation: Math.PI / 2 },
};

/** Pull the character anchor this far BEYOND the chair along the seat facing so
 *  the clips' baked sit/stand root motion plays around the accepted chair. */
const SEAT_ANCHOR_PULL = 0.15;

/**
 * Desk-local (SharedDesk frame) rest anchor for an agent — the exact place the
 * character renders when seated. This is the visual home position.
 */
export function agentRestAnchor(agentId: AgentId): Vec3 {
  const seat = AGENT_SEATS[agentId];
  const facingX = -Math.sin(seat.rotation);
  const facingZ = -Math.cos(seat.rotation);
  return [
    seat.chairPosition[0] - facingX * SEAT_ANCHOR_PULL,
    0,
    seat.chairPosition[2] - facingZ * SEAT_ANCHOR_PULL,
  ] as Vec3;
}

/** World-space rest anchor for an agent — the desk-local anchor moved into the
 *  office frame, and therefore the authoritative nav home for that agent. */
export function agentHomeWorld(agentId: AgentId): Vec3 {
  const anchor = agentRestAnchor(agentId);
  return [
    anchor[0] + SHARED_DESK_WORLD_OFFSET[0],
    anchor[1] + SHARED_DESK_WORLD_OFFSET[1],
    anchor[2] + SHARED_DESK_WORLD_OFFSET[2],
  ] as Vec3;
}
