"use client";

import AgentDummy from "../furniture/AgentDummy";
import OfficeChair from "../furniture/OfficeChair";
import Keyboard from "../furniture/Keyboard";
import Monitor from "../furniture/Monitor";
import type { AgentVisualState } from "../semantic";
import {
  AGENT_HOME,
  type AgentId,
} from "../navigation/waypoints";
import { demoRouteFor } from "../navigation/routes";

interface SharedDeskAgent {
  agentId: string;
  name: string;
  status: string;
  visualState: AgentVisualState;
}

interface SharedDeskProps {
  agents: SharedDeskAgent[];
}

/**
 * Per-seat configuration using direct world-space positions.
 *
 * All positions are in SharedDesk local space (SharedDesk group sits at
 * MainOffice world offset [0, 0, 0.2], so world = local + [0, 0, 0.2]).
 *
 * Table footprint (local/world X same, local Z = world Z - 0.2):
 *   width  X = 3.15  →  X ∈ [-1.575, +1.575]
 *   depth  Z = 6.80  →  local Z ∈ [-3.40, +3.40]  (world Z ∈ [-3.20, +3.60])
 *   tabletop top Y ≈ 0.78
 *
 * Agents and chairs MUST be outside the footprint (|X| > 1.575 or |local Z| > 3.40).
 * Devices MUST be on the tabletop (Y = 0.78) inside the footprint.
 *
 * Device placement/orientation restores the accepted seat-local layout from
 * the b3ee78f baseline (seat origin + R_y(seatRotation) · deviceOffset),
 * flattened to world space. Devices face their agent in world space:
 *   ATLAS  — seat yaw π → both device yaw π (front −Z toward agent z ≈ −4.1)
 *   SCOUT/QA (left, −X) — device yaw −π/2 (front −X toward agent)
 *   FORGE/PULSE (right, +X) — device yaw π/2 (front +X toward agent)
 * Chair yaw faces the chair GLB front toward the table.
 *
 * AgentDummy is always positioned at AGENT_HOME (world space) and does not
 * live inside the seat group — it navigates the whole office.
 */
interface SeatConfig {
  agentId: SharedDeskAgent["agentId"];
  modelPath: string;
  /** World yaw of the seat/agent. Also the monitor & keyboard yaw so each
   *  device faces its agent (matches the accepted seat-local frame). */
  rotation: number;
  /** Chair world-space position (local to SharedDesk group) */
  chairPosition: [number, number, number];
  /** Chair Y-rotation so GLB front faces toward the table */
  chairRotation: number;
  /** Monitor world-space position (local to SharedDesk group) */
  monitorPosition: [number, number, number];
  /** Keyboard world-space position (local to SharedDesk group) */
  keyboardPosition: [number, number, number];
}

