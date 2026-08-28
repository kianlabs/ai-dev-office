"use client";

import { useEffect, useRef, useState } from "react";
import type { ActivityItem, AgentRecord } from "@/lib/types";

/* ================================================================
 * TYPES
 * ================================================================ */

export type AgentVisualMode =
  | "idle"
  | "planning"
  | "dispatching"
  | "researching"
  | "coding"
  | "building"
  | "testing"
  | "monitoring"
  | "reporting"
  | "repairing"
  | "waiting"
  | "success"
  | "error";

export interface AgentVisualState {
  mode: AgentVisualMode;
  label: string;
  active: boolean;
  attention: boolean;
}

export interface TransientAgentVisual {
  mode: AgentVisualMode;
  label: string;
  attention: boolean;
  expiresAt: number;
}

/* ================================================================
 * CONSTANTS
 * ================================================================ */

const ROLE_MODE: Record<string, AgentVisualMode> = {
  atlas: "planning",
  scout: "researching",
  forge: "coding",
  qa: "testing",
  pulse: "monitoring",
};

const ROLE_LABEL: Record<string, string> = {
  atlas: "Planning",
  scout: "Researching",
  forge: "Coding",
  qa: "Testing",
  pulse: "Monitoring",
};

/* ================================================================
 * UTILITY FUNCTIONS
 * ================================================================ */

/**
 * Match a phrase safely.
 *
 * This avoids false positives such as:
 * "fix" matching "prefix".
 */
export function containsPhrase(text: string, phrase: string): boolean {
  const escaped = phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  return new RegExp(
    `(?:^|[^a-z0-9])${escaped}(?:$|[^a-z0-9])`,
    "i",
  ).test(text);
}

export function containsAny(text: string, phrases: string[]): boolean {
  return phrases.some((phrase) => containsPhrase(text, phrase));
}

/* ================================================================
 * PERSISTENT/BASE SEMANTIC RESOLVER
 * ================================================================ */

/**
 * Resolve the presentation state from the agent's current backend state.
 *
 * IMPORTANT:
 * This function describes the persistent/base state only.
 * Success/error events that should disappear after a few seconds are handled
 * separately by the transient activity layer below.
 */
export function deriveAgentVisualState(
  agent: AgentRecord,
): AgentVisualState {
  const activity = (agent.activity ?? "").trim();
  const text = activity.toLowerCase();

  // ERROR always wins
  if (agent.status === "ERROR") {
    return {
      mode: "error",
      label: activity || "Error",
      active: true,
      attention: true,
    };
  }

  // Repairing has higher priority than normal coding/testing
  const repairingPhrases = [
    "repairing",
    "repair",
    "fixing",
    "qa failure",
    "failed qa",
    "routed back to forge",
    "routed back",
  ];

  if (containsAny(text, repairingPhrases)) {
    return {
      mode: "repairing",
      label: activity || "Repairing",
      active: true,
      attention: true,
    };
  }

  // Waiting is an explicit state
  if (
    agent.status === "WAITING" ||
    containsAny(text, ["waiting for", "holding watch window"])
  ) {
    return {
      mode: "waiting",
      label: activity || "Waiting",
      active: true,
      attention: false,
    };
  }

  // Role-specific state resolution
  const roleState = resolveRoleState(agent.agent_id, text, activity);
  if (roleState) {
    return roleState;
  }

  // Explicit idle backend state always returns idle
  if (agent.status === "IDLE") {
    return {
      mode: "idle",
      label: "Idle",
      active: false,
      attention: false,
    };
  }

  // Generic fallback based on role
  const mode = ROLE_MODE[agent.agent_id] ?? "idle";

  return {
    mode,
    label: activity || ROLE_LABEL[agent.agent_id] || "Working",
    active: agent.status === "WORKING",
    attention: false,
  };
}

/**
 * Resolve role-specific visual state.
 * Returns null if no role-specific state matches.
 */
function resolveRoleState(
  agentId: string,
  text: string,
  activity: string,
): AgentVisualState | null {
  switch (agentId) {
    case "atlas":
      return resolveAtlasState(text, activity);
    case "scout":
      return resolveScoutState(text, activity);
    case "forge":
      return resolveForgeState(text, activity);
    case "qa":
      return resolveQaState(text, activity);
    case "pulse":
      return resolvePulseState(text, activity);
    default:
      return null;
  }
}

