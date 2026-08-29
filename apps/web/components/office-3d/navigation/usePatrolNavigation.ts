"use client";

/**
 * Single-owner locomotion/posture state machine for desk agents.
 *
 * This is the ONE place that owns an agent's position, facing and posture. It
 * consumes a short-lived *goal* (stand at a conversation point, or settle to
 * the desk seat) and deterministically walks the posture machine below. The
 * caller (MixamoAgent) is a passive renderer: it plays whatever clip the
 * current posture asks for and reports clip completion upward for the one-shot
 * transitions (STANDING_UP -> STANDING_IDLE, SITTING_DOWN -> seated).
 *
 *   HOME_SEATED --[new stand goal]--> STANDING_UP --[sit->stand done]-->
 *   STANDING_IDLE --[not at goal]--> MOVING --[arrive]--> CONVERSATION
 *   CONVERSATION --[goal cleared]--> RETURNING_HOME --[arrive home]--> SITTING_DOWN
 *   STANDING_IDLE --[goal cleared, at home]--> SITTING_DOWN
 *   SITTING_DOWN --[stand->sit done]--> WORKING_SEATED/HOME_SEATED
 *
 * Hardness rules enforced here (not by offsets):
 *   - Never snap the transform to home at runtime: position is integrated
 *     continuously and only initialised to the anchor on mount.
 *   - Never start Walking while seated: MOVING is only reachable from
 *     STANDING_IDLE after STANDING_UP completes.
 *   - Never enter seated directly from MOVING/CONVERSATION: always via
 *     RETURNING_HOME arrival -> SITTING_DOWN -> seated.
 *   - The character root X/Z is persistent across directive/phase/semantic
 *     changes; AGENT_HOME is only ever a navigation destination.
 *   - All horizontal travel uses the desk-avoiding corridor (no straight-line
 *     through the desk).
 *
 * ?movementDemo=1 runs a SEPARATE standing patrol branch that never touches
 * the production handoff state.
 */
