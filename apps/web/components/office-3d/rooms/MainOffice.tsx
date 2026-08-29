"use client";

import type { ActivityItem, AgentRecord } from "@/lib/types";

import Plant from "../furniture/Plant";
import {
  applyTransientVisualState,
  deriveAgentVisualState,
  useTransientAgentVisuals,
} from "../semantic";
import SharedDesk from "../stations/SharedDesk";

import Lounge from "./Lounge";
import MeetingRoom from "./MeetingRoom";
import Pantry from "./Pantry";
import ServerRoom from "./ServerRoom";

interface MainOfficeProps {
  agents: AgentRecord[];
  activity: ActivityItem[];
}

function FoosballTable({
  position,
}: {
  position: [number, number, number];
}) {
  return (
    <group position={position}>
      <mesh
        position={[0, 0.45, 0]}
        castShadow
        receiveShadow
      >
        <boxGeometry args={[1.75, 0.13, 0.95]} />
        <meshStandardMaterial
          color="#704b2f"
          roughness={0.72}
        />
      </mesh>

      <mesh position={[0, 0.52, 0]}>
        <boxGeometry args={[1.5, 0.03, 0.72]} />
        <meshStandardMaterial
          color="#315d39"
          roughness={0.8}
        />
      </mesh>

      {[
        [-0.7, 0.08, -0.36],
        [0.7, 0.08, -0.36],
        [-0.7, 0.08, 0.36],
        [0.7, 0.08, 0.36],
      ].map((p, index) => (
        <mesh
          key={index}
          position={p as [number, number, number]}
          castShadow
        >
          <boxGeometry args={[0.09, 0.75, 0.09]} />
          <meshStandardMaterial
            color="#20242b"
            roughness={0.6}
          />
        </mesh>
      ))}
    </group>
  );
}

function BackShelf() {
  return (
    <group position={[-2.8, 0, -6.7]}>
      <mesh position={[0, 0.55, 0]}>
        <boxGeometry args={[3.3, 1.1, 0.45]} />
        <meshStandardMaterial
          color="#594332"
          roughness={0.82}
        />
      </mesh>

      <mesh position={[0, 1.12, 0]}>
        <boxGeometry args={[3.35, 0.08, 0.5]} />
        <meshStandardMaterial
          color="#7b5a3e"
          roughness={0.75}
        />
      </mesh>

      {[-1.2, -0.6, 0, 0.6, 1.2].map((x) => (
        <group key={x} position={[x, 1.28, 0]}>
          <mesh>
            <cylinderGeometry args={[0.1, 0.12, 0.16, 8]} />
            <meshStandardMaterial color="#ddd2bf" />
          </mesh>

          <mesh position={[0, 0.18, 0]}>
            <sphereGeometry args={[0.13, 8, 6]} />
            <meshStandardMaterial color="#4d7442" />
          </mesh>
        </group>
      ))}
    </group>
  );
}

