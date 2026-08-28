// Tiny client for the control-room API.

import type { AgentRecord, Snapshot, Task } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, init);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status} on ${url}: ${body.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchSnapshot(): Promise<Snapshot> {
  return json<Snapshot>("/api/snapshot");
}

export async function fetchAgents(): Promise<AgentRecord[]> {
  return json<AgentRecord[]>("/api/agents");
}

export async function createTask(title: string, description: string): Promise<Task> {
  return json<Task>("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, description }),
  });
}