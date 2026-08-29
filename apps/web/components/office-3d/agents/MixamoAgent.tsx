"use client";

/**
 * Native Mixamo shared-desk agent — one per agent seat (default character
 * system).
 *
 * During ACTIVE work the agent stays seated at its workstation and is a
 * PASSIVE renderer of the seated-behavior machine (seatedBehavior.ts). It
 * never decides posture, position or work on its own: it renders the current
 * seated phase (SeatedIdle / SeatedTalking / seated work cycle) for the
 * delegation + semantic inputs it receives, crossfading between them and
 * never standing, walking or resetting because React props/state reran.
 *
 *   SEATED_IDLE   -> SeatedIdle (loop)             [resting between talks]
 *   SEATED_TALKING-> sittingTalking (loop, held)   [new delegation announce]
 *   SEATED_WORK   -> seated work cycle (typing or seated rest) [no chairs]
 *
 * ?movementDemo=1 (route present) instead drives the legible locomotion demo
 * via the navigation/posture machine: Walking for MOVING, Idle for standing,
 * and the one-shot remove/posture transitions. That path is the only one that
 * stands/walks; production work never does.
 */
import { useFBX, useGLTF } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import {
  MIXAMO_AGENTS,
  MIXAMO_CLIP_URLS,
  MIXAMO_FADE_SECONDS,
  detectMixamoPrefix,
  makeClipInPlace,
  normalizeMixamoClip,
  type MixamoClipKey,
} from "./mixamo";
import {
  usePatrolNavigation,
  type AgentPosture,
} from "../navigation/usePatrolNavigation";
import {
  isSeatedTalking,
  nextSeatedPhase,
  seatedWorkSequence,
  SEATED_TALK_CLIP,
  SEATED_TALK_HOLD_SECONDS,
  type SeatedPhase,
  type WorkMode,
} from "./seatedBehavior";
import { SHARED_DESK_WORLD_OFFSET } from "../navigation/layout";
import AgentBubble from "./AgentBubble";
import { AGENT_SIGNAL } from "../signal";
import type { AgentDelegation } from "./useAgentDelegation";
import type { HandoffBubble } from "../navigation/handoff";

type MixamoClips = Record<MixamoClipKey, THREE.AnimationClip>;
type MixamoActions = Record<MixamoClipKey, THREE.AnimationAction>;

const CLIP_KEYS = Object.keys(MIXAMO_CLIP_URLS) as MixamoClipKey[];

function phaseDuration(
  phase: { clip: MixamoClipKey; mode: "loop" | "once"; seconds?: number },
  actions: MixamoActions,
): number {
  if (phase.mode === "once") return actions[phase.clip].getClip().duration;
  return phase.seconds ?? 0;
}

/** Starts `next`, crossfading `previous` out. A fade needs a pose to fade
 *  FROM: on mixer creation (previous === null) a fade would blend from/to the
 *  bind pose and flash a T-pose, so those restarts go straight to full weight. */
