"use client";

// Simple flat low-poly keyboard on the desk.
export default function Keyboard({
  position,
  rotation = 0,
}: {
  position: [number, number, number];
  rotation?: number;
}) {
  return (
    <group position={position} rotation={[0, rotation, 0]}>
      <mesh position={[0, 0, 0]} castShadow>
        <boxGeometry args={[0.38, 0.03, 0.9]} />
        <meshStandardMaterial color="#1a1d24" metalness={0.3} roughness={0.6} />
      </mesh>
      {/* key bumps */}
      {Array.from({ length: 4 }).map((_, i) => (
        <mesh key={i} position={[-0.12 + i * 0.08, 0.02, 0.1]}>
          <boxGeometry args={[0.05, 0.015, 0.05]} />
          <meshStandardMaterial color="#2a2f3a" roughness={0.7} />
        </mesh>
      ))}
    </group>
  );
}