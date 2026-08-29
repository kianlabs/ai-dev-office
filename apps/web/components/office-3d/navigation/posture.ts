/**
 * Pure locomotion/posture state machine for desk agents.
 *
 * Given the current posture and a snapshot of the navigation context, returns
 * the next posture. It encodes the hard rules of the single-owner model:
 *
 *   - a seated agent may only leave the desk via STANDING_UP (sit->stand); it
 *     can NEVER transition straight into MOVING (Walking while seated).
 *   - MOVING / CONVERSATION may never drop straight into a seated posture —
 *     they must first RETURNING_HOME, arrive at the desk (nearHome), then
 *     SITTING_DOWN (stand->sit) before seated.
 *   - STANDING_UP and SITTING_DOWN only complete via an explicit external
 *     signal (finishOneShot) — here they return themselves to indicate 'await'.
 *   - closing the stand goal mid-route cancels smoothly toward home.
 *
 * Pure + testable; the hook (usePatrolNavigation) integrates position each
 * frame using these transitions plus its movement stepping.
 */

export type AgentPosture =
  | "HOME_SEATED"
  | "STANDING_UP"
  | "STANDING_IDLE"
  | "MOVING"
  | "CONVERSATION"
  | "RETURNING_HOME"
  | "SITTING_DOWN"
  | "WORKING_SEATED";

export interface TransitionContext {
  /** True when a conversation stand point is requested (stand at it). */
  wantsStand: boolean;
  /** True when the agent's current XZ is at the desk home anchor. */
  nearHome: boolean;
  /** True when the agent's current XZ is at the requested stand point. */
  nearStand: boolean;
}

/** One-shot transitions resolved externally (clip-completion feedback). */
export function completeStandingUp(): AgentPosture {
  return "STANDING_IDLE";
}
export function completeSittingDown(): AgentPosture {
  return "WORKING_SEATED";
}

/**
 * Next posture given the current one and the navigation context. One-shot
 * states (STANDING_UP / SITTING_DOWN) are unchanged here — they wait for the
 * external completion signal.
 */
export function nextPosture(
  state: AgentPosture,
  ctx: TransitionContext,
): AgentPosture {
  switch (state) {
    case "HOME_SEATED":
    case "WORKING_SEATED":
      // Leave the desk only after standing up; never walk from seated.
      return ctx.wantsStand ? "STANDING_UP" : state;

    case "STANDING_UP":
    case "SITTING_DOWN":
      return state;

    case "STANDING_IDLE":
      if (ctx.wantsStand) {
        return ctx.nearStand ? "CONVERSATION" : "MOVING";
      }
      return ctx.nearHome ? "SITTING_DOWN" : "RETURNING_HOME";

    case "MOVING":
      if (ctx.wantsStand) {
        return ctx.nearStand ? "CONVERSATION" : "MOVING";
      }
      // Stand goal closed mid-route → cancel smoothly toward home.
      return ctx.nearHome ? "SITTING_DOWN" : "RETURNING_HOME";

    case "CONVERSATION":
      if (ctx.wantsStand) return "CONVERSATION";
      return ctx.nearHome ? "SITTING_DOWN" : "RETURNING_HOME";

    case "RETURNING_HOME":
      // Never sit before actually arriving at the desk.
      return ctx.nearHome ? "SITTING_DOWN" : "RETURNING_HOME";
  }
}

/**
 * Convenience for tests: whether a posture is a seated posture.
 */
export function isSeatedPosture(state: AgentPosture): boolean {
  return state === "HOME_SEATED" || state === "WORKING_SEATED";
}
