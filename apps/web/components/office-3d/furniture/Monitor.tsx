"use client";

import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import type { Mesh, MeshStandardMaterial } from "three";

import type { AgentVisualMode } from "../semantic";
import OfficeAsset from "../assets/OfficeAsset";

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
      return 0.55;
    case "planning":
      return 0.8 + Math.sin(t * 1.8) * 0.1;
    case "dispatching":
      return 0.95 + Math.sin(t * 5) * 0.12;
    case "researching":
      return 0.9 + Math.sin(t * 4) * 0.14;
    case "coding":
      return 1 + Math.sin(t * 7) * 0.1;
    case "building":
      return 1.05 + Math.sin(t * 8) * 0.12;
    case "repairing":
      return 1.15 + Math.sin(t * 10) * 0.16;
    case "testing":
      return 1 + Math.sin(t * 5) * 0.2;
    case "monitoring":
      return 0.95 + Math.sin(t * 2) * 0.22;
    case "reporting":
      return 1.05 + Math.sin(t * 4) * 0.16;
    case "waiting":
      return 0.65 + Math.sin(t * 1.2) * 0.06;
    case "success":
      return 1.25 + Math.sin(t * 3.5) * 0.14;
    case "error":
      return 1.05 + Math.sin(t * 9) * 0.25;
    default:
      return 0.55;
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
    if (!screenRef.current) return;

    const material =
      screenRef.current.material as MeshStandardMaterial;

    material.emissiveIntensity =
      screenGlow *
      Math.max(
        0.15,
        modePulse(mode, clock.getElapsedTime()),
      );
  });

  return (
    <group
      position={position}
      rotation={[0, rotation, 0]}
    >
      {/*
       * Original GLB:
       * X = depth
       * Z = width
       *
       * Rotate 90deg so it behaves like our old monitor:
       * X = width
       * Z = depth
       */}
      <OfficeAsset
        src="/models/office/workstation/monitor.glb"
        rotation={[0, Math.PI / 2, 0]}
        scale={0.72}
        bottomCenter
      />

      {/* semantic screen */}
      <mesh
        ref={screenRef}
        position={[0, 0.30, -0.095]}
        rotation={[0, Math.PI, 0]}
      >
        <planeGeometry args={[0.64, 0.35]} />

        <meshStandardMaterial
          color={screenColor}
          emissive={screenColor}
          emissiveIntensity={screenGlow}
          transparent
          opacity={0.22}
          toneMapped={false}
        />
      </mesh>
    </group>
  );
}
