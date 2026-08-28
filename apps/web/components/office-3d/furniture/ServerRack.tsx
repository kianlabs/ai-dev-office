"use client";

// Server rack with subtle glowing indicator strips.
export default function ServerRack({
  position,
  rotation = 0,
  glow = 0.6,
}: {
  position: [number, number, number];
  rotation?: number;
  glow?: number;
}) {
  return (
    <group position={position} rotation={[0, rotation, 0]}>
      {/* cabinet */}
      <mesh position={[0, 1.0, 0]} castShadow>
        <boxGeometry args={[0.85, 2.0, 1.1]} />
        <meshStandardMaterial color="#15181f" metalness={0.5} roughness={0.35} />
      </mesh>
      {/* server units + glowing leds */}
      {Array.from({ length: 7 }).map((_, i) => {
        const y = 1.82 - i * 0.26;
        return (
          <group key={i}>
            <mesh position={[0, y, 0]}>
              <boxGeometry args={[0.72, 0.2, 1.0]} />
              <meshStandardMaterial color="#1b2027" metalness={0.4} roughness={0.4} />
            </mesh>
            <mesh position={[0.3, y, 0.52]}>
              <boxGeometry args={[0.02, 0.02, 0.35]} />
              <meshStandardMaterial
                color="#22d3ee"
                emissive="#22d3ee"
                emissiveIntensity={glow}
                toneMapped={false}
              />
            </mesh>
            <mesh position={[0, y, 0.52]}>
              <boxGeometry args={[0.02, 0.02, 0.05]} />
              <meshStandardMaterial
                color="#34d399"
                emissive="#34d399"
                emissiveIntensity={glow}
                toneMapped={false}
              />
            </mesh>
          </group>
        );
      })}
    </group>
  );
}