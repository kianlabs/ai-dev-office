"use client";

import { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import type { ActivityItem, AgentRecord } from "@/lib/types";

import OfficeEnvironment from "./OfficeEnvironment";
import OfficeScene from "./OfficeScene";
import { resetOfficeCamera, useOfficeCamera } from "./useOfficeCamera";

interface OfficeCanvasProps {
  agents: AgentRecord[];
  activity: ActivityItem[];
}

// The WebGL canvas that hosts the low-poly office, plus a minimal overlay
// (title + Reset View). Camera refs live here and drive the Reset View button.
export default function OfficeCanvas({
  agents,
  activity,
}: OfficeCanvasProps) {
  const refs = useOfficeCamera();

  return (
    <div className="relative h-full w-full overflow-hidden rounded-xl border border-line bg-[#080b12]">
      {/* header overlay */}
      <div className="pointer-events-none absolute left-3 top-2.5 z-10">
        <div className="font-mono text-[11px] font-semibold uppercase tracking-widest text-slate-400">
          Miniature Office
        </div>
        <div className="text-[10px] text-slate-600">isometric · low-poly</div>
      </div>

      {/* Reset View */}
      <button
        onClick={() => resetOfficeCamera(refs)}
        className="absolute right-3 top-2.5 z-10 flex items-center gap-1.5 rounded-md border border-line bg-black/50 px-2.5 py-1.5 font-mono text-[11px] text-slate-300 transition hover:border-accent hover:text-accent"
      >
        <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 5V2L7 7l5 5V8a5 5 0 1 1-5 5H5a7 7 0 1 0 7-8z" />
        </svg>
        Reset View
      </button>

      <Canvas
        shadows
        flat
        dpr={[1, 1.5]}
        gl={{ antialias: true, alpha: true }}
        camera={{ position: [0, 22, 20], zoom: 26, near: 0.1, far: 120 }}
      >
        <Suspense fallback={null}>
          <OfficeEnvironment />
          <OfficeScene agents={agents} activity={activity} refs={refs} />
        </Suspense>
      </Canvas>
    </div>
  );
}