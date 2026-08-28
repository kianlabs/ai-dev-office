"use client";

// Lightweight lighting for the office: soft ambient + a key directional that
// casts shadows. Kept cheap and readable, not physically accurate.
export default function OfficeLighting() {
  return (
    <>
      <ambientLight intensity={1.0} color="#dfe6ff" />
      <directionalLight
        position={[10, 18, 8]}
        intensity={2.0}
        color="#fff4e0"
        castShadow
        shadow-mapSize-width={1024}
        shadow-mapSize-height={1024}
        shadow-camera-left={-20}
        shadow-camera-right={20}
        shadow-camera-top={20}
        shadow-camera-bottom={-20}
      />
      {/* cool fill from the window side */}
      <directionalLight position={[-12, 8, -10]} intensity={0.7} color="#7aa2ff" />
      {/* subtle neutral fill from the front */}
      <hemisphereLight args={["#4a5570", "#2a2218", 1.0]} />
    </>
  );
}