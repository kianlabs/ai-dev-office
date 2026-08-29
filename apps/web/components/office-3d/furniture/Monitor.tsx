"use client";

import OfficeAsset from "../assets/OfficeAsset";
import type { AgentVisualMode } from "../semantic";

interface MonitorProps {
  position: [number, number, number];
  rotation?: number;

  // Compatibility props.
  // Semantic screen overlay is intentionally disabled for now.
  screenGlow?: number;
  screenColor?: string;
  mode?: AgentVisualMode;
}

export default function Monitor({
  position,
  rotation = 0,
}: MonitorProps) {
  return (
    <group
      position={position}
      rotation={[0, rotation, 0]}
    >
      <OfficeAsset
        src="/models/office/workstation/monitor.glb"
        rotation={[0, Math.PI / 2, 0]}
        scale={0.72}
        bottomCenter
      />
    </group>
  );
}
