"use client";

import { AGENT_ORDER, type AgentRecord } from "@/lib/types";

import { useControlRoom } from "@/lib/use-control-room";
import ActivityFeed from "@/components/activity-feed";
import AgentCard from "@/components/agent-card";
import CreateTaskForm from "@/components/create-task";
import StatCard from "@/components/stat-card";
import TasksPanel from "@/components/tasks-panel";
import TopBar from "@/components/top-bar";
import ClientOffice from "@/components/office-3d/ClientOffice";

function TaskIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M4 6h16v2H4zm0 5h16v2H4zm0 5h10v2H4z" />
    </svg>
  );
}
function RunIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <circle cx="12" cy="12" r="9" opacity="0.25" />
      <circle cx="12" cy="12" r="5" />
    </svg>
  );
}
function DoneIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z" />
    </svg>
  );
}
function FailIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2 2 7v6c0 5 4.3 8.6 10 9 5.7-.4 10-4 10-9V7zM11 7h2v7h-2zm0 9h2v2h-2z" />
    </svg>
  );
}

export default function Home() {
  const room = useControlRoom();

  const orderedAgents: AgentRecord[] = AGENT_ORDER.map(
    (id) => room.agents.find((a) => a.agent_id === id) as AgentRecord,
  ).filter(Boolean);

  const stats = [
    { label: "Tasks", value: room.stats.total, accent: "#60a5fa", icon: <TaskIcon /> },
    { label: "Running", value: room.stats.running, accent: "#34d399", icon: <RunIcon /> },
    { label: "Completed", value: room.stats.done, accent: "#34d399", icon: <DoneIcon /> },
    { label: "Failed", value: room.stats.failed, accent: "#f87171", icon: <FailIcon /> },
  ];

  return (
    <div className="flex h-screen flex-col">
      <TopBar connected={room.connected} taskCount={room.stats.total} />

      {/* stats row */}
      <div className="grid grid-cols-2 gap-3 border-b border-line bg-panel2/40 p-3 md:grid-cols-4">
        {stats.map((s) => (
          <StatCard key={s.label} {...s} />
        ))}
      </div>

      {/* main row: 3D office (primary) + activity feed */}
      <main className="flex min-h-0 flex-1 overflow-hidden">
        <div className="relative min-w-0 flex-1 p-3">
          <ClientOffice agents={room.agents} activity={room.activity} />
        </div>

        <aside className="hidden w-[360px] shrink-0 border-l border-line p-3 lg:block">
          <ActivityFeed items={room.activity} />
        </aside>
      </main>

      {/* bottom: task controls / secondary information */}
      <div className="grid max-h-[38%] grid-cols-1 gap-3 overflow-y-auto border-t border-line bg-panel2/40 p-3 md:grid-cols-2 xl:grid-cols-3">
        <div className="max-h-full overflow-y-auto">
          <CreateTaskForm disabled={!room.connected} onCreate={room.addTask} />
        </div>

        <div className="max-h-full overflow-y-auto">
          <TasksPanel tasks={room.tasks} />
        </div>

        <div className="max-h-full overflow-y-auto">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-mono text-sm font-semibold uppercase tracking-wider text-slate-300">
              Agent Bay
            </h2>
            <span className="font-mono text-xs text-slate-500">
              {room.agents.filter((a) => a.status !== "IDLE").length}/5 active
            </span>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {orderedAgents.map((agent) => (
              <AgentCard
                key={agent.agent_id}
                agent={agent}
                isOrchestrator={agent.agent_id === "atlas"}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}