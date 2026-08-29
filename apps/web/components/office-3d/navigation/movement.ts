/**
 * Pure movement + patrol math. No React, no three.js, no scene access — safe
 * to unit-test in isolation and to reuse from any component or future agent
 * driver.
 */

export type Vec2 = readonly [number, number];

export function distance2d(a: Vec2, b: Vec2): number {
  return Math.hypot(b[0] - a[0], b[1] - a[1]);
}

export function arrived(
  current: Vec2,
  target: Vec2,
  threshold: number,
): boolean {
  return distance2d(current, target) <= threshold;
}

export interface MoveStep {
  position: Vec2;
  moved: boolean;
  remaining: number;
}

/** Moves `current` toward `target` by `speed * dt` at most. The step is
 *  clamped to the remaining distance, so the mover never overshoots and
 *  never jitters in place once the target is reached. */
export function moveToward(
  current: Vec2,
  target: Vec2,
  dt: number,
  speed: number,
): MoveStep {
  const dx = target[0] - current[0];
  const dz = target[1] - current[1];
  const distance = Math.hypot(dx, dz);

  if (distance <= 0 || dt <= 0 || speed <= 0) {
    return { position: current, moved: false, remaining: distance };
  }

  const step = Math.min(distance, speed * dt);
  const k = step / distance;

  return {
    position: [current[0] + dx * k, current[1] + dz * k],
    moved: step > 0,
    remaining: distance - step,
  };
}

/** World Y-rotation (yaw) that makes the character's front (-Z) point along
 *  (+dx, +dz). Verified: moving -Z -> 0, +X -> -PI/2, +Z -> PI, -X -> PI/2.
 *  The kit models are flipped to face local -Z inside AgentCharacter. */
export function facingYaw(dx: number, dz: number): number {
  return Math.atan2(-dx, -dz);
}

/** Patrol cursor: advance one waypoint. Routes are symmetric loops
 *  ([home, ..., target, ..., home]), so the cursor wraps from the last
 *  waypoint back to 1 (the first step after home). */
export function advanceCursor(cursor: number, length: number): number {
  return (cursor + 1) % length;
}

export interface PatrolPauses {
  home: number;
  target: number;
  waypoint: number;
}

/** Idle pause to take when arrived at `cursor`, with `length` waypoints.
 *  Home sits at both ends (cursor 0 and cursor length - 1); the outbound
 *  destination is the midpoint of the symmetric route. */
export function patrolPause(
  cursor: number,
  length: number,
  pauses: PatrolPauses,
): number {
  if (cursor === 0 || cursor === length - 1) return pauses.home;
  if (cursor === Math.floor(length / 2)) return pauses.target;
  return pauses.waypoint;
}