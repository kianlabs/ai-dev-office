import { describe, expect, it } from "vitest";

import {
  isSeatedTalking,
  nextSeatedPhase,
  seatedWorkSequence,
  SEATED_TALK_CLIP,
  SEATED_TALK_HOLD_SECONDS,
  type SeatedPhase,
  type WorkMode,
} from "../components/office-3d/agents/seatedBehavior";

const STANDING_CLIPS = new Set(["standToSit", "sitToStand", "walking"]);

describe("nextSeatedPhase — seated micro machine", () => {
  it("a new delegation announcement sends a seated agent to SeatedTalking", () => {
    expect(nextSeatedPhase("SEATED_IDLE", true, SEATED_TALK_HOLD_SECONDS)).toBe(
      "SEATED_TALKING",
    );
    expect(isSeatedTalking("SEATED_TALKING")).toBe(true);
  });

  it("holds SeatedTalking during the talk window, then moves to work", () => {
    expect(
      nextSeatedPhase("SEATED_TALKING", false, 1.0),
    ).toBe("SEATED_TALKING");
    expect(
      nextSeatedPhase("SEATED_TALKING", false, 0),
    ).toBe("SEATED_WORK");
  });

  it("a new announcement during work goes back through SeatedTalking", () => {
    expect(
      nextSeatedPhase("SEATED_WORK", true, SEATED_TALK_HOLD_SECONDS),
    ).toBe("SEATED_TALKING");
  });

  it("semantic text changes with no new announcement keep the agent seated working", () => {
    // A status/activity update must NEVER restart sit/stand or leave work.
    expect(nextSeatedPhase("SEATED_WORK", false, 0)).toBe("SEATED_WORK");
    expect(nextSeatedPhase("SEATED_IDLE", false, 0)).toBe("SEATED_IDLE");
  });
});

describe("seatedWorkSequence — work never stands", () => {
  const modes: WorkMode[] = ["typing", "monitor"];

  it("neither work mode contains any stand/sit-stand/walk clip", () => {
    for (const mode of modes) {
      for (const phase of seatedWorkSequence(mode)) {
        expect(STANDING_CLIPS.has(phase.clip)).toBe(false);
      }
    }
  });

  it("typing cycles the keyboard without re-entering the chair", () => {
    const seq = seatedWorkSequence("typing");
    // Starts toward the keys and never stands; ends back at a seated rest.
    expect(seq[0].clip).toBe("sitToType");
    expect(seq.at(-1)?.clip).toBe("seatedIdle");
    for (const phase of seq) expect(phase.clip).not.toBe("sitToStand");
    for (const phase of seq) expect(phase.clip).not.toBe("standToSit");
  });

  it("monitor stays on a seated rest loop (no locomotion)", () => {
    const seq = seatedWorkSequence("monitor");
    expect(seq).toEqual([{ clip: "seatedIdle", mode: "loop", seconds: 6 }]);
  });
});

describe("seated talking clip", () => {
  it("uses the Sitting Talking Mixamo clip for the held talk window", () => {
    expect(SEATED_TALK_CLIP).toBe("sittingTalking");
    expect(SEATED_TALK_HOLD_SECONDS).toBeGreaterThan(0);
  });
});

describe("MIXAMO_SEATED_SEQUENCE integration", () => {
  it("typing work derives from the shared seated sequence and excludes walking", () => {
    const seq = seatedWorkSequence("typing");
    expect(seq.map((p) => p.clip)).not.toContain("walking");
  });
});
