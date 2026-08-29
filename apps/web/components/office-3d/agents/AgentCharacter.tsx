"use client";

import { useGLTF } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";
import { clone as cloneSkeleton } from "three/examples/jsm/utils/SkeletonUtils.js";

type AgentCharacterVariant = "male" | "female";

interface AgentCharacterProps {
  variant?: AgentCharacterVariant;
  position?: [number, number, number];
  rotation?: number;
  scale?: number;
}

const MODELS = {
  male: "/models/agents/base/Superhero_Male_FullBody.gltf",
  female: "/models/agents/base/Superhero_Female_FullBody.gltf",
} as const;

export default function AgentCharacter({
  variant = "male",
  position = [0, 0, 0],
  rotation = 0,
  scale = 1,
}: AgentCharacterProps) {
  const gltf = useGLTF(MODELS[variant]);

  const scene = useMemo(
    () => cloneSkeleton(gltf.scene),
    [gltf.scene],
  );

  const offset = useMemo<[number, number, number]>(() => {
    scene.updateMatrixWorld(true);

    const box = new THREE.Box3().setFromObject(scene);

    if (box.isEmpty()) return [0, 0, 0];

    const centerX = (box.min.x + box.max.x) / 2;
    const centerZ = (box.min.z + box.max.z) / 2;

    return [
      -centerX,
      -box.min.y,
      -centerZ,
    ];
  }, [scene]);

  return (
    <group
      position={position}
      rotation={[0, rotation, 0]}
      scale={scale}
    >
      <primitive
        object={scene}
        position={offset}
      />
    </group>
  );
}

useGLTF.preload(MODELS.male);
useGLTF.preload(MODELS.female);
