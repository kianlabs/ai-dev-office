// Types mirrored from the Python domain models (ai_dev_shared).

export type TaskStatus =
  | "QUEUED"
  | "PLANNING"
  | "RUNNING"
  | "REVIEW"
  | "DONE"
  | "FAILED"
  | "INTERRUPTED";

export type AgentStatus = "IDLE" | "WORKING" | "WAITING" | "ERROR";

export type EventKind =
  | "STATUS"
  | "LOG"
  | "SUBTASKS"
  | "QA_RESULT"
  | "HEALTH"
  | "REVIEW"
  | "RESULT";

export interface Subtask {
  id: string;
  title: string;
  agent_id: string;
  status: TaskStatus;
}

export interface Task {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  subtasks: Subtask[];
  summary?: string | null;
  error?: string | null;
  created_at: number;
  updated_at: number;
}

export interface AgentRecord {
  agent_id: string;
  name: string;
  role: string;
  color: string;
  status: AgentStatus;
  activity: string;
  last_event_at: number;
}

export interface ActivityItem {
  id: string;
  at: number;
  agent_id: string;
  agent_name: string;
  task_id?: string | null;
  message: string;
  kind: EventKind;
}

export interface AgentBaySnapshot {
  id: string;
  title: string;
  status: TaskStatus;
}

export interface Stats {
  total: number;
  running: number;
  queued: number;
  done: number;
  failed: number;
}

export interface Snapshot {
  tasks: Task[];
  agents: AgentRecord[];
  activity: ActivityItem[];
  stats: Stats;
  running_task_id: string | null;
}

export type WsMessage =
  | { type: "snapshot"; data: Snapshot }
  | { type: "feed"; data: ActivityItem }
  | { type: "agent_status"; data: AgentRecord }
  | { type: "task_status"; data: Task }
  | { type: "task_finished"; data: Task }
  | { type: "pong" };

export const AGENT_ORDER = ["atlas", "scout", "forge", "qa", "pulse"] as const;