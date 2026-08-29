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
 * Devices MUST be on the tabletop (Y ≈ 0.79–0.82) inside the footprint.
 *
 * Rotations (world Y-rotation for chairs and monitor facing):
 *   ATLAS  (south end): chair faces +Z  → Math.PI / 2 for chair, 0 for monitor
 *   SCOUT/QA (left):   chair faces +X  → Math.PI for chair, -Math.PI/2 for monitor
 *   FORGE/PULSE (right): chair faces -X → 0 for chair, Math.PI/2 for monitor
 *
 * AgentDummy is always positioned at AGENT_HOME (world space) and does not
 * live inside the seat group — it navigates the whole office.
 */
interface SeatConfig {
  agentId: SharedDeskAgent["agentId"];
  modelPath: string;
  /** Y-rotation of the agent (world) — used for baseYaw and chair/monitor */
  rotation: number;
  /** Chair world-space position (local to SharedDesk group) */
  chairPosition: [number, number, number];
  /** Chair Y-rotation so GLB front faces toward the table */
  chairRotation: number;
  /** Monitor world-space position (local to SharedDesk group) */
  monitorPosition: [number, number, number];
  /** Monitor Y-rotation so screen faces toward the agent */
  monitorRotation: number;
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
//           devices local z ≈ -2.9 .. -2.6      (inside footprint) ✓
//
// SCOUT  — left side:  agent world x ≈ -2.15, chair world x ≈ -1.9
//           local chair x = -1.9                (outside footprint edge -1.575) ✓
//           devices local x ≈ -1.0 .. -0.5      (inside footprint) ✓
//
// QA     — left side:  same x targets as SCOUT, different z row
//
// FORGE  — right side: agent world x ≈ +2.15, chair world x ≈ +1.9
//           local chair x = +1.9                (outside footprint edge +1.575) ✓
//           devices local x ≈ +1.0 .. +0.5      (inside footprint) ✓
//
// PULSE  — right side: same x targets as FORGE, different z row
const SEATS: SeatConfig[] = [
  // ── ATLAS ─────────────────────────────────────────────────────────────────
  // Agent world: (0, 0, -4.1) → AGENT_HOME.atlas = [0, 0, -4.1] ✓
  // Chair world: (0, 0, -3.8) → local (0, 0, -4.0)  outside footprint (-3.40) ✓
  // Monitor local: (0, 0.80, -2.9)  inside footprint ✓
  // Keyboard local: (0, 0.80, -2.6) inside footprint ✓
  // Chair faces +Z (toward table interior), rotation = π/2
  // Monitor screen faces +Z (toward agent at -Z), monitorRotation = 0
  {
    agentId: "atlas",
    modelPath: "/models/agents/characters/men_suit.gltf",
    rotation: Math.PI,
    chairPosition: [0, 0, -4.0],
    chairRotation: Math.PI / 2,
    monitorPosition: [0, 0.80, -2.9],
    monitorRotation: 0,
    keyboardPosition: [0, 0.80, -2.6],
  },

  // ── SCOUT ─────────────────────────────────────────────────────────────────
  // Agent world: (-2.15, 0, -1.2) → AGENT_HOME.scout = [-2.325, 0, -1.2]
  // Chair world: (-1.9, 0, -1.2) → local (-1.9, 0, -1.4)  outside footprint (-1.575) ✓
  // Monitor local: (-1.0, 0.80, -1.4)  inside footprint ✓
  // Keyboard local: (-0.6, 0.80, -1.4) inside footprint ✓
  // Chair faces +X (toward table interior), rotation = π
  // Monitor screen faces -X (toward agent at -X), monitorRotation = -π/2
  {
    agentId: "scout",
    modelPath: "/models/agents/characters/women_casual.gltf",
    rotation: -Math.PI / 2,
    chairPosition: [-1.9, 0, -1.4],
    chairRotation: Math.PI,
    monitorPosition: [-1.0, 0.80, -1.4],
    monitorRotation: -Math.PI / 2,
    keyboardPosition: [-0.6, 0.80, -1.4],
  },

  // ── QA ────────────────────────────────────────────────────────────────────
  // Agent world: (-2.15, 0, 1.6) → AGENT_HOME.qa = [-2.325, 0, 1.6]
  // Chair world: (-1.9, 0, 1.6) → local (-1.9, 0, 1.4)  outside footprint (-1.575) ✓
  // Monitor local: (-1.0, 0.80, 1.4)  inside footprint ✓
  // Keyboard local: (-0.6, 0.80, 1.4) inside footprint ✓
  // Chair faces +X (toward table interior), rotation = π
  // Monitor screen faces -X (toward agent at -X), monitorRotation = -π/2
  {
    agentId: "qa",
    modelPath: "/models/agents/characters/women_formal.gltf",
    rotation: -Math.PI / 2,
    chairPosition: [-1.9, 0, 1.4],
    chairRotation: Math.PI,
    monitorPosition: [-1.0, 0.80, 1.4],
    monitorRotation: -Math.PI / 2,
    keyboardPosition: [-0.6, 0.80, 1.4],
  },

  // ── FORGE ─────────────────────────────────────────────────────────────────
  // Agent world: (2.15, 0, -1.2) → AGENT_HOME.forge = [2.325, 0, -1.2]
  // Chair world: (1.9, 0, -1.2) → local (1.9, 0, -1.4)  outside footprint (+1.575) ✓
  // Monitor local: (1.0, 0.80, -1.4)  inside footprint ✓
  // Keyboard local: (0.6, 0.80, -1.4) inside footprint ✓
  // Chair faces -X (toward table interior), rotation = 0
  // Monitor screen faces +X (toward agent at +X), monitorRotation = π/2
  {
    agentId: "forge",
    modelPath: "/models/agents/characters/men_casual_hoodie.gltf",
    rotation: Math.PI / 2,
    chairPosition: [1.9, 0, -1.4],
    chairRotation: 0,
    monitorPosition: [1.0, 0.80, -1.4],
    monitorRotation: Math.PI / 2,
    keyboardPosition: [0.6, 0.80, -1.4],
  },

  // ── PULSE ─────────────────────────────────────────────────────────────────
  // Agent world: (2.15, 0, 1.6) → AGENT_HOME.pulse = [2.325, 0, 1.6]
  // Chair world: (1.9, 0, 1.6) → local (1.9, 0, 1.4)  outside footprint (+1.575) ✓
  // Monitor local: (1.0, 0.80, 1.4)  inside footprint ✓
  // Keyboard local: (0.6, 0.80, 1.4) inside footprint ✓
  // Chair faces -X (toward table interior), rotation = 0
  // Monitor screen faces +X (toward agent at +X), monitorRotation = π/2
  {
    agentId: "pulse",
    modelPath: "/models/agents/characters/men_casual_2.gltf",
    rotation: Math.PI / 2,
    chairPosition: [1.9, 0, 1.4],
    chairRotation: 0,
    monitorPosition: [1.0, 0.80, 1.4],
    monitorRotation: Math.PI / 2,
    keyboardPosition: [0.6, 0.80, 1.4],
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

            {/* Monitor on tabletop — direct world-space position */}
            <Monitor
              position={seat.monitorPosition}
              rotation={seat.monitorRotation}
              mode={agent.visualState.mode}
              screenColor={COLORS[seat.agentId]}
            />

            {/* Keyboard on tabletop — direct world-space position */}
            <Keyboard position={seat.keyboardPosition} rotation={0} />

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
