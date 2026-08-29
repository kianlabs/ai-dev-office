"use client";

/**
 * Native Mixamo shared-desk agent — one per agent seat (default character
 * system).
 *
 * Loads the agent's Mixamo character FBX and the six raw Mixamo
 * sitting/typing clips with FBXLoader, normalizes the clip track namespaces
 * onto the character skeleton (every export uses its own "mixamorig*"
 * namespace; topology is identical) and plays the sequence directly on the
 * rendered character root with one AnimationMixer:
 *
 *   standing → Stand To Sit → Seated Idle → Sit To Type → Typing →
 *   Type To Sit → Seated Idle → Sit To Stand → standing (loops)
 *
 * One-shots use LoopOnce + clampWhenFinished; loops repeat until their hold
 * elapses. Every phase change is a crossfade, which also smooths the clips'
 * differing seat reference frames into a small scoot. No navigation and no
 * workflow/semantic integration — the accepted workstation (chair, monitor,
 * keyboard) is rendered by SharedDesk exactly as committed.
 */
import { useFBX, useGLTF } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import {
  MIXAMO_AGENTS,
  MIXAMO_CLIP_URLS,
  MIXAMO_FADE_SECONDS,
  MIXAMO_SEQUENCE,
  detectMixamoPrefix,
  normalizeMixamoClip,
  type MixamoClipKey,
} from "./mixamo";

type MixamoClips = Record<MixamoClipKey, THREE.AnimationClip>;
type MixamoActions = Record<MixamoClipKey, THREE.AnimationAction>;

const CLIP_KEYS = Object.keys(MIXAMO_CLIP_URLS) as MixamoClipKey[];

function phaseDuration(
  phase: (typeof MIXAMO_SEQUENCE)[number],
  actions: MixamoActions,
): number {
  if (phase.mode === "once") return actions[phase.clip].getClip().duration;
  return phase.seconds ?? 0;
}

/** Starts `next`, crossfading `previous` out. hold-end clamps the final
 *  frame immediately so the standing baseline shows a natural stance.
 *  A fade needs a pose to fade FROM: on mixer creation (previous === null)
 *  and on the loop wrap (previous === next's action — the standing hold
 *  reuses sitToStand's final frame) a fade would blend from/to the bind
 *  pose and flash a T-pose, so those restarts go straight to full weight. */
function enterPhase(
  actions: MixamoActions,
  previous: THREE.AnimationAction | null,
  next: (typeof MIXAMO_SEQUENCE)[number],
) {
  const action = actions[next.clip];

  action.reset();
  if (next.mode === "loop") {
    action.setLoop(THREE.LoopRepeat, Infinity);
    action.clampWhenFinished = false;
  } else {
    action.setLoop(THREE.LoopOnce, 1);
    action.clampWhenFinished = true;
    if (next.mode === "hold-end") {
      action.time = action.getClip().duration;
    }
  }

  if (previous === null || previous === action) {
    action.setEffectiveWeight(1).play();
    return;
  }

  action.fadeIn(MIXAMO_FADE_SECONDS).play();
  previous?.fadeOut(MIXAMO_FADE_SECONDS);
}

interface MixamoAgentProps {
  agentId: keyof typeof MIXAMO_AGENTS;
  /** Seat anchor (mixamoSeatAnchor) in SharedDesk local space. */
  position: [number, number, number];
  /** Seat-facing world yaw (the seat rotation in SharedDesk). */
  rotation?: number;
}

