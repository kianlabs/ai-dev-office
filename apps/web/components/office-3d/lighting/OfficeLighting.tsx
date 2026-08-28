"use client";

// Lightweight lighting for the office: soft ambient + a key directional that
// casts shadows. Kept cheap and readable, not physically accurate.
export default function OfficeLighting() {
  return (
    <>
      <ambientLight intensity={0.55} color="#cdd6ff" />
      <directionalLight
        position={[10, 18, 8]}
        intensity={1.6}
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
      <directionalLight position={[-12, 8, -10]} intensity={0.45} color="#7aa2ff" />
      {/* subtle neutral fill from the front */}
      <hemisphereLight args={["#3a4458", "#1a1712", 0.6]} />
    </>
  );
}