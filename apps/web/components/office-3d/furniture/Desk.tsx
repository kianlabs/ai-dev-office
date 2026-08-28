"use client";

// Low-poly developer desk built from primitives.
export default function Desk({ position, rotation = 0 }: { position: [number, number, number]; rotation?: number }) {
  return (
    <group position={position} rotation={[0, rotation, 0]}>
      {/* top */}
      <mesh castShadow receiveShadow position={[0, 0.72, 0]}>
        <boxGeometry args={[2.2, 0.08, 1.0]} />
        <meshStandardMaterial color="#2b2f3a" roughness={0.6} metalness={0.2} />
      </mesh>
      {/* legs */}
      {[
        [-0.9, -0.34, 0.4],
        [0.9, -0.34, 0.4],
        [-0.9, -0.34, -0.4],
        [0.9, -0.34, -0.4],
      ].map((p, i) => (
        <mesh key={i} position={p as [number, number, number]} castShadow>
          <boxGeometry args={[0.08, 0.68, 0.08]} />
          <meshStandardMaterial color="#1f232c" metalness={0.3} roughness={0.5} />
        </mesh>
      ))}
      {/* back panel */}
      <mesh position={[0, 0.4, 0.48]}>
        <boxGeometry args={[2.0, 0.55, 0.04]} />
        <meshStandardMaterial color="#232733" roughness={0.7} />
      </mesh>
    </group>
  );
}