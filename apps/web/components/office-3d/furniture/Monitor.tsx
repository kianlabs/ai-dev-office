"use client";

import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import type { Mesh, MeshStandardMaterial } from "three";

import type { AgentVisualMode } from "../semantic";

interface MonitorProps {
  position: [number, number, number];
  rotation?: number;
  screenGlow?: number;
  screenColor?: string;
  mode?: AgentVisualMode;
}

function modePulse(mode: AgentVisualMode, t: number): number {
  switch (mode) {
    case "idle":
      return 0.75;

    case "planning":
      return 0.95 + Math.sin(t * 1.8) * 0.12;

    case "researching":
      return 1 + Math.sin(t * 4.2) * 0.16;

    case "coding":
      return 1.05 + Math.sin(t * 7) * 0.1;

    case "repairing":
      return 1.2 + Math.sin(t * 10) * 0.18;

    case "testing":
      return 1 + Math.sin(t * 5) * 0.22;

    case "monitoring":
      return 1 + Math.sin(t * 2) * 0.28;

    case "reporting":
      return 1.15 + Math.sin(t * 4) * 0.2;

    case "waiting":
      return 0.8 + Math.sin(t * 1.2) * 0.08;

    case "success":
      return 1.35 + Math.sin(t * 3.5) * 0.18;

    case "error":
      return 1.1 + Math.sin(t * 9) * 0.3;
  }
}

export default function Monitor({
  position,
  rotation = 0,
  screenGlow = 1,
  screenColor = "#7dd3fc",
  mode = "idle",
}: MonitorProps) {
  const screenRef = useRef<Mesh>(null);

  useFrame(({ clock }) => {
    const mesh = screenRef.current;
    if (!mesh) return;

    const material = mesh.material as MeshStandardMaterial;
    material.emissiveIntensity =
      screenGlow * Math.max(0.15, modePulse(mode, clock.getElapsedTime()));
  });

  return (
    <group position={position} rotation={[0, rotation, 0]}>
      {/* stand */}
      <mesh position={[0, -0.08, 0]}>
        <boxGeometry args={[0.06, 0.1, 0.14]} />
        <meshStandardMaterial
          color="#1a1d24"
          metalness={0.3}
          roughness={0.5}
        />
      </mesh>

      {/* panel bezel */}
      <mesh position={[0, 0.28, 0]}>
        <boxGeometry args={[0.16, 0.62, 0.9]} />
        <meshStandardMaterial
          color="#14161c"
          metalness={0.2}
          roughness={0.6}
        />
      </mesh>

      {/* semantic screen */}
      <mesh ref={screenRef} position={[0, 0.3, 0.462]}>
        <boxGeometry args={[0.12, 0.52, 0.02]} />
        <meshStandardMaterial
          color={screenColor}
          emissive={screenColor}
          emissiveIntensity={screenGlow}
          toneMapped={false}
        />
      </mesh>

      {/* faint headphone hook / top accent */}
      <mesh position={[0, 0.62, 0]}>
        <boxGeometry args={[0.05, 0.03, 0.4]} />
        <meshStandardMaterial
          color="#22d3ee"
          emissive="#22d3ee"
          emissiveIntensity={0.3}
        />
      </mesh>
    </group>
  );
}