export default function MixamoAgent({
  agentId,
  position,
  rotation = 0,
}: MixamoAgentProps) {
  const { modelUrl, scale } = MIXAMO_AGENTS[agentId];

  // Characters: optimized GLB (meshopt+webp, meters). Draco is explicitly
  // off (no decoder needed); meshopt uses the decoder bundled with
  // three-stdlib, which drei wires automatically.
  const { scene: characterGltf } = useGLTF(modelUrl, false, true);
  const standToSitFbx = useFBX(MIXAMO_CLIP_URLS.standToSit);
  const seatedIdleFbx = useFBX(MIXAMO_CLIP_URLS.seatedIdle);
  const sitToTypeFbx = useFBX(MIXAMO_CLIP_URLS.sitToType);
  const typingFbx = useFBX(MIXAMO_CLIP_URLS.typing);
  const typeToSitFbx = useFBX(MIXAMO_CLIP_URLS.typeToSit);
  const sitToStandFbx = useFBX(MIXAMO_CLIP_URLS.sitToStand);

  const { model, offset, clips } = useMemo(() => {
    // Mixamo characters face +Z; the office convention (seat yaw + model)
    // expects the model to face local -Z, so flip it before measuring.
    characterGltf.rotation.y = Math.PI;

    // Animated skinned meshes can out-grow their bind-pose bounds (sitting,
    // reaching) and get culled mid-pose — keep them always drawn.
    characterGltf.traverse((object) => {
      if (object instanceof THREE.SkinnedMesh) object.frustumCulled = false;
    });

    characterGltf.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(characterGltf);
    const offset: [number, number, number] = box.isEmpty()
      ? [0, 0, 0]
      : [
          -(box.min.x + box.max.x) / 2,
          -box.min.y,
          -(box.min.z + box.max.z) / 2,
        ];

    const prefix = detectMixamoPrefix(characterGltf);

    // Characters whose skeletons are authored larger/smaller than the clip
    // reference (the Ch22 FBX, bind hips 100.35 cm) need their hips position
    // track scaled by the same factor, or the pelvis trajectory sinks/floats
    // (Remy is authored ~2.1x). Clone-per-agent below keeps the shared
    // cached tracks untouched.
    const hipsBone = characterGltf.getObjectByProperty(
      "name",
      `${prefix}Hips`,
    );
    const bindHips = hipsBone?.getWorldPosition(new THREE.Vector3());
    const hipsScale = bindHips ? bindHips.y / 100.35 : 1;

    // The six clip FBXs come from drei's shared cache, so every agent would
    // otherwise mutate the SAME clip objects with its own bone namespace —
    // the last agent to normalize would win and the rest would lose their
    // bindings. Clone per agent, then rewrite onto this character's prefix.
    const clips = {
      standToSit: normalizeMixamoClip(
        standToSitFbx.animations[0].clone(),
        prefix,
        "standToSit",
        hipsScale,
      ),
      seatedIdle: normalizeMixamoClip(
        seatedIdleFbx.animations[0].clone(),
        prefix,
        "seatedIdle",
        hipsScale,
      ),
      sitToType: normalizeMixamoClip(
        sitToTypeFbx.animations[0].clone(),
        prefix,
        "sitToType",
        hipsScale,
      ),
      typing: normalizeMixamoClip(
        typingFbx.animations[0].clone(),
        prefix,
        "typing",
        hipsScale,
      ),
      typeToSit: normalizeMixamoClip(
        typeToSitFbx.animations[0].clone(),
        prefix,
        "typeToSit",
        hipsScale,
      ),
      sitToStand: normalizeMixamoClip(
        sitToStandFbx.animations[0].clone(),
        prefix,
        "sitToStand",
        hipsScale,
      ),
    } satisfies MixamoClips;

    return { model: characterGltf, offset, clips };
  }, [characterGltf, standToSitFbx, seatedIdleFbx, sitToTypeFbx, typingFbx, typeToSitFbx, sitToStandFbx]);

  const mixerRef = useRef<THREE.AnimationMixer | null>(null);
  const actionsRef = useRef<MixamoActions | null>(null);
  const phaseRef = useRef(0);
  const elapsedRef = useRef(0);

  useEffect(() => {
    const mixer = new THREE.AnimationMixer(model);
    const actions = {} as MixamoActions;
    for (const key of CLIP_KEYS) {
      actions[key] = mixer.clipAction(clips[key]);
    }

    // Phase 0 is the standing baseline: clamp the sitToStand final frame
    // without a fade (nothing is playing yet).
    phaseRef.current = 0;
    elapsedRef.current = 0;
    enterPhase(actions, null, MIXAMO_SEQUENCE[0]);

    mixerRef.current = mixer;
    actionsRef.current = actions;

    return () => {
      mixer.stopAllAction();
      mixer.uncacheRoot(model);
      mixerRef.current = null;
      actionsRef.current = null;
    };
  }, [model, clips]);

  useFrame((_, delta) => {
    const mixer = mixerRef.current;
    const actions = actionsRef.current;
    if (!mixer || !actions) return;

    mixer.update(delta);
    elapsedRef.current += delta;

    const phase = MIXAMO_SEQUENCE[phaseRef.current];
    if (elapsedRef.current < phaseDuration(phase, actions)) return;

    const previous = actions[phase.clip];
    phaseRef.current = (phaseRef.current + 1) % MIXAMO_SEQUENCE.length;
    elapsedRef.current = 0;
    enterPhase(actions, previous, MIXAMO_SEQUENCE[phaseRef.current]);
  });

  return (
    <group position={position} rotation={[0, rotation, 0]}>
      <group scale={scale}>
        <primitive object={model} position={offset} />
      </group>
    </group>
  );
}
