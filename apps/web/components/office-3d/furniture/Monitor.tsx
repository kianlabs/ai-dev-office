"use client";

// Monitor with an emissive screen whose brightness reacts to agent status.
export default function Monitor({
  position,
  rotation = 0,
  screenGlow = 1.0,
  screenColor = "#7dd3fc",
}: {
  position: [number, number, number];
  rotation?: number;
  screenGlow?: number;
  screenColor?: string;
}) {
  return (
    <group position={position} rotation={[0, rotation, 0]}>
      {/* stand */}
      <mesh position={[0, -0.08, 0]}>
        <boxGeometry args={[0.06, 0.1, 0.14]} />
        <meshStandardMaterial color="#1a1d24" metalness={0.3} roughness={0.5} />
      </mesh>
      {/* panel bezel */}
      <mesh position={[0, 0.28, 0]}>
        <boxGeometry args={[0.16, 0.62, 0.9]} />
        <meshStandardMaterial color="#14161c" metalness={0.2} roughness={0.6} />
      </mesh>
      {/* screen */}
      <mesh position={[0, 0.3, 0.462]}>
        <boxGeometry args={[0.12, 0.52, 0.02]} />
        <meshStandardMaterial
          color={screenColor}
          emissive={screenColor}
          emissiveIntensity={screenGlow}
          toneMapped={false}
        />
      </mesh>
      {/* faint headphone hook / top accent */}
      <mesh position={[0, 0.62, 0]}>
        <boxGeometry args={[0.05, 0.03, 0.4]} />
        <meshStandardMaterial color="#22d3ee" emissive="#22d3ee" emissiveIntensity={0.3} />
      </mesh>
    </group>
  );
}