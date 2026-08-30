"use client";

import { FormEvent, KeyboardEvent, useMemo, useState } from "react";

import ActivityFeed from "@/components/activity-feed";
import AtlasResponseCard from "@/components/atlas-response-card";
import ClientOffice from "@/components/office-3d/ClientOffice";
import { useControlRoom } from "@/lib/use-control-room";
import { taskInputParts } from "@/lib/task-input";
import { AGENT_ORDER, type AgentRecord } from "@/lib/types";

function Icon({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <span className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400">
      {children}
    </span>
  );
}

function HomeIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z" />
    </svg>
  );
}

function TaskIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <path d="M8 8h8M8 12h8M8 16h5" />
    </svg>
  );
}

function AgentIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="8" r="4" />
      <path d="M5 21a7 7 0 0 1 14 0" />
    </svg>
  );
}

function FolderIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
    </svg>
  );
}

function ReportIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21h-4v-.09A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3v-4h.09A1.7 1.7 0 0 0 4.6 8.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3h4v.09A1.7 1.7 0 0 0 15.4 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.38.27.73.62 1 .99.25.34.39.75.4 1.17V11h.2v2h-.2v-.09a1.7 1.7 0 0 0-1.4 2.09Z" />
    </svg>
  );
}

function StatBox({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "blue" | "amber" | "green" | "red" | "purple";
}) {
  const toneClass = {
    blue: "bg-blue-500/10 text-blue-400",
    amber: "bg-amber-500/10 text-amber-400",
    green: "bg-emerald-500/10 text-emerald-400",
    red: "bg-red-500/10 text-red-400",
    purple: "bg-violet-500/10 text-violet-400",
  }[tone];

  return (
    <div className="flex min-w-0 items-center justify-between rounded-xl border border-white/[0.07] bg-[#111722]/85 px-4 py-3 shadow-sm">
      <div>
        <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500">
          {label}
        </div>
        <div className="mt-1 font-mono text-2xl font-semibold text-slate-100">
          {value}
        </div>
      </div>
      <div className={`h-9 w-9 rounded-lg ${toneClass}`} />
    </div>
  );
}

function NavItem({
  active = false,
  label,
  icon,
}: {
  active?: boolean;
  label: string;
  icon: React.ReactNode;
}) {
  return (
    <button
      type="button"
      disabled={!active}
      className={[
        "flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left text-sm transition",
        active
          ? "bg-emerald-400/[0.09] text-slate-100"
          : "cursor-default text-slate-500",
      ].join(" ")}
    >
      <Icon>{icon}</Icon>
      <span>{label}</span>
      {!active && (
        <span className="ml-auto text-[9px] uppercase tracking-widest text-slate-700">
          soon
        </span>
      )}
    </button>
  );
}

