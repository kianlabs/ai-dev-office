"use client";

import { Suspense, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";

import type { ActivityItem, AgentRecord } from "@/lib/types";

import OfficeEnvironment from "./OfficeEnvironment";
import OfficeScene from "./OfficeScene";
import { useOfficeCamera } from "./useOfficeCamera";

interface OfficeCanvasProps {
  agents: AgentRecord[];
  activity: ActivityItem[];
}

export default function OfficeCanvas({
  agents,
  activity,
}: OfficeCanvasProps) {
  const refs = useOfficeCamera();
  const containerRef = useRef<HTMLDivElement>(null);
  const [fullscreen, setFullscreen] = useState(false);

  async function toggleFullscreen() {
    const container = containerRef.current;
    if (!container) return;

    try {
      if (!document.fullscreenElement) {
        await container.requestFullscreen();
        setFullscreen(true);
      } else {
        await document.exitFullscreen();
        setFullscreen(false);
      }
    } catch {
      // Browser/platform may reject fullscreen without user permission.
    }
  }

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full overflow-hidden bg-[#080b12]"
    >
      <Canvas
        shadows
        flat
        dpr={[1, 1.5]}
        gl={{ antialias: true, alpha: true }}
        camera={{
          position: [15, 18, 20],
          zoom: 42,
          near: 0.1,
          far: 120,
        }}
      >
        <Suspense fallback={null}>
          <OfficeEnvironment />
          <OfficeScene
            agents={agents}
            activity={activity}
            refs={refs}
          />
        </Suspense>
      </Canvas>

      <button
        type="button"
        onClick={() => void toggleFullscreen()}
        className="absolute bottom-4 right-4 z-30 flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-[#0c121c]/80 text-slate-400 shadow-xl backdrop-blur-md transition hover:border-white/20 hover:text-white"
        aria-label={fullscreen ? "Exit fullscreen" : "Fullscreen"}
        title={fullscreen ? "Exit fullscreen" : "Fullscreen"}
      >
        {fullscreen ? (
          <svg
            width="17"
            height="17"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
          >
            <path d="M9 3v6H3M15 3v6h6M9 21v-6H3M15 21v-6h6" />
          </svg>
        ) : (
          <svg
            width="17"
            height="17"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
          >
            <path d="M9 3H3v6M15 3h6v6M9 21H3v-6M15 21h6v-6" />
          </svg>
        )}
      </button>
    </div>
  );
}
