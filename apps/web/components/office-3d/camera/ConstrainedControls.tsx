"use client";

import { OrbitControls } from "@react-three/drei";
import type { OrbitControls as OrbitImpl } from "three-stdlib";

interface ConstrainedControlsProps {
  controlsRef: React.RefObject<OrbitImpl | null>;
}

// OrbitControls limited for a management-sim feel: bounded zoom, bounded orbit,
// no rolling, and the camera can't sink below the floor.
export default function ConstrainedControls({ controlsRef }: ConstrainedControlsProps) {
  return (
    <OrbitControls
      ref={controlsRef}
      enablePan
      enableZoom
      enableRotate
      enableDamping
      dampingFactor={0.08}
      minZoom={12}
      maxZoom={46}
      minDistance={6}
      maxDistance={60}
      minPolarAngle={0.2}
      maxPolarAngle={1.35}
      target={[0, 0, 0]}
    />
  );
}