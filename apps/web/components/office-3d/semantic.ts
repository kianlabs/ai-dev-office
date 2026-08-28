import type { AgentRecord } from "@/lib/types";

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
