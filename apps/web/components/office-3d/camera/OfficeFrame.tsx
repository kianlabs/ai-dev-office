"use client";

import { useEffect } from "react";
import * as THREE from "three";
import { useThree } from "@react-three/fiber";
import type { OfficeCameraRefs } from "../useOfficeCamera";

// View direction (normalized) and distance from the scene, plus a little margin
// so the whole miniature office fits comfortably inside the viewport.
const VIEW_DIR = new THREE.Vector3(0.72, 0.9, 1.0).normalize();
const VIEW_DIST = 27;
const MARGIN = 1.02;

// Current compact office footprint: 22 x 15.
// Keep bounds aligned with MainOffice so framing does not include empty space.
const OFFICE_MIN = new THREE.Vector3(-11.1, 0, -7.55);
const OFFICE_MAX = new THREE.Vector3(11.1, 2.8, 7.55);

// Compute a camera framing that fits the office footprint and apply it on the
// first frame. The fitted state is stored so "Reset View" can restore it.
export default function OfficeFrame({ refs }: { refs: OfficeCameraRefs }) {
  const size = useThree((s) => s.size);

  useEffect(() => {
    const cam = refs.camRef.current;
    const controls = refs.controlsRef.current;
    if (!cam || !controls) return;

    const box = new THREE.Box3(OFFICE_MIN, OFFICE_MAX);
    const center = box.getCenter(new THREE.Vector3());
    const target = new THREE.Vector3(center.x, 0.7, center.z);

    cam.position.copy(target).addScaledVector(VIEW_DIR, VIEW_DIST);
    cam.lookAt(target);
    cam.updateMatrixWorld();

    // Project the 8 corners onto the camera's screen axes to measure extents.
    const quat = cam.quaternion;
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(quat);
    const up = new THREE.Vector3(0, 1, 0).applyQuaternion(quat);

    const corners: [number, number, number][] = [
      [box.min.x, box.min.y, box.min.z],
      [box.min.x, box.min.y, box.max.z],
      [box.min.x, box.max.y, box.min.z],
      [box.min.x, box.max.y, box.max.z],
      [box.max.x, box.min.y, box.min.z],
      [box.max.x, box.min.y, box.max.z],
      [box.max.x, box.max.y, box.min.z],
      [box.max.x, box.max.y, box.max.z],
    ];

    const tmpv = new THREE.Vector3();
    let minX = Infinity,
      maxX = -Infinity,
      minY = Infinity,
      maxY = -Infinity;
    for (const [x, y, z] of corners) {
      tmpv.set(x, y, z).sub(target);
      minX = Math.min(minX, tmpv.dot(right));
      maxX = Math.max(maxX, tmpv.dot(right));
      minY = Math.min(minY, tmpv.dot(up));
      maxY = Math.max(maxY, tmpv.dot(up));
    }

    const spanX = (maxX - minX) * MARGIN;
    const spanY = (maxY - minY) * MARGIN;
    const zoomX = size.width / spanX;
    const zoomY = size.height / spanY;
    const zoom = Math.max(1, Math.min(Math.min(zoomX, zoomY), 90));

    cam.zoom = zoom;
    cam.updateProjectionMatrix();
    controls.target.copy(target);
    controls.update();

    refs.fittedRef.current = {
      position: [cam.position.x, cam.position.y, cam.position.z],
      target: [target.x, target.y, target.z],
      zoom,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}