export default function Home() {
  const room = useControlRoom();
  const [prompt, setPrompt] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const orderedAgents: AgentRecord[] = AGENT_ORDER.map(
    (id) => room.agents.find((a) => a.agent_id === id) as AgentRecord,
  ).filter(Boolean);

  const atlas = orderedAgents.find((agent) => agent.agent_id === "atlas");

  const activeAgents = useMemo(
    () => room.agents.filter((agent) => agent.status !== "IDLE").length,
    [room.agents],
  );

  async function submitTask() {
    const text = prompt.trim();

    if (!text || submitting || !room.connected) return;

    setSubmitting(true);

    try {
      // Keep the full multi-line content as the task description; only the
      // display title is the (shortened) first line.
      const { displayTitle, content } = taskInputParts(prompt);
      await room.addTask(displayTitle, content);
      setPrompt("");
    } finally {
      setSubmitting(false);
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void submitTask();
  }

  function handlePromptKeyDown(
    event: KeyboardEvent<HTMLTextAreaElement>,
  ) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitTask();
    }
  }

  return (
    <div className="flex h-[100dvh] min-h-0 flex-col overflow-hidden bg-[#080c14] text-slate-100">
      {/* Header */}
      <header className="flex h-16 shrink-0 items-center justify-between border-b border-white/[0.06] bg-[#090e17]/95 px-5">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/[0.08] bg-[#111824] font-mono text-sm font-bold text-slate-200">
            AO
          </div>

          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-lg font-semibold tracking-tight text-slate-100">
                AI Dev Office
              </h1>

              <span className="flex items-center gap-1.5 text-xs text-slate-400">
                <span
                  className={`h-2 w-2 rounded-full ${
                    room.connected
                      ? "bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,.7)]"
                      : "bg-amber-400"
                  }`}
                />
                {room.connected ? "Live" : "Connecting"}
              </span>
            </div>
          </div>
        </div>

        <div className="hidden items-center gap-3 md:flex">
          <div className="rounded-xl border border-white/[0.07] bg-[#101620] px-4 py-2">
            <div className="text-[9px] uppercase tracking-wider text-slate-600">
              Runtime
            </div>
            <div className="text-xs font-medium text-slate-300">
              Local Development
            </div>
          </div>

          <div className="flex h-10 w-10 items-center justify-center rounded-full border border-white/[0.08] bg-[#151c28] text-sm font-medium text-slate-300">
            K
          </div>
        </div>
      </header>

      {/* Dashboard */}
      <div className="grid min-h-0 flex-1 grid-cols-1 xl:grid-cols-[188px_minmax(0,1fr)_292px]">
        {/* Left sidebar */}
        <aside className="hidden min-h-0 flex-col border-r border-white/[0.06] bg-[#0b111a]/90 p-3 xl:flex">
          <nav className="space-y-1">
            <NavItem active label="Office" icon={<HomeIcon />} />
            <NavItem label="Tasks" icon={<TaskIcon />} />
            <NavItem label="Agents" icon={<AgentIcon />} />
            <NavItem label="Projects" icon={<FolderIcon />} />
            <NavItem label="Reports" icon={<ReportIcon />} />
            <NavItem label="Settings" icon={<SettingsIcon />} />
          </nav>

          <div className="mt-7 border-t border-white/[0.06] pt-4">
            <div className="mb-3 px-2 text-[9px] font-semibold uppercase tracking-[0.18em] text-slate-600">
              System health
            </div>

            <div className="space-y-2">
              {[
                ["API Server", room.connected],
                ["WebSocket", room.connected],
                ["Agent Runtime", room.connected],
              ].map(([label, ok]) => (
                <div
                  key={String(label)}
                  className="flex items-center justify-between rounded-lg border border-white/[0.05] bg-white/[0.025] px-3 py-2"
                >
                  <span className="text-[11px] text-slate-400">
                    {String(label)}
                  </span>
                  <span className="flex items-center gap-1.5 text-[9px] text-slate-500">
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        ok ? "bg-emerald-400" : "bg-amber-400"
                      }`}
                    />
                    {ok ? "Online" : "Waiting"}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-auto rounded-xl border border-white/[0.07] bg-[#101722] p-3">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-500/15 font-mono text-xs font-bold text-blue-300">
                AT
              </div>
              <div className="min-w-0">
                <div className="text-xs font-semibold text-slate-200">
                  ATLAS
                </div>
                <div className="truncate text-[9px] text-slate-600">
                  Engineering Manager
                </div>
              </div>
            </div>

            <div className="mt-3 flex items-center gap-2 text-[10px] text-slate-500">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  atlas?.status && atlas.status !== "IDLE"
                    ? "bg-emerald-400"
                    : "bg-slate-600"
                }`}
              />
              {atlas?.status ?? "IDLE"}
              {atlas?.activity ? ` · ${atlas.activity}` : ""}
            </div>
          </div>
        </aside>

        {/* Center */}
        <main className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-3 overflow-hidden p-3">
          {/* Compact stats */}
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-5">
            <StatBox label="Total tasks" value={room.stats.total} tone="blue" />
            <StatBox label="Running" value={room.stats.running} tone="amber" />
            <StatBox label="Completed" value={room.stats.done} tone="green" />
            <StatBox label="Failed" value={room.stats.failed} tone="red" />
            <StatBox label="Agents" value={activeAgents} tone="purple" />
          </div>

          {/* 3D office + prompt composer */}
          <section className="relative min-h-0 overflow-hidden rounded-2xl border border-white/[0.07] bg-[#070b12] shadow-2xl">
            <ClientOffice
              agents={room.agents}
              activity={room.activity}
            />

            <div className="absolute bottom-4 left-1/2 z-20 flex w-[min(680px,calc(100%-48px))] -translate-x-1/2 flex-col gap-2">
              {/* Structured ATLAS answer (Phase 4.1) above the composer. */}
              <AtlasResponseCard tasks={room.tasks} />

              <form
                onSubmit={handleSubmit}
                className="rounded-2xl border border-white/[0.12] bg-[#0c121c]/95 p-2 shadow-2xl backdrop-blur-xl"
              >
              <div className="rounded-2xl border border-white/[0.12] bg-[#0c121c]/95 p-2 shadow-2xl backdrop-blur-xl">
                <div className="flex items-end gap-2">
                  <textarea
                    value={prompt}
                    onChange={(event) => setPrompt(event.target.value)}
                    onKeyDown={handlePromptKeyDown}
                    rows={1}
                    disabled={!room.connected || submitting}
                    placeholder={
                      room.connected
                        ? "Ask ATLAS to build something..."
                        : "Waiting for AI Dev Office..."
                    }
                    className="max-h-24 min-h-11 flex-1 resize-none bg-transparent px-3 py-3 text-sm text-slate-200 outline-none placeholder:text-slate-600 disabled:cursor-not-allowed"
                  />

                  <button
                    type="submit"
                    disabled={!room.connected || submitting || !prompt.trim()}
                    className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-emerald-400 text-[#06100b] transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-600"
                    aria-label="Send task to ATLAS"
                  >
                    {submitting ? (
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                    ) : (
                      <svg
                        width="17"
                        height="17"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                      >
                        <path d="m5 12 14-7-4 14-3-6Z" />
                      </svg>
                    )}
                  </button>
                </div>

                <div className="px-3 pb-1 text-[9px] text-slate-600">
                  Enter to dispatch · Shift+Enter for new line · ATLAS delegates automatically
                </div>
              </div>
              </form>
            </div>
          </section>
        </main>

        {/* Activity */}
        <aside className="hidden min-h-0 border-l border-white/[0.06] bg-[#0a1019] p-3 xl:block">
          <div className="h-full overflow-hidden rounded-2xl border border-white/[0.07] bg-[#0d131d]">
            <ActivityFeed items={room.activity} />
          </div>
        </aside>
      </div>
    </div>
  );
}