function resolveAtlasState(
  text: string,
  activity: string,
): AgentVisualState | null {
  // Dispatching states
  if (
    containsAny(text, [
      "dispatching",
      "created subtasks",
      "selected specialists",
    ])
  ) {
    return {
      mode: "dispatching",
      label: activity || "Dispatching",
      active: true,
      attention: false,
    };
  }

  // Reviewing/Reporting states
  if (
    containsAny(text, [
      "reviewing",
      "review specialist",
      "reviewing specialist results",
      "reviewing failed",
      "reviewing qa",
      "reporting",
      "report to",
    ])
  ) {
    return {
      mode: "reporting",
      label: activity || "Reviewing",
      active: true,
      attention: false,
    };
  }

  // Planning states
  if (
    containsAny(text, [
      "parsing task",
      "requirement understood",
      "planning",
    ])
  ) {
    return {
      mode: "planning",
      label: activity || "Planning",
      active: true,
      attention: false,
    };
  }

  return null;
}

function resolveScoutState(
  text: string,
  activity: string,
): AgentVisualState | null {
  // Reporting/Handoff states
  if (
    containsAny(text, [
      "research brief",
      "research accepted",
      "report delivered",
      "research delivered",
      "hand off",
      "handoff",
    ])
  ) {
    return {
      mode: "reporting",
      label: activity || "Reporting",
      active: true,
      attention: false,
    };
  }

  // Researching states
  if (
    containsAny(text, [
      "scanning",
      "research",
      "reading documentation",
      "reading docs",
      "evaluating",
      "investigating",
      "analyzing",
      "analysis",
    ])
  ) {
    return {
      mode: "researching",
      label: activity || "Researching",
      active: true,
      attention: false,
    };
  }

  return null;
}

function resolveForgeState(
  text: string,
  activity: string,
): AgentVisualState | null {
  // Building states
  if (
    containsAny(text, [
      "build",
      "compiling",
      "compiled",
      "npm run build",
      "building",
    ])
  ) {
    return {
      mode: "building",
      label: activity || "Building",
      active: true,
      attention: false,
    };
  }

  // Handoff states
  if (
    containsAny(text, [
      "handing off",
      "hand off",
      "handoff",
      "waiting for qa",
    ])
  ) {
    return {
      mode: "reporting",
      label: activity || "Handing off",
      active: true,
      attention: false,
    };
  }

  // Coding states
  if (
    containsAny(text, [
      "editing",
      "implementing",
      "implementation",
      "coding",
      "updated",
      "restoring workspace",
      "source implementation",
    ])
  ) {
    return {
      mode: "coding",
      label: activity || "Coding",
      active: true,
      attention: false,
    };
  }

  return null;
}

function resolveQaState(
  text: string,
  activity: string,
): AgentVisualState | null {
  // Repairing states (QA-specific)
  if (
    containsAny(text, [
      "repair",
      "qa failure",
      "failed qa",
      "routed back",
    ])
  ) {
    return {
      mode: "repairing",
      label: activity || "Repairing",
      active: true,
      attention: true,
    };
  }

  // Testing states
  if (
    containsAny(text, [
      "running test",
      "running tests",
      "running typecheck",
      "running lint",
      "regression",
      "test suite",
      "verification",
    ])
  ) {
    return {
      mode: "testing",
      label: activity || "Testing",
      active: true,
      attention: false,
    };
  }

  return null;
}

function resolvePulseState(
  text: string,
  activity: string,
): AgentVisualState | null {
  // Error states (Pulse-specific)
  if (
    containsAny(text, [
      "unhealthy",
      "runtime unhealthy",
      "health check failed",
      "unhandled exception",
    ])
  ) {
    return {
      mode: "error",
      label: activity || "Unhealthy",
      active: true,
      attention: true,
    };
  }

  // Monitoring states
  if (
    containsAny(text, [
      "watching",
      "scanning runtime",
      "scanning runtime error",
      "runtime error logs",
      "deploy",
      "deployment",
      "health",
      "monitoring",
      "tail ",
    ])
  ) {
    return {
      mode: "monitoring",
      label: activity || "Monitoring",
      active: true,
      attention: false,
    };
  }

  return null;
}

/* ================================================================
 * TRANSIENT EVENT RESOLVER
 * ================================================================ */

/**
 * Resolve transient visual state from an activity event.
 * Returns null if the event doesn't produce a transient state.
 */