export default function MainOffice({
  agents,
  activity,
}: MainOfficeProps) {
  const transientVisuals =
    useTransientAgentVisuals(activity);

  const team = [
    { agentId: "atlas", name: "ATLAS" },
    { agentId: "scout", name: "SCOUT" },
    { agentId: "forge", name: "FORGE" },
    { agentId: "qa", name: "QA" },
    { agentId: "pulse", name: "PULSE" },
  ] as const;

  const sharedAgents = team.map(({ agentId, name }) => {
    const agent = agents.find((item) => item.agent_id === agentId);

    if (!agent) {
      return {
        agentId,
        name,
        status: "IDLE" as const,
        visualState: {
          mode: "idle" as const,
          label: "Idle",
          active: false,
          attention: false,
        },
      };
    }

    const base = deriveAgentVisualState(agent);

    return {
      agentId,
      name,
      status: agent.status,
      visualState: applyTransientVisualState(
        base,
        transientVisuals[agentId],
      ),
    };
  });

  return (
    <group>
      {/* =====================================================
          FLOOR
      ===================================================== */}

      <mesh
        position={[0, 0, 0]}
        rotation={[-Math.PI / 2, 0, 0]}
        receiveShadow
      >
        <planeGeometry args={[22, 15]} />
        <meshStandardMaterial
          color="#806044"
          roughness={0.92}
          metalness={0.02}
        />
      </mesh>

      {/* =====================================================
          CUTAWAY WALLS
      ===================================================== */}

      {/* back */}
      <mesh position={[0, 1.35, -7.35]}>
        <boxGeometry args={[22, 2.7, 0.25]} />
        <meshStandardMaterial
          color="#dfd6c9"
          roughness={0.75}
        />
      </mesh>

      {/* left */}
      <mesh position={[-10.9, 1.05, -0.4]}>
        <boxGeometry args={[0.25, 2.1, 13.9]} />
        <meshStandardMaterial
          color="#ddd5c9"
          roughness={0.75}
        />
      </mesh>

      {/* right */}
      <mesh position={[10.9, 1.05, -0.4]}>
        <boxGeometry args={[0.25, 2.1, 13.9]} />
        <meshStandardMaterial
          color="#ddd5c9"
          roughness={0.75}
        />
      </mesh>

      {/* low front walls */}
      <mesh position={[-7.6, 0.65, 7.35]}>
        <boxGeometry args={[6.6, 1.3, 0.25]} />
        <meshStandardMaterial
          color="#ddd5c9"
          roughness={0.75}
        />
      </mesh>

      <mesh position={[7.6, 0.65, 7.35]}>
        <boxGeometry args={[6.6, 1.3, 0.25]} />
        <meshStandardMaterial
          color="#ddd5c9"
          roughness={0.75}
        />
      </mesh>

      {/* =====================================================
          BACK WINDOWS
      ===================================================== */}

      <mesh position={[3.5, 1.85, -7.2]}>
        <boxGeometry args={[7.8, 1.25, 0.06]} />
        <meshStandardMaterial
          color="#9fc2dd"
          emissive="#5685a8"
          emissiveIntensity={0.18}
          transparent
          opacity={0.75}
        />
      </mesh>

      {/* BUILD SHIP REPEAT visual block */}
      <mesh position={[-4.7, 1.9, -7.18]}>
        <boxGeometry args={[2.1, 1.1, 0.04]} />
        <meshStandardMaterial
          color="#476dff"
          emissive="#476dff"
          emissiveIntensity={0.7}
          toneMapped={false}
        />
      </mesh>

      <BackShelf />

      {/* standalone whiteboard */}
      <group position={[2.8, 0, -6.45]}>
        <mesh position={[0, 1.15, 0]}>
          <boxGeometry args={[2.1, 1.25, 0.08]} />
          <meshStandardMaterial color="#f1eee6" />
        </mesh>

        <mesh position={[-0.92, 0.72, 0]}>
          <boxGeometry args={[0.07, 1.45, 0.07]} />
          <meshStandardMaterial color="#444a52" />
        </mesh>
        <mesh position={[0.92, 0.72, 0]}>
          <boxGeometry args={[0.07, 1.45, 0.07]} />
          <meshStandardMaterial color="#444a52" />
        </mesh>
      </group>

      {/* =====================================================
          CENTRAL TEAM
      ===================================================== */}

      <group position={[0, 0, 0.2]}>
        <SharedDesk agents={sharedAgents} />
      </group>

      <FoosballTable position={[4.4, 0, -0.7]} />

      {/* =====================================================
          ROOMS
      ===================================================== */}

      <MeetingRoom position={[-7.55, 0, -3.55]} />

      <ServerRoom position={[7.65, 0, -3.6]} />

      <Pantry position={[-7.4, 0, 4.7]} />

      <Lounge position={[7.2, 0, 4.65]} />

      {/* =====================================================
          DECOR
      ===================================================== */}

      <Plant position={[-10.0, 0, -6.4]} />
      <Plant position={[10.0, 0, -6.4]} />

      <Plant position={[-10.0, 0, 5.6]} />
      <Plant position={[10.0, 0, 5.6]} />

      <Plant position={[5.1, 0, 2.8]} />
    </group>
  );
}
