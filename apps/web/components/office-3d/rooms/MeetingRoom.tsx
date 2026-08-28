"use client";

import OfficeChair from "../furniture/OfficeChair";

// Meeting room: long table, chairs on both sides, and a wall display (screen).
export default function MeetingRoom({ position }: { position: [number, number, number] }) {
  const chairPositions: [number, number][] = [
    // front row (facing north, toward table center -Z)
    [0.0, 1.2],
    [1.35, 1.2],
    [-1.35, 1.2],
    // back row
    [0.0, -1.2],
    [1.35, -1.2],
    [-1.35, -1.2],
  ];

  return (
    <group position={position}>
      {/* meeting table */}
      <mesh position={[0, 0.4, 0]} castShadow receiveShadow>
        <boxGeometry args={[3.4, 0.08, 2.4]} />
        <meshStandardMaterial color="#2c313d" roughness={0.6} metalness={0.15} />
      </mesh>
      {/* table legs */}
      {[[-1.5, -0.36, -1.0], [1.5, -0.36, -1.0], [-1.5, -0.36, 1.0], [1.5, -0.36, 1.0]].map(
        (p, i) => (
          <mesh key={i} position={p as [number, number, number]} castShadow>
            <boxGeometry args={[0.1, 0.72, 0.1]} />
            <meshStandardMaterial color="#1b1f27" metalness={0.3} roughness={0.5} />
          </mesh>
        ),
      )}

      {/* chairs */}
      {chairPositions.map(([x, z], i) => (
        <OfficeChair key={i} position={[x, 0, z]} rotation={z > 0 ? 0 : Math.PI} />
      ))}

      {/* wall display / screen */}
      <group position={[0, 1.5, -1.6]}>
        <mesh>
          <boxGeometry args={[2.6, 1.5, 0.08]} />
          <meshStandardMaterial color="#14161c" metalness={0.3} roughness={0.5} />
        </mesh>
        <mesh position={[0, 0, 0.042]}>
          <boxGeometry args={[2.4, 1.3, 0.02]} />
          <meshStandardMaterial
            color="#0ea5e9"
            emissive="#0ea5e9"
            emissiveIntensity={0.7}
            toneMapped={false}
          />
        </mesh>
      </group>
    </group>
  );
}