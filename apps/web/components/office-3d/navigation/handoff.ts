/**
 * Semantic Agent Handoff V1 — pure seated delegation helpers.
 *
 * During ACTIVE work agents stay seated, so delegation is expressed purely as
 * bubble/status text and a "talk" trigger — there is NO walk-to-agent
 * interplay routing here anymore. These helpers are pure and shared by the
 * seated delegation hook (useAgentDelegation) and the agent renderer.
 *
 * The old handoff choreography (ATLAS walking to a specialist, interaction-
 * point routing) has been removed; the desk-avoiding corridor (routing.ts) and
 * the posture/nav engine remain intact for ambient IDLE and ?movementDemo=1.
 */
import type { AgentId } from "./waypoints";
import type { AgentVisualMode } from "../semantic";

/** A world-anchored text indicator shown above an agent. */
export interface HandoffBubble {
  text: string;
  /** 'speech' = transient delegation bubble; 'status' = persistent work. */
  kind: "speech" | "status";
}

/** V1 delegation roles: target agent → persistent work state. */
export type HandoffRole = "scout" | "forge" | "qa" | "pulse";

/**
 * Agent work-state derived from role. ATLAS is the coordinator.
 * `label` is USER-FACING display copy (Bahasa Indonesia); `mode` is the
 * internal semantic key and must stay unchanged.
 */
export interface WorkState {
  label: string;
  mode: AgentVisualMode;
}

export const WORK_STATE: Record<AgentId, WorkState> = {
  atlas: { label: "Mengoordinasikan...", mode: "dispatching" },
  scout: { label: "Meneliti...", mode: "researching" },
  forge: { label: "Menulis kode...", mode: "coding" },
  qa: { label: "Menguji...", mode: "testing" },
  pulse: { label: "Memantau...", mode: "monitoring" },
};

/** Work state for an agent by id (persistent compact status label). */
export function handoffWorkState(agentId: AgentId): WorkState {
  return WORK_STATE[agentId];
}

/** Bubble text for the V1 seated delegation conversation. */
export interface HandoffBubbles {
  /** ATLAS → target while announcing the delegation. */
  assign: string;
  /** Target → ATLAS acknowledging receipt. */
  received: string;
}

export const HANDOFF_BUBBLES: Record<HandoffRole, HandoffBubbles> = {
  scout: {
    assign: "Assigning research...",
    received: "Task received",
  },
  forge: {
    assign: "Assigning implementation...",
    received: "Task received",
  },
  qa: {
    assign: "Assigning review...",
    received: "Task received",
  },
  pulse: {
    assign: "Check runtime...",
    received: "Task received",
  },
};

/**
 * Persistent work-status bubble derived from an agent's semantic visual state.
 * Single source of truth: shows the role's compact work label whenever the
 * agent is actively working, hides when idle/error/waiting. Never drives
 * posture — semantic changes only alter text, not the seated state.
 */
export function statusBubbleFor(
  agentId: AgentId,
  mode: AgentVisualMode,
  active: boolean,
): HandoffBubble | undefined {
  if (!active) return undefined;
  switch (mode) {
    case "researching":
    case "coding":
    case "testing":
    case "monitoring":
    case "building":
    case "dispatching":
    case "planning":
      return { text: WORK_STATE[agentId].label, kind: "status" };
    default:
      return undefined;
  }
}

const AGENT_TOKEN_RE = /\b(SCOUT|FORGE|QA|PULSE)\b/g;

/** Normalize an upper-cased specialist token to a HandoffRole. */
function tokenToRole(token: string): HandoffRole {
  return token.toLowerCase() as HandoffRole;
}

/**
 * Determine which agent ATLAS is currently delegating to, from ATLAS's
 * existing activity text. Prefers an explicit "Dispatching <AGENT>" mention;
 * falls back to the first specialist token present. Returns null when no
 * delegation is in progress (e.g. "Dispatching selected specialists").
 */
export function detectHandoffTarget(atlasActivity: string): HandoffRole | null {
  const text = (atlasActivity ?? "").toUpperCase();

  const dispatch = text.match(
    /\bDISPATCH\w*\s+(SCOUT|FORGE|QA|PULSE)\b/,
  );
  const dispatchToken = dispatch?.[1];
  if (dispatchToken) return tokenToRole(dispatchToken);

  const tokens = text.match(AGENT_TOKEN_RE) ?? [];
  const first = tokens[0];
  if (first) return tokenToRole(first);

  return null;
}
