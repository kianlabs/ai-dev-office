"use client";

import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import type { Group } from "three";

import AgentCharacter from "../agents/AgentCharacter";
import type { AgentVisualMode } from "../semantic";

interface AgentDummyProps {
  position: [number, number, number];
  mode?: AgentVisualMode;
  modelPath: string;
}

export default function AgentDummy({
  position,
  mode = "idle",
  modelPath,
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
  });

  return (
    <group position={position}>
      <group ref={actorRef}>
        <AgentCharacter
          modelPath={modelPath}
          scale={0.9}
        />
      </group>
    </group>
  );
}
