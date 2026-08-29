import { describe, expect, it } from "vitest";
import * as THREE from "three";

import {
  MIXAMO_AGENTS,
  MIXAMO_CLIP_URLS,
  MIXAMO_SEATED_SEQUENCE,
  MIXAMO_SEQUENCE,
  detectMixamoPrefix,
  makeClipInPlace,
  mixamoPrefixOf,
  normalizeMixamoClip,
} from "../components/office-3d/agents/mixamo";
import { AGENT_ORDER } from "../lib/types";
import {
  AGENT_HOME,
  type AgentId,
} from "../components/office-3d/navigation/waypoints";
import {
  SHARED_DESK_WORLD_OFFSET,
  agentHomeWorld,
  agentRestAnchor,
} from "../components/office-3d/navigation/layout";

describe("mixamoPrefixOf", () => {
  it("detects bare and numbered namespaces", () => {
    expect(mixamoPrefixOf("mixamorigHips")).toBe("mixamorig");
    expect(mixamoPrefixOf("mixamorig2Hips")).toBe("mixamorig2");
    expect(mixamoPrefixOf("mixamorig12HeadTop_End")).toBe("mixamorig12");
  });

  it("detects colon-separated namespaces", () => {
    expect(mixamoPrefixOf("mixamorig:Hips")).toBe("mixamorig:");
    expect(mixamoPrefixOf("mixamorig1:Hips")).toBe("mixamorig1:");
  });

  it("returns empty for unprefixed names", () => {
    expect(mixamoPrefixOf("Hips")).toBe("");
    expect(mixamoPrefixOf("Armature")).toBe("");
  });
});

describe("detectMixamoPrefix", () => {
  it("finds the character skeleton namespace", () => {
    const hips = new THREE.Bone();
    hips.name = "mixamorig2Hips";
    const spine = new THREE.Bone();
    spine.name = "mixamorig2Spine";
    hips.add(spine);

    expect(detectMixamoPrefix(hips)).toBe("mixamorig2");
  });

  it("returns empty when no Mixamo bone exists", () => {
    const group = new THREE.Group();
    group.add(new THREE.Mesh(new THREE.BoxGeometry()));

    expect(detectMixamoPrefix(group)).toBe("");
  });
});

describe("normalizeMixamoClip", () => {
  function clipWithTracks(names: string[]): THREE.AnimationClip {
    return new THREE.AnimationClip(
      "mixamo.com",
      1,
      names.map(
        (name) => new THREE.VectorKeyframeTrack(name, [0, 1], [0, 0, 0, 0, 0, 0]),
      ),
    );
  }

  it("rewrites animation namespaces onto the character skeleton", () => {
    const clip = clipWithTracks([
      "mixamorigHips.position",
      "mixamorigSpine.quaternion",
    ]);

    normalizeMixamoClip(clip, "mixamorig2", "standToSit");

    expect(clip.tracks.map((track) => track.name)).toEqual([
      "mixamorig2Hips.position",
      "mixamorig2Spine.quaternion",
    ]);
  });

  it("normalizes colon and numbered namespace variants", () => {
    const clip = clipWithTracks([
      "mixamorig:Spine.position",
      "mixamorig12HeadTop_End.scale",
    ]);

    normalizeMixamoClip(clip, "mixamorig2", "typing");

    expect(clip.tracks.map((track) => track.name)).toEqual([
      "mixamorig2Spine.position",
      "mixamorig2HeadTop_End.scale",
    ]);
  });

  it("leaves non-Mixamo nodes untouched", () => {
    const clip = clipWithTracks(["Armature.position", "mixamorigHips.position"]);

    normalizeMixamoClip(clip, "mixamorig2", "seatedIdle");

    expect(clip.tracks.map((track) => track.name)).toEqual([
      "Armature.position",
      "mixamorig2Hips.position",
    ]);
  });

  it("renames the clip away from the colliding mixamo.com name", () => {
    const clip = clipWithTracks(["mixamorigHips.position"]);

    normalizeMixamoClip(clip, "mixamorig2", "sitToType");

    expect(clip.name).toBe("sitToType");
  });

  it("scales only the Hips position track by hipsScale", () => {
    const hips = new THREE.VectorKeyframeTrack(
      "mixamorigHips.position",
      [0, 1],
      [10, 20, 30, 1, 2, 3],
    );
    const spine = new THREE.VectorKeyframeTrack(
      "mixamorigSpine.position",
      [0, 1],
      [10, 20, 30, 1, 2, 3],
    );
    const clip = new THREE.AnimationClip("mixamo.com", 1, [hips, spine]);

    normalizeMixamoClip(clip, "mixamorig7", "typing", 2);

    const [hipsTrack, spineTrack] = clip.tracks;
    expect(hipsTrack.name).toBe("mixamorig7Hips.position");
    expect([...hipsTrack.values]).toEqual([20, 40, 60, 2, 4, 6]);
    expect(spineTrack.name).toBe("mixamorig7Spine.position");
    expect([...spineTrack.values]).toEqual([10, 20, 30, 1, 2, 3]);
  });

  it("copies hips values before scaling so cached source tracks stay intact", () => {
    const shared = new Float32Array([10, 20, 30, 1, 2, 3]);
    const hips = new THREE.VectorKeyframeTrack(
      "mixamorigHips.position",
      [0, 1],
      shared,
    );
    const clip = new THREE.AnimationClip("mixamo.com", 1, [hips]);

    normalizeMixamoClip(clip, "mixamorig2", "typing", 2);

    expect(clip.tracks[0].values).not.toBe(shared);
    expect([...shared]).toEqual([10, 20, 30, 1, 2, 3]);
  });
});

