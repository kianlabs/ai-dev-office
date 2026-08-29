"use client";

/**
 * Native Mixamo shared-desk agent — one per agent seat (default character
 * system). Without the movement demo the agent plays the seated clip cycle
 * at its seat; with ?movementDemo=1 it patrols its demo route with the
 * navigation engine, Walking while moving and Idling on arrival.
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
  makeClipInPlace,
  normalizeMixamoClip,
  type MixamoClipKey,
} from "./mixamo";
import { usePatrolNavigation } from "../navigation/usePatrolNavigation";
import { SHARED_DESK_WORLD_OFFSET } from "../navigation/layout";

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

/** Starts `next`, crossfading `previous` out. A fade needs a pose to fade
 *  FROM: on mixer creation (previous === null) and on the loop wrap
 *  (previous === next's action) a fade would blend from/to the bind pose and
 *  flash a T-pose, so those restarts go straight to full weight. */
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
  /** Desk-local rest anchor (agentRestAnchor) in SharedDesk local space. */
  position: readonly [number, number, number];
  /** Seat-facing world yaw (the seat rotation in SharedDesk). */
  rotation?: number;
  /** Demo patrol route (?movementDemo=1). While active the navigation
   *  engine moves the agent and Idle/Walking replace the seated cycle. */
  route?: readonly string[];
}

export default function MixamoAgent({
  agentId,
  position,
  rotation = 0,
  route,
}: MixamoAgentProps) {
  const { homeRef, turnRef, walking } = usePatrolNavigation({
    position,
    baseYaw: rotation,
    route,
    frameOffset: SHARED_DESK_WORLD_OFFSET,
  });
  const demoActive = Boolean(route);
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
  const idleFbx = useFBX(MIXAMO_CLIP_URLS.idle);
  const walkingFbx = useFBX(MIXAMO_CLIP_URLS.walking);

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
      idle: normalizeMixamoClip(
        idleFbx.animations[0].clone(),
        prefix,
        "idle",
        hipsScale,
      ),
      walking: makeClipInPlace(
        normalizeMixamoClip(
          walkingFbx.animations[0].clone(),
          prefix,
          "walking",
          hipsScale,
        ),
      ),
    } satisfies MixamoClips;

    return { model: characterGltf, offset, clips };
  }, [characterGltf, standToSitFbx, seatedIdleFbx, sitToTypeFbx, typingFbx, typeToSitFbx, sitToStandFbx, idleFbx, walkingFbx]);

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

    // Phase 0 is the standing Idle baseline (full weight — no pose to fade
    // from yet).
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

  // Movement demo: the navigation engine owns locomotion — the seated
  // sequencer is suspended and Idle/Walking follow the patrol state.
  const demoStartedRef = useRef(false);
  useEffect(() => {
    const mixer = mixerRef.current;
    const actions = actionsRef.current;
    if (!mixer || !actions) return;

    if (!demoActive) {
      demoStartedRef.current = false;
      return;
    }

    const target = walking ? actions.walking : actions.idle;
    if (!demoStartedRef.current) {
      // First demo frame: cut the seated cycle and start from full weight.
      mixer.stopAllAction();
      target.reset();
      target.setEffectiveWeight(1);
      target.setLoop(THREE.LoopRepeat, Infinity);
      target.clampWhenFinished = false;
      target.play();
      demoStartedRef.current = true;
      return;
    }

    for (const action of Object.values(actions)) {
      if (action !== target && action.isRunning()) action.fadeOut(0.35);
    }
    target.reset();
    target.setLoop(THREE.LoopRepeat, Infinity);
    target.clampWhenFinished = false;
    target.fadeIn(0.35).play();
  }, [demoActive, walking]);

  useFrame((_, delta) => {
    const mixer = mixerRef.current;
    const actions = actionsRef.current;
    if (!mixer || !actions) return;

    mixer.update(delta);

    // While the demo patrols, the sequencer must not fight Idle/Walking.
    if (demoActive) return;

    elapsedRef.current += delta;

    const phase = MIXAMO_SEQUENCE[phaseRef.current];
    if (elapsedRef.current < phaseDuration(phase, actions)) return;

    const previous = actions[phase.clip];
    phaseRef.current = (phaseRef.current + 1) % MIXAMO_SEQUENCE.length;
    elapsedRef.current = 0;
    enterPhase(actions, previous, MIXAMO_SEQUENCE[phaseRef.current]);
  });

  return (
    <group ref={homeRef} position={position}>
      <group ref={turnRef}>
        <group scale={scale}>
          <primitive object={model} position={offset} />
        </group>
      </group>
    </group>
  );
}