// Desk geometry (kept in sync with the mesh below):
//   width  = 3.15  (X)
//   depth  = 6.80  (Z)
//   height = 0.78 (tabletop top)
//
// SharedDesk group is at MainOffice [0, 0, 0.2], so:
//   world X = local X   (no X offset)
//   world Z = local Z + 0.2
//
// ATLAS  — south end:  agent world z ≈ -4.1, chair world z ≈ -3.8
//           local chair z = -3.8 - 0.2 = -4.0  (outside footprint edge -3.40) ✓
//           devices local z ≈ -3.15 .. -2.9      (inside footprint) ✓
//
// SCOUT  — left side:  agent world x ≈ -2.325, chair world x ≈ -1.9
//           local chair x = -1.9                (outside footprint edge -1.575) ✓
//           devices local x ≈ -1.425 .. -1.05     (inside footprint) ✓
//
// QA     — left side:  same x targets as SCOUT, different z row
//
// FORGE  — right side: agent world x ≈ +2.325, chair world x ≈ +1.9
//           local chair x = +1.9                (outside footprint edge +1.575) ✓
//           devices local x ≈ +1.05 .. +1.425     (inside footprint) ✓
//
// PULSE  — right side: same x targets as FORGE, different z row
const SEATS: SeatConfig[] = [
  // ── ATLAS ─────────────────────────────────────────────────────────────────
  // Agent world: (0, 0, -4.1) → AGENT_HOME.atlas = [0, 0, -4.1] ✓
  // Chair world: (0, 0, -3.8) → local (0, 0, -4.0)  outside footprint (-3.40) ✓
  // Devices local (b3ee78f: seat (0,0,-3.4), seat yaw π, offsets −0.5 / −0.25):
  //   monitor (0, 0.78, -2.9)  keyboard (0, 0.78, -3.15)  inside footprint ✓
  //   keyboard (−3.15) sits between the agent (−4.1) and monitor (−2.9) ✓
  // Chair faces +Z (toward table interior), rotation = π/2
  // Devices yaw = π → front −Z toward the agent at −Z
  {
    agentId: "atlas",
    modelPath: "/models/agents/characters/men_suit.gltf",
    rotation: Math.PI,
    chairPosition: [0, 0, -4.0],
    chairRotation: Math.PI / 2,
    monitorPosition: [0, 0.78, -2.9],
    keyboardPosition: [0, 0.78, -3.15],
  },

  // ── SCOUT ─────────────────────────────────────────────────────────────────
  // Agent world: (-2.325, 0, -1.2) → AGENT_HOME.scout ✓
  // Chair world: (-1.9, 0, -1.2) → local (-1.9, 0, -1.4)  outside footprint (-1.575) ✓
  // Devices local (b3ee78f: seat (-1.575,0,-1.4), seat yaw −π/2, offsets −0.525/−0.15):
  //   monitor (-1.05, 0.78, -1.4)  keyboard (-1.425, 0.78, -1.4)  inside footprint ✓
  //   keyboard (−1.425) between the agent (−2.325) and monitor (−1.05) ✓
  // Chair faces +X (toward table interior), rotation = π
  // Devices yaw = −π/2 → front −X toward the agent at −X
  {
    agentId: "scout",
    modelPath: "/models/agents/characters/women_casual.gltf",
    rotation: -Math.PI / 2,
    chairPosition: [-1.9, 0, -1.4],
    chairRotation: Math.PI,
    monitorPosition: [-1.05, 0.78, -1.4],
    keyboardPosition: [-1.425, 0.78, -1.4],
  },

  // ── QA ────────────────────────────────────────────────────────────────────
  // Agent world: (-2.325, 0, 1.6) → AGENT_HOME.qa ✓
  // Chair world: (-1.9, 0, 1.6) → local (-1.9, 0, 1.4)  outside footprint (-1.575) ✓
  // Devices local (b3ee78f: seat (-1.575,0,1.4), seat yaw −π/2, offsets −0.525/−0.15):
  //   monitor (-1.05, 0.78, 1.4)  keyboard (-1.425, 0.78, 1.4)  inside footprint ✓
  //   keyboard (−1.425) between the agent (−2.325) and monitor (−1.05) ✓
  // Chair faces +X (toward table interior), rotation = π
  // Devices yaw = −π/2 → front −X toward the agent at −X
  {
    agentId: "qa",
    modelPath: "/models/agents/characters/women_formal.gltf",
    rotation: -Math.PI / 2,
    chairPosition: [-1.9, 0, 1.4],
    chairRotation: Math.PI,
    monitorPosition: [-1.05, 0.78, 1.4],
    keyboardPosition: [-1.425, 0.78, 1.4],
  },

  // ── FORGE ─────────────────────────────────────────────────────────────────
  // Agent world: (2.325, 0, -1.2) → AGENT_HOME.forge ✓
  // Chair world: (1.9, 0, -1.2) → local (1.9, 0, -1.4)  outside footprint (+1.575) ✓
  // Devices local (b3ee78f: seat (1.575,0,-1.4), seat yaw π/2, offsets −0.525/−0.15):
  //   monitor (1.05, 0.78, -1.4)  keyboard (1.425, 0.78, -1.4)  inside footprint ✓
  //   keyboard (1.425) between the agent (2.325) and monitor (1.05) ✓
  // Chair faces -X (toward table interior), rotation = 0
  // Devices yaw = π/2 → front +X toward the agent at +X
  {
    agentId: "forge",
    modelPath: "/models/agents/characters/men_casual_hoodie.gltf",
    rotation: Math.PI / 2,
    chairPosition: [1.9, 0, -1.4],
    chairRotation: 0,
    monitorPosition: [1.05, 0.78, -1.4],
    keyboardPosition: [1.425, 0.78, -1.4],
  },

  // ── PULSE ─────────────────────────────────────────────────────────────────
  // Agent world: (2.325, 0, 1.6) → AGENT_HOME.pulse ✓
  // Chair world: (1.9, 0, 1.6) → local (1.9, 0, 1.4)  outside footprint (+1.575) ✓
  // Devices local (b3ee78f: seat (1.575,0,1.4), seat yaw π/2, offsets −0.525/−0.15):
  //   monitor (1.05, 0.78, 1.4)  keyboard (1.425, 0.78, 1.4)  inside footprint ✓
  //   keyboard (1.425) between the agent (2.325) and monitor (1.05) ✓
  // Chair faces -X (toward table interior), rotation = 0
  // Devices yaw = π/2 → front +X toward the agent at +X
  {
    agentId: "pulse",
    modelPath: "/models/agents/characters/men_casual_2.gltf",
    rotation: Math.PI / 2,
    chairPosition: [1.9, 0, 1.4],
    chairRotation: 0,
    monitorPosition: [1.05, 0.78, 1.4],
    keyboardPosition: [1.425, 0.78, 1.4],
  },
];

