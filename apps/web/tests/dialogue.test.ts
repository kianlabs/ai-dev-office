import { describe, expect, it } from "vitest";

import {
  clampLineSeconds,
  conversationWorkStatus,
  cumulativeDialogueSeconds,
  MAX_DIALOGUE_LINES,
  MAX_LINE_SECONDS,
  MIN_LINE_SECONDS,
  roleDialogue,
  shouldStartConversation,
  type DialogueLine,
} from "../components/office-3d/agents/dialogue";
import type { HandoffRole } from "../components/office-3d/navigation/handoff";

const ROLES: HandoffRole[] = ["scout", "forge", "qa", "pulse"];

describe("role -> dialogue", () => {
  it("produces the correct scripted lines for every role", () => {
    expect(roleDialogue("scout").map((l) => l.text)).toEqual([
      "Scout, coba cek bagian ini dulu.",
      "Siap, saya telusuri.",
      "Fokus ke temuan yang paling penting.",
      "Oke, nanti saya rangkum.",
    ]);
    expect(roleDialogue("forge").map((l) => l.text)).toEqual([
      "Forge, lanjut implementasikan ini.",
      "Siap, saya kerjakan.",
      "Jaga perubahannya tetap fokus.",
      "Oke, saya lanjut.",
    ]);
    expect(roleDialogue("qa").map((l) => l.text)).toEqual([
      "QA, coba periksa hasil Forge.",
      "Siap, saya cek.",
      "Pastikan tidak ada regresi.",
      "Oke, saya verifikasi.",
    ]);
    expect(roleDialogue("pulse").map((l) => l.text)).toEqual([
      "Pulse, cek kondisi runtime.",
      "Siap, saya pantau.",
      "Kabari kalau ada masalah.",
      "Oke, saya awasi.",
    ]);
  });

  it("assigns an in-window duration to every line", () => {
    for (const role of ROLES) {
      for (const line of roleDialogue(role)) {
        expect(line.seconds).toBeGreaterThanOrEqual(MIN_LINE_SECONDS);
        expect(line.seconds).toBeLessThanOrEqual(MAX_LINE_SECONDS);
      }
    }
  });
});

describe("alternating speaker order", () => {
  it("alternates ATLAS then target, never two of the same speaker back-to-back", () => {
    for (const role of ROLES) {
      const lines = roleDialogue(role);
      expect(lines[0].speaker).toBe("atlas");
      for (let i = 0; i < lines.length; i++) {
        const expected = i % 2 === 0 ? "atlas" : role;
        expect(lines[i].speaker).toBe(expected);
      }
    }
  });
});

describe("max 4 lines", () => {
  it("never exceeds MAX_DIALOGUE_LINES", () => {
    for (const role of ROLES) {
      expect(roleDialogue(role).length).toBeLessThanOrEqual(MAX_DIALOGUE_LINES);
      // Scripts are authored at exactly the cap.
      expect(roleDialogue(role).length).toBe(MAX_DIALOGUE_LINES);
    }
  });

  it("clamps line durations into [1.3, 1.8]", () => {
    expect(clampLineSeconds(1.0)).toBe(MIN_LINE_SECONDS);
    expect(clampLineSeconds(1.5)).toBe(1.5);
    expect(clampLineSeconds(5.0)).toBe(MAX_LINE_SECONDS);
  });
});

describe("duplicate dispatch does not replay", () => {
  it("a repeated (unchanged) dispatch does not start a new conversation", () => {
    expect(shouldStartConversation("forge", "forge")).toBe(false);
    expect(shouldStartConversation(null, null)).toBe(false);
  });

  it("starts only on a brand-new delegation", () => {
    expect(shouldStartConversation(null, "scout")).toBe(true);
    expect(shouldStartConversation("scout", "qa")).toBe(true);
  });

  it("a cleared target never replays", () => {
    expect(shouldStartConversation("pulse", null)).toBe(false);
  });
});

describe("conversation ends in correct work status", () => {
  const expected: Record<HandoffRole, string> = {
    scout: "Meneliti...",
    forge: "Menulis kode...",
    qa: "Menguji...",
    pulse: "Memantau...",
  };

  it("each role's terminal status matches its conversation", () => {
    for (const role of ROLES) {
      expect(conversationWorkStatus(role)).toBe(expected[role]);
    }
  });
});

describe("cumulative timing helper", () => {
  it("sums the display time of completed lines", () => {
    const lines: DialogueLine[] = [
      { speaker: "atlas", text: "a", seconds: 1.3 },
      { speaker: "scout", text: "b", seconds: 1.8 },
      { speaker: "atlas", text: "c", seconds: 1.5 },
    ];
    expect(cumulativeDialogueSeconds(lines, 0)).toBeCloseTo(0);
    expect(cumulativeDialogueSeconds(lines, 1)).toBeCloseTo(1.3);
    expect(cumulativeDialogueSeconds(lines, 2)).toBeCloseTo(3.1);
    expect(cumulativeDialogueSeconds(lines, 3)).toBeCloseTo(4.6);
  });
});
