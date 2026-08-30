// The "AI Developer Control Room" state hook:
// connects to the API WebSocket, hydrates from the initial snapshot, and
// applies incremental events (feed, agent status, task status) to live state.

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchSnapshot } from "./api";
import type {
  ActivityItem,
  AgentRecord,
  Snapshot,
  Stats,
  Task,
  WsMessage,
} from "./types";

function computeStats(tasks: Task[]): Stats {
  return {
    total: tasks.length,
    running: tasks.filter((t) =>
      ["PLANNING", "RUNNING", "REVIEW"].includes(t.status),
    ).length,
    queued: tasks.filter((t) => t.status === "QUEUED").length,
    done: tasks.filter((t) => t.status === "DONE").length,
    failed: tasks.filter((t) =>
      ["FAILED", "INTERRUPTED"].includes(t.status),
    ).length,
  };
}

export interface UseControlRoom {
  agents: AgentRecord[];
  tasks: Task[];
  activity: ActivityItem[];
  stats: Stats;
  runningTaskId: string | null;
  connected: boolean;
  addTask: (title: string, description: string) => Promise<void>;
}

export function useControlRoom(): UseControlRoom {
  const [agents, setAgents] = useState<AgentRecord[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [runningTaskId, setRunningTaskId] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const applySnapshot = (snap: Snapshot) => {
      setAgents(snap.agents);
      setTasks(snap.tasks);
      setActivity(snap.activity);
      setRunningTaskId(snap.running_task_id);
    };

    const onMessage = (ev: MessageEvent) => {
      let msg: WsMessage;
      try {
        msg = JSON.parse(ev.data) as WsMessage;
      } catch {
        return;
      }
      switch (msg.type) {
        case "snapshot":
          applySnapshot(msg.data);
          break;
        case "feed":
          setActivity((prev) => [msg.data, ...prev].slice(0, 200));
          break;
        case "agent_status":
          setAgents((prev) =>
            prev.map((a) => (a.agent_id === msg.data.agent_id ? msg.data : a)),
          );
          break;
        case "task_status":
          setTasks((prev) => {
            const i = prev.findIndex((t) => t.id === msg.data.id);
            if (i === -1) return [msg.data, ...prev];
            const next = [...prev];
            next[i] = msg.data;
            return next;
          });
          if (["PLANNING", "RUNNING", "REVIEW"].includes(msg.data.status)) {
            setRunningTaskId(msg.data.id);
          }
          break;
        case "task_finished":
          setTasks((prev) => {
            const i = prev.findIndex((t) => t.id === msg.data.id);
            const next = [...prev];
            if (i === -1) next.unshift(msg.data);
            else next[i] = msg.data;
            return next;
          });
          setRunningTaskId((cur) => (cur === msg.data.id ? null : cur));
          break;
      }
    };

    const connect = () => {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const host =
        process.env.NEXT_PUBLIC_WS_HOST ??
        `${window.location.hostname}:8000`;

      const ws = new WebSocket(`${proto}://${host}/ws`);
      wsRef.current = ws;
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) {
          retry = setTimeout(connect, 2000);
        }
      };
      ws.onerror = () => ws.close();
      ws.onmessage = onMessage;
    };

    fetchSnapshot()
      .then(applySnapshot)
      .catch(() => {})
      .finally(() => connect());

    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      wsRef.current?.close();
    };
  }, []);

  const addTask = useCallback(async (title: string, description: string) => {
    // Optimistically optimise: POST returns the queued task; fall back to a
    // refresh on failure.
    const res = await fetch("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, description }),
    });
    if (!res.ok) throw new Error("Failed to create task");
    const task = (await res.json()) as Task;
    setTasks((prev) => {
      const i = prev.findIndex((t) => t.id === task.id);
      const next = [...prev];
      if (i === -1) next.unshift(task);
      else next[i] = task;
      return next;
    });
  }, []);

  const stats = useMemo(() => computeStats(tasks), [tasks]);

  return { agents, tasks, activity, stats, runningTaskId, connected, addTask };
}