function enterPhase(
  actions: MixamoActions,
  previous: THREE.AnimationAction | null,
  next: { clip: MixamoClipKey; mode: "loop" | "once"; seconds?: number },
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

/** Map an agent's role to its seated work mode. */
function workModeFor(agentId: keyof typeof MIXAMO_AGENTS): WorkMode {
  switch (agentId) {
    case "scout":
    case "forge":
    case "qa":
      return "typing";
    case "atlas":
    case "pulse":
      return "monitor";
  }
}

interface MixamoAgentProps {
  agentId: keyof typeof MIXAMO_AGENTS;
  /** Desk-local rest anchor (agentRestAnchor) in SharedDesk local space. */
  position: readonly [number, number, number];
  /** Seat-facing world yaw (the seat rotation in SharedDesk). */
  rotation?: number;
  /** Demo patrol route (?movementDemo=1). Overrides the delegation inputs. */
  route?: readonly string[];
  /** Seated delegation inputs (speech bubble + talk trigger), no movement. */
  delegation?: AgentDelegation;
  /** Persistent work-status bubble derived from the agent's semantic state. */
  workBubble?: HandoffBubble;
}

export default function MixamoAgent({
  agentId,
  position,
  rotation = 0,
  route,
  delegation,
  workBubble,
}: MixamoAgentProps) {
  const demoActive = Boolean(route);
  const { homeRef, turnRef, posture, finishOneShot } = usePatrolNavigation({
    position,
    baseYaw: rotation,
    route,
    frameOffset: SHARED_DESK_WORLD_OFFSET,
  });
  const { modelUrl, scale } = MIXAMO_AGENTS[agentId];
  const signalColor = AGENT_SIGNAL[agentId] ?? "#94a3b8";
  const workMode = workModeFor(agentId);

  // Characters: optimized GLB (meshopt+webp, meters). Draco is explicitly
  // off (no decoder needed); meshopt uses the decoder bundled with
  // three-stdlib, which drei wires automatically.
  const { scene: characterGltf } = useGLTF(modelUrl, false, true);
  const standToSitFbx = useFBX(MIXAMO_CLIP_URLS.standToSit);
  const seatedIdleFbx = useFBX(MIXAMO_CLIP_URLS.seatedIdle);
  const sittingTalkingFbx = useFBX(MIXAMO_CLIP_URLS.sittingTalking);
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
      sittingTalking: normalizeMixamoClip(
        sittingTalkingFbx.animations[0].clone(),
        prefix,
        "sittingTalking",
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
  }, [characterGltf, standToSitFbx, seatedIdleFbx, sittingTalkingFbx, sitToTypeFbx, typingFbx, typeToSitFbx, sitToStandFbx, idleFbx, walkingFbx]);

  const mixerRef = useRef<THREE.AnimationMixer | null>(null);
  const actionsRef = useRef<MixamoActions | null>(null);

  useEffect(() => {
    const mixer = new THREE.AnimationMixer(model);
    const actions = {} as MixamoActions;
    for (const key of CLIP_KEYS) {
      actions[key] = mixer.clipAction(clips[key]);
    }

    mixerRef.current = mixer;
    actionsRef.current = actions;

    return () => {
      mixer.stopAllAction();
      mixer.uncacheRoot(model);
      mixerRef.current = null;
      actionsRef.current = null;
    };
  }, [model, clips]);

  // ---- clip playback helpers ----------------------------------------------
  const oneShotActionRef = useRef<THREE.AnimationAction | null>(null);

  useEffect(() => {
    const mixer = mixerRef.current;
    if (!mixer) return;
    const onFinished = (event: { action: THREE.AnimationAction }) => {
      if (oneShotActionRef.current && event.action === oneShotActionRef.current) {
        oneShotActionRef.current = null;
        finishOneShot();
      }
    };
    mixer.addEventListener("finished", onFinished);
    return () => mixer.removeEventListener("finished", onFinished);
  }, [finishOneShot]);

  function playLoop(key: MixamoClipKey) {
    const actions = actionsRef.current;
    if (!actions) return;
    oneShotActionRef.current = null;
    for (const action of Object.values(actions)) {
      if (action !== actions[key] && action.isRunning()) {
        action.fadeOut(MIXAMO_FADE_SECONDS);
      }
    }
    const action = actions[key];
    action.reset();
    action.setLoop(THREE.LoopRepeat, Infinity);
    action.clampWhenFinished = false;
    action.fadeIn(MIXAMO_FADE_SECONDS).play();
  }

  function playOneShot(key: MixamoClipKey) {
    const actions = actionsRef.current;
    if (!actions) return;
    const action = actions[key];
    for (const other of Object.values(actions)) {
      if (other !== action && other.isRunning()) {
        other.fadeOut(MIXAMO_FADE_SECONDS);
      }
    }
    action.reset();
    action.setLoop(THREE.LoopOnce, 1);
    action.clampWhenFinished = true;
    action.fadeIn(MIXAMO_FADE_SECONDS).play();
    oneShotActionRef.current = action;
  }

  // ---- DEMO path: posture-driven locomotion (walking/standing only here) ---
  const appliedPostureRef = useRef<AgentPosture | null>(null);

  function applyPosture(p: AgentPosture) {
    switch (p) {
      case "MOVING":
      case "RETURNING_HOME":
        playLoop("walking");
        break;
      case "STANDING_IDLE":
      case "CONVERSATION":
        playLoop("idle");
        break;
      case "STANDING_UP":
        playOneShot("sitToStand");
        break;
      case "SITTING_DOWN":
        playOneShot("standToSit");
        break;
      case "HOME_SEATED":
        playLoop("seatedIdle");
        break;
      case "WORKING_SEATED":
        playLoop("seatedIdle");
        break;
    }
  }

  // ---- SEATED path: micro-machine (idle/talking/work), never stands --------
  const seatedPhaseRef = useRef<SeatedPhase>("SEATED_IDLE");
  const seatedInitRef = useRef(false);
  const talkHoldRef = useRef(0);
  const prevTalkKeyRef = useRef<string | null>(null);
  // Seated work cycle position (advanced in place, never reset on semantics).
  const workIdxRef = useRef(0);
  const workElapsedRef = useRef(0);

  // The action currently holding the stage (used as the crossfade source).
  function currentRunningAction(actions: MixamoActions): THREE.AnimationAction | null {
    for (const key of CLIP_KEYS) {
      const action = actions[key];
      if (action?.isRunning()) return action;
    }
    return null;
  }

  function playSeatedPhase(next: SeatedPhase) {
    const actions = actionsRef.current;
    if (!actions) return;

    let clip: MixamoClipKey;
    if (isSeatedTalking(next)) {
      clip = SEATED_TALK_CLIP;
    } else if (next === "SEATED_WORK") {
      const sequence = seatedWorkSequence(workMode);
      workIdxRef.current = 0;
      workElapsedRef.current = 0;
      clip = sequence[0].clip;
    } else {
      clip = "seatedIdle";
    }

    enterPhase(
      actions,
      currentRunningAction(actions),
      { clip, mode: "loop" },
    );
    seatedPhaseRef.current = next;
  }

  useFrame((_, delta) => {
    const mixer = mixerRef.current;
    const actions = actionsRef.current;
    if (!mixer || !actions) return;

    mixer.update(delta);

    if (demoActive) {
      const current = appliedPostureRef.current;
      const target = posture;
      if (current !== target) {
        applyPosture(target);
        appliedPostureRef.current = target;
      }
      return;
    }

    // Kick off the initial seated pose on the first frame (agent starts seated).
    if (!seatedInitRef.current) {
      seatedInitRef.current = true;
      playSeatedPhase("SEATED_IDLE");
    }

    // Detect a new delegation announcement (talk trigger edge).
    const talkKey = delegation?.talkKey ?? null;
    let hasTalk = false;
    if (talkKey !== null && talkKey !== prevTalkKeyRef.current) {
      hasTalk = true;
      talkHoldRef.current = SEATED_TALK_HOLD_SECONDS;
    }
    prevTalkKeyRef.current = talkKey;

    // Advance talking hold each frame while speaking.
    if (seatedPhaseRef.current === "SEATED_TALKING") {
      talkHoldRef.current -= delta;
    }

    const next = nextSeatedPhase(
      seatedPhaseRef.current,
      hasTalk,
      talkHoldRef.current,
    );

    if (next !== seatedPhaseRef.current) {
      playSeatedPhase(next);
    }

    // Advance the seated work cycle in place.
    if (seatedPhaseRef.current === "SEATED_WORK") {
      const sequence = seatedWorkSequence(workMode);
      workElapsedRef.current += delta;
      const phase = sequence[workIdxRef.current];
      if (workElapsedRef.current >= phaseDuration(phase, actions)) {
        const previous = actions[phase.clip];
        workIdxRef.current = (workIdxRef.current + 1) % sequence.length;
        workElapsedRef.current = 0;
        enterPhase(actions, previous, sequence[workIdxRef.current]);
      }
    }
  });

  return (
    <group ref={homeRef} position={position}>
      <group ref={turnRef}>
        <group scale={scale}>
          <primitive object={model} position={offset} />
        </group>
      </group>
      <AgentBubble
        bubble={
          delegation?.speech ??
          (delegation?.conversing ? undefined : workBubble)
        }
        color={signalColor}
      />
    </group>
  );
}
