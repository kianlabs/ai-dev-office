"use client";

/**
 * Shared patrol navigation for desk agents (?movementDemo=1).
 *
 * This is the navigation glue the committed AgentDummy ran inline, extracted
 * unchanged into a hook so both character systems can reuse the ONE
 * navigation engine (movement.ts math, routes.ts demo routes, waypoints).
 * The hook owns no animation — it moves a home group along the resolved
 * route, turns a yaw group toward travel (or the seat baseYaw when parked),
 * and reports `walking` so the caller can pick Idle vs Walking.
 */
import { useRef, useState } from "react";
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
  PATROL_PAUSES,
  WALK_SPEED,
  resolveRoute,
} from "./routes";

function lerpAngle(from: number, to: number, t: number): number {
  const diff =
    ((((to - from + Math.PI) % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2)) -
    Math.PI;
  return from + diff * t;
}

interface PatrolNavigationOptions {
  /** Home position in the parent's space (the agent's seat anchor). */
  position: readonly [number, number, number];
  /** Rest-facing yaw at home (the seat rotation). */
  baseYaw: number;
  /** Waypoint route to patrol. When absent the agent never leaves home. */
  route?: readonly string[];
  /** World→parent frame offset. Route waypoints are authored in world
   *  space, but `position` and the moved groups live in the parent group's
   *  local frame (SharedDesk sits at MainOffice world [0, 0, 0.2]). This
   *  offset is subtracted from each resolved waypoint so the whole patrol
   *  runs in the same frame as the agent. Defaults to [0, 0, 0]. */
  frameOffset?: readonly [number, number, number];
}

interface RouteState {
  waypoints: readonly Vec2[];
  cursor: number;
  /** Seconds of idle remaining at the current waypoint. */
  idle: number;
}

export function usePatrolNavigation({
  position,
  baseYaw,
  route,
  frameOffset = [0, 0, 0],
}: PatrolNavigationOptions) {
  const homeRef = useRef<Group>(null);
  const turnRef = useRef<Group>(null);

  const routeState = useRef<RouteState | null>(null);
  const positionRef = useRef<Vec2>([position[0], position[2]]);
  const yawRef = useRef(baseYaw);
  const [walking, setWalking] = useState(false);

  useFrame((_, delta) => {
    const turn = turnRef.current;
    const canPatrol = route && route.length > 1;

    if (!canPatrol) {
      if (walking) setWalking(false);
      yawRef.current = baseYaw;
      if (turn) turn.rotation.y = baseYaw;
      return;
    }

    if (!routeState.current) {
      routeState.current = {
        waypoints: resolveRoute(route).map(
          ([x, z]) => [x - frameOffset[0], z - frameOffset[2]] as Vec2,
        ),
        cursor: 0,
        idle: 0,
      };
      positionRef.current = [...routeState.current.waypoints[0]] as Vec2;
      yawRef.current = baseYaw;
    }

    const state = routeState.current;
    let moving = false;

    if (state.idle > 0) {
      state.idle -= delta;
    } else {
      const target = state.waypoints[state.cursor];
      const current: Vec2 = positionRef.current;

      if (arrived(current, target, ARRIVAL_DISTANCE)) {
        state.idle = patrolPause(
          state.cursor,
          state.waypoints.length,
          PATROL_PAUSES,
        );
        state.cursor = advanceCursor(state.cursor, state.waypoints.length);
        // Snap back to the exact home waypoint when the loop restarts so
        // float steps never compound across cycles.
        if (state.cursor === 0) {
          positionRef.current = [...state.waypoints[0]] as Vec2;
        }
      } else {
        const step = moveToward(current, target, delta, WALK_SPEED);
        positionRef.current = step.position;

        const dx = target[0] - step.position[0];
        const dz = target[1] - step.position[1];
        const desired = facingYaw(dx, dz);
        yawRef.current = lerpAngle(
          yawRef.current,
          desired,
          Math.min(1, delta * 7),
        );

        moving = step.moved;
      }
    }

    const home = homeRef.current;
    if (home) {
      home.position.set(positionRef.current[0], 0, positionRef.current[1]);
    }
    if (turn) {
      // Face the direction of travel while walking, face the seat while
      // parked at home.
      const atHome = state.cursor === 0 && state.idle > 0;
      turn.rotation.y = moving || !atHome ? yawRef.current : baseYaw;
    }
    if (moving !== walking) setWalking(moving);
  });

  return { homeRef, turnRef, walking };
}
