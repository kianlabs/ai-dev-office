/**
 * Desk-avoiding corridor routing for the shared desk.
 *
 * The shared desk sits at the centre of the office with a rectangular footprint
 * (world XZ). Agents must never walk straight through it, so all movement —
 * handoff, return-home, cancel — is routed along a fixed OUTER corridor that
 * wraps the desk. Route segments are axis-aligned along the corridor, all of
 * them OUTSIDE the desk footprint.
 *
 * Corridor node positions are world-space on the shared-desk frame's XZ plane
 * (y is always 0 and ignored). Interaction/approach points reuse these nodes
 * (scout/qa on the west corridor, forge/pulse on the east corridor), so the
 * ATLAS handoff route naturally terminates exactly at a corridor node.
 *
 * Pure + testable; no React / three.js.
 */
import { ARRIVAL_DISTANCE } from "./routes";
import { distance2d, type Vec2 } from "./movement";

/** Shared-desk footprint (world XZ), matching the rendered tabletop. */
export const DESK_MIN_X = -1.575;
export const DESK_MAX_X = 1.575;
export const DESK_MIN_Z = -3.2;
export const DESK_MAX_Z = 3.6;

export interface CorridorNode {
  id: string;
  position: readonly [number, number];
}

/**
 * Outer corridor nodes around the desk (world XZ). Every node is outside the
 * footprint; the ring fully encircles the desk so any two points can route
 * around without crossing it.
 */
export const CORRIDOR_NODES: readonly CorridorNode[] = [
  { id: "n_mid", position: [0, -3.9] }, // north central (atlas gateway)
  { id: "nw", position: [-3.7, -3.9] },
  { id: "ne", position: [3.7, -3.9] },
  { id: "w_s", position: [-3.7, -1.2] }, // scout approach / interaction
  { id: "w_mid", position: [-3.7, 0.2] },
  { id: "w_q", position: [-3.7, 1.6] }, // qa approach / interaction
  { id: "e_f", position: [3.7, -1.2] }, // forge approach / interaction
  { id: "e_mid", position: [3.7, 0.2] },
  { id: "e_p", position: [3.7, 1.6] }, // pulse approach / interaction
  { id: "sw", position: [-3.7, 4.0] },
  { id: "se", position: [3.7, 4.0] },
  { id: "s_mid", position: [0, 4.0] }, // south central
];

const NODE_POS: Record<string, readonly [number, number]> = Object.fromEntries(
  CORRIDOR_NODES.map((n) => [n.id, n.position]),
);

/** Undirected corridor edges (perimeter ring). */
export const CORRIDOR_EDGES: readonly (readonly [string, string])[] = [
  ["nw", "n_mid"],
  ["n_mid", "ne"],
  ["nw", "w_s"],
  ["w_s", "w_mid"],
  ["w_mid", "w_q"],
  ["w_q", "sw"],
  ["ne", "e_f"],
  ["e_f", "e_mid"],
  ["e_mid", "e_p"],
  ["e_p", "se"],
  ["sw", "s_mid"],
  ["s_mid", "se"],
];

const ADJ: Record<string, readonly string[]> = CORRIDOR_EDGES.reduce(
  (acc, [a, b]) => {
    (acc[a] ??= []).push(b);
    (acc[b] ??= []).push(a);
    return acc;
  },
  {} as Record<string, string[]>,
);

function nearestNodeId(position: Vec2): string {
  let best = CORRIDOR_NODES[0].id;
  let bestDist = Infinity;
  for (const node of CORRIDOR_NODES) {
    const d = distance2d(position, node.position);
    if (d < bestDist) {
      bestDist = d;
      best = node.id;
    }
  }
  return best;
}

/** Shortest corridor node path (node ids) from `startId` to `goalId`. */
function corridorPath(startId: string, goalId: string): string[] {
  if (startId === goalId) return [startId];

  const queue: string[] = [startId];
  const prev: Record<string, string | null> = { [startId]: null };
  const seen = new Set<string>([startId]);

  while (queue.length > 0) {
    const current = queue.shift()!;
    for (const next of ADJ[current] ?? []) {
      if (seen.has(next)) continue;
      seen.add(next);
      prev[next] = current;
      if (next === goalId) {
        const path: string[] = [];
        let cursor: string | null = goalId;
        while (cursor !== null) {
          path.unshift(cursor);
          cursor = prev[cursor];
        }
        return path;
      }
      queue.push(next);
    }
  }

  // Unreachable — every node is connected, but keep a safe fallback.
  return [startId, goalId];
}

/**
 * Build a desk-avoiding waypoint path from `start` to `goal` (world XZ).
 * Returns [start, ...corridor nodes..., goal] with consecutive duplicates
 * removed. When start and goal are effectively the same point, returns [start].
 *
 * The straight leg between any two consecutive waypoints never crosses the
 * shared-desk footprint (the corridor ring is entirely outside it, and the
 * start/end legs are short hops from the desk-edge seats to the nearest
 * corridor node, still on their own side of the desk).
 */
export function routeTo(start: Vec2, goal: Vec2): Vec2[] {
  if (distance2d(start, goal) <= ARRIVAL_DISTANCE) return [start];

  const startNode = nearestNodeId(start);
  const goalNode = nearestNodeId(goal);
  const corridor = corridorPath(startNode, goalNode);

  const raw: Vec2[] = [
    start,
    ...corridor.map((id) => NODE_POS[id] as Vec2),
    goal,
  ];

  const out: Vec2[] = [];
  for (const point of raw) {
    const last = out[out.length - 1];
    if (!last || distance2d(last, point) > 1e-6) out.push(point);
  }
  return out;
}

/** True if the segment [a, b] passes through the shared-desk footprint. */
export function segmentIntersectsDesk(
  a: Vec2,
  b: Vec2,
): boolean {
  // Sample the segment; if any sample is inside the footprint, it crosses.
  const samples = 32;
  for (let i = 1; i < samples; i++) {
    const t = i / samples;
    const x = a[0] + (b[0] - a[0]) * t;
    const z = a[1] + (b[1] - a[1]) * t;
    if (x > DESK_MIN_X && x < DESK_MAX_X && z > DESK_MIN_Z && z < DESK_MAX_Z) {
      return true;
    }
  }
  return false;
}

/** True if EVERY consecutive segment of `route` avoids the desk footprint. */
export function routeAvoidsDesk(route: readonly Vec2[]): boolean {
  for (let i = 0; i < route.length - 1; i++) {
    if (segmentIntersectsDesk(route[i], route[i + 1])) return false;
  }
  return true;
}
