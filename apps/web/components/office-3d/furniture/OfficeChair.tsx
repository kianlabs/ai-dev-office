"use client";

// Simple low-poly office chair (seat + backrest + base + stem).
export default function OfficeChair({
  position,
  rotation = 0,
}: {
  position: [number, number, number];
  rotation?: number;
}) {
  return (
    <group position={position} rotation={[0, rotation, 0]}>
      {/* stem */}
      <mesh position={[0, 0.25, 0]} castShadow>
        <cylinderGeometry args={[0.03, 0.03, 0.5, 8]} />
        <meshStandardMaterial color="#1a1d24" metalness={0.4} roughness={0.4} />
      </mesh>
      {/* base */}
      <mesh position={[0, 0.02, 0]}>
        <cylinderGeometry args={[0.32, 0.36, 0.05, 6]} />
        <meshStandardMaterial color="#14161c" metalness={0.3} roughness={0.6} />
      </mesh>
      {/* seat */}
      <mesh position={[0, 0.52, 0]} castShadow>
        <boxGeometry args={[0.5, 0.09, 0.5]} />
        <meshStandardMaterial color="#333947" roughness={0.85} />
      </mesh>
      {/* backrest */}
      <mesh position={[0, 0.72, -0.26]} rotation={[-0.15, 0, 0]} castShadow>
        <boxGeometry args={[0.5, 0.55, 0.09]} />
        <meshStandardMaterial color="#333947" roughness={0.85} />
      </mesh>
      {/* armrests */}
      <mesh position={[0.33, 0.58, 0.02]}>
        <boxGeometry args={[0.06, 0.04, 0.3]} />
        <meshStandardMaterial color="#262a34" roughness={0.7} />
      </mesh>
      <mesh position={[-0.33, 0.58, 0.02]}>
        <boxGeometry args={[0.06, 0.04, 0.3]} />
        <meshStandardMaterial color="#262a34" roughness={0.7} />
      </mesh>
    </group>
  );
}