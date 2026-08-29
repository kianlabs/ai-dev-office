/**
 * Mixamo character/animation config for the shared-desk agents (default
 * character system).
 *
 * All five agents render native Mixamo characters at their accepted seat
 * positions (accepted chair / monitor / keyboard placement untouched) and
 * play the raw Mixamo sitting/typing clip cycle — no Quaternius
 * retargeting, no workflow integration, no navigation. The Quaternius
 * character path (AgentDummy / AgentCharacter) remains in the tree as a
 * temporary fallback until the later cleanup.
 *
 * Skeleton audit: every character uses the standard Mixamo humanoid rig but
 * each export carries its own bone namespace ("mixamorig", "mixamorig2",
 * "mixamorig7", "mixamorig9" …). Topology is identical, so the only fix
 * applied per character is track-name prefix normalization onto the
 * character's own namespace. The GLB characters are in meters while the
 * shared animation FBX clips stay in FBX cm; the hipsScale factor below
 * (bind hips vs the Ch22 clip reference) converts between the two spaces
 * automatically, and per-agent wrapper scales normalize every character to
 * the accepted ~1.67 u agent height.
 */
import * as THREE from "three";

import type { AgentId } from "../navigation/waypoints";

/** Animation-only Mixamo FBXs, one clip each, all named "mixamo.com" inside. */
export const MIXAMO_CLIP_URLS = {
  idle: "/models/agents/mixamo/idle.fbx",
  walking: "/models/agents/mixamo/walking.fbx",
  standToSit: "/models/agents/mixamo/stand-to-sit.fbx",
  seatedIdle: "/models/agents/mixamo/seated-idle.fbx",
  sittingTalking: "/models/agents/mixamo/sitting-talking.fbx",
  sitToType: "/models/agents/mixamo/sit-to-type.fbx",
  typing: "/models/agents/mixamo/typing.fbx",
  typeToSit: "/models/agents/mixamo/type-to-sit.fbx",
  sitToStand: "/models/agents/mixamo/sit-to-stand.fbx",
} as const;

export type MixamoClipKey = keyof typeof MIXAMO_CLIP_URLS;

/**
 * agent → native Mixamo character (optimized GLB: meshopt geometry + webp
 * textures; converted from the original FBX with FBX2glTF — skeleton, bone
 * names, skin weights and materials preserved, units auto-converted cm→m).
 * Audited from the FBXs:
 *   ch33 = business suit + tie (manager look)  → ATLAS
 *   ch22 = shirt/pants/sneakers                → SCOUT
 *   ch06 = single-mesh, tallest (183 cm)       → FORGE
 *   ch02 = casual cloth                        → QA
 *   remy = casual tops/bottoms, 2x export unit → PULSE
 * Heights are normalized to the accepted ~1.667 u agent height; swapping a
 * mapping is a one-line change here.
 */
export const MIXAMO_AGENTS: Record<
  AgentId,
  { modelUrl: string; scale: number }
> = {
  atlas: { modelUrl: "/models/agents/mixamo/ch33-nonpbr.glb", scale: 0.9344 },
  scout: { modelUrl: "/models/agents/mixamo/ch22-nonpbr.glb", scale: 0.9515 },
  forge: { modelUrl: "/models/agents/mixamo/ch06-nonpbr.glb", scale: 0.9125 },
  qa: { modelUrl: "/models/agents/mixamo/ch02-nonpbr.glb", scale: 0.9452 },
  pulse: { modelUrl: "/models/agents/mixamo/remy.glb", scale: 0.4404 },
};

/**
 * Agent rest anchors are owned by the navigation layout config (layout.ts):
 * each desk agent's rest position and its navigation home derive from the same
 * seat geometry, so a ?movementDemo=1 patrol never drifts from the rendered
 * character. `agentRestAnchor` (SharedDesk local) and `agentHomeWorld` (office
 * frame) live there and are reused by SharedDesk and the nav engine.
 */

export interface MixamoPhase {
  clip: MixamoClipKey;
  /** "once" = LoopOnce + clampWhenFinished, advance after one clip pass.
   *  "loop" = LoopRepeat, advance after `seconds`. */
  mode: "once" | "loop";
  /** Hold duration for loop phases; ignored for "once". */
  seconds?: number;
}

/** standing (Idle) → Stand To Sit → Seated Idle → Sit To Type → Typing →
 *  Type To Sit → Seated Idle → Sit To Stand → (Idle) — loops. Walking is not
 *  sequencer-driven; the navigation demo plays it while an agent moves. */
