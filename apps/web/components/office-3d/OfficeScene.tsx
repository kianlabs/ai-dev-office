"use client";

import type { OrthographicCamera as CamType } from "three";
import type { OrbitControls as OrbitImpl } from "three-stdlib";
import type { AgentRecord } from "@/lib/types";

import IsometricCamera from "./camera/IsometricCamera";
import ConstrainedControls from "./camera/ConstrainedControls";
import OfficeLighting from "./lighting/OfficeLighting";
import MainOffice from "./rooms/MainOffice";

interface OfficeSceneProps {
  agents: AgentRecord[];
  camRef: React.RefObject<CamType | null>;
  controlsRef: React.RefObject<OrbitImpl | null>;
}

// The static 3D scene: camera, constrained orbit controls, lighting and the
// main office assembled from rooms/furniture/stations.
export default function OfficeScene({ agents, camRef, controlsRef }: OfficeSceneProps) {
  return (
    <>
      <IsometricCamera camRef={camRef} />
      <ConstrainedControls controlsRef={controlsRef} />
      <OfficeLighting />
      <MainOffice agents={agents} />
    </>
  );
}