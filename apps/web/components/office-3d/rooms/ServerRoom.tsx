"use client";

import ServerRack from "../furniture/ServerRack";

export default function ServerRoom({
  position,
}: {
  position: [number, number, number];
}) {
  const W = 3.7;
  const D = 3.8;
  const H = 2.4;

  const glass = (
    <meshStandardMaterial
      color="#a9c4d6"
      transparent
      opacity={0.14}
      roughness={0.08}
      depthWrite={false}
    />
  );

  return (
    <group position={position}>
      <mesh
        position={[0, 0.012, 0]}
        rotation={[-Math.PI / 2, 0, 0]}
      >
        <planeGeometry args={[W, D]} />
        <meshStandardMaterial
          color="#171b22"
          roughness={0.92}
        />
      </mesh>

      <mesh position={[-W / 2, H / 2, 0]}>
        <boxGeometry args={[0.04, H, D]} />
        {glass}
      </mesh>

      <mesh position={[0, H / 2, D / 2]}>
        <boxGeometry args={[W, H, 0.04]} />
        {glass}
      </mesh>

      <mesh position={[-1.3, H / 2, -D / 2]}>
        <boxGeometry args={[1.05, H, 0.04]} />
        {glass}
      </mesh>

      <mesh position={[1.3, H / 2, -D / 2]}>
        <boxGeometry args={[1.05, H, 0.04]} />
        {glass}
      </mesh>

      {/* thin frame, never a solid roof */}
      <mesh position={[-W / 2, H, 0]}>
        <boxGeometry args={[0.07, 0.07, D]} />
        <meshStandardMaterial color="#343c46" />
      </mesh>

      <mesh position={[0, H, D / 2]}>
        <boxGeometry args={[W, 0.07, 0.07]} />
        <meshStandardMaterial color="#343c46" />
      </mesh>

      <ServerRack
        position={[-0.85, 0, 0.25]}
        glow={0.75}
      />

      <ServerRack
        position={[0.85, 0, 0.25]}
        glow={0.9}
      />
    </group>
  );
}
