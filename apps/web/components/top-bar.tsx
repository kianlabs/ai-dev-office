"use client";

const AGENT_ICON: Record<string, string> = {
  atlas: "#60a5fa",
  scout: "#a78bfa",
  forge: "#f59e0b",
  qa: "#34d399",
  pulse: "#22d3ee",
};

export default function TopBar({
  connected,
  taskCount,
}: {
  connected: boolean;
  taskCount: number;
}) {
  return (
    <header className="flex items-center justify-between border-b border-line bg-panel/60 px-6 py-4 backdrop-blur">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/15 font-mono text-lg font-bold text-accent">
          AO
        </div>
        <div>
          <h1 className="font-mono text-lg font-bold tracking-tight text-white">
            AI Dev Office
          </h1>
          <p className="text-[11px] uppercase tracking-widest text-slate-500">
            Multi-Agent Developer Control Room
          </p>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <div className="hidden items-center gap-2 md:flex">
          {(["atlas", "scout", "forge", "qa", "pulse"] as const).map((a) => (
            <span
              key={a}
              title={a}
              className="flex h-6 w-6 items-center justify-center rounded font-mono text-[10px] font-bold text-black"
              style={{ backgroundColor: AGENT_ICON[a], opacity: 0.9 }}
            >
              {a[0].toUpperCase()}
            </span>
          ))}
        </div>

        <div
          className={`flex items-center gap-2 rounded-full border px-3 py-1.5 font-mono text-xs ${
            connected
              ? "border-mint/40 bg-mint/10 text-mint"
              : "border-amber/40 bg-amber/10 text-amber"
          }`}
        >
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{
              backgroundColor: connected ? "#34d399" : "#fbbf24",
              boxShadow: `0 0 8px ${connected ? "#34d399" : "#fbbf24"}`,
            }}
          />
          {connected ? "SYSTEM ONLINE" : "CONNECTING…"}
        </div>

        <span className="hidden font-mono text-xs text-slate-500 sm:inline">
          {taskCount} tasks tracked
        </span>
      </div>
    </header>
  );
}