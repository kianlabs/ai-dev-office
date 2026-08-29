"use client";

/**
 * Seated delegation controller driving a SHORT alternating dialogue.
 *
 * Reads EXISTING semantic state (ATLAS activity) as the source of truth and
 * turns delegation into per-agent seated behavior INPUTS:
 *   - a per-agent `speech` bubble for the CURRENT dialogue line (one speaker
 *     visible at a time, alternating ATLAS ↔ target),
 *   - a `talkKey` trigger (seated talking clip, once per new delegation), and
 *   - a `conversing` flag so the persistent work status is masked while the
 *     conversation plays, then revealed when it resolves.
 *
 * Dialogue only starts on a NEW delegation (target change); repeated semantic
 * updates for the same delegation NEVER replay the conversation. After the
 * last line the speech bubbles clear and the compact persistent work status
 * takes over (● Researching... / ● Coding... / etc.).
 *
 * This hook never emits movement — no stand point, no walking. The navigation
 * engine and seated behavior are untouched; only bubble/timing is new.
 */
import { useEffect, useRef, useState } from "react";

import type { AgentId } from "../navigation/waypoints";
import { detectHandoffTarget, type HandoffRole } from "../navigation/handoff";
import type { HandoffBubble } from "../navigation/handoff";
import {
  cumulativeDialogueSeconds,
  roleDialogue,
  shouldStartConversation,
  type DialogueLine,
} from "./dialogue";

interface DialogueState {
  lines: DialogueLine[];
  index: number;
}

export interface AgentDelegation {
  /** Current dialogue line bubble for this agent (null = not speaking). */
  speech: HandoffBubble | null;
  /** Opaque key bumped on every NEW delegation announcement (seated talk). */
  talkKey: string | null;
  /** Whether this agent is the delegated target this round. */
  isTarget: boolean;
  /** True while this agent is inside an active conversation (masks status). */
  conversing: boolean;
}

export type DelegationMap = Partial<Record<AgentId, AgentDelegation>>;

function scheduleTimers(
  lines: DialogueLine[],
  advance: (index: number) => void,
  finish: () => void,
) {
  const timers: ReturnType<typeof setTimeout>[] = [];
  for (let i = 1; i < lines.length; i++) {
    timers.push(
      setTimeout(
        () => advance(i),
        cumulativeDialogueSeconds(lines, i) * 1000,
      ),
    );
  }
  timers.push(
    setTimeout(
      () => finish(),
      cumulativeDialogueSeconds(lines, lines.length) * 1000,
    ),
  );
  return timers;
}

export function useAgentDelegation({
  atlasActivity,
  demoActive,
}: {
  atlasActivity: string;
  demoActive: boolean;
}): {
  active: HandoffRole | null;
  delegations: DelegationMap;
} {
  const [active, setActive] = useState<HandoffRole | null>(null);
  const [talkNonce, setTalkNonce] = useState(0);
  const [dialogue, setDialogue] = useState<DialogueState | null>(null);

  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const targetRef = useRef<HandoffRole | null>(null);

  function clearTimers() {
    for (const t of timers.current) clearTimeout(t);
    timers.current = [];
  }

  useEffect(() => {
    if (demoActive) {
      clearTimers();
      targetRef.current = null;
      setActive(null);
      setDialogue(null);
      return;
    }

    const target = detectHandoffTarget(atlasActivity);
    const previous = targetRef.current;

    if (target && shouldStartConversation(previous, target)) {
      targetRef.current = target;
      setActive(target);
      setTalkNonce((n) => n + 1);

      const lines = roleDialogue(target);
      clearTimers();
      setDialogue({ lines, index: 0 });

      timers.current = scheduleTimers(
        lines,
        (index) =>
          setDialogue((d) => (d && d.lines === lines ? { lines, index } : d)),
        () =>
          setDialogue((d) => (d && d.lines === lines ? null : d)),
      );
    } else if (target === null && previous !== null) {
      clearTimers();
      targetRef.current = null;
      setActive(null);
      setDialogue(null);
    }
  }, [atlasActivity, demoActive]);

  // Clean up timers on unmount.
  useEffect(() => {
    return () => clearTimers();
  }, []);

  const line = dialogue ? dialogue.lines[dialogue.index] : null;
  const conversationActive = active !== null && dialogue !== null;

  const delegations: DelegationMap = {};
  if (active) {
    const key = `d${talkNonce}`;
    delegations.atlas = {
      speech:
        line && line.speaker === "atlas"
          ? { text: line.text, kind: "speech" }
          : null,
      talkKey: key,
      isTarget: false,
      conversing: conversationActive,
    };
    delegations[active] = {
      speech:
        line && line.speaker === active
          ? { text: line.text, kind: "speech" }
          : null,
      talkKey: key,
      isTarget: true,
      conversing: conversationActive,
    };
  }

  return { active, delegations };
}