describe("MIXAMO_AGENTS", () => {
  it("assigns a distinct Mixamo character to every agent", () => {
    expect(Object.keys(MIXAMO_AGENTS).sort()).toEqual([...AGENT_ORDER].sort());

    const urls = Object.values(MIXAMO_AGENTS).map((a) => a.modelUrl);
    expect(new Set(urls).size).toBe(urls.length);

    for (const agent of Object.values(MIXAMO_AGENTS)) {
      expect(agent.modelUrl).toMatch(/^\/models\/agents\/mixamo\/.+\.glb$/);
      expect(agent.scale).toBeGreaterThan(0.1);
      expect(agent.scale).toBeLessThan(2); // GLB meters → accepted ~1.67 u
    }
  });

  it("maps the accepted characters", () => {
    expect(MIXAMO_AGENTS.atlas.modelUrl).toContain("ch33");
    expect(MIXAMO_AGENTS.scout.modelUrl).toContain("ch22");
    expect(MIXAMO_AGENTS.forge.modelUrl).toContain("ch06");
    expect(MIXAMO_AGENTS.qa.modelUrl).toContain("ch02");
    expect(MIXAMO_AGENTS.pulse.modelUrl).toContain("remy");
  });
});

describe("layout agent anchors", () => {
  function expectAnchor(actual: readonly number[], expected: readonly number[]) {
    actual.forEach((value, i) => expect(value).toBeCloseTo(expected[i], 9));
  }

  it("pulls the rest anchor 0.15 u away from the desk along the seat facing", () => {
    // scout seat: chair (-1.9, -1.4), rotation -π/2 → faces +X
    expectAnchor(agentRestAnchor("scout"), [-2.05, 0, -1.4]);

    // atlas seat: chair (0, -4.0), rotation π → faces +Z
    expectAnchor(agentRestAnchor("atlas"), [0, 0, -4.15]);

    // forge seat: chair (1.9, -1.4), rotation π/2 → faces -X
    expectAnchor(agentRestAnchor("forge"), [2.05, 0, -1.4]);
  });

  it("places the nav home exactly at the rendered anchor (world frame)", () => {
    // The demo must start/end exactly where the character renders: the world
    // home is the desk-local anchor shifted by the shared-desk frame offset,
    // and the resolved home equals it in the desk frame (zero drift).
    for (const agentId of Object.keys(AGENT_HOME) as AgentId[]) {
      const local = agentRestAnchor(agentId);
      const world = agentHomeWorld(agentId);
      const home = AGENT_HOME[agentId];
      // world home == AGENT_HOME
      expectAnchor(world, home);

      const offset = SHARED_DESK_WORLD_OFFSET;
      // world home - offset == local anchor  →  nav arrives at the visual anchor
      expectAnchor(
        [world[0] - offset[0], world[1] - offset[1], world[2] - offset[2]],
        local,
      );
    }
  });
});

