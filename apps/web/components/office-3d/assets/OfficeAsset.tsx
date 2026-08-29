"use client";

import { Clone, useGLTF } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";

interface OfficeAssetProps {
  src: string;
  position?: [number, number, number];
  rotation?: [number, number, number];
  scale?: number | [number, number, number];

  /**
   * Re-anchor model so:
   * x/z = geometric center
   * y   = bottom of asset
   *
   * Useful because imported GLBs have inconsistent origins.
   */
  bottomCenter?: boolean;
}

export default function OfficeAsset({
  src,
  position = [0, 0, 0],
  rotation = [0, 0, 0],
  scale = 1,
  bottomCenter = false,
}: OfficeAssetProps) {
  const gltf = useGLTF(src);

  const offset = useMemo<[number, number, number]>(() => {
    if (!bottomCenter) {
      return [0, 0, 0];
    }

    const box = new THREE.Box3().setFromObject(gltf.scene);

    const centerX = (box.min.x + box.max.x) / 2;
    const centerZ = (box.min.z + box.max.z) / 2;

    return [
      -centerX,
      -box.min.y,
      -centerZ,
    ];
  }, [gltf.scene, bottomCenter]);

  return (
    <group
      position={position}
      rotation={rotation}
      scale={scale}
    >
      <group position={offset}>
        <Clone
          object={gltf.scene}
          castShadow
          receiveShadow
        />
      </group>
    </group>
  );
}

useGLTF.preload("/models/office/workstation/office-chair.glb");
useGLTF.preload("/models/office/workstation/monitor.glb");
useGLTF.preload("/models/office/workstation/keyboard.glb");
useGLTF.preload("/models/office/workstation/laptop.glb");
