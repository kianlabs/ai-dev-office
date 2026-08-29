import { describe, expect, it } from "vitest";

import {
  detectHandoffTarget,
  statusBubbleFor,
  WORK_STATE,
  type HandoffRole,
} from "../components/office-3d/navigation/handoff";

const ROLES: HandoffRole[] = ["scout", "forge", "qa", "pulse"];

describe("detectHandoffTarget", () => {
  it("reads an explicit Dispatching <AGENT> mention", () => {
    expect(detectHandoffTarget("Dispatching SCOUT — research request")).toBe(
      "scout",
    );
    expect(
      detectHandoffTarget("Now dispatching FORGE for the API contract"),
    ).toBe("forge");
    expect(detectHandoffTarget("DISPATCHING QA — run the suite")).toBe("qa");
    expect(
      detectHandoffTarget("Dispatch pulse to monitor the service"),
    ).toBe("pulse");
  });

  it("falls back to the first specialist token without a dispatch verb", () => {
    expect(detectHandoffTarget("delegating to FORGE now")).toBe("forge");
    expect(detectHandoffTarget("SCOUT please look into it")).toBe("scout");
  });

  it("returns null when no delegation is signalled", () => {
    expect(detectHandoffTarget("")).toBeNull();
    expect(detectHandoffTarget("Reviewing the plan")).toBeNull();
    expect(detectHandoffTarget("Dispatching selected specialists")).toBeNull();
  });

  it("never treats ATLAS itself as a delegation target", () => {
    expect(detectHandoffTarget("Dispatching ATLAS")).toBeNull();
  });
});

describe("statusBubbleFor (persistent work status from semantic state)", () => {
  it("shows the role's compact work label (Bahasa Indonesia) while actively working", () => {
    expect(statusBubbleFor("scout", "researching", true)).toEqual({
      text: "Meneliti...",
      kind: "status",
    });
    expect(statusBubbleFor("forge", "coding", true)).toEqual({
      text: "Menulis kode...",
      kind: "status",
    });
    expect(statusBubbleFor("qa", "testing", true)).toEqual({
      text: "Menguji...",
      kind: "status",
    });
    expect(statusBubbleFor("pulse", "monitoring", true)).toEqual({
      text: "Memantau...",
      kind: "status",
    });
    expect(statusBubbleFor("atlas", "dispatching", true)).toEqual({
      text: "Mengoordinasikan...",
      kind: "status",
    });
  });

  it("hides when the agent is idle, erroring, or inactive", () => {
    expect(statusBubbleFor("forge", "idle", true)).toBeUndefined();
    expect(statusBubbleFor("forge", "error", true)).toBeUndefined();
    expect(statusBubbleFor("forge", "coding", false)).toBeUndefined();
  });
});

describe("work-state mapping", () => {
  it("maps each role to the expected persistent work state (display tr.), mode intact", () => {
    expect(WORK_STATE.scout).toEqual({ label: "Meneliti...", mode: "researching" });
    expect(WORK_STATE.forge).toEqual({ label: "Menulis kode...", mode: "coding" });
    expect(WORK_STATE.qa).toEqual({ label: "Menguji...", mode: "testing" });
    expect(WORK_STATE.pulse).toEqual({ label: "Memantau...", mode: "monitoring" });
    expect(WORK_STATE.atlas).toEqual({ label: "Mengoordinasikan...", mode: "dispatching" });
  });
});