describe("makeClipInPlace", () => {
  function hipsClip(values: number[]): THREE.AnimationClip {
    const hips = new THREE.VectorKeyframeTrack(
      "mixamorigHips.position",
      [0, 1, 2],
      values,
    );
    return new THREE.AnimationClip("walking", 2, [hips]);
  }

  it("freezes the Hips X/Z root motion at their first-frame values", () => {
    const clip = hipsClip([0, 100, 10, 10, 101, 12, 90, 102, 15]);
    makeClipInPlace(clip);
    expect([...clip.tracks[0].values]).toEqual([0, 100, 10, 0, 101, 10, 0, 102, 10]);
  });

  it("leaves the Hips Y (vertical bob) fully animated", () => {
    const clip = hipsClip([0, 100, 10, 10, 101, 12]);
    makeClipInPlace(clip);
    expect(clip.tracks[0].values[1]).toBe(100);
    expect(clip.tracks[0].values[4]).toBe(101);
  });

  it("returns the clip untouched when no Hips position track exists", () => {
    const clip = new THREE.AnimationClip("walking", 1, [
      new THREE.VectorKeyframeTrack(
        "mixamorigSpine.position",
        [0],
        [0, 0, 0],
      ),
    ]);
    expect(makeClipInPlace(clip)).toBe(clip);
  });
});

describe("MIXAMO_SEQUENCE", () => {
  it("covers every standing entry/exit clip with a URL (except the non-cycle clips)", () => {
    // Walking is demo-driven; Sitting Talking is the seated-talk clip, played
    // by the seated micro-machine — neither is part of the standing cycle.
    const clipsInSequence = new Set(MIXAMO_SEQUENCE.map((p) => p.clip));
    expect([...clipsInSequence].sort()).toEqual(
      Object.keys(MIXAMO_CLIP_URLS)
        .filter((key) => key !== "walking" && key !== "sittingTalking")
        .sort(),
    );
  });

  it("holds a standing Idle baseline, then sits, types and stands back up", () => {
    expect(MIXAMO_SEQUENCE[0]).toMatchObject({
      clip: "idle",
      mode: "loop",
      seconds: 2.5,
    });
    expect(MIXAMO_SEQUENCE.at(-1)).toMatchObject({
      clip: "sitToStand",
      mode: "once",
    });

    const modes = MIXAMO_SEQUENCE.map((p) => p.mode);
    expect(modes).toContain("once");
    expect(modes).toContain("loop");
  });

  it("gives every loop phase a hold duration", () => {
    for (const phase of MIXAMO_SEQUENCE) {
      if (phase.mode === "loop") {
        expect(phase.seconds).toBeGreaterThan(0);
      }
    }
  });
});

describe("MIXAMO_SEATED_SEQUENCE", () => {
  it("keeps an active agent seated — no stand-to-sit/sit-to-stand/walking", () => {
    for (const phase of MIXAMO_SEATED_SEQUENCE) {
      expect(phase.clip).not.toBe("standToSit");
      expect(phase.clip).not.toBe("sitToStand");
      expect(phase.clip).not.toBe("walking");
    }
  });

  it("works the keyboard and rests seated, without ever leaving the chair", () => {
    expect(MIXAMO_SEATED_SEQUENCE[0].clip).toBe("sitToType");
    expect(MIXAMO_SEATED_SEQUENCE.at(-1)?.clip).toBe("seatedIdle");
  });

  it("loads the SeatedTalking clip into the clip registry", () => {
    expect(MIXAMO_CLIP_URLS.sittingTalking).toContain("sitting-talking.fbx");
  });
});
