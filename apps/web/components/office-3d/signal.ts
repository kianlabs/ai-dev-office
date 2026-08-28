import type { AgentStatus } from "@/lib/types";

// Shared visual mapping for an agent status. Used by the 3D office to drive
// workstation visuals. Reading existing domain state, not inventing new one.

export interface StatusVisual {
  label: string;
  color: string;      // primary glow / indicator color
  screen: number;     // monitor emissive intensity
  system: string;     // hex for HTML overlay accents
}

export const STATUS_VISUAL: Record<AgentStatus, StatusVisual> = {
  IDLE: { label: "Idle", color: "#475569", screen: 0.25, system: "#94a3b8" },
  WORKING: { label: "Working", color: "#34d399", screen: 1.3, system: "#34d399" },
  WAITING: { label: "Waiting", color: "#fbbf24", screen: 0.8, system: "#fbbf24" },
  ERROR: { label: "Error", color: "#f87171", screen: 1.0, system: "#f87171" },
};

export const ACTIVITY_LABEL: Record<string, string> = {
  atlas: "Planning",
  scout: "Researching",
  forge: "Coding",
  qa: "Testing",
  pulse: "Monitoring",
};

export const AGENT_SIGNAL: Record<string, string> = {
  atlas: "#60a5fa",
  scout: "#a78bfa",
  forge: "#f59e0b",
  qa: "#34d399",
  pulse: "#22d3ee",
};