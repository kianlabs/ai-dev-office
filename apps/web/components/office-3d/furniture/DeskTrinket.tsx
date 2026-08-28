"use client";

// Small desk decoration - a coffee mug + a stack of books. Keeps workstations
// feeling inhabited without extra assets.
export default function DeskTrinket({
  position,
}: {
  position: [number, number, number];
}) {
  return (
    <group position={position}>
      {/* mug */}
      <mesh position={[0, 0.045, 0]} castShadow>
        <cylinderGeometry args={[0.05, 0.05, 0.09, 8]} />
        <meshStandardMaterial color="#7c4a3a" roughness={0.6} />
      </mesh>
      {/* books */}
      <mesh position={[0.2, 0.06, 0]} castShadow>
        <boxGeometry args={[0.18, 0.05, 0.26]} />
        <meshStandardMaterial color="#3b5b8c" roughness={0.7} />
      </mesh>
      <mesh position={[0.16, 0.13, 0.02]} castShadow>
        <boxGeometry args={[0.16, 0.05, 0.24]} />
        <meshStandardMaterial color="#5c3b8c" roughness={0.7} />
      </mesh>
    </group>
  );
}