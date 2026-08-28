"use client";

// Scene atmosphere: dark neutral background + subtle fog for depth. Cheap,
// no heavy post-processing.
export default function OfficeEnvironment() {
  return (
    <>
      <color attach="background" args={["#080b12"]} />
      <fog attach="fog" args={["#080b12", 55, 110]} />
    </>
  );
}