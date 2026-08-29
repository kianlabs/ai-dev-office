"use client";

import OfficeAsset from "../assets/OfficeAsset";

export default function Laptop({
  position,
  rotation = 0,
  scale = 0.9,
}: {
  position: [number, number, number];
  rotation?: number;
  scale?: number;
}) {
  return (
    <OfficeAsset
      src="/models/office/workstation/laptop.glb"
      position={position}
      rotation={[0, rotation, 0]}
      scale={scale}
      bottomCenter
    />
  );
}
