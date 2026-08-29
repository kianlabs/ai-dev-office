"use client";

/**
 * Lightweight billboarded text indicator above an agent's head.
 *
 * Pure rendering: no scene/semantic logic. Always faces the camera via drei
 * <Billboard> (NOT <Html>, which previously broke the canvas) and uses troika
 * <Text> for readable small labels. Two kinds:
 *   - "speech": short-lived conversation bubble (subtle rounded panel).
 *   - "status": persistent compact work label (dot + text, dimmer).
 */
import { Billboard, Text } from "@react-three/drei";
import type { HandoffBubble } from "../navigation/handoff";

interface AgentBubbleProps {
  bubble?: HandoffBubble;
  /** Accent color (agent signal color). */
  color: string;
  /** Vertical offset above the character root (world units). */
  height?: number;
}

const PANEL_OPACITY = 0.86;
const STATUS_OPACITY = 0.72;

export default function AgentBubble({
  bubble,
  color,
  height = 1.9,
}: AgentBubbleProps) {
  if (!bubble) return null;

  const isSpeech = bubble.kind === "speech";
  // Rough width estimate so the panel hugs short text (never giant).
  const textWidth = Math.min(1.7, 0.28 + bubble.text.length * 0.075);

  return (
    <group position={[0, height, 0]}>
      <Billboard>
        <group>
          {/* subtle backing panel */}
          <mesh position={[0, 0, -0.01]}>
            <planeGeometry args={[textWidth, 0.3]} />
            <meshStandardMaterial
              color="#0b0f16"
              transparent
              opacity={isSpeech ? PANEL_OPACITY : STATUS_OPACITY}
              roughness={0.9}
              depthWrite={false}
            />
          </mesh>
          {/* status accent dot */}
          <mesh position={[-textWidth / 2 + 0.12, 0, 0]}>
            <circleGeometry args={[0.045, 12]} />
            <meshStandardMaterial
              color={color}
              transparent
              opacity={isSpeech ? 0.95 : 0.7}
              toneMapped={false}
            />
          </mesh>
          <Text
            position={[0.05, 0, 0]}
            fontSize={0.11}
            color="#e2e8f0"
            anchorX="center"
            anchorY="middle"
            maxWidth={textWidth - 0.28}
            outlineWidth={0}
          >
            {bubble.text}
          </Text>
        </group>
      </Billboard>
    </group>
  );
}
