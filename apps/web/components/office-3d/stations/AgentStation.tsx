"use client";

import { Html } from "@react-three/drei";
import type { AgentStatus } from "@/lib/types";

import { ACTIVITY_LABEL, AGENT_SIGNAL, STATUS_VISUAL } from "../signal";
import AgentDummy from "../furniture/AgentDummy";
import Desk from "../furniture/Desk";
import DeskTrinket from "../furniture/DeskTrinket";
import Keyboard from "../furniture/Keyboard";
import Monitor from "../furniture/Monitor";
import OfficeChair from "../furniture/OfficeChair";

interface AgentStationProps {
  agentId: string;
  name: string;
  status: AgentStatus;
  activity: string;
  position: [number, number, number];
  // rotate the whole station on the floor (90° steps)
  facing?: Facing;
}

// Direction → rotation about Y. "north" faces +Z (toward the front of the view).
const FACING_Y = {
  north: 0,
  east: Math.PI / 2,
  south: Math.PI, // faces -Z (back wall)
  west: -Math.PI / 2,
} as const;
type Facing = keyof typeof FACING_Y;

export default function AgentStation({
  agentId,
  name,
  status,
  activity,
  position,
  facing = "south",
}: AgentStationProps) {
  const visual = STATUS_VISUAL[status];
  const signal = AGENT_SIGNAL[agentId] ?? "#60a5fa";
  const activityLine = activity && activity !== "Idle" ? activity : "Idle";

  // "Empty" only when no status is wired yet; normal run always has one.
  const hasSignal = status === "WORKING" || status === "WAITING" || status === "ERROR";

  return (
    <group position={position}>
      <group rotation={[0, FACING_Y[facing], 0]}>
        {/* workstation furniture */}
        <Desk position={[0, 0, 0]} />
        {/* chair on the outer side of the desk (toward +Z of the facing) */}
        <OfficeChair position={[0, 0, 1.15]} rotation={Math.PI} />
        <Monitor
          position={[0.18, 0.74, -0.28]}
          screenGlow={visual.screen}
          screenColor={signal}
        />
        <Keyboard position={[0.05, 0.8, 0.05]} />
        <DeskTrinket position={[-0.72, 0.8, 0.05]} />

        {/* agent placeholder sits in the chair area */}
        <AgentDummy position={[0, 0, 1.15]} color={signal} />

        {/* status indicator: a floating low-poly beacon above the monitor */}
        <group position={[0, 1.55, -0.28]}>
          <mesh>
            <octahedronGeometry args={[0.09, 0]} />
            <meshStandardMaterial
              color={visual.color}
              emissive={visual.color}
              emissiveIntensity={hasSignal ? 1.4 : 0.3}
              toneMapped={false}
            />
          </mesh>
        </group>

        {/* activity + status label */}
        <Html
          position={[0, 1.95, 0]}
          center
          distanceFactor={9}
          style={{
            pointerEvents: "none",
            userSelect: "none",
            whiteSpace: "nowrap",
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            transform: "translateX(-50%)",
          }}
        >
          <div className="flex flex-col items-center gap-0.5 rounded-md border border-white/10 bg-black/55 px-2 py-1 backdrop-blur-sm">
            <div className="flex items-center gap-1.5">
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{
                  backgroundColor: hasSignal ? visual.system : "#475569",
                  boxShadow: hasSignal ? `0 0 6px ${visual.system}` : undefined,
                }}
              />
              <span className="text-[10px] font-semibold text-white">{name}</span>
            </div>
            <span
              className="text-[9px] font-medium tracking-wide"
              style={{ color: visual.system }}
            >
              {ACTIVITY_LABEL[agentId] ?? "Agent"} · {activityLine}
            </span>
          </div>
        </Html>
      </group>
    </group>
  );
}