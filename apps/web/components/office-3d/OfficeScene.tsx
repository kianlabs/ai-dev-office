"use client";

import type { ActivityItem, AgentRecord } from "@/lib/types";

import IsometricCamera from "./camera/IsometricCamera";
import ConstrainedControls from "./camera/ConstrainedControls";
import OfficeFrame from "./camera/OfficeFrame";
import OfficeLighting from "./lighting/OfficeLighting";
import MainOffice from "./rooms/MainOffice";
import type { OfficeCameraRefs } from "./useOfficeCamera";

interface OfficeSceneProps {
  agents: AgentRecord[];
  activity: ActivityItem[];
  refs: OfficeCameraRefs;
}

// The static 3D scene: camera, constrained orbit controls, lighting and the
// main office assembled from rooms/furniture/stations. OfficeFrame fits the
// whole office into the viewport on the first frame.
export default function OfficeScene({
  agents,
  activity,
  refs,
}: OfficeSceneProps) {
  return (
    <>
      <IsometricCamera camRef={refs.camRef} />
      <ConstrainedControls controlsRef={refs.controlsRef} />
      <OfficeLighting />
      <MainOffice agents={agents} activity={activity} />
      <OfficeFrame refs={refs} />
    </>
  );
}