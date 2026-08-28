import { useEffect, useRef, useState } from "react";
import type { ActivityItem, AgentRecord } from "@/lib/types";

export type AgentVisualMode =
  | "idle"
  | "planning"
  | "researching"
  | "coding"
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

function containsAny(text: string, terms: string[]): boolean {
  return terms.some((term) => text.includes(term));
}

export function deriveAgentVisualState(
  agent: AgentRecord,
): AgentVisualState {
  const activity = (agent.activity ?? "").trim();
  const text = activity.toLowerCase();

  if (agent.status === "ERROR") {
    return {
      mode: "error",
      label: activity || "Error",
      active: true,
      attention: true,
    };
  }

  if (
    containsAny(text, [
      "repair",
      "fixing",
      "fix ",
      "qa failure",
      "failed qa",
    ])
  ) {
    return {
      mode: "repairing",
      label: activity || "Repairing",
      active: true,
      attention: true,
    };
  }

  if (
    containsAny(text, [
      "reporting",
      "report to",
      "hand off",
      "handoff",
      "reviewing failed",
      "routed back",
    ])
  ) {
    return {
      mode: "reporting",
      label: activity || "Reporting",
      active: true,
      attention: true,
    };
  }

  if (
    containsAny(text, [
      "completed",
      "complete",
      "passed",
      "all checks green",
      "success",
    ])
  ) {
    return {
      mode: "success",
      label: activity || "Complete",
      active: false,
      attention: false,
    };
  }

  if (agent.status === "WAITING") {
    return {
      mode: "waiting",
      label: activity || "Waiting",
      active: true,
      attention: false,
    };
  }

  if (agent.status === "IDLE") {
    return {
      mode: "idle",
      label: "Idle",
      active: false,
      attention: false,
    };
  }

  const mode = ROLE_MODE[agent.agent_id] ?? "idle";

  return {
    mode,
    label: activity || ROLE_LABEL[agent.agent_id] || "Working",
    active: agent.status === "WORKING",
    attention: false,
  };
}

interface TransientAgentVisual {
  mode: AgentVisualMode;
  label: string;
  attention: boolean;
  expiresAt: number;
}

function transientFromActivity(
  item: ActivityItem,
): Omit<TransientAgentVisual, "expiresAt"> | null {
  const message = item.message.trim();
  const text = message.toLowerCase();

  // Structured backend events are the primary semantic signal.
  if (item.kind === "QA_RESULT") {
    if (containsAny(text, ["fail", "failed", "error"])) {
      return {
        mode: "error",
        label: message || "QA failed",
        attention: true,
      };
    }

    return {
      mode: "success",
      label: message || "QA passed",
      attention: false,
    };
  }

  if (item.kind === "RESULT") {
    if (containsAny(text, ["fail", "failed", "error"])) {
      return {
        mode: "error",
        label: message || "Failed",
        attention: true,
      };
    }

    return {
      mode: "success",
      label: message || "Complete",
      attention: false,
    };
  }

  if (item.kind === "REVIEW") {
    return {
      mode: "reporting",
      label: message || "Reviewing",
      attention: true,
    };
  }

  // Repair currently has no dedicated EventKind, so message parsing is
  // intentionally kept as a narrow fallback until the backend contract
  // exposes structured repair semantics.
  if (
    containsAny(text, [
      "repair",
      "routed back to forge",
      "fixing",
      "qa failure",
      "failed qa",
    ])
  ) {
    return {
      mode: "repairing",
      label: message || "Repairing",
      attention: true,
    };
  }

  // Generic fallback for errors that arrive through LOG/STATUS events.
  if (containsAny(text, ["failed", "error", "unhealthy"])) {
    return {
      mode: "error",
      label: message || "Error",
      attention: true,
    };
  }

  // Compatibility fallback for completion messages that are not yet
  // represented by RESULT in every executor.
  if (
    text.includes("completed successfully") ||
    text.startsWith("completed:")
  ) {
    return {
      mode: "success",
      label: message || "Complete",
      attention: false,
    };
  }

  return null;
}

function transientDuration(mode: AgentVisualMode): number {
  switch (mode) {
    case "error":
      return 3200;
    case "success":
      return 2600;
    case "repairing":
      return 2800;
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
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  useEffect(() => {
    const unseen = activity
      .filter((item) => !seenIds.current.has(item.id))
      .sort((a, b) => a.at - b.at);

    for (const item of unseen) {
      seenIds.current.add(item.id);

      const transient = transientFromActivity(item);
      if (!transient) continue;

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

          // A newer transient event replaced this one.
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
