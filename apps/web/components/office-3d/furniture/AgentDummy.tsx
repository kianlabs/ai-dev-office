"use client";

import { useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import type { Group } from "three";

import AgentCharacter from "../agents/AgentCharacter";
import type { AgentVisualMode } from "../semantic";
import {
  advanceCursor,
  arrived,
  facingYaw,
  moveToward,
  patrolPause,
  type Vec2,
} from "../navigation/movement";
import {
  ARRIVAL_DISTANCE,
  PATROL_PAUSES,
  WALK_SPEED,
  resolveRoute,
} from "../navigation/routes";

interface AgentDummyProps {
  /** World position of the agent's home (see navigation/waypoints). */
  position: readonly [number, number, number];
  mode?: AgentVisualMode;
  modelPath: string;
  /** Rest-facing yaw at home (the seat rotation). */
  baseYaw?: number;
  /** Waypoint route to patrol. When absent the agent never leaves home. */
  route?: readonly string[];
}

interface RouteState {
  waypoints: readonly Vec2[];
  cursor: number;
  /** Seconds of idle remaining at the current waypoint. */
  idle: number;
}

function lerpAngle(from: number, to: number, t: number): number {
  const diff =
    ((((to - from + Math.PI) % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2)) -
    Math.PI;
  return from + diff * t;
}

export default function AgentDummy({
  position,
  mode = "idle",
  modelPath,
  baseYaw = 0,
  route,
}: AgentDummyProps) {
  const homeRef = useRef<Group>(null);
  const turnRef = useRef<Group>(null);
  const actorRef = useRef<Group>(null);

  const routeState = useRef<RouteState | null>(null);
  const positionRef = useRef<Vec2>([position[0], position[2]]);
  const yawRef = useRef(baseYaw);
  const [walking, setWalking] = useState(false);

  useFrame(({ clock }, delta) => {
    const actor = actorRef.current;
    if (!actor) return;

    const t = clock.getElapsedTime();

    let y = 0;
    let rotX = 0;
    let rotY = 0;
    let rotZ = 0;

    switch (mode) {
      // "idle" is left empty: AgentCharacter already plays the character's
      // native Idle animation, so an extra bob here would double-motion.
      case "idle":
        break;

      case "planning":
        rotX = -0.03;
        break;

      case "dispatching":
        rotY = Math.sin(t * 3) * 0.05;
        break;

      case "researching":
        rotX = -0.025;
        break;

      case "coding":
      case "building":
        rotX = -0.05;
        break;

      case "repairing":
        rotX = -0.07;
        rotZ = Math.sin(t * 5) * 0.01;
        break;

      case "testing":
        rotY = Math.sin(t * 2.4) * 0.025;
        break;

      case "monitoring":
        rotY = Math.sin(t * 0.8) * 0.055;
        break;

      case "reporting":
        rotY = Math.sin(t * 2.2) * 0.08;
        break;

      case "waiting":
        rotZ = Math.sin(t * 0.6) * 0.018;
        break;

      case "success":
        y = Math.abs(Math.sin(t * 3.2)) * 0.025;
        break;

      case "error":
        rotZ = Math.sin(t * 7.5) * 0.035;
        break;
    }

    actor.position.y = y;
    actor.rotation.x = rotX;
    actor.rotation.y = rotY;
    actor.rotation.z = rotZ;

    // ---- Route movement (only active when a route is provided) ----
    const turn = turnRef.current;
    const home = homeRef.current;
    const canPatrol = route && route.length > 1;

    if (!canPatrol) {
      if (walking) setWalking(false);
      yawRef.current = baseYaw;
      if (turn) turn.rotation.y = baseYaw;
      return;
    }

    if (!routeState.current) {
      routeState.current = {
        waypoints: resolveRoute(route),
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

  return (
    <group position={[position[0], position[1], position[2]]} ref={homeRef}>
      <group ref={turnRef}>
        <group ref={actorRef}>
          <AgentCharacter
            modelPath={modelPath}
            scale={0.9}
            animation={walking ? "Walk" : "Idle"}
          />
        </group>
      </group>
    </group>
  );
}