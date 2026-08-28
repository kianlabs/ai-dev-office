"use client";

import ServerRack from "../furniture/ServerRack";

// Server room: a row of racks with soft glowing indicators, darker finish.
export default function ServerRoom({ position }: { position: [number, number, number] }) {
  const racks: { pos: [number, number, number]; glow: number }[] = [
    { pos: [-1.8, 0, 0.35], glow: 0.7 },
    { pos: [-0.6, 0, 0.35], glow: 0.5 },
    { pos: [0.6, 0, 0.35], glow: 0.8 },
    { pos: [1.8, 0, 0.35], glow: 0.6 },
  ];

  return (
    <group position={position}>
      {/* darker floor plate for the room */}
      <mesh position={[0, 0.005, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[5.6, 4.6]} />
        <meshStandardMaterial color="#0c0f16" roughness={0.9} />
      </mesh>

      {racks.map((r, i) => (
        <ServerRack key={i} position={r.pos} glow={r.glow} />
      ))}

      {/* small access door / panel */}
      <mesh position={[0, 1.1, -2.1]}>
        <boxGeometry args={[1.4, 2.2, 0.06]} />
        <meshStandardMaterial color="#11141b" metalness={0.4} roughness={0.4} />
      </mesh>
    </group>
  );
}