"use client";

export default function Lounge({
  position,
}: {
  position: [number, number, number];
}) {
  return (
    <group position={position}>
      {/* rug */}
      <mesh position={[0, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[3.6, 2.4]} />
        <meshStandardMaterial color="#6a625d" roughness={1} />
      </mesh>

      {/* TV console */}
      <mesh position={[0, 0.3, -1.1]} castShadow receiveShadow>
        <boxGeometry args={[2.2, 0.6, 0.45]} />
        <meshStandardMaterial color="#46372e" roughness={0.82} />
      </mesh>

      {/* TV */}
      <mesh position={[0, 1.0, -1.34]}>
        <boxGeometry args={[1.7, 0.95, 0.05]} />
        <meshStandardMaterial
          color="#5cb8ff"
          emissive="#5cb8ff"
          emissiveIntensity={0.35}
          toneMapped={false}
        />
      </mesh>

      {/* sofa */}
      <mesh position={[0, 0.38, 0.75]} castShadow receiveShadow>
        <boxGeometry args={[2.15, 0.36, 0.82]} />
        <meshStandardMaterial color="#5f6368" roughness={0.92} />
      </mesh>
      <mesh position={[0, 0.72, 1.03]} castShadow>
        <boxGeometry args={[2.15, 0.56, 0.2]} />
        <meshStandardMaterial color="#5f6368" roughness={0.92} />
      </mesh>
      <mesh position={[-1.02, 0.66, 0.75]} castShadow>
        <boxGeometry args={[0.16, 0.46, 0.82]} />
        <meshStandardMaterial color="#5f6368" roughness={0.92} />
      </mesh>
      <mesh position={[1.02, 0.66, 0.75]} castShadow>
        <boxGeometry args={[0.16, 0.46, 0.82]} />
        <meshStandardMaterial color="#5f6368" roughness={0.92} />
      </mesh>

      {/* coffee table */}
      <mesh position={[0.55, 0.25, -0.05]} castShadow receiveShadow>
        <cylinderGeometry args={[0.45, 0.45, 0.08, 18]} />
        <meshStandardMaterial color="#7f5d43" roughness={0.74} />
      </mesh>
      <mesh position={[0.55, 0.11, -0.05]} castShadow>
        <cylinderGeometry args={[0.07, 0.08, 0.26, 12]} />
        <meshStandardMaterial color="#242932" roughness={0.6} />
      </mesh>

      {/* bean bag */}
      <mesh position={[-0.9, 0.24, -0.1]} castShadow receiveShadow>
        <sphereGeometry args={[0.42, 18, 16]} />
        <meshStandardMaterial color="#4d4fbf" roughness={0.96} />
      </mesh>

      {/* floor lamp */}
      <mesh position={[1.7, 0.55, -0.55]} castShadow>
        <cylinderGeometry args={[0.03, 0.03, 1.1, 10]} />
        <meshStandardMaterial color="#1e232b" />
      </mesh>
      <mesh position={[1.7, 1.15, -0.55]}>
        <coneGeometry args={[0.16, 0.22, 14]} />
        <meshStandardMaterial color="#efe6b0" emissive="#efe6b0" emissiveIntensity={0.15} />
      </mesh>
    </group>
  );
}