import { useCallback, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import type { Group } from "three";

import {
  advanceCursor,
  arrived,
  facingYaw,
  moveToward,
  patrolPause,
  type Vec2,
} from "./movement";
import {
  ARRIVAL_DISTANCE,
  WALK_SPEED,
  resolveRoute,
  PATROL_PAUSES,
} from "./routes";
import { routeTo } from "./routing";
import { nextPosture, type AgentPosture } from "./posture";
import type { Vec3 } from "./waypoints";

export type { AgentPosture } from "./posture";

export interface HandoffStandPoint {
  /** World-space position to walk to and stand. */
  position: Vec3;
  /** Yaw to face once parked (world space). */
  facing: number;
}

function lerpAngle(from: number, to: number, t: number): number {
  const diff =
    ((((to - from + Math.PI) % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2)) -
    Math.PI;
  return from + diff * t;
}

interface NavigationOptions {
  /** Home / rest anchor in the parent's space (the agent's desk anchor). */
  position: readonly [number, number, number];
  /** Rest-facing yaw at home (the seat rotation). */
  baseYaw: number;
  /** Demo patrol route (?movementDemo=1). Overrides handoff. Absent = never
   *  leave home for the demo. */
  route?: readonly string[];
  /** Conversation stand point (world). Absent = settle to the desk seat. */
  standPoint?: HandoffStandPoint;
  /** World→parent frame offset (SharedDesk sits at MainOffice [0,0,0.2]).
   *  Subtracted from world-space waypoints/stand points. */
  frameOffset?: readonly [number, number, number];
}

interface RoutePathState {
  /** Local-space waypoints, [0] = start, last = destination. */
  waypoints: Vec2[];
  cursor: number;
  /** Destination the path was built for (local). */
  dest: Vec2;
}

export function usePatrolNavigation({
  position,
  baseYaw,
  route,
  standPoint,
  frameOffset = [0, 0, 0],
}: NavigationOptions) {
  const homeRef = useRef<Group>(null);
  const turnRef = useRef<Group>(null);

  const stateRef = useRef<AgentPosture>("HOME_SEATED");
  const positionRef = useRef<Vec2>([position[0], position[2]]);
  const yawRef = useRef(baseYaw);
  const pathRef = useRef<RoutePathState | null>(null);

  const [posture, setPosture] = useState<AgentPosture>("HOME_SEATED");
  const [walking, setWalking] = useState(false);

  // ---- demo branch state (isolated from production handoff) ----------------
  const demoRoute = useRef<{ waypoints: Vec2[]; cursor: number; idle: number } | null>(null);

  const buildPath = useCallback(
    (currentLocal: Vec2, destLocal: Vec2): Vec2[] => {
      const cw: Vec2 = [currentLocal[0] + frameOffset[0], currentLocal[1] + frameOffset[2]];
      const gw: Vec2 = [destLocal[0] + frameOffset[0], destLocal[1] + frameOffset[2]];
      return routeTo(cw, gw).map(([x, z]) => [x - frameOffset[0], z - frameOffset[2]] as Vec2);
    },
    [frameOffset],
  );

  const startMove = (current: Vec2, dest: Vec2) => {
    const waypoints = buildPath(current, dest);
    pathRef.current = { waypoints, cursor: 1, dest };
  };

  /** Advance along the current path toward `dest`; returns arrived flag. */
  const stepPath = (delta: number, dest: Vec2): { arrived: boolean } => {
    const current = positionRef.current;
    let path = pathRef.current;
    if (!path || path.dest[0] !== dest[0] || path.dest[1] !== dest[1]) {
      startMove(current, dest);
      path = pathRef.current!;
    }
    let cursor = path.cursor;
    while (
      cursor < path.waypoints.length &&
      arrived(current, path.waypoints[cursor], ARRIVAL_DISTANCE)
    ) {
      cursor++;
    }
    if (cursor >= path.waypoints.length) {
      path.cursor = cursor;
      return { arrived: true };
    }
    const step = moveToward(current, path.waypoints[cursor], delta, WALK_SPEED);
    positionRef.current = step.position;
    path.cursor = cursor;

    const dx = path.waypoints[cursor][0] - step.position[0];
    const dz = path.waypoints[cursor][1] - step.position[1];
    yawRef.current = lerpAngle(yawRef.current, facingYaw(dx, dz), Math.min(1, delta * 7));
    return { arrived: false };
  };

  /** Called by the renderer when a one-shot clip (sit/stand) finishes. */
  const finishOneShot = useCallback(() => {
    if (stateRef.current === "STANDING_UP") {
      stateRef.current = "STANDING_IDLE";
    } else if (stateRef.current === "SITTING_DOWN") {
      stateRef.current = "WORKING_SEATED";
    }
  }, []);

  // ---- demo patrol (standing) — separate state, never touches handoff ----
  const runDemo = (home: Group | null, turn: Group | null, delta: number) => {
    if (!demoRoute.current) {
      demoRoute.current = {
        waypoints: resolveRoute(route as readonly string[]).map(
          ([x, z]) => [x - frameOffset[0], z - frameOffset[2]] as Vec2,
        ),
        cursor: 0,
        idle: 0,
      };
      positionRef.current = [...demoRoute.current.waypoints[0]] as Vec2;
      yawRef.current = baseYaw;
    }
    const state = demoRoute.current;
    let moving = false;
    if (state.idle > 0) {
      state.idle -= delta;
    } else {
      const target = state.waypoints[state.cursor];
      const current = positionRef.current;
      if (arrived(current, target, ARRIVAL_DISTANCE)) {
        state.idle = patrolPause(state.cursor, state.waypoints.length, PATROL_PAUSES);
        state.cursor = advanceCursor(state.cursor, state.waypoints.length);
        if (state.cursor === 0) {
          positionRef.current = [...state.waypoints[0]] as Vec2;
        }
      } else {
        const step = moveToward(current, target, delta, WALK_SPEED);
        positionRef.current = step.position;
        const dx = target[0] - step.position[0];
        const dz = target[1] - step.position[1];
        yawRef.current = lerpAngle(yawRef.current, facingYaw(dx, dz), Math.min(1, delta * 7));
        moving = step.moved;
      }
    }
    if (home) home.position.set(positionRef.current[0], 0, positionRef.current[1]);
    if (turn) {
      const atHome = state.cursor === 0 && state.idle > 0;
      turn.rotation.y = moving || !atHome ? yawRef.current : baseYaw;
    }
    setWalking(moving);
    setPosture(moving ? "MOVING" : "STANDING_IDLE");
  };

  useFrame((_, delta) => {
    const turn = turnRef.current;
    const home = homeRef.current;

    if (route && route.length > 1) {
      runDemo(home, turn, delta);
      return;
    }
    // No demo route → reset demo state so re-entry starts fresh.
    demoRoute.current = null;

    const homeLocal: Vec2 = [position[0], position[2]];
    const standLocal: Vec2 | null = standPoint
      ? [standPoint.position[0] - frameOffset[0], standPoint.position[2] - frameOffset[2]]
      : null;
    // 'seat' settles to the desk; a stand point implies standing at it.
    const wantsStand = Boolean(standLocal);

    const current = positionRef.current;
    const nearHome = arrived(current, homeLocal, ARRIVAL_DISTANCE);
    const nearStand = standLocal ? arrived(current, standLocal, ARRIVAL_DISTANCE) : false;

    let movingNow = false;

    const next = nextPosture(stateRef.current, { wantsStand, nearHome, nearStand });

    // Movement side effects — only MOVING / RETURNING_HOME integrate position.
    if (next === "MOVING") {
      const m = stepPath(delta, standLocal!);
      movingNow = true;
      if (m.arrived) {
        positionRef.current = [...(standLocal as Vec2)] as Vec2;
        yawRef.current = standPoint!.facing;
        stateRef.current = "CONVERSATION";
        if (home) home.position.set(positionRef.current[0], 0, positionRef.current[1]);
        if (turn) turn.rotation.y = yawRef.current;
        setWalking(false);
        setPosture(stateRef.current);
        return;
      }
    } else if (next === "RETURNING_HOME") {
      const m = stepPath(delta, homeLocal);
      movingNow = true;
      if (m.arrived) {
        positionRef.current = [...homeLocal] as Vec2;
        yawRef.current = baseYaw;
        stateRef.current = "SITTING_DOWN";
        if (home) home.position.set(positionRef.current[0], 0, positionRef.current[1]);
        if (turn) turn.rotation.y = yawRef.current;
        setWalking(false);
        setPosture(stateRef.current);
        return;
      }
    } else if (next === "CONVERSATION" && wantsStand) {
      yawRef.current = standPoint!.facing;
    }

    stateRef.current = next;
    setWalking(movingNow);
    setPosture(stateRef.current);

    if (home) home.position.set(positionRef.current[0], 0, positionRef.current[1]);
    if (turn) turn.rotation.y = yawRef.current;
  });

  return { homeRef, turnRef, posture, walking, finishOneShot };
}