function transientFromActivity(
  item: ActivityItem,
): Omit<TransientAgentVisual, "expiresAt"> | null {
  const message = item.message.trim();
  const text = message.toLowerCase();
  const kind = String(item.kind).toUpperCase();

  // ERROR has the highest transient priority
  if (
    kind === "ERROR" ||
    containsAny(text, [
      "unhealthy",
      "unhandled exception",
      "execution failed",
      "task failed",
      "qa failed",
      "failed qa",
    ])
  ) {
    return {
      mode: "error",
      label: message || "Error",
      attention: true,
    };
  }

  // Repair event
  if (
    containsAny(text, [
      "repairing",
      "repair attempt",
      "routed back to forge",
      "routed back",
      "fixing",
    ])
  ) {
    return {
      mode: "repairing",
      label: message || "Repairing",
      attention: true,
    };
  }

  // QA PASS
  if (
    kind === "QA_RESULT" &&
    containsAny(text, ["pass", "passed", "green"])
  ) {
    return {
      mode: "success",
      label: message || "QA passed",
      attention: false,
    };
  }

  // Generic successful RESULT (deliberately transient)
  if (
    kind === "RESULT" &&
    !containsAny(text, ["failed", "error"])
  ) {
    return {
      mode: "success",
      label: message || "Complete",
      attention: false,
    };
  }

  // Explicit success phrases
  if (
    containsAny(text, [
      "completed successfully",
      "completed:",
      "all checks green",
      "health: build green",
      "deploy healthy",
    ])
  ) {
    return {
      mode: "success",
      label: message || "Complete",
      attention: false,
    };
  }

  // Reporting / handoff
  if (
    kind === "REVIEW" ||
    containsAny(text, [
      "reviewing",
      "reporting",
      "research brief delivered",
      "research accepted",
      "handing off",
      "hand off",
      "handoff",
    ])
  ) {
    return {
      mode: "reporting",
      label: message || "Reporting",
      attention: false,
    };
  }

  return null;
}

/* ================================================================
 * TRANSIENT LIFECYCLE
 * ================================================================ */

function transientDuration(mode: AgentVisualMode): number {
  switch (mode) {
    case "error":
      return 3200;

    case "repairing":
      return 2800;

    case "success":
      return 2600;

    case "reporting":
      return 1800;

    default:
      return 2000;
  }
}

export function useTransientAgentVisuals(
  activity: ActivityItem[],
): Record<string, TransientAgentVisual> {
  const [visuals, setVisuals] = useState<
    Record<string, TransientAgentVisual>
  >({});

  const seenIds = useRef(new Set<string>());
  const timers = useRef(
    new Map<string, ReturnType<typeof setTimeout>>(),
  );

  useEffect(() => {
    const unseen = activity
      .filter((item) => !seenIds.current.has(item.id))
      .sort((a, b) => a.at - b.at);

    for (const item of unseen) {
      seenIds.current.add(item.id);

      const transient = transientFromActivity(item);

      if (!transient) {
        continue;
      }

      const duration = transientDuration(transient.mode);
      const expiresAt = Date.now() + duration;

      setVisuals((current) => ({
        ...current,
        [item.agent_id]: {
          ...transient,
          expiresAt,
        },
      }));

      const previousTimer = timers.current.get(item.agent_id);

      if (previousTimer) {
        clearTimeout(previousTimer);
      }

      const timer = setTimeout(() => {
        setVisuals((current) => {
          const active = current[item.agent_id];

          // A newer event replaced this transient state
          if (!active || active.expiresAt !== expiresAt) {
            return current;
          }

          const next = { ...current };
          delete next[item.agent_id];

          return next;
        });

        timers.current.delete(item.agent_id);
      }, duration);

      timers.current.set(item.agent_id, timer);
    }
  }, [activity]);

  useEffect(() => {
    const activeTimers = timers.current;

    return () => {
      for (const timer of activeTimers.values()) {
        clearTimeout(timer);
      }

      activeTimers.clear();
    };
  }, []);

  return visuals;
}

/* ================================================================
 * STATE MERGER
 * ================================================================ */

export function applyTransientVisualState(
  base: AgentVisualState,
  transient: TransientAgentVisual | undefined,
): AgentVisualState {
  if (!transient) {
    return base;
  }

  return {
    mode: transient.mode,
    label: transient.label,
    active: true,
    attention: transient.attention,
  };
}
