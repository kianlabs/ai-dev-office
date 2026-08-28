"use client";

import { useEffect, useState } from "react";
import type { ActivityItem, AgentRecord } from "@/lib/types";

import OfficeCanvas from "./OfficeCanvas";

// Mounts the WebGL office only in the browser. SSR renders a clean placeholder
// so there is no `window is not defined` / hydration mismatch from three.js.
interface ClientOfficeProps {
  agents: AgentRecord[];
  activity: ActivityItem[];
}

export default function ClientOffice({
  agents,
  activity,
}: ClientOfficeProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <div className="flex h-full w-full items-center justify-center rounded-xl border border-line bg-[#080b12]">
        <span className="font-mono text-xs text-slate-600">Loading 3D office…</span>
      </div>
    );
  }

  return <OfficeCanvas agents={agents} activity={activity} />;
}