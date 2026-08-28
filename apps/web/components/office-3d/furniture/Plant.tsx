"use client";

// Low-poly plant: pot + a few leaf blades. Keep it cheap.
export default function Plant({
  position,
  scale = 1,
}: {
  position: [number, number, number];
  scale?: number;
}) {
  return (
    <group position={position} scale={scale}>
      {/* pot */}
      <mesh position={[0, 0.18, 0]} castShadow>
        <cylinderGeometry args={[0.28, 0.2, 0.36, 6]} />
        <meshStandardMaterial color="#2c3a33" roughness={0.8} />
      </mesh>
      {/* soil */}
      <mesh position={[0, 0.37, 0]}>
        <cylinderGeometry args={[0.24, 0.24, 0.04, 6]} />
        <meshStandardMaterial color="#3a3226" roughness={1} />
      </mesh>
      {/* leaves */}
      {[0, 1, 2, 3].map((i) => {
        const a = (i / 4) * Math.PI * 2;
        return (
          <mesh
            key={i}
            position={[Math.cos(a) * 0.12, 0.85, Math.sin(a) * 0.12]}
            rotation={[0, a, 0.4]}
            castShadow
          >
            <coneGeometry args={[0.07, 0.95, 5]} />
            <meshStandardMaterial color="#2f7d52" roughness={0.85} />
          </mesh>
        );
      })}
    </group>
  );
}