"use client";

import type { AgentRecord } from "@/lib/types";

import Plant from "../furniture/Plant";
import { deriveAgentVisualState } from "../semantic";
import AgentStation from "../stations/AgentStation";
import MeetingRoom from "./MeetingRoom";
import ServerRoom from "./ServerRoom";

interface MainOfficeProps {
  agents: AgentRecord[];
}

// Workstation layout across the open plan. Each faces an inner atrium.
const STATION_PLACEMENT: { agentId: string; name: string; pos: [number, number, number]; facing: "north" | "east" | "south" | "west" }[] = [
  { agentId: "atlas", name: "ATLAS", pos: [-7.0, 0, -3.4], facing: "east" },
  { agentId: "scout", name: "SCOUT", pos: [-3.6, 0, -5.6], facing: "north" },
  { agentId: "forge", name: "FORGE", pos: [0, 0, -5.6], facing: "north" },
  { agentId: "qa", name: "QA", pos: [3.6, 0, -5.6], facing: "north" },
  { agentId: "pulse", name: "PULSE", pos: [7.0, 0, -3.4], facing: "west" },
];

export default function MainOffice({ agents }: MainOfficeProps) {
  const byId = new Map(agents.map((a) => [a.agent_id, a]));

  // Open-plan floor: dark wooden tones.
  return (
    <group>
      {/* office floor */}
      <mesh position={[0, 0, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[26, 18]} />
        <meshStandardMaterial color="#3b352e" roughness={0.9} metalness={0.05} />
      </mesh>

      {/* partial walls at the back / sides */}
      <mesh position={[-12.5, 1.5, -8.5]} castShadow>
        <boxGeometry args={[0.3, 3, 17]} />
        <meshStandardMaterial color="#2d363e" roughness={0.65} />
      </mesh>
      <mesh position={[12.5, 1.5, -8.5]} castShadow>
        <boxGeometry args={[0.3, 3, 17]} />
        <meshStandardMaterial color="#2d363e" roughness={0.65} />
      </mesh>
      <mesh position={[0, 1.5, -9.8]} castShadow>
        <boxGeometry args={[25, 3, 0.3]} />
        <meshStandardMaterial color="#2d363e" roughness={0.65} />
      </mesh>

      {/* back wall window strip with soft glass glow */}
      <mesh position={[0, 2.4, -9.55]}>
        <boxGeometry args={[20, 1.1, 0.08]} />
        <meshStandardMaterial
          color="#24407a"
          emissive="#1e3a8a"
          emissiveIntensity={0.7}
          transparent
          opacity={0.9}
        />
      </mesh>

      {/* floor plants */}
      <Plant position={[-10.6, 0, 5.4]} />
      <Plant position={[10.6, 0, 5.4]} />
      <Plant position={[-10.6, 0, -7.4]} />
      <Plant position={[10.6, 0, -7.4]} />

      {/* front facade divider walls (left/right halves) */}
      <mesh position={[-5.8, 1.5, 8.6]} castShadow>
        <boxGeometry args={[0.25, 3, 0.25]} />
        <meshStandardMaterial color="#2d363e" roughness={0.65} />
      </mesh>
      <mesh position={[5.8, 1.5, 8.6]} castShadow>
        <boxGeometry args={[0.25, 3, 0.25]} />
        <meshStandardMaterial color="#2d363e" roughness={0.65} />
      </mesh>

      {/* 5 live agent workstations */}
      {STATION_PLACEMENT.map((s) => {
        const agent = byId.get(s.agentId);

        const visualState = agent
          ? deriveAgentVisualState(agent)
          : {
              mode: "idle" as const,
              label: "Idle",
              active: false,
              attention: false,
            };

        return (
          <AgentStation
            key={s.agentId}
            agentId={s.agentId}
            name={s.name}
            status={agent?.status ?? "IDLE"}
            visualState={visualState}
            position={s.pos}
            facing={s.facing}
          />
        );
      })}

      {/* side rooms */}
      <MeetingRoom position={[-7.4, 0, 5.6]} />
      <ServerRoom position={[7.4, 0, 5.2]} />
    </group>
  );
}