import type { AgentRecord, AgentStatus } from "@/lib/types";

const STATUS_STYLE: Record<AgentStatus, { dot: string; label: string }> = {
  IDLE: { dot: "#64748b", label: "Idle" },
  WORKING: { dot: "#34d399", label: "Working" },
  WAITING: { dot: "#fbbf24", label: "Waiting" },
  ERROR: { dot: "#f87171", label: "Error" },
};

const ACTIVITY_LABEL: Record<string, string> = {
  atlas: "Planning",
  scout: "Researching",
  forge: "Coding",
  qa: "Testing",
  pulse: "Monitoring",
};

const ACTIVITY_COLOR: Record<string, string> = {
  atlas: "#60a5fa",
  scout: "#a78bfa",
  forge: "#f59e0b",
  qa: "#34d399",
  pulse: "#22d3ee",
};

interface AgentCardProps {
  agent: AgentRecord;
  isOrchestrator: boolean;
}

function InitialBadge({ name, color }: { name: string; color: string }) {
  return (
    <div
      className="flex h-10 w-10 items-center justify-center rounded-lg font-mono text-sm font-bold text-black"
      style={{ backgroundColor: color }}
    >
      {name.slice(0, 2)}
    </div>
  );
}

export default function AgentCard({ agent, isOrchestrator }: AgentCardProps) {
  const st = STATUS_STYLE[agent.status];
  const live = agent.status !== "IDLE";

  return (
    <div
      className="relative rounded-xl border border-line bg-panel p-4 transition-colors"
      style={{
        boxShadow: live
          ? `0 0 0 1px ${agent.color}22, 0 0 24px -8px ${agent.color}55`
          : undefined,
      }}
    >
      {live && (
        <span
          className="absolute left-0 top-0 h-full w-1 rounded-l-xl"
          style={{ backgroundColor: agent.color, boxShadow: `0 0 12px ${agent.color}` }}
        />
      )}

      <div className="flex items-start gap-3">
        <InitialBadge name={agent.name} color={agent.color} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-base font-semibold text-white">
              {agent.name}
            </span>
            {isOrchestrator && (
              <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold text-accent">
                ORCH
              </span>
            )}
          </div>
          <div className="text-xs text-slate-400">{agent.role}</div>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <span
          className="inline-block h-2.5 w-2.5 rounded-full"
          style={{
            backgroundColor: st.dot,
            boxShadow: `0 0 8px ${st.dot}`,
            animation: live ? "pulse 1.2s ease-in-out infinite" : undefined,
          }}
        />
        <span className="text-sm font-medium text-slate-200">{st.label}</span>
      </div>

      <div className="mt-2 h-9">
        <div className="flex items-center gap-2 text-sm" style={{ color: ACTIVITY_COLOR[agent.agent_id] }}>
          <span className="font-medium uppercase tracking-wider text-xs">
            {ACTIVITY_LABEL[agent.agent_id]}
          </span>
          <span className="truncate text-slate-300">· {agent.activity}</span>
        </div>
      </div>

      <style jsx>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.35; }
        }
      `}</style>
    </div>
  );
}