export const MIXAMO_SEQUENCE: readonly MixamoPhase[] = [
  { clip: "idle", mode: "loop", seconds: 2.5 },
  { clip: "standToSit", mode: "once" },
  { clip: "seatedIdle", mode: "loop", seconds: 8 },
  { clip: "sitToType", mode: "once" },
  { clip: "typing", mode: "loop", seconds: 16.5 },
  { clip: "typeToSit", mode: "once" },
  { clip: "seatedIdle", mode: "loop", seconds: 8 },
  { clip: "sitToStand", mode: "once" },
];

/** How long a seated agent holds the SeatedTalking clip on a delegation /
 *  announcement before returning to its seated work cycle. */
export const SEATED_TALK_SECONDS = 1.6;

/**
 * THE seated work cycle used during ACTIVE work. Agents stay at their desk and
 * never stand: no convenient `standToSit`/`sitToStand` in here, so a seated
 * agent can never "replay" entering/leaving the chair from a semantic change.
 * Typing specialists cycle between the keyboard and a brief seated rest; the
 * same loop is reused for pulse-style monitoring (the spoken part is already
 * over by the time this plays).
 */
export const MIXAMO_SEATED_SEQUENCE: readonly MixamoPhase[] = [
  { clip: "sitToType", mode: "once" },
  { clip: "typing", mode: "loop", seconds: 12 },
  { clip: "typeToSit", mode: "once" },
  { clip: "seatedIdle", mode: "loop", seconds: 4 },
];

/** Crossfade used on every phase change. Long enough that the clips'
 *  differing seat reference frames (~10 cm between Seated Idle and the typed
 *  chain) read as a scoot instead of a pop. */
export const MIXAMO_FADE_SECONDS = 0.5;

/** Matches "mixamorig", "mixamorig2", "mixamorig:" … namespace variants. */
const MIXAMO_PREFIX_RE = /^mixamorig\d*:*/i;

/** Namespace prefix of a Mixamo node name, or "" when it has none. */
export function mixamoPrefixOf(name: string): string {
  const match = name.match(MIXAMO_PREFIX_RE);
  return match ? match[0] : "";
}

/** First Mixamo bone namespace found under `root` (e.g. "mixamorig2" for
 *  Ch22_nonPBR.fbx). Empty string when the skeleton is unprefixed. */
export function detectMixamoPrefix(root: THREE.Object3D): string {
  let prefix = "";
  root.traverse((object) => {
    if (prefix || !(object instanceof THREE.Bone)) return;
    const candidate = mixamoPrefixOf(object.name);
    if (candidate) prefix = candidate;
  });
  return prefix;
}

/**
 * Flattens a clip's Hips horizontal root motion so it plays in place: X/Z
 * are frozen at their FIRST-frame values (preserving any body offset), Y is
 * left fully animated (walk bob, breathing). Used for Walking — its baked
 * ~1.77 m forward locomotion would fight the navigation engine. Idle clips
 * keep their sub-cm sway and are not passed through this.
 */
export function makeClipInPlace(clip: THREE.AnimationClip): THREE.AnimationClip {
  const hips = clip.tracks.find((track) => /Hips\.position$/.test(track.name));
  if (!hips) return clip;

  const values = hips.values;
  const next = values.map((value, index) => {
    const component = index % 3;
    return component === 1 ? value : values[component];
  });
  hips.values = next;
  return clip;
}

/**
 * Rewrites a clip's Mixamo bone names to `targetPrefix` so raw Mixamo clips
 * can play directly on the character skeleton (same topology, different
 * namespace). Non-Mixamo nodes are left untouched. The clip is renamed to
 * `clipName` because Mixamo names every clip "mixamo.com", which would
 * collide when several clips feed one mixer.
 *
 * `hipsScale` compensates characters whose skeletons are authored larger or
 * smaller than the clip reference (the Ch22 FBX, bind hips 100.35 cm): the
 * Hips position track values are multiplied by it so the pelvis trajectory
 * keeps the authored proportions (e.g. Remy is authored ~2.1x). Because
 * bind hips is measured in the character's own units, this also absorbs the
 * GLB cm→m conversion. Values are copied before scaling — the source track
 * may share arrays with the cached FBX other agents still read.
 */
export function normalizeMixamoClip(
  clip: THREE.AnimationClip,
  targetPrefix: string,
  clipName: string,
  hipsScale = 1,
): THREE.AnimationClip {
  for (const track of clip.tracks) {
    const dot = track.name.indexOf(".");
    const node = dot === -1 ? track.name : track.name.slice(0, dot);
    const rest = dot === -1 ? "" : track.name.slice(dot);

    if (!MIXAMO_PREFIX_RE.test(node)) continue;

    const stripped = node.replace(MIXAMO_PREFIX_RE, "");
    track.name = `${targetPrefix}${stripped}${rest}`;

    if (hipsScale !== 1 && /Hips\.position$/.test(track.name)) {
      track.values = track.values.map((value) => value * hipsScale);
    }
  }

  clip.name = clipName;
  return clip;
}
