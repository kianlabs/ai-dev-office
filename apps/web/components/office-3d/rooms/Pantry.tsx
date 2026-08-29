"use client";

import OfficeChair from "../furniture/OfficeChair";
import Plant from "../furniture/Plant";

export default function Pantry({
  position,
}: {
  position: [number, number, number];
}) {
  return (
    <group position={position}>
      {/* round table */}
      <mesh position={[0, 0.42, 0]} castShadow receiveShadow>
        <cylinderGeometry args={[0.78, 0.78, 0.08, 24]} />
        <meshStandardMaterial color="#8f6d4f" roughness={0.72} />
      </mesh>
      <mesh position={[0, 0.2, 0]} castShadow>
        <cylinderGeometry args={[0.08, 0.1, 0.42, 12]} />
        <meshStandardMaterial color="#2a2f38" roughness={0.6} />
      </mesh>
      <mesh position={[0, 0.04, 0]}>
        <cylinderGeometry args={[0.42, 0.45, 0.05, 18]} />
        <meshStandardMaterial color="#1a1e26" roughness={0.65} />
      </mesh>

      <OfficeChair position={[0, 0, 1.05]} rotation={-Math.PI / 2} />
      <OfficeChair position={[1.05, 0, 0]} rotation={0} />
      <OfficeChair position={[-1.05, 0, 0]} rotation={Math.PI} />
      <OfficeChair position={[0, 0, -1.05]} rotation={Math.PI / 2} />

      {/* counter */}
      <mesh position={[-1.95, 0.45, -1.35]} castShadow receiveShadow>
        <boxGeometry args={[1.75, 0.9, 0.62]} />
        <meshStandardMaterial color="#7d868f" roughness={0.72} />
      </mesh>
      <mesh position={[-1.95, 0.95, -1.35]}>
        <boxGeometry args={[1.78, 0.08, 0.68]} />
        <meshStandardMaterial color="#bab8b2" roughness={0.48} />
      </mesh>

      {/* coffee machine */}
      <mesh position={[-2.3, 1.12, -1.35]}>
        <boxGeometry args={[0.28, 0.28, 0.22]} />
        <meshStandardMaterial color="#20242b" roughness={0.5} metalness={0.2} />
      </mesh>

      {/* mugs */}
      <mesh position={[-1.7, 1.07, -1.25]}>
        <cylinderGeometry args={[0.05, 0.05, 0.1, 12]} />
        <meshStandardMaterial color="#f5f1ea" roughness={0.4} />
      </mesh>
      <mesh position={[-1.55, 1.07, -1.4]}>
        <cylinderGeometry args={[0.05, 0.05, 0.1, 12]} />
        <meshStandardMaterial color="#f5f1ea" roughness={0.4} />
      </mesh>

      <Plant position={[1.75, 0, -1.25]} />
    </group>
  );
}
