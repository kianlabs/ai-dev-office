"use client";

import { useRef } from "react";
import type { OrthographicCamera as CamType } from "three";
import type { OrbitControls as OrbitImpl } from "three-stdlib";

export interface FittedView {
  position: [number, number, number];
  target: [number, number, number];
  zoom: number;
}

export interface OfficeCameraRefs {
  camRef: React.RefObject<CamType | null>;
  controlsRef: React.RefObject<OrbitImpl | null>;
  fittedRef: React.RefObject<FittedView | null>;
}

export function useOfficeCamera(): OfficeCameraRefs {
  const camRef = useRef<CamType | null>(null);
  const controlsRef = useRef<OrbitImpl | null>(null);
  const fittedRef = useRef<FittedView | null>(null);
  return { camRef, controlsRef, fittedRef };
}

// Restore the default isometric overview. Prefers the first-frame fitted view
// (computed from the actual scene bounds), falling back to the constants.
export function resetOfficeCamera({ camRef, controlsRef, fittedRef }: OfficeCameraRefs) {
  const cam = camRef.current;
  const controls = controlsRef.current;
  const fitted = fittedRef.current;

  let position: [number, number, number] = [15, 18, 20];
  let target: [number, number, number] = [0, 0.7, 0];
  let zoom = 42;

  if (fitted) {
    position = fitted.position;
    target = fitted.target;
    zoom = fitted.zoom;
  }

  if (cam) {
    cam.position.set(...position);
    cam.zoom = zoom;
    cam.updateProjectionMatrix();
  }
  if (controls) {
    controls.target.set(...target);
    controls.update();
  }
}