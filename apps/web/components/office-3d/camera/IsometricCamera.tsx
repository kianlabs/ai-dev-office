"use client";

import { OrthographicCamera } from "@react-three/drei";
import type { OrthographicCamera as CamType } from "three";

// Isometric-style view. The camera looks down at 45° and is set far enough to
// fit the whole miniature office with a slight isometric tilt.

export const ISOMETRIC_POSITION: [number, number, number] = [15, 18, 20];
export const ISOMETRIC_ZOOM = 42;

interface IsometricCameraProps {
  camRef: React.RefObject<CamType | null>;
}

export default function IsometricCamera({ camRef }: IsometricCameraProps) {
  return (
    <OrthographicCamera
      ref={camRef}
      makeDefault
      position={ISOMETRIC_POSITION}
      zoom={ISOMETRIC_ZOOM}
      near={0.1}
      far={120}
    />
  );
}