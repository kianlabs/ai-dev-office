"use client";

import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import type { Group } from "three";

import type { AgentVisualMode } from "../semantic";

interface AgentDummyProps {
  position: [number, number, number];
  color?: string;
  mode?: AgentVisualMode;
}

// Procedural placeholder animation.
//
// This component intentionally knows only the semantic visual mode.
// It does not know about tasks, WebSockets, ATLAS routing, or backend events.
// A future GLB character can preserve this same contract.
export default function AgentDummy({
  position,
  color = "#3b82f6",
  mode = "idle",
}: AgentDummyProps) {
  const actorRef = useRef<Group>(null);

  useFrame(({ clock }) => {
    const actor = actorRef.current;
    if (!actor) return;

    const t = clock.getElapsedTime();

    let y = 0;
    let rotX = 0;
    let rotY = 0;
    let rotZ = 0;

    switch (mode) {
      case "idle":
        y = Math.sin(t * 1.1) * 0.008;
        rotY = Math.sin(t * 0.45) * 0.035;
        break;

      case "planning":
        y = Math.sin(t * 1.8) * 0.006;
        rotZ = Math.sin(t * 1.2) * 0.025;
        rotX = -0.035;
        break;

      case "researching":
        y = Math.sin(t * 2.2) * 0.006;
        rotY = Math.sin(t * 1.5) * 0.045;
        rotX = -0.025;
        break;

      case "coding":
        y = Math.abs(Math.sin(t * 5.5)) * 0.012;
        rotX = -0.055 + Math.sin(t * 4.5) * 0.008;
        break;

      case "repairing":
        y = Math.abs(Math.sin(t * 8.5)) * 0.016;
        rotX = -0.075 + Math.sin(t * 7) * 0.012;
        rotZ = Math.sin(t * 5) * 0.01;
        break;

      case "testing":
        y = Math.sin(t * 3.1) * 0.006;
        rotY = Math.sin(t * 2.4) * 0.025;
        break;

      case "monitoring":
        y = Math.sin(t * 1.5) * 0.006;
        rotY = Math.sin(t * 0.8) * 0.055;
        break;

      case "reporting":
        y = Math.abs(Math.sin(t * 2.8)) * 0.014;
        rotY = Math.sin(t * 2.2) * 0.08;
        break;

      case "waiting":
        y = Math.sin(t * 0.8) * 0.004;
        rotZ = Math.sin(t * 0.6) * 0.018;
        break;

      case "success":
        y = Math.abs(Math.sin(t * 3.2)) * 0.025;
        rotY = Math.sin(t * 2.2) * 0.06;
        break;

      case "error":
        y = Math.abs(Math.sin(t * 6.5)) * 0.012;
        rotZ = Math.sin(t * 7.5) * 0.035;
        break;
    }

    actor.position.y = y;
    actor.rotation.x = rotX;
    actor.rotation.y = rotY;
    actor.rotation.z = rotZ;
  });

  return (
    <group position={position}>
      <group ref={actorRef}>
        {/* legs */}
        <mesh position={[0, 0.3, 0]} castShadow>
          <capsuleGeometry args={[0.06, 0.5, 4, 8]} />
          <meshStandardMaterial color={color} roughness={0.6} />
        </mesh>

        {/* torso */}
        <mesh position={[0, 0.72, 0]} castShadow>
          <capsuleGeometry args={[0.16, 0.28, 4, 8]} />
          <meshStandardMaterial color={color} roughness={0.6} />
        </mesh>

        {/* head */}
        <mesh position={[0, 1.08, 0]} castShadow>
          <sphereGeometry args={[0.11, 16, 12]} />
          <meshStandardMaterial color="#d8cbb8" roughness={0.7} />
        </mesh>
      </group>
    </group>
  );
}
