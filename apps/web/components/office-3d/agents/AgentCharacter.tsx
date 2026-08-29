"use client";

import { useGLTF, useAnimations } from "@react-three/drei";
import { useEffect, useMemo } from "react";
import * as THREE from "three";
import { clone as cloneSkeleton } from "three/examples/jsm/utils/SkeletonUtils.js";

interface AgentCharacterProps {
  modelPath: string;
  position?: [number, number, number];
  rotation?: number;
  scale?: number;
  /** World-space pivot override. When omitted the model is auto-centered on
   *  X/Z and planted on the floor (feet at Y=0). */
  offset?: [number, number, number];
}

const IDLE_CLIP_NAME = "Idle";
const IDLE_FADE_SECONDS = 0.4;

const AGENT_MODELS = [
  "/models/agents/characters/men_suit.gltf",
  "/models/agents/characters/men_casual_hoodie.gltf",
  "/models/agents/characters/men_casual_2.gltf",
  "/models/agents/characters/women_casual.gltf",
  "/models/agents/characters/women_formal.gltf",
] as const;

/** Removes weapon/prop meshes (e.g. the Suit's Pistol) that have no place in
 *  the office. Mesh names come from the kit: Pistol / Gun / Sword / etc. */
function stripProps(scene: THREE.Object3D) {
  const toRemove: THREE.Object3D[] = [];
  scene.traverse((object) => {
    const name = object.name ?? "";
    if (/^(Pistol|Gun|Weapon|Sword|Shield|Prop)/i.test(name)) {
      toRemove.push(object);
    }
  });
  for (const object of toRemove) {
    object.parent?.remove(object);
  }
}

export default function AgentCharacter({
  modelPath,
  position = [0, 0, 0],
  rotation = 0,
  scale = 1,
  offset,
}: AgentCharacterProps) {
  const gltf = useGLTF(modelPath);

  const scene = useMemo(() => {
    const cloned = cloneSkeleton(gltf.scene);

    stripProps(cloned);

    // The kit's characters face +Z (toes + nose point toward +Z). The seat
    // frame in SharedDesk expects the model to face local -Z (into the
    // table), so flip the whole model to match that convention.
    cloned.rotation.y = Math.PI;

    return cloned;
  }, [gltf]);

  // Each agent owns its own cloned skeleton + mixer + actions, so animations
  // never share mutable state between stations.
  const { actions } = useAnimations(gltf.animations, scene);

  // Phase 1: every character loops its own native Idle clip continuously.
  // Native Idle is the most readable of the kit's natural standing clips
  // (Body breathe ~8mm + subtle wrist/finger motion; Idle_Neutral is flatter).
  // Idle clips only key regular bones (never Root/Hips), so there is no
  // root-motion drift and feet stay planted. The crossfade also hides the
  // bind (T/A-pose) frame on first mount.
  useEffect(() => {
    const idle = actions[IDLE_CLIP_NAME];
    if (!idle) return;

    idle.reset();
    idle.fadeIn(IDLE_FADE_SECONDS);
    idle.play();

    return () => {
      idle.fadeOut(IDLE_FADE_SECONDS);
    };
  }, [actions]);

  const autoOffset = useMemo<[number, number, number]>(() => {
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
        position={offset ?? autoOffset}
      />
    </group>
  );
}

for (const path of AGENT_MODELS) {
  useGLTF.preload(path);
}