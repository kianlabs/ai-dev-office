"use client";

// Low-poly placeholder for an agent (no humanoid animation). Simple capsule
// body + head. Will be replaced by a GLB character in a later phase.
export default function AgentDummy({
  position,
  color = "#3b82f6",
}: {
  position: [number, number, number];
  color?: string;
}) {
  return (
    <group position={position}>
      {/* legs */}
      <mesh position={[0, 0.3, 0]} castShadow>
        <capsuleGeometry args={[0.06, 0.5, 4, 8]} />
        <meshStandardMaterial color={color} roughness={0.6} />
      </mesh>
      {/* torso */}
      <mesh position={[0, 0.72, 0]} castShadow>
        <capsuleGeometry args={[0.16, 0.28, 4, 8]} />
        <meshStandardMaterial color={color} roughness={0.6} />
      </mesh>
      {/* head */}
      <mesh position={[0, 1.08, 0]} castShadow>
        <sphereGeometry args={[0.11, 16, 12]} />
        <meshStandardMaterial color="#d8cbb8" roughness={0.7} />
      </mesh>
    </group>
  );
}