"use client";

import AgentDummy from "../furniture/AgentDummy";
import OfficeChair from "../furniture/OfficeChair";
import Keyboard from "../furniture/Keyboard";
import Monitor from "../furniture/Monitor";
import type { AgentVisualState } from "../semantic";

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
 * Per-seat configuration.
 *
 * Each seat is a local group rotated about Y so that inside its frame:
 *
 *   local -Z = INTO the table (devices sit here, on the tabletop)
 *   local +Z = OUT of the table (chair + agent stand here, on the floor)
 *
 * The AgentCharacter model faces local -Z by default. The office-chair GLB
 * faces local -X, so OfficeChair props a rotation of -π/2 to turn the chair
 * toward local -Z (the table), matching the agent.
 *
 * Seat origins sit exactly on the table edge, so small outward offsets (+Z)
 * land outside the footprint while small inward offsets (-Z) land on the
 * tabletop. Every offset is in metres within the rotated seat frame; the
 * resulting world position is annotated on each seat below.
 */
interface SeatConfig {
  agentId: SharedDeskAgent["agentId"];
  position: [number, number, number]; // seat origin in desk-local coords
  rotation: number; // 0 / π/2 / -π/2 / π  (about Y)
  variant: "male" | "female";
  agentOffset: [number, number, number]; // local offset from seat origin
  chairOffset: [number, number, number]; // local offset from seat origin
  monitorOffset: [number, number, number]; // local offset from seat origin
  keyboardOffset: [number, number, number]; // local offset from seat origin
}

// Desk geometry (kept in sync with the mesh below):
//   width  = 3.15  (X)
//   depth  = 6.80  (Z)
//   height = 0.78 (tabletop)
//
// Table footprint is X = [-1.575, +1.575], Z = [-3.40, +3.40], so the seat
// origins are placed on the edges: ATLAS on the -Z edge, side seats on the
// ±X edges. The world positions below are the local offset transformed by
// the seat rotation and added to the seat origin:
//   agents/chairs  -> outside the footprint (|X| > 1.575 or |Z| > 3.40)
//   devices        -> on the tabletop (Y = 0.78), inside the footprint
const SEATS: SeatConfig[] = [
  // ATLAS — head of table. Rotation π flips local +Z to world -Z, so
  // outward offsets push past the -Z edge and devices land inside.
  //   chair offset +0.35  -> world (0, 0, -3.75)   outside footprint
  //   agent offset +0.90  -> world (0, 0, -4.30)   outside footprint
  //   keyboard -0.25      -> world (0, 0.78, -3.15) on tabletop
  //   monitor  -0.50      -> world (0, 0.78, -2.90) on tabletop
  {
    agentId: "atlas",
    position: [0, 0, -3.4],
    rotation: Math.PI,
    variant: "male",
    agentOffset: [0, 0, 0.9],
    chairOffset: [0, 0, 0.35],
    monitorOffset: [0, 0.78, -0.5],
    keyboardOffset: [0, 0.78, -0.25],
  },
  // SCOUT — left side (rotation -π/2 maps local +Z to world -X), back row.
  //   chair offset +0.35    -> world (-1.93, 0, -1.4)   outside footprint
  //   agent offset +0.75    -> world (-2.33, 0, -1.4)   outside footprint
  //   keyboard -0.15        -> world (-1.425, 0.78, -1.4) on tabletop
  //   monitor  -0.525       -> world (-1.05, 0.78, -1.4)  on tabletop
  {
    agentId: "scout",
    position: [-1.575, 0, -1.4],
    rotation: -Math.PI / 2,
    variant: "female",
    agentOffset: [0, 0, 0.75],
    chairOffset: [0, 0, 0.35],
    monitorOffset: [0, 0.78, -0.525],
    keyboardOffset: [0, 0.78, -0.15],
  },
  // QA — left side (rotation -π/2 maps local +Z to world -X), front row.
  //   chair offset +0.35    -> world (-1.93, 0, 1.4)    outside footprint
  //   agent offset +0.75    -> world (-2.33, 0, 1.4)    outside footprint
  //   keyboard -0.15        -> world (-1.425, 0.78, 1.4) on tabletop
  //   monitor  -0.525       -> world (-1.05, 0.78, 1.4)  on tabletop
  {
    agentId: "qa",
    position: [-1.575, 0, 1.4],
    rotation: -Math.PI / 2,
    variant: "female",
    agentOffset: [0, 0, 0.75],
    chairOffset: [0, 0, 0.35],
    monitorOffset: [0, 0.78, -0.525],
    keyboardOffset: [0, 0.78, -0.15],
  },
  // FORGE — right side (rotation π/2 maps local +Z to world +X), back row.
  //   chair offset +0.35   -> world (1.93, 0, -1.4)   outside footprint
  //   agent offset +0.75   -> world (2.33, 0, -1.4)   outside footprint
  //   keyboard -0.15       -> world (1.425, 0.78, -1.4) on tabletop
  //   monitor  -0.525      -> world (1.05, 0.78, -1.4)  on tabletop
  {
    agentId: "forge",
    position: [1.575, 0, -1.4],
    rotation: Math.PI / 2,
    variant: "male",
    agentOffset: [0, 0, 0.75],
    chairOffset: [0, 0, 0.35],
    monitorOffset: [0, 0.78, -0.525],
    keyboardOffset: [0, 0.78, -0.15],
  },
  // PULSE — right side (rotation π/2 maps local +Z to world +X), front row.
  //   chair offset +0.35   -> world (1.93, 0, 1.4)    outside footprint
  //   agent offset +0.75   -> world (2.33, 0, 1.4)    outside footprint
  //   keyboard -0.15       -> world (1.425, 0.78, 1.4) on tabletop
  //   monitor  -0.525      -> world (1.05, 0.78, 1.4)  on tabletop
  {
    agentId: "pulse",
    position: [1.575, 0, 1.4],
    rotation: Math.PI / 2,
    variant: "male",
    agentOffset: [0, 0, 0.75],
    chairOffset: [0, 0, 0.35],
    monitorOffset: [0, 0.78, -0.525],
    keyboardOffset: [0, 0.78, -0.15],
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

        // Orient the seat so local -Z points inward (toward the table) and
        // local +Z points outward. All offsets below are in this frame; their
        // resulting world positions are annotated on each seat config above.
        const seatY = seat.rotation;

        return (
          <group
            key={seat.agentId}
            position={seat.position}
            rotation={[0, seatY, 0]}
          >
            {/* Chair — the GLB's front points along local -X; a chair rotation of -π/2
                turns that into local -Z, i.e. the table, matching the agent. */}
            <OfficeChair position={seat.chairOffset} rotation={-Math.PI / 2} />

            {/* Agent standing clearly behind the chair, outside the table. */}
            <AgentDummy
              position={seat.agentOffset}
              color={COLORS[seat.agentId]}
              mode={agent.visualState.mode}
              variant={seat.variant}
            />

            {/* Monitor + keyboard sit on the tabletop (Y ≈ 0.78), facing
                their agent (local +Z). */}
            <Monitor
              position={seat.monitorOffset}
              rotation={0}
              mode={agent.visualState.mode}
              screenColor={COLORS[seat.agentId]}
            />
            <Keyboard position={seat.keyboardOffset} rotation={0} />
          </group>
        );
      })}
    </group>
  );
}