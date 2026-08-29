"use client";

import { useGLTF } from "@react-three/drei";
import { useMemo } from "react";
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

/** Bakes the character's own "Idle" mo-cap pose into the clone's skeleton so
 *  it renders standing naturally (arms relaxed) instead of the T/A-pose bind
 *  pose. The clip never animates Root/Hips, so the feet stay planted on the
 *  floor and there is no positional drift. */
function bakeIdlePose(scene: THREE.Object3D, clip?: THREE.AnimationClip) {
  if (!clip) return;

  const bones = new Map<string, THREE.Bone>();
  scene.traverse((object) => {
    if ((object as THREE.Bone).isBone) {
      bones.set(object.name, object as THREE.Bone);
    }
  });

  for (const track of clip.tracks) {
    const sep = track.name.lastIndexOf(".");
    if (sep < 1) continue;
    const boneName = track.name.slice(0, sep);
    const prop = track.name.slice(sep + 1);
    const bone = bones.get(boneName);
    if (!bone) continue;

    const size = track.getValueSize();
    const value = track.values.slice(0, size);
    if (prop === "quaternion" && value.length === 4) {
      bone.quaternion.fromArray(value);
    } else if (prop === "translation" && value.length === 3) {
      bone.position.fromArray(value);
    } else if (prop === "scale" && value.length === 3) {
      bone.scale.fromArray(value);
    }
  }

  scene.traverse((object) => {
    if ((object as THREE.SkinnedMesh).isSkinnedMesh) {
      (object as THREE.SkinnedMesh).skeleton.update();
    }
  });
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

    bakeIdlePose(cloned, gltf.animations?.find((a) => a.name === IDLE_CLIP_NAME));

    return cloned;
  }, [gltf]);

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