const COLORS: Record<string, string> = {
  atlas: "#60a5fa",
  scout: "#a78bfa",
  forge: "#f59e0b",
  qa: "#34d399",
  pulse: "#22d3ee",
};

export default function SharedDesk({ agents }: SharedDeskProps) {
  return (
    <group>
      {/* ====================== DESK BODY ====================== */}

      {/* tabletop */}
      <mesh position={[0, 0.72, 0]} castShadow receiveShadow>
        <boxGeometry args={[3.15, 0.12, 6.8]} />
        <meshStandardMaterial color="#8a6545" roughness={0.7} />
      </mesh>

      {/* legs */}
      {[
        [-1.35, 0.35, -3.2],
        [1.35, 0.35, -3.2],
        [-1.35, 0.35, 3.2],
        [1.35, 0.35, 3.2],
      ].map(([x, y, z], i) => (
        <mesh key={i} position={[x, y, z]}>
          <boxGeometry args={[0.12, 0.7, 0.12]} />
          <meshStandardMaterial color="#24272b" />
        </mesh>
      ))}

      {/* center cable channel — narrow ridge running along the length */}
      <mesh position={[0, 0.84, 0]}>
        <boxGeometry args={[0.16, 0.1, 5.7]} />
        <meshStandardMaterial color="#30343a" />
      </mesh>

      {/* ====================== SEATS ====================== */}

      {SEATS.map((seat) => {
        const agent = agents.find((a) => a.agentId === seat.agentId);
        if (!agent) return null;

        const agentId = seat.agentId as AgentId;

        return (
          <group key={seat.agentId}>
            {/* Chair — direct world-space position, no intermediate rotation group */}
            <OfficeChair
              position={seat.chairPosition}
              rotation={seat.chairRotation}
            />

            {/* Monitor + keyboard on tabletop — placed and oriented exactly as
                the accepted seat-local layout (b3ee78f), flattened to world
                space. Yaw = seat rotation so each device faces its agent. */}
            <Monitor
              position={seat.monitorPosition}
              rotation={seat.rotation}
              mode={agent.visualState.mode}
              screenColor={COLORS[seat.agentId]}
            />

            <Keyboard position={seat.keyboardPosition} rotation={seat.rotation} />

            {/* Agent at its world-space home (navigation/waypoints).
                baseYaw reproduces the seat orientation for the rest pose. */}
            <AgentDummy
              position={AGENT_HOME[agentId]}
              baseYaw={seat.rotation}
              mode={agent.visualState.mode}
              modelPath={seat.modelPath}
              route={demoRouteFor(agentId)}
            />
          </group>
        );
      })}
    </group>
  );
}
