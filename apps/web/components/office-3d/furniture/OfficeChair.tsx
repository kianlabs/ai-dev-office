"use client";

import OfficeAsset from "../assets/OfficeAsset";

export default function OfficeChair({
  position,
  rotation = 0,
}: {
  position: [number, number, number];
  rotation?: number;
}) {
  return (
    <OfficeAsset
      src="/models/office/workstation/office-chair.glb"
      position={position}
      rotation={[0, rotation, 0]}
      scale={0.66}
      bottomCenter
    />
  );
}
