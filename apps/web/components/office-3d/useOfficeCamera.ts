"use client";

import { useRef } from "react";
import type { OrthographicCamera as CamType } from "three";
import type { OrbitControls as OrbitImpl } from "three-stdlib";

import { ISOMETRIC_POSITION, ISOMETRIC_ZOOM } from "./camera/IsometricCamera";

export interface OfficeCameraRefs {
  camRef: React.RefObject<CamType | null>;
  controlsRef: React.RefObject<OrbitImpl | null>;
}

export function useOfficeCamera(): OfficeCameraRefs {
  const camRef = useRef<CamType | null>(null);
  const controlsRef = useRef<OrbitImpl | null>(null);
  return { camRef, controlsRef };
}

// Reset the orthographic camera + controls to the default isometric view.
export function resetOfficeCamera({ camRef, controlsRef }: OfficeCameraRefs) {
  const cam = camRef.current;
  if (cam) {
    cam.position.set(...ISOMETRIC_POSITION);
    cam.zoom = ISOMETRIC_ZOOM;
    cam.updateProjectionMatrix();
  }
  const controls = controlsRef.current;
  if (controls) {
    controls.target.set(0, 0, 0);
    controls.update();
  }
}