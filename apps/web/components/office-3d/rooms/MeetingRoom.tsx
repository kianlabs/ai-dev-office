"use client";

import OfficeChair from "../furniture/OfficeChair";

export default function MeetingRoom({
  position,
}: {
  position: [number, number, number];
}) {
  const W = 4.5;
  const D = 4.0;
  const H = 2.35;

  const glass = (
    <meshStandardMaterial
      color="#bcd1dc"
      transparent
      opacity={0.15}
      roughness={0.08}
      metalness={0.02}
      depthWrite={false}
    />
  );

  return (
    <group position={position}>
      {/* darker inset floor */}
      <mesh
        position={[0, 0.012, 0]}
        rotation={[-Math.PI / 2, 0, 0]}
      >
        <planeGeometry args={[W, D]} />
        <meshStandardMaterial
          color="#695747"
          roughness={0.95}
        />
      </mesh>

      {/* glass partitions */}
      <mesh position={[W / 2, H / 2, 0]}>
        <boxGeometry args={[0.04, H, D]} />
        {glass}
      </mesh>

      <mesh position={[0, H / 2, D / 2]}>
        <boxGeometry args={[W, H, 0.04]} />
        {glass}
      </mesh>

      {/* door side */}
      <mesh position={[-1.55, H / 2, -D / 2]}>
        <boxGeometry args={[1.35, H, 0.04]} />
        {glass}
      </mesh>

      <mesh position={[1.55, H / 2, -D / 2]}>
        <boxGeometry args={[1.35, H, 0.04]} />
        {glass}
      </mesh>

      {/* perimeter frame only */}
      <mesh position={[W / 2, H, 0]}>
        <boxGeometry args={[0.07, 0.07, D]} />
        <meshStandardMaterial color="#343b42" />
      </mesh>

      <mesh position={[0, H, D / 2]}>
        <boxGeometry args={[W, 0.07, 0.07]} />
        <meshStandardMaterial color="#343b42" />
      </mesh>

      {/* conference table */}
      <mesh
        position={[0, 0.43, 0.15]}
        castShadow
        receiveShadow
      >
        <boxGeometry args={[2.8, 0.09, 1.4]} />
        <meshStandardMaterial
          color="#906b49"
          roughness={0.7}
        />
      </mesh>

      <OfficeChair
        position={[-1.55, 0, 0.1]}
        rotation={Math.PI / 2}
      />
      <OfficeChair
        position={[1.55, 0, 0.1]}
        rotation={-Math.PI / 2}
      />
      <OfficeChair
        position={[-0.65, 0, -1.05]}
        rotation={0}
      />
      <OfficeChair
        position={[0.65, 0, -1.05]}
        rotation={0}
      />
      <OfficeChair
        position={[-0.65, 0, 1.18]}
        rotation={Math.PI}
      />
      <OfficeChair
        position={[0.65, 0, 1.18]}
        rotation={Math.PI}
      />

      {/* whiteboard */}
      <mesh position={[-W / 2 + 0.04, 1.25, 0]}>
        <boxGeometry args={[0.04, 1.05, 2.2]} />
        <meshStandardMaterial color="#f3f1ec" />
      </mesh>
    </group>
  );
}
