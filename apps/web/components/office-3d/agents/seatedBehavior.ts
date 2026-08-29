/**
 * Pure seated-behavior state machine for ACTIVE work.
 *
 * During active work every agent stays at its workstation — no standing, no
 * walking, no teleport. Semantic changes may update bubble/status text but must
 * never replay sit/stand or reset posture. This module owns the SEATED micro
 * transitions only:
 *
 *   SEATED_IDLE --[delegation/announcement]--> SEATED_TALKING --[hold]--> SEATED_WORK
 *   SEATED_WORK --[new delegation/announcement]--> SEATED_TALKING --[hold]--> SEATED_WORK
 *   (any semantic text change with no new announcement keeps SEATED_WORK)
 *
 * Sitting Talking uses the Mixamo SeatedTalking clip for the hold window; then
 * the agent returns to its seated work cycle (typing, or seated rest for
 * monitor/coordinator roles) — all crossfaded, never standing.
 *
 * Pure + testable; MixamoAgent manages the per-frame hold timer and feeds the
 * (hasTalk, talkRemaining) inputs. The navigation/posture machine (posture.ts),
 * the desk routing (routing.ts) and usePatrolNavigation are intentionally left
 * intact for ambient IDLE later and for ?movementDemo=1 — they are simply not
 * driven during active seated work.
 */
import { MIXAMO_SEATED_SEQUENCE, SEATED_TALK_SECONDS, type MixamoPhase } from "./mixamo";

export type SeatedPhase = "SEATED_IDLE" | "SEATED_TALKING" | "SEATED_WORK";

/** How an agent "works" while seated. */
export type WorkMode = "typing" | "monitor";

/** Seated clip a role replays on a NEW announcement (transient, held). */
export const SEATED_TALK_CLIP = "sittingTalking" as const;

/** Next seated phase given the current one and the tick inputs.
 *  - `hasTalk`: true on the very frame a new delegation announcement arrived.
 *  - `talkRemaining`: seconds of talking hold left (>0 while speaking). */
export function nextSeatedPhase(
  phase: SeatedPhase,
  hasTalk: boolean,
  talkRemaining: number,
): SeatedPhase {
  switch (phase) {
    case "SEATED_IDLE":
      return hasTalk ? "SEATED_TALKING" : phase;
    case "SEATED_TALKING":
      return talkRemaining > 0 ? "SEATED_TALKING" : "SEATED_WORK";
    case "SEATED_WORK":
      return hasTalk ? "SEATED_TALKING" : phase;
  }
}

/**
 * The seated work clip cycle for a role's work mode. Typing (SCOUT/FORGE/QA)
 * works the keyboard; monitor (PULSE) and coordinator (ATLAS) rest seated.
 * Neither variant touches standToSit/sitToStand, so a seated agent is locked
 * to its chair.
 */
export function seatedWorkSequence(mode: WorkMode): readonly MixamoPhase[] {
  if (mode === "typing") return MIXAMO_SEATED_SEQUENCE;
  return [{ clip: "seatedIdle", mode: "loop", seconds: 6 }];
}

/** Convenience: whether a seated phase maps to the SeatedTalking clip. */
export function isSeatedTalking(phase: SeatedPhase): boolean {
  return phase === "SEATED_TALKING";
}

export const SEATED_TALK_HOLD_SECONDS = SEATED_TALK_SECONDS;
