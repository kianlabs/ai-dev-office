"use client";

import { useGLTF } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";
import { clone as cloneSkeleton } from "three/examples/jsm/utils/SkeletonUtils.js";

type AgentCharacterVariant = "male" | "female";

export type HairStyleKey =
  | "simple-parted"
  | "long"
  | "buzzed"
  | "buns";

interface AgentCharacterProps {
  variant?: AgentCharacterVariant;
  position?: [number, number, number];
  rotation?: number;
  scale?: number;
  /** Hairstyle mesh, rigged to the matching-gender skeleton. */
  hairstyle?: HairStyleKey;
  /** Tints the hair material by this color (multiply). Skin, eyes and body
   *  materials are left untouched. */
  hairColor?: string;
}

const MODELS = {
  male: "/models/agents/base/Superhero_Male_FullBody.gltf",
  female: "/models/agents/base/Superhero_Female_FullBody.gltf",
} as const;

const HAIRSTYLES: Record<
  HairStyleKey,
  { path: string; mesh: string }
> = {
  "simple-parted": {
    path: "/models/agents/hair/Hair_SimpleParted.gltf",
    mesh: "Hair_SimpleParted",
  },
  long: {
    path: "/models/agents/hair/Hair_Long.gltf",
    mesh: "Hair_Long",
  },
  buzzed: {
    path: "/models/agents/hair/Hair_Buzzed.gltf",
    mesh: "Hair_Buzzed",
  },
  buns: {
    path: "/models/agents/hair/Hair_Buns.gltf",
    mesh: "Hair_Buns",
  },
};

const DEFAULT_HAIRSTYLE: HairStyleKey = "buzzed";

function findSkinnedMesh(object: THREE.Object3D): THREE.SkinnedMesh | null {
  if ((object as THREE.SkinnedMesh).isSkinnedMesh) {
    return object as THREE.SkinnedMesh;
  }
  for (const child of object.children) {
    const found = findSkinnedMesh(child);
    if (found) return found;
  }
  return null;
}

// Tints ONLY the hair ("MI_Hair_*") materials of a cloned scene. The models
// have no separate outfit material (skin and outfit share one "MI_Superhero_*"
// body material), so that material is preserved as-is. Materials are cloned
// per instance so the shared useGLTF cache is never mutated.
function tintHair(scene: THREE.Object3D, color?: string) {
  if (!color) return;

  const isColored = (
    material: THREE.Material,
  ): material is THREE.MeshStandardMaterial =>
    (material as THREE.MeshStandardMaterial).color !== undefined;

  scene.traverse((object) => {
    if (!(object as THREE.Mesh).isMesh) return;

    const mesh = object as THREE.Mesh;
    const materials = Array.isArray(mesh.material)
      ? mesh.material
      : [mesh.material];

    const next = materials.map((material) => {
      if (!material.name.includes("Hair")) return material;

      const tinted = material.clone();
      if (isColored(tinted)) {
        tinted.color = tinted.color.clone().multiply(new THREE.Color(color));
      }
      return tinted;
    });

    if (Array.isArray(mesh.material)) {
      mesh.material = next;
    } else {
      mesh.material = next[0];
    }
  });
}

export default function AgentCharacter({
  variant = "male",
  position = [0, 0, 0],
  rotation = 0,
  scale = 1,
  hairstyle = DEFAULT_HAIRSTYLE,
  hairColor,
}: AgentCharacterProps) {
  const gltf = useGLTF(MODELS[variant]);
  const hairGltf = useGLTF(HAIRSTYLES[hairstyle].path);

  const scene = useMemo(() => {
    const cloned = cloneSkeleton(gltf.scene);

    // Attach the rigged hairstyle mesh onto the character's own skeleton.
    // Both share the exact same bone hierarchy and rest pose for a given
    // gender, so rebinding the hair mesh to the character's skeleton places
    // it on the head and makes it follow any head/skeleton movement.
    const bodyMesh = findSkinnedMesh(cloned);
    const hairMesh = bodyMesh
      ? (cloneSkeleton(hairGltf.scene).getObjectByName(
          HAIRSTYLES[hairstyle].mesh,
        ) as THREE.SkinnedMesh | null)
      : null;

    if (bodyMesh && hairMesh) {
      hairMesh.skeleton = bodyMesh.skeleton;
      hairMesh.parent?.remove(hairMesh);
      cloned.add(hairMesh);
    }

    tintHair(cloned, hairColor);
    return cloned;
  }, [gltf.scene, hairGltf.scene, hairstyle, hairColor]);

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
useGLTF.preload(HAIRSTYLES["simple-parted"].path);
useGLTF.preload(HAIRSTYLES.long.path);
useGLTF.preload(HAIRSTYLES.buzzed.path);
useGLTF.preload(HAIRSTYLES.buns.path);
