import type { ReactNode } from "react";

interface StatCardProps {
  label: string;
  value: number;
  accent: string;
  icon: ReactNode;
}

export default function StatCard({ label, value, accent, icon }: StatCardProps) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-line bg-panel2 px-4 py-3">
      <div
        className="flex h-9 w-9 items-center justify-center rounded-md"
        style={{ backgroundColor: `${accent}1a`, color: accent }}
      >
        {icon}
      </div>
      <div>
        <div className="font-mono text-2xl font-semibold leading-none text-white">
          {value}
        </div>
        <div className="mt-1 text-xs uppercase tracking-wider text-slate-400">
          {label}
        </div>
      </div>
    </div>
